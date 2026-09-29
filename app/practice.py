"""成员实践与共练：私人实践稿 + 常设共练 + 提交快照 + 回复反馈。

契约冻结（.fleet/growth-content-20260924/practice-contract.md）：
- 全部路由需成员 session：匿名被 auth 中间件 401；Agent token 403；他人私稿 404。
- 所有响应 Cache-Control: no-store；私稿创建不自动公开。
- 提交是独立快照（title/body/result_url 落库拷贝），后续私稿修改不污染已发内容。
- revision 乐观并发；join/submit/reply 幂等；分页 total 真实。
- schema 初始化幂等，迁移只加不删。
"""

import datetime
import json
import re
import secrets
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field

CST = datetime.timezone(datetime.timedelta(hours=8))
SEEDS = Path(__file__).with_name("practice_seeds.json")

_db: Callable[[], Any] | None = None


def configure(*, db: Callable[[], Any]) -> None:
    """由 main 注入现有 db()，避免环状 import。"""
    global _db
    _db = db


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["practice"], dependencies=[Depends(_no_store)])


def _member(request: Request) -> dict:
    """成员实践区：Agent 403，匿名 401（通常已被中间件拦），成员 session 通过。"""
    kind = getattr(request.state, "auth_kind", None)
    if kind == "agent":
        raise HTTPException(403, "成员实践区暂不开放 Agent")
    if kind != "session" or not getattr(request.state, "user", None):
        raise HTTPException(401, "请先登录")
    return request.state.user


# ── schema（幂等）──

def ensure_schema(connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS practice_items(
          id TEXT PRIMARY KEY,
          owner_id INTEGER NOT NULL,
          title TEXT NOT NULL,
          outcome TEXT NOT NULL DEFAULT '',
          next_step TEXT NOT NULL DEFAULT '',
          notes TEXT NOT NULL DEFAULT '',
          result_url TEXT NOT NULL DEFAULT '',
          source_url TEXT NOT NULL DEFAULT '',
          source_title TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'active',
          revision INTEGER NOT NULL DEFAULT 1,
          challenge_id TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS practice_items_owner ON practice_items(owner_id);
        -- 同一用户同一共练只建一份实践（join 幂等的 DB 兜底）
        CREATE UNIQUE INDEX IF NOT EXISTS practice_items_join
          ON practice_items(owner_id, challenge_id) WHERE challenge_id IS NOT NULL;

        -- 创建幂等回执：owner+client_id 唯一；同 id 换负载判 409
        CREATE TABLE IF NOT EXISTS practice_create_actions(
          owner_id INTEGER NOT NULL,
          client_id TEXT NOT NULL,
          payload TEXT NOT NULL,
          practice_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(owner_id, client_id)
        );

        CREATE TABLE IF NOT EXISTS practice_challenges(
          id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          summary TEXT NOT NULL DEFAULT '',
          instructions_json TEXT NOT NULL DEFAULT '[]',
          outcome TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'open',
          created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS practice_submissions(
          id TEXT PRIMARY KEY,
          practice_id TEXT NOT NULL,
          challenge_id TEXT NOT NULL,
          owner_id INTEGER NOT NULL,
          title TEXT NOT NULL,
          body TEXT NOT NULL,
          result_url TEXT NOT NULL DEFAULT '',
          practice_revision INTEGER NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS practice_submissions_ch ON practice_submissions(challenge_id);
        -- 同实践同 revision 重复提交返回同一快照
        CREATE UNIQUE INDEX IF NOT EXISTS practice_submissions_rev
          ON practice_submissions(practice_id, practice_revision);

        CREATE TABLE IF NOT EXISTS practice_replies(
          id TEXT PRIMARY KEY,
          submission_id TEXT NOT NULL,
          owner_id INTEGER NOT NULL,
          text TEXT NOT NULL,
          client_id TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS practice_replies_sub ON practice_replies(submission_id);
        -- 同一作者/提交/client_id 重试幂等
        CREATE UNIQUE INDEX IF NOT EXISTS practice_replies_idem
          ON practice_replies(submission_id, owner_id, client_id);
        """
    )
    _seed_challenges(connection)


def _seed_challenges(connection) -> None:
    """常设共练来自 practice_seeds.json 真实配置；INSERT OR IGNORE 幂等。"""
    if not SEEDS.exists():
        return
    for ch in json.loads(SEEDS.read_text("utf-8")):
        connection.execute(
            """INSERT OR IGNORE INTO practice_challenges
               (id,title,summary,instructions_json,outcome,status,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (ch["id"], ch["title"], ch["summary"],
             json.dumps(ch["instructions"], ensure_ascii=False),
             ch["outcome"], ch.get("status", "open"), _now()),
        )


# ── 输入校验 ──

_CONTROL = re.compile(r"[\x00-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
_LINE_CONTROL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060\ufeff]")


def _text(value, limit, *, required=False, multiline=False, label="字段") -> str:
    value = str(value or "")
    if multiline:
        value = _LINE_CONTROL.sub("", value.replace("\r\n", "\n").replace("\r", "\n"))
    else:
        value = _CONTROL.sub("", value)
    value = value.strip()
    if len(value) > limit:
        raise HTTPException(422, f"{label}不能超过 {limit} 字")
    if required and not value:
        raise HTTPException(422, f"{label}不能为空")
    return value


def _url(value, label="链接") -> str:
    """只允许 http(s) 真主机 或 站内单斜线路径；禁控制字节/反斜杠/协议相对/空主机。"""
    value = str(value or "").strip()
    if not value:
        return ""
    if len(value) > 2000 or "\\" in value or any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in value):
        raise HTTPException(422, f"{label}格式不对")
    if value.startswith("/"):
        if value.startswith("//"):
            raise HTTPException(422, f"{label}格式不对")
        return value
    if re.match(r"^https?://", value.lower()):
        try:
            host = urlsplit(value).hostname
        except ValueError:
            host = None
        if not host:
            raise HTTPException(422, f"{label}格式不对")
        return value
    raise HTTPException(422, f"{label}格式不对")


def _page(limit: int, offset: int) -> tuple[int, int]:
    return min(max(1, int(limit)), 50), max(0, int(offset))


def _now() -> str:
    return datetime.datetime.now(CST).isoformat()


class PracticeCreateReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    outcome: str
    next_step: str | None = None
    source_url: str | None = None
    source_title: str | None = None
    client_id: str | None = Field(default=None, min_length=1, max_length=80)


class PracticePatchReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    title: str | None = None
    outcome: str | None = None
    next_step: str | None = None
    notes: str | None = None
    result_url: str | None = None
    status: Literal["active", "completed", "archived"] | None = None


class SubmitReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0)
    body: str
    result_url: str | None = None


class ReplyCreateReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    client_id: str = Field(min_length=1, max_length=80)


class JoinReq(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ── 序列化 ──

def _practice(r) -> dict:
    """Practice 输出；owner_id 不暴露。"""
    return {
        "id": r["id"], "title": r["title"], "outcome": r["outcome"],
        "next_step": r["next_step"], "notes": r["notes"],
        "result_url": r["result_url"], "source_url": r["source_url"],
        "source_title": r["source_title"], "status": r["status"],
        "revision": r["revision"], "challenge_id": r["challenge_id"],
        "created_at": r["created_at"], "updated_at": r["updated_at"],
    }


def _author_from_row(u) -> dict:
    if not u:
        return {"name": "成员", "kind": "human"}
    a = {"name": u["display_name"] or u["username"], "kind": "human"}
    if u["member_key"]:
        a["member_key"] = u["member_key"]
    return a


def _authors(c, owner_ids) -> dict:
    ids = sorted(set(owner_ids))
    if not ids:
        return {}
    rows = c.execute(
        f"SELECT id,username,display_name,member_key FROM users WHERE id IN ({','.join('?' * len(ids))})",
        ids,
    ).fetchall()
    return {u["id"]: _author_from_row(u) for u in rows}


def _submission(r, me_id, author, reply_count) -> dict:
    return {
        "id": r["id"],
        "practice_id": r["practice_id"] if r["owner_id"] == me_id else None,
        "challenge_id": r["challenge_id"],
        "title": r["title"], "body": r["body"], "result_url": r["result_url"],
        "author": author,
        "created_at": r["created_at"],
        "revision": r["practice_revision"],
        "reply_count": reply_count,
        "is_mine": r["owner_id"] == me_id,
    }


def _submission_map(c, rows, me_id) -> list[dict]:
    authors = _authors(c, [r["owner_id"] for r in rows])
    counts: dict[str, int] = {}
    if rows:
        ph = ",".join("?" * len(rows))
        for r in c.execute(
            f"SELECT submission_id,COUNT(*) n FROM practice_replies WHERE submission_id IN ({ph}) GROUP BY submission_id",
            [r["id"] for r in rows],
        ):
            counts[r["submission_id"]] = r["n"]
    return [
        _submission(r, me_id, authors.get(r["owner_id"], {"name": "成员", "kind": "human"}), counts.get(r["id"], 0))
        for r in rows
    ]


def _reply(r, author) -> dict:
    return {"id": r["id"], "text": r["text"], "author": author, "created_at": r["created_at"]}


def _own_practice(c, pid: str, user_id: int):
    r = c.execute("SELECT * FROM practice_items WHERE id=?", (pid,)).fetchone()
    if not r or r["owner_id"] != user_id:
        raise HTTPException(404, "这条实践不存在")
    return r


# ── 我的实践 ──

@router.get("/api/practice/mine")
def list_mine(request: Request, status: str = "all", limit: int = 20, offset: int = 0):
    user = _member(request)
    if status not in ("all", "active", "completed", "archived"):
        raise HTTPException(422, "status 只接受 all/active/completed/archived")
    limit, offset = _page(limit, offset)
    c = _db()
    try:
        where = "owner_id=?" if status == "all" else "owner_id=? AND status=?"
        args = (user["id"],) if status == "all" else (user["id"], status)
        total = c.execute(f"SELECT COUNT(*) FROM practice_items WHERE {where}", args).fetchone()[0]
        rows = c.execute(
            f"SELECT * FROM practice_items WHERE {where} ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?",
            args + (limit, offset),
        ).fetchall()
        return {"items": [_practice(r) for r in rows], "total": total, "limit": limit, "offset": offset}
    finally:
        c.close()


@router.post("/api/practice/mine")
def create_mine(req: PracticeCreateReq, request: Request):
    user = _member(request)
    title = _text(req.title, 120, required=True, label="标题")
    outcome = _text(req.outcome, 1000, required=True, multiline=True, label="目标")
    next_step = _text(req.next_step, 1000, multiline=True, label="下一步")
    source_url = _url(req.source_url, "来源链接")
    source_title = _text(req.source_title, 240, label="来源标题")
    client_id = (req.client_id or "").strip() or None
    now = _now()
    c = _db()
    try:
        c.execute("BEGIN IMMEDIATE")
        try:
            if client_id:
                # 先鉴权再查幂等：同 client_id 换规范化负载 → 409；重放返当前真值
                payload = json.dumps(
                    {"title": title, "outcome": outcome, "next_step": next_step,
                     "source_url": source_url, "source_title": source_title},
                    sort_keys=True, ensure_ascii=False)
                r = c.execute(
                    "SELECT payload,practice_id FROM practice_create_actions "
                    "WHERE owner_id=? AND client_id=?",
                    (user["id"], client_id),
                ).fetchone()
                if r and r["payload"] != payload:
                    raise HTTPException(409, "client_id 已被其它请求占用，请换新")
                if r:
                    pr = c.execute(
                        "SELECT * FROM practice_items WHERE id=?", (r["practice_id"],)
                    ).fetchone()
                    if pr:
                        c.commit()
                        return _practice(pr)
            # 同 owner 同站内来源的 active 练习 → 返回既存（不加唯一索引：
            # 历史重复记录不许被迁移删并，事务内取最新一份即可）
            if source_url.startswith("/"):
                ex = c.execute(
                    """SELECT * FROM practice_items
                       WHERE owner_id=? AND source_url=? AND status='active'
                       ORDER BY created_at DESC, id DESC LIMIT 1""",
                    (user["id"], source_url),
                ).fetchone()
                if ex:
                    # 每个成功分支都要登记幂等回执：dedupe 命中也存 client_id，
                    # 否则既存被归档后同 key 重试会绕过幂等新建
                    if client_id:
                        c.execute(
                            "INSERT INTO practice_create_actions(owner_id,client_id,payload,practice_id,created_at) "
                            "VALUES(?,?,?,?,?)",
                            (user["id"], client_id, payload, ex["id"], now),
                        )
                    c.commit()
                    return _practice(ex)
            pid = "pr_" + secrets.token_urlsafe(9)
            c.execute(
                """INSERT INTO practice_items
                   (id,owner_id,title,outcome,next_step,notes,result_url,source_url,source_title,
                    status,revision,challenge_id,created_at,updated_at)
                   VALUES(?,?,?,?,?,'','',?,?,'active',1,NULL,?,?)""",
                (pid, user["id"], title, outcome, next_step, source_url, source_title, now, now),
            )
            if client_id:
                c.execute(
                    "INSERT INTO practice_create_actions(owner_id,client_id,payload,practice_id,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (user["id"], client_id, payload, pid, now),
                )
            c.commit()
            return _practice(c.execute("SELECT * FROM practice_items WHERE id=?", (pid,)).fetchone())
        except sqlite3.IntegrityError:
            c.rollback()
            # 并发创建撞单：赢家的幂等行已落库 → 读现状返回（响应形态不变）
            if client_id:
                r = c.execute(
                    "SELECT practice_id FROM practice_create_actions "
                    "WHERE owner_id=? AND client_id=?",
                    (user["id"], client_id),
                ).fetchone()
                if r:
                    pr = c.execute(
                        "SELECT * FROM practice_items WHERE id=?", (r["practice_id"],)
                    ).fetchone()
                    if pr:
                        return _practice(pr)
            raise HTTPException(409, "创建冲突，请重试")
        except Exception:
            c.rollback()
            raise
    finally:
        c.close()


@router.get("/api/practice/mine/{pid}")
def get_mine(pid: str, request: Request):
    user = _member(request)
    c = _db()
    try:
        return _practice(_own_practice(c, pid, user["id"]))
    finally:
        c.close()


@router.patch("/api/practice/mine/{pid}")
def patch_mine(pid: str, req: PracticePatchReq, request: Request):
    user = _member(request)
    c = _db()
    try:
        _own_practice(c, pid, user["id"])
        fields = req.model_dump(exclude_unset=True)
        fields.pop("revision", None)
        # 显式 null 非法：字段列均 NOT NULL，null 落库会 500——先挡在 422
        for k, v in fields.items():
            if v is None:
                raise HTTPException(422, f"{k} 不能为 null")
        sets: list[str] = []
        args: list[Any] = []
        if "title" in fields:
            sets.append("title=?"); args.append(_text(fields["title"], 120, required=True, label="标题"))
        if "outcome" in fields:
            sets.append("outcome=?"); args.append(_text(fields["outcome"], 1000, required=True, multiline=True, label="目标"))
        if "next_step" in fields:
            sets.append("next_step=?"); args.append(_text(fields["next_step"], 1000, multiline=True, label="下一步"))
        if "notes" in fields:
            sets.append("notes=?"); args.append(_text(fields["notes"], 20000, multiline=True, label="笔记"))
        if "result_url" in fields:
            sets.append("result_url=?"); args.append(_url(fields["result_url"], "结果链接"))
        if "status" in fields:
            sets.append("status=?"); args.append(fields["status"])  # Literal 已校验枚举
        if not sets:
            # 仅带 revision 的空 PATCH：版本对得上返回现状，对不上 409
            cur = c.execute("SELECT revision FROM practice_items WHERE id=?", (pid,)).fetchone()
            if cur["revision"] != req.revision:
                raise HTTPException(409, "版本不对，请刷新后再改")
            return _practice(c.execute("SELECT * FROM practice_items WHERE id=?", (pid,)).fetchone())
        sets.append("revision=revision+1")
        sets.append("updated_at=?"); args.append(_now())
        cur = c.execute(
            f"UPDATE practice_items SET {', '.join(sets)} WHERE id=? AND owner_id=? AND revision=?",
            args + [pid, user["id"], req.revision],
        )
        if cur.rowcount == 0:
            raise HTTPException(409, "这条实践已被改过，请刷新后再改")
        # 状态离开 completed → 同事务藏起已公开木牌（重新完成也不自动复开）
        if fields.get("status") and fields["status"] != "completed":
            has_marks = c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='garden_marks'"
            ).fetchone()
            if has_marks:
                c.execute(
                    "UPDATE garden_marks SET shown=0, revision=revision+1, updated_at=? "
                    "WHERE practice_id=? AND shown=1",
                    (_now(), pid),
                )
        c.commit()
        return _practice(c.execute("SELECT * FROM practice_items WHERE id=?", (pid,)).fetchone())
    finally:
        c.close()


# ── 共练 ──

@router.get("/api/practice/challenges")
def list_challenges(request: Request):
    user = _member(request)
    c = _db()
    try:
        rows = c.execute("SELECT * FROM practice_challenges ORDER BY created_at ASC, id ASC").fetchall()
        mine = {r["challenge_id"]: r["id"] for r in c.execute(
            "SELECT id,challenge_id FROM practice_items WHERE owner_id=? AND challenge_id IS NOT NULL",
            (user["id"],),
        )}
        counts = {r["challenge_id"]: r["n"] for r in c.execute(
            "SELECT challenge_id,COUNT(*) n FROM practice_submissions GROUP BY challenge_id"
        )}
        items = [{
            "id": r["id"], "title": r["title"], "summary": r["summary"],
            "instructions": json.loads(r["instructions_json"]), "outcome": r["outcome"],
            "status": r["status"], "my_practice_id": mine.get(r["id"]),
            "submission_count": counts.get(r["id"], 0),
        } for r in rows]
        return {"items": items, "total": len(items)}
    finally:
        c.close()


@router.post("/api/practice/challenges/{cid}/join")
def join_challenge(cid: str, request: Request, req: JoinReq | None = None):
    user = _member(request)
    c = _db()
    try:
        ch = c.execute("SELECT * FROM practice_challenges WHERE id=?", (cid,)).fetchone()
        if not ch:
            raise HTTPException(404, "共练不存在")
        if ch["status"] != "open":
            raise HTTPException(409, "这个共练已关闭")
        existing = c.execute(
            "SELECT * FROM practice_items WHERE owner_id=? AND challenge_id=?", (user["id"], cid)
        ).fetchone()
        if existing:
            return _practice(existing)  # 幂等：同一用户同一共练返回自己那份
        now = _now()
        pid = "pr_" + secrets.token_urlsafe(9)
        try:
            c.execute(
                """INSERT INTO practice_items
                   (id,owner_id,title,outcome,next_step,notes,result_url,source_url,source_title,
                    status,revision,challenge_id,created_at,updated_at)
                   VALUES(?,?,?,?,'','','','','', 'active',1,?,?,?)""",
                (pid, user["id"], ch["title"], ch["outcome"], cid, now, now),
            )
            c.commit()
        except sqlite3.IntegrityError:
            c.rollback()  # 并发重复参加被唯一索引拦下，回落读取已建那份
        return _practice(c.execute(
            "SELECT * FROM practice_items WHERE owner_id=? AND challenge_id=?", (user["id"], cid)
        ).fetchone())
    finally:
        c.close()


# ── 提交快照 ──

@router.get("/api/practice/submissions")
def list_submissions(request: Request, challenge_id: str = Query(min_length=1), limit: int = 20, offset: int = 0):
    user = _member(request)
    limit, offset = _page(limit, offset)
    c = _db()
    try:
        if not c.execute("SELECT 1 FROM practice_challenges WHERE id=?", (challenge_id,)).fetchone():
            raise HTTPException(404, "共练不存在")
        total = c.execute(
            "SELECT COUNT(*) FROM practice_submissions WHERE challenge_id=?", (challenge_id,)
        ).fetchone()[0]
        rows = c.execute(
            """SELECT * FROM practice_submissions WHERE challenge_id=?
               ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?""",
            (challenge_id, limit, offset),
        ).fetchall()
        return {"items": _submission_map(c, rows, user["id"]), "total": total, "limit": limit, "offset": offset}
    finally:
        c.close()


@router.post("/api/practice/mine/{pid}/submit")
def submit_mine(pid: str, req: SubmitReq, request: Request):
    user = _member(request)
    body = _text(req.body, 20000, required=True, multiline=True, label="提交正文")
    result_url = _url(req.result_url, "结果链接")
    c = _db()
    try:
        # BEGIN IMMEDIATE：revision 校验与快照插入在同一写锁内，
        # 校验通过后并发 PATCH 只能排队到本事务提交后，不会再放行旧版本提交。
        c.execute("BEGIN IMMEDIATE")
        try:
            p = _own_practice(c, pid, user["id"])
            if p["revision"] != req.revision:
                raise HTTPException(409, "实践已改过，请刷新后再提交")
            if not p["challenge_id"]:
                raise HTTPException(422, "这条实践没有关联共练，不能提交")
            ch = c.execute("SELECT * FROM practice_challenges WHERE id=?", (p["challenge_id"],)).fetchone()
            if not ch or ch["status"] != "open":
                raise HTTPException(409, "这个共练已关闭")
            sid = "sub_" + secrets.token_urlsafe(9)
            try:
                c.execute(
                    """INSERT INTO practice_submissions
                       (id,practice_id,challenge_id,owner_id,title,body,result_url,practice_revision,created_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (sid, pid, p["challenge_id"], user["id"], p["title"], body,
                     result_url, p["revision"], _now()),  # 只存显式提交的链接：留空即空，不回退私人实践 URL
                )
            except sqlite3.IntegrityError:
                pass  # 同 practice 同 revision 重复提交：返回既有快照，不加倍
            c.commit()
        except Exception:
            if c.in_transaction:
                c.rollback()
            raise
        snap = c.execute(
            "SELECT * FROM practice_submissions WHERE practice_id=? AND practice_revision=?",
            (pid, p["revision"]),
        ).fetchone()
        authors = _authors(c, [snap["owner_id"]])
        count = c.execute(
            "SELECT COUNT(*) FROM practice_replies WHERE submission_id=?", (snap["id"],)
        ).fetchone()[0]
        return _submission(snap, user["id"], authors.get(snap["owner_id"], {"name": "成员", "kind": "human"}), count)
    finally:
        c.close()


@router.get("/api/practice/submissions/{sid}")
def get_submission(sid: str, request: Request):
    user = _member(request)
    c = _db()
    try:
        r = c.execute("SELECT * FROM practice_submissions WHERE id=?", (sid,)).fetchone()
        if not r:
            raise HTTPException(404, "提交不存在")
        authors = _authors(c, [r["owner_id"]])
        count = c.execute(
            "SELECT COUNT(*) FROM practice_replies WHERE submission_id=?", (sid,)
        ).fetchone()[0]
        return _submission(r, user["id"], authors.get(r["owner_id"], {"name": "成员", "kind": "human"}), count)
    finally:
        c.close()


# ── 提交回复 ──

@router.get("/api/practice/submissions/{sid}/replies")
def list_replies(sid: str, request: Request, limit: int = 20, offset: int = 0):
    user = _member(request)
    limit, offset = _page(limit, offset)
    c = _db()
    try:
        if not c.execute("SELECT 1 FROM practice_submissions WHERE id=?", (sid,)).fetchone():
            raise HTTPException(404, "提交不存在")
        total = c.execute(
            "SELECT COUNT(*) FROM practice_replies WHERE submission_id=?", (sid,)
        ).fetchone()[0]
        rows = c.execute(
            """SELECT * FROM practice_replies WHERE submission_id=?
               ORDER BY created_at ASC, id ASC LIMIT ? OFFSET ?""",
            (sid, limit, offset),
        ).fetchall()
        authors = _authors(c, [r["owner_id"] for r in rows])
        return {
            "items": [_reply(r, authors.get(r["owner_id"], {"name": "成员", "kind": "human"})) for r in rows],
            "total": total, "limit": limit, "offset": offset,
        }
    finally:
        c.close()


@router.post("/api/practice/submissions/{sid}/replies")
def create_reply(sid: str, req: ReplyCreateReq, request: Request):
    user = _member(request)
    text = _text(req.text, 4000, required=True, multiline=True, label="回复")
    client_id = _text(req.client_id, 80, required=True, label="client_id")
    c = _db()
    try:
        if not c.execute("SELECT 1 FROM practice_submissions WHERE id=?", (sid,)).fetchone():
            raise HTTPException(404, "提交不存在")
        rid = "rp_" + secrets.token_urlsafe(9)
        try:
            c.execute(
                """INSERT INTO practice_replies(id,submission_id,owner_id,text,client_id,created_at)
                   VALUES(?,?,?,?,?,?)""",
                (rid, sid, user["id"], text, client_id, _now()),
            )
            c.commit()
        except sqlite3.IntegrityError:
            c.rollback()  # 同作者/提交/client_id 重试：返回已有回复
        r = c.execute(
            "SELECT * FROM practice_replies WHERE submission_id=? AND owner_id=? AND client_id=?",
            (sid, user["id"], client_id),
        ).fetchone()
        authors = _authors(c, [r["owner_id"]])
        return _reply(r, authors.get(r["owner_id"], {"name": "成员", "kind": "human"}))
    finally:
        c.close()
