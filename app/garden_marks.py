"""GARDEN-MARKS R1：家园木牌——完成实践后把「标题+阅读来源」挂到家园。

契约 frozen（garden-marks-contract.md）：
- 仅登录真人（Agent403/匿名401），全部响应 no-store；私园/不存在统一 404。
- 挂牌默认仅本人（shown=false），显式 PATCH shown 才公开；访客只见 shown 且实践仍 completed。
- 同 owner/practice 只一块；上限由 garden_marks_rules.json max_marks 决定。
- 标题/来源是挂牌时快照；实践离开 completed → shown=false 且 revision+1，重新完成不自动公开。
- mutation 一律 BEGIN IMMEDIATE：先鉴权→client_id 幂等（换负载409/重放返现状）→业务校验→落库。
- 无积分/奖励逻辑。
"""

from __future__ import annotations

import datetime
import json
import re
import secrets
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

try:
    from . import garden as _g  # 复用鉴权/私园404语义，避免双份实现漂移
except ImportError:
    import garden as _g

CST = datetime.timezone(datetime.timedelta(hours=8))
RULES_PATH = Path(__file__).with_name("garden_marks_rules.json")

_db: Callable[[], Any] | None = None
_static_dir: Path | None = None


def configure(*, db: Callable[[], Any], static_dir: Any = None) -> None:
    """由 main 注入 db() 与静态根（source_url 存在性检查用）。"""
    global _db, _static_dir
    _db = db
    _static_dir = Path(static_dir) if static_dir else None


def _load_rules() -> dict:
    data = json.loads(RULES_PATH.read_text("utf-8"))
    if not isinstance(data.get("max_marks"), int) or data["max_marks"] < 1:
        raise ValueError("garden_marks_rules.json: max_marks 必须是 >=1 的整数")
    return data


RULES = _load_rules()


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["garden-marks"], dependencies=[Depends(_no_store)])

_member = _g._member
_now_dt = _g._now_dt


# ── schema（幂等，只加不删）──

def ensure_schema(connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS garden_marks(
          id TEXT PRIMARY KEY,
          garden_id TEXT NOT NULL,
          owner_id INTEGER NOT NULL,
          practice_id TEXT NOT NULL,
          title TEXT NOT NULL,
          source_title TEXT NOT NULL DEFAULT '',
          source_url TEXT NOT NULL DEFAULT '',
          shown INTEGER NOT NULL DEFAULT 0,
          revision INTEGER NOT NULL DEFAULT 1,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        -- 同一主人同一实践只一块木牌
        CREATE UNIQUE INDEX IF NOT EXISTS garden_marks_owner_practice
          ON garden_marks(owner_id, practice_id);
        CREATE INDEX IF NOT EXISTS garden_marks_garden
          ON garden_marks(garden_id, created_at DESC);

        -- mutation 幂等回执：actor+client_id 唯一；同 id 换负载判 409
        CREATE TABLE IF NOT EXISTS garden_mark_actions(
          actor_id INTEGER NOT NULL,
          client_id TEXT NOT NULL,
          op TEXT NOT NULL,
          payload TEXT NOT NULL,
          mark_id TEXT,
          created_at TEXT NOT NULL,
          PRIMARY KEY(actor_id, client_id)
        );
        """
    )


# ── 输入 ──

class MarkCreateReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    practice_id: str = Field(min_length=1, max_length=80)
    client_id: str = Field(min_length=1, max_length=80)


class MarkPatchReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shown: bool
    revision: int = Field(ge=0)
    client_id: str = Field(min_length=1, max_length=80)


class MarkDeleteReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: str = Field(min_length=1, max_length=80)


# ── 序列化与工具 ──

def _owner_mark(r) -> dict:
    return {
        "id": r["id"], "practice_id": r["practice_id"],
        "title": r["title"], "source_title": r["source_title"],
        "source_url": r["source_url"] or None,
        "shown": bool(r["shown"]), "revision": r["revision"],
        "created_at": r["created_at"], "updated_at": r["updated_at"],
    }


def _visitor_mark(r) -> dict:
    # 访客严格字段：无 practice_id/owner_id/notes/outcome/result_url/revision
    return {
        "id": r["id"], "title": r["title"], "source_title": r["source_title"],
        "source_url": r["source_url"] or None, "created_at": r["created_at"],
    }


def _owner_response(c, g, items, replayed: bool) -> dict:
    return {
        "garden_id": g["id"] if g else None,
        "max_marks": int(RULES["max_marks"]),
        "items": items,
        "replayed": replayed,
    }


_MARK_PATH = re.compile(r"^/readings/(?:books/)?[A-Za-z0-9_-]+/$")


def _source_url(value) -> str:
    """只允许存在的本站精读静态页（/readings/<id>/、/readings/books/<id>/）。
    ai325.com 绝对地址归一到站内相对路径；无 query/hash/用户名/转义；
    静态目录下无 index.html 或不合规 → ''（输出层转 null）。"""
    v = str(value or "").strip()
    if not v or len(v) > 2000 or "\\" in v or "%" in v or ".." in v:
        return ""
    if re.match(r"^https?://", v, re.I):
        try:
            u = urlsplit(v)
        except ValueError:
            return ""
        host = (u.hostname or "").lower()
        if host not in ("ai325.com", "www.ai325.com") or u.username or u.query or u.fragment:
            return ""
        v = u.path
    if "?" in v or "#" in v or not _MARK_PATH.match(v):
        return ""
    if _static_dir is None:
        return ""
    return v if (_static_dir / v.lstrip("/") / "index.html").is_file() else ""


def _text(value, limit, label) -> str:
    v = str(value or "").strip()
    if len(v) > limit:
        raise HTTPException(422, f"{label}不能超过 {limit} 字")
    return v


def _own_garden_row(c, user_id: int):
    return c.execute("SELECT * FROM gardens WHERE owner_id=?", (user_id,)).fetchone()


def _reconcile(c, garden_id: str, now) -> None:
    """实践离开 completed → 该木牌 shown=false 且 revision+1（重新完成不自动公开）。"""
    c.execute(
        """UPDATE garden_marks SET shown=0, revision=revision+1, updated_at=?
           WHERE garden_id=? AND shown=1 AND practice_id IN
             (SELECT id FROM practice_items WHERE status!='completed')""",
        (now.isoformat(), garden_id),
    )


def _mine_items(c, g) -> list:
    if not g:
        return []
    return [_owner_mark(r) for r in c.execute(
        "SELECT * FROM garden_marks WHERE garden_id=? ORDER BY created_at ASC", (g["id"],)
    ).fetchall()]


def _idem_lookup(c, actor_id: int, client_id: str, op: str, payload: str):
    r = c.execute(
        "SELECT op,payload FROM garden_mark_actions WHERE actor_id=? AND client_id=?",
        (actor_id, client_id),
    ).fetchone()
    if r and (r["op"] != op or r["payload"] != payload):
        raise HTTPException(409, "client_id 已被其它请求占用，请换新")
    return r


def _idem_record(c, actor_id: int, client_id: str, op: str, payload: str, mark_id, now) -> None:
    c.execute(
        "INSERT INTO garden_mark_actions(actor_id,client_id,op,payload,mark_id,created_at) "
        "VALUES(?,?,?,?,?,?)",
        (actor_id, client_id, op, payload, mark_id, now.isoformat()),
    )


def _finish(c, user: dict, replayed: bool) -> dict:
    """提交后主流程统一出口：回读当前真值，不重建任何状态。"""
    g = _own_garden_row(c, user["id"])
    return _owner_response(c, g, _mine_items(c, g), replayed)


# ── 我的木牌 ──

@router.get("/api/garden/mine/marks")
def list_mine(request: Request):
    user = _member(request)
    c = _db()
    try:
        g = _own_garden_row(c, user["id"])
        if g:
            _reconcile(c, g["id"], _now_dt())
            c.commit()
        return _owner_response(c, g, _mine_items(c, g), False)
    finally:
        c.close()


@router.post("/api/garden/mine/marks")
def create_mark(req: MarkCreateReq, request: Request):
    user = _member(request)
    c = _db()
    try:
        c.execute("BEGIN IMMEDIATE")
        try:
            now = _now_dt()
            replayed = _idem_lookup(c, user["id"], req.client_id, "create", req.practice_id) is not None
            if not replayed:
                g = _own_garden_row(c, user["id"])
                if not g:
                    raise HTTPException(409, "先开通家园再挂牌")
                p = c.execute(
                    "SELECT * FROM practice_items WHERE id=? AND owner_id=?",
                    (req.practice_id, user["id"]),
                ).fetchone()
                if not p:
                    raise HTTPException(404, "这条实践不存在")
                if p["status"] != "completed":
                    raise HTTPException(409, "只有已完成的实践才能挂牌")
                existing = c.execute(
                    "SELECT id FROM garden_marks WHERE owner_id=? AND practice_id=?",
                    (user["id"], p["id"]),
                ).fetchone()
                if existing:
                    # 同实践已有木牌：登记本次 client_id 指向既存，重放口径一致；
                    # 上限检查放其后——满 4 块的重复请求不该误 409
                    _idem_record(c, user["id"], req.client_id, "create",
                                 req.practice_id, existing["id"], now)
                    replayed = True
                else:
                    n = c.execute(
                        "SELECT COUNT(*) FROM garden_marks WHERE owner_id=?", (user["id"],)
                    ).fetchone()[0]
                    if n >= int(RULES["max_marks"]):
                        raise HTTPException(409, f"木牌最多 {RULES['max_marks']} 块，先撤下一块")
                    # 标题与阅读来源是挂牌时快照；source_url 只留存在的站内精读页
                    mid = "mk_" + secrets.token_urlsafe(9)
                    c.execute(
                        """INSERT INTO garden_marks
                           (id,garden_id,owner_id,practice_id,title,source_title,source_url,
                            shown,revision,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,0,1,?,?)""",
                        (mid, g["id"], user["id"], p["id"],
                         _text(p["title"], 120, "标题"), _text(p["source_title"], 240, "来源标题"),
                         _source_url(p["source_url"]), now.isoformat(), now.isoformat()),
                    )
                    _idem_record(c, user["id"], req.client_id, "create", req.practice_id, mid, now)
            c.commit()
        except Exception:
            c.rollback()
            raise
        return _finish(c, user, replayed=replayed)
    finally:
        c.close()


@router.patch("/api/garden/mine/marks/{mid}")
def patch_mark(mid: str, req: MarkPatchReq, request: Request):
    user = _member(request)
    payload = json.dumps({"id": mid, "shown": bool(req.shown), "revision": req.revision}, sort_keys=True)
    c = _db()
    try:
        c.execute("BEGIN IMMEDIATE")
        try:
            now = _now_dt()
            replayed = _idem_lookup(c, user["id"], req.client_id, "patch", payload) is not None
            if not replayed:
                m = c.execute(
                    "SELECT * FROM garden_marks WHERE id=? AND owner_id=?",
                    (mid, user["id"]),
                ).fetchone()
                if not m:
                    raise HTTPException(404, "这块木牌不存在")
                if req.revision != m["revision"]:
                    raise HTTPException(409, "木牌已被改过，请刷新后重试")
                p = c.execute(
                    "SELECT status FROM practice_items WHERE id=?", (m["practice_id"],)
                ).fetchone()
                if req.shown and (not p or p["status"] != "completed"):
                    # 实践已离开 completed：不能宣称已展示——诚实 409 让 UI 重取
                    raise HTTPException(409, "实践已不在完成状态，请刷新后重取")
                shown = 1 if req.shown else 0
                new_rev = m["revision"] + (1 if shown != m["shown"] else 0)
                c.execute(
                    "UPDATE garden_marks SET shown=?, revision=?, updated_at=? WHERE id=?",
                    (shown, new_rev, now.isoformat(), mid),
                )
                _idem_record(c, user["id"], req.client_id, "patch", payload, mid, now)
            # 同事务联动：本园其它木牌若对应实践已离开 completed，一并藏起
            g = _own_garden_row(c, user["id"])
            if g:
                _reconcile(c, g["id"], now)
            c.commit()
        except Exception:
            c.rollback()
            raise
        return _finish(c, user, replayed=replayed)
    finally:
        c.close()


@router.delete("/api/garden/mine/marks/{mid}")
def delete_mark(mid: str, request: Request, req: MarkDeleteReq = Body(...)):
    user = _member(request)
    c = _db()
    try:
        c.execute("BEGIN IMMEDIATE")
        try:
            now = _now_dt()
            replayed = _idem_lookup(c, user["id"], req.client_id, "delete", mid) is not None
            if not replayed:
                m = c.execute(
                    "SELECT id FROM garden_marks WHERE id=? AND owner_id=?",
                    (mid, user["id"]),
                ).fetchone()
                if not m:
                    raise HTTPException(404, "这块木牌不存在")
                c.execute("DELETE FROM garden_marks WHERE id=?", (mid,))  # 只撤木牌，不动实践
                _idem_record(c, user["id"], req.client_id, "delete", mid, mid, now)
            c.commit()
        except Exception:
            c.rollback()
            raise
        return _finish(c, user, replayed=replayed)
    finally:
        c.close()


@router.get("/api/garden/visit/{gid}/marks")
def visit_marks(gid: str, request: Request):
    user = _member(request)
    c = _db()
    try:
        g = _g._visible_garden(c, gid, user["id"])  # 私园/不存在统一 404
        _reconcile(c, g["id"], _now_dt())
        c.commit()
        rows = c.execute(
            """SELECT m.* FROM garden_marks m
               JOIN practice_items p ON p.id = m.practice_id
               WHERE m.garden_id=? AND m.shown=1 AND p.status='completed'
               ORDER BY m.created_at ASC""",
            (g["id"],),
        ).fetchall()
        return {"garden_id": g["id"], "items": [_visitor_mark(r) for r in rows]}
    finally:
        c.close()
