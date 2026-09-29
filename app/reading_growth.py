"""阅读成长 R1：私密阅读记录 + 我的参与归并（契约 .fleet/reading-growth-20260924/contract.md）。

- kind: book_note | reading；resource_id 服务端白名单（STATIC 下治理索引解析标题/分类/url，mtime/size 失效缓存）。
- 全部端点仅真人 session：匿名 401、Agent 403；no-store；按 session.user_id 归属，不提供他人查询参数。
- open 只记最近打开时间，不重置收藏/完成；PATCH 显式赋值幂等，未变值不改时间；DELETE 幂等只删本人记录。
- 我的参与只读归并现有 comments/question_threads/question_replies/practice_items/practice_replies/favorites，不存事件副本，无积分。
"""

import datetime
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, StrictBool

CST = datetime.timezone(datetime.timedelta(hours=8))
KINDS = ("book_note", "reading")
INDEX_FILES = {
    "book_note": "book-notes/index.json",
    "reading": "readings/practice-index.json",
}
_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,80}")
# 日报收藏 anchor：<YYYY-MM-DD>#<section>[-pN] → /ledger/<date>/#<section>（同 MyCellar favUrl）
_LEDGER_ANCHOR_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})#(.+)$")
_LEDGER_SEC_TRIM = re.compile(r"-p\d+$")
# anchor -> 站内可读页（仅白名单前缀；其余一律 url=None 不拼链）
_ANCHOR_ROUTES = (
    ("article:reading:", "/readings/", False),
    ("article:book_note:", "/readings/books/", False),
    ("article:knowledge:", "/learn/entries/", False),
    ("article:journey:", "/journey/", True),
)
_EXCERPT = 180

_db: Callable[[], Any] | None = None
_static_dir: Path | None = None
_index_cache: dict[str, tuple] = {}


def configure(*, db: Callable[[], Any], static_dir: Any = None) -> None:
    global _db, _static_dir
    _db = db
    _static_dir = Path(static_dir) if static_dir else None
    _index_cache.clear()


def _now() -> str:
    return datetime.datetime.now(CST).isoformat()


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["reading-growth"], dependencies=[Depends(_no_store)])


def _member(request: Request) -> dict:
    kind = getattr(request.state, "auth_kind", None)
    if kind == "agent":
        raise HTTPException(403, "阅读成长区暂不开放 Agent")
    if kind != "session" or not getattr(request.state, "user", None):
        raise HTTPException(401, "请先登录")
    return request.state.user


def ensure_schema(connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS reading_records(
          user_id INTEGER NOT NULL,
          kind TEXT NOT NULL,
          resource_id TEXT NOT NULL,
          title TEXT NOT NULL,
          url TEXT,
          category TEXT NOT NULL DEFAULT '',
          available INTEGER NOT NULL DEFAULT 1,
          last_opened_at TEXT,
          saved INTEGER NOT NULL DEFAULT 0,
          saved_at TEXT,
          finished INTEGER NOT NULL DEFAULT 0,
          finished_at TEXT,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(user_id, kind, resource_id)
        );
        CREATE INDEX IF NOT EXISTS idx_reading_records_list
          ON reading_records(user_id, updated_at DESC, kind, resource_id);
        -- 归并活动各源的 owner+time/id 索引（现有表上补，幂等）
        CREATE INDEX IF NOT EXISTS idx_reading_activity_threads
          ON question_threads(user_id, author_kind, created_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_reading_activity_qreplies
          ON question_replies(user_id, author_kind, created_at DESC, id DESC);
        CREATE INDEX IF NOT EXISTS idx_reading_activity_preplies
          ON practice_replies(owner_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_reading_activity_pitems
          ON practice_items(owner_id, updated_at DESC, id DESC);
        """
    )


# ── 资源索引（白名单 + mtime/size 缓存失效）──

def _index_path(kind: str) -> Path:
    if _static_dir is None:
        raise HTTPException(503, "资源目录暂不可用")
    return _static_dir / INDEX_FILES[kind]


def _load_index(kind: str) -> dict:
    path = _index_path(kind)
    try:
        st = path.stat()
    except OSError:
        raise HTTPException(503, "资源目录暂不可用")
    sig = (str(path), st.st_mtime_ns, st.st_size)
    hit = _index_cache.get(kind)
    if hit and hit[0] == sig:
        return hit[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("bad shape")
    except (OSError, ValueError, TypeError):
        raise HTTPException(503, "资源目录暂不可用")
    def _check_item(it: Any) -> dict:
        """条目必须是 dict、id 正则、title/category 字符串；坏形状由外层转 503。"""
        if not isinstance(it, dict):
            raise ValueError("entry not dict")
        rid = it.get("id")
        if not isinstance(rid, str) or not _ID_RE.fullmatch(rid):
            raise ValueError("bad id")
        title = it.get("title")
        cat = it.get("category", "")
        if (title is not None and not isinstance(title, str)) or not isinstance(cat, str):
            raise ValueError("bad fields")
        return {"rid": rid, "title": title, "category": cat}

    items: dict[str, dict] = {}
    try:
        if kind == "book_note":
            raw = data.get("items", [])
            if not isinstance(raw, list):
                raise ValueError("items bad shape")
            for it in raw:
                e = _check_item(it)
                items[e["rid"]] = {
                    "title": e["title"] or e["rid"],
                    "category": e["category"],
                    "url": f"/readings/books/{e['rid']}/",
                }
        else:
            entries = data.get("entries", {})
            if not isinstance(entries, dict):
                raise ValueError("entries bad shape")
            for rid, it in entries.items():
                if not isinstance(rid, str) or not _ID_RE.fullmatch(rid):
                    raise ValueError("bad id")
                if not isinstance(it, dict):
                    raise ValueError("entry not dict")
                title = it.get("source_title") or it.get("title")
                cat = it.get("category", "")
                if (title is not None and not isinstance(title, str)) or not isinstance(cat, str):
                    raise ValueError("bad fields")
                items[rid] = {
                    "title": title or rid,
                    "category": cat,
                    # url 由 id 规范生成，不盲信条目内 source_url
                    "url": f"/readings/{rid}/",
                }
    except (TypeError, ValueError, AttributeError):
        raise HTTPException(503, "资源目录暂不可用")
    _index_cache[kind] = (sig, items)
    return items


def _resolve(kind: str, resource_id: str) -> dict:
    """白名单解析；目录挂 503，未知资源 404。"""
    if kind not in KINDS:
        raise HTTPException(404, "未知的资源类型")
    if not _ID_RE.fullmatch(resource_id or ""):
        raise HTTPException(404, "资源不存在")
    meta = _load_index(kind).get(resource_id)
    if meta is None:
        raise HTTPException(404, "资源不存在")
    return meta


def _record(kind: str, resource_id: str, meta: dict | None, row) -> dict:
    if row is None:
        return {
            "kind": kind, "resource_id": resource_id,
            "title": meta["title"], "url": meta["url"],
            "category": meta["category"], "available": True,
            "last_opened_at": None, "saved": False, "saved_at": None,
            "finished": False, "finished_at": None, "updated_at": None,
        }
    # 索引挂 → 503 透传；索引在而 id 不在 → 已下架快照 available=false/url=None
    live = _load_index(kind).get(resource_id)
    if live:
        title, url, category, available = live["title"], live["url"], live["category"], True
    else:
        title, url, category, available = row["title"], None, row["category"], False
    return {
        "kind": row["kind"], "resource_id": row["resource_id"],
        "title": title, "url": url, "category": category, "available": available,
        "last_opened_at": row["last_opened_at"],
        "saved": bool(row["saved"]), "saved_at": row["saved_at"],
        "finished": bool(row["finished"]), "finished_at": row["finished_at"],
        "updated_at": row["updated_at"],
    }


def _get_row(c, uid: int, kind: str, rid: str):
    return c.execute(
        "SELECT * FROM reading_records WHERE user_id=? AND kind=? AND resource_id=?",
        (uid, kind, rid),
    ).fetchone()


def _upsert(c, uid: int, kind: str, rid: str, meta: dict, now: str,
            *, open_at: bool = False, saved=None, finished=None) -> None:
    row = _get_row(c, uid, kind, rid)
    if row is None:
        c.execute(
            """INSERT INTO reading_records(
                 user_id,kind,resource_id,title,url,category,available,
                 last_opened_at,saved,saved_at,finished,finished_at,updated_at)
               VALUES(?,?,?,?,?,?,1,?,?,?,?,?,?)""",
            (uid, kind, rid, meta["title"], meta["url"], meta["category"],
             now if open_at else None,
             int(saved) if saved else 0, now if saved else None,
             int(finished) if finished else 0, now if finished else None, now),
        )
        return
    sets, args, changed = [], [], False
    if open_at:
        sets += ["last_opened_at=?"]
        args += [now]
        changed = True
    if saved is not None and bool(row["saved"]) != bool(saved):
        sets += ["saved=?", "saved_at=?"]
        args += [int(saved), now if saved else None]
        changed = True
    if finished is not None and bool(row["finished"]) != bool(finished):
        sets += ["finished=?", "finished_at=?"]
        args += [int(finished), now if finished else None]
        changed = True
    if changed:
        sets += ["updated_at=?"]
        args += [now]
        args += [uid, kind, rid]
        c.execute(f"UPDATE reading_records SET {', '.join(sets)} WHERE user_id=? AND kind=? AND resource_id=?", args)


# ── 阅读记录端点 ──

@router.get("/api/me/reading-progress/{kind}/{resource_id}")
def get_progress(kind: str, resource_id: str, request: Request):
    user = _member(request)
    meta = None
    c = _db()
    try:
        row = _get_row(c, user["id"], kind, resource_id)
        if row is None:
            meta = _resolve(kind, resource_id)
        else:
            if kind not in KINDS or not _ID_RE.fullmatch(resource_id or ""):
                raise HTTPException(404, "资源不存在")
        return {"item": _record(kind, resource_id, meta, row)}
    finally:
        c.close()


class ProgressPatchReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    saved: StrictBool | None = None
    finished: StrictBool | None = None


@router.post("/api/me/reading-progress/{kind}/{resource_id}/open")
def open_progress(kind: str, resource_id: str, request: Request):
    user = _member(request)
    meta = _resolve(kind, resource_id)
    c = _db()
    try:
        c.execute("BEGIN IMMEDIATE")
        _upsert(c, user["id"], kind, resource_id, meta, _now(), open_at=True)
        c.commit()
        return {"item": _record(kind, resource_id, None, _get_row(c, user["id"], kind, resource_id))}
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


@router.patch("/api/me/reading-progress/{kind}/{resource_id}")
def patch_progress(kind: str, resource_id: str, req: ProgressPatchReq, request: Request):
    user = _member(request)
    # 显式 null 与未传区分：null 一律拒（StrictBool|None 允许 None 通过校验）
    for field in req.model_fields_set:
        if getattr(req, field) is None:
            raise HTTPException(422, f"{field} 不接受 null")
    if req.saved is None and req.finished is None:
        raise HTTPException(422, "至少提供 saved 或 finished 一项")
    meta = _resolve(kind, resource_id)
    c = _db()
    try:
        c.execute("BEGIN IMMEDIATE")
        _upsert(c, user["id"], kind, resource_id, meta, _now(),
                saved=req.saved, finished=req.finished)
        c.commit()
        return {"item": _record(kind, resource_id, None, _get_row(c, user["id"], kind, resource_id))}
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


@router.delete("/api/me/reading-progress/{kind}/{resource_id}")
def delete_progress(kind: str, resource_id: str, request: Request):
    user = _member(request)
    c = _db()
    try:
        c.execute("BEGIN IMMEDIATE")
        c.execute(
            "DELETE FROM reading_records WHERE user_id=? AND kind=? AND resource_id=?",
            (user["id"], kind, resource_id),
        )
        c.commit()
        return {"ok": True}
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


@router.get("/api/me/reading-progress")
def list_progress(
    request: Request,
    filter: str = Query("all"),
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    user = _member(request)
    if filter not in ("all", "saved", "finished"):
        raise HTTPException(422, "filter 只接受 all/saved/finished")
    # 索引必须可用（要重标 available/url），挂则 503
    _load_index("book_note")
    _load_index("reading")
    where = {"all": "1=1", "saved": "saved=1", "finished": "finished=1"}[filter]
    c = _db()
    try:
        rows = c.execute(
            f"""SELECT * FROM reading_records WHERE user_id=? AND {where}
                ORDER BY updated_at DESC, kind, resource_id LIMIT ? OFFSET ?""",
            (user["id"], limit + 1, offset),
        ).fetchall()
        total = c.execute(
            f"SELECT COUNT(*) FROM reading_records WHERE user_id=? AND {where}",
            (user["id"],),
        ).fetchone()[0]
        items = [_record(kind=row["kind"], resource_id=row["resource_id"], meta=None, row=row)
                 for row in rows[:limit]]
        return {
            "items": items,
            "total": total,
            "has_more": offset + len(items) < total,
            "summary": {
                "opened": c.execute(
                    "SELECT COUNT(*) FROM reading_records WHERE user_id=? AND last_opened_at IS NOT NULL",
                    (user["id"],)).fetchone()[0],
                "saved": c.execute(
                    "SELECT COUNT(*) FROM reading_records WHERE user_id=? AND saved=1",
                    (user["id"],)).fetchone()[0],
                "finished": c.execute(
                    "SELECT COUNT(*) FROM reading_records WHERE user_id=? AND finished=1",
                    (user["id"],)).fetchone()[0],
            },
        }
    finally:
        c.close()


# ── 我的参与（只读归并）──

def _anchor_url(anchor: str | None) -> str | None:
    if not anchor:
        return None
    for prefix, route, fixed in _ANCHOR_ROUTES:
        if anchor.startswith(prefix):
            if fixed:
                return route
            rid = anchor[len(prefix):]
            if _ID_RE.fullmatch(rid):
                return f"{route}{rid}/"
            return None
    m = _LEDGER_ANCHOR_RE.match(anchor)
    if m:
        sec = _LEDGER_SEC_TRIM.sub("", m.group(2))
        if sec:
            return f"/ledger/{m.group(1)}/#{sec}"
    return None


def _anchor_title(anchor: str | None) -> str | None:
    """评论标题解析到资源标题；不可解析由调用方落「文章评论」。"""
    if not anchor:
        return None
    for prefix, kind in (("article:reading:", "reading"), ("article:book_note:", "book_note")):
        if anchor.startswith(prefix):
            rid = anchor[len(prefix):]
            if not _ID_RE.fullmatch(rid):
                return None
            try:
                meta = _load_index(kind).get(rid)
            except HTTPException:
                return None
            return meta["title"] if meta else None
    return None


def _ref_url(ref: str | None) -> str | None:
    """UNION 里 ref 列 → 真实站内链接（现有路由，不猜 anchor）。"""
    if not ref:
        return None
    if ref.startswith("thread:"):
        return f"/community/?thread={ref[7:]}"
    if ref.startswith("practice:"):
        return f"/me/?view=mine&p={ref[9:]}"
    if ref.startswith("submission:"):
        return f"/me/?view=challenges&s={ref[11:]}"
    return _anchor_url(ref)


_ACTIVITY_UNION = """
SELECT id, type, title, excerpt, ref, at FROM (
  SELECT 'comment:'||id AS id, 'comment' AS type, anchor AS title,
         substr(text,1,180) AS excerpt, anchor AS ref, created_at AS at
    FROM comments
   WHERE user_id=? AND deleted=0 AND status='accepted'
     AND agent_token_id IS NULL AND (via IS NULL OR via<>'agent')
  UNION ALL
  SELECT 'question:'||id, 'question', title, substr(body,1,180), 'thread:'||id, created_at
    FROM question_threads WHERE user_id=? AND author_kind='human'
  UNION ALL
  SELECT 'reply:'||r.id, 'reply', t.title, substr(r.text,1,180), 'thread:'||t.id, r.created_at
    FROM question_replies r JOIN question_threads t ON t.id=r.thread_id
   WHERE r.user_id=? AND r.author_kind='human'
  UNION ALL
  SELECT 'practice:'||id, 'practice', title, substr(outcome,1,180), 'practice:'||id, updated_at
    FROM practice_items WHERE owner_id=?
  UNION ALL
  SELECT 'practice_reply:'||r.id, 'practice_reply', s.title, substr(r.text,1,180),
         'submission:'||r.submission_id, r.created_at
    FROM practice_replies r JOIN practice_submissions s ON s.id=r.submission_id
   WHERE r.owner_id=?
  UNION ALL
  SELECT 'paragraph_saved:'||id, 'paragraph_saved',
         COALESCE(NULLIF(section,''),anchor), substr(text,1,180), anchor, created_at
    FROM favorites WHERE user_id=?
) ORDER BY at DESC, id DESC LIMIT ? OFFSET ?
"""

_COUNT_SQL = [
    """SELECT COUNT(*) FROM comments
       WHERE user_id=? AND deleted=0 AND status='accepted'
         AND agent_token_id IS NULL AND (via IS NULL OR via<>'agent')""",
    "SELECT COUNT(*) FROM question_threads WHERE user_id=? AND author_kind='human'",
    """SELECT COUNT(*) FROM question_replies r JOIN question_threads t ON t.id=r.thread_id
       WHERE r.user_id=? AND r.author_kind='human'""",
    "SELECT COUNT(*) FROM practice_items WHERE owner_id=?",
    """SELECT COUNT(*) FROM practice_replies r JOIN practice_submissions s ON s.id=r.submission_id
       WHERE r.owner_id=?""",
    "SELECT COUNT(*) FROM favorites WHERE user_id=?",
]


@router.get("/api/me/growth-activity")
def growth_activity(
    request: Request,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    user = _member(request)
    uid = user["id"]
    c = _db()
    try:
        rows = c.execute(
            _ACTIVITY_UNION,
            (uid, uid, uid, uid, uid, uid, limit + 1, offset),
        ).fetchall()
        items = []
        for r in rows[:limit]:
            title = r["title"]
            if r["type"] == "comment":
                title = _anchor_title(r["ref"]) or "文章评论"
            elif r["type"] == "paragraph_saved" and (not title or title == r["ref"]):
                title = _anchor_title(r["ref"]) or "段落收藏"
            items.append({
                "id": r["id"], "type": r["type"], "title": title,
                "excerpt": r["excerpt"], "url": _ref_url(r["ref"]), "at": r["at"],
            })
        source_counts = [c.execute(q, (uid,)).fetchone()[0] for q in _COUNT_SQL]
        total = sum(source_counts)
        return {
            "items": items,
            "total": total,
            "has_more": offset + len(items) < total,
            "summary": {
                "contributions": source_counts[0] + source_counts[1] + source_counts[2] + source_counts[4],
                "practices_completed": c.execute(
                    "SELECT COUNT(*) FROM practice_items WHERE owner_id=? AND status='completed'",
                    (uid,)).fetchone()[0],
                "paragraphs_saved": source_counts[5],
            },
        }
    finally:
        c.close()
