"""内容互动 R1：公开阅读/点赞/评论计数 + 本人点赞（契约 .fleet/interactions-stickers-20260924/contract.md）。

- kind: book_note|reading|journey|knowledge；白名单解析（book_notes/reading 治理索引，journey/knowledge 取 discuss/directory.json），目录挂 503、未知 404。
- views 按「浏览器-资源-北京时间日」去重：唯一约束+BEGIN IMMEDIATE；visitor_id 只落 sha256，不存原值/IP/UA/用户足迹；不从私密阅读记录回填。
- likes 唯一(user,kind,id)，显式赋值幂等，取消删行；无积分。
- comments 为公开可见评论真值（deleted=0 AND status='accepted'，含回复）；无评论区类型返回 0，不伪造。
- 全部响应 no-store；me 端点匿名 401/Agent 403；公共 GET 匿名可用。
"""

import datetime
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, StrictBool

CST = datetime.timezone(datetime.timedelta(hours=8))
KINDS = ("book_note", "reading", "journey", "knowledge")
# 各 kind 的权威白名单文件
INDEX_FILES = {
    "book_note": "book-notes/index.json",
    "reading": "readings/practice-index.json",
    # journey/knowledge 共用目录索引
    "journey": "discuss/directory.json",
    "knowledge": "discuss/directory.json",
}
_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,80}")
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
# 评论 anchor 方案（book_note 暂无评论面 → 0；预留 scheme 供 pS 接入）
_ANCHOR_PREFIX = {
    "book_note": "article:book_note:",
    "reading": "article:reading:",
    "journey": "article:journey:",
    "knowledge": "article:knowledge:",
}

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


def _today() -> str:
    return datetime.datetime.now(CST).strftime("%Y-%m-%d")


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(tags=["content-engagement"], dependencies=[Depends(_no_store)])


def _member(request: Request) -> dict:
    kind = getattr(request.state, "auth_kind", None)
    if kind == "agent":
        raise HTTPException(403, "内容互动暂不开放 Agent")
    if kind != "session" or not getattr(request.state, "user", None):
        raise HTTPException(401, "请先登录")
    return request.state.user


def ensure_schema(connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS engagement_views(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          kind TEXT NOT NULL,
          resource_id TEXT NOT NULL,
          day TEXT NOT NULL,
          visitor_hash TEXT NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(kind, resource_id, day, visitor_hash)
        );
        CREATE INDEX IF NOT EXISTS idx_engagement_views_res
          ON engagement_views(kind, resource_id);
        CREATE TABLE IF NOT EXISTS engagement_likes(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          kind TEXT NOT NULL,
          resource_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(user_id, kind, resource_id)
        );
        CREATE INDEX IF NOT EXISTS idx_engagement_likes_res
          ON engagement_likes(kind, resource_id);
        """
    )
    # 统计启用时间一次性登记：首个 init_db 写定，此后只读（since 稳定真值）
    connection.execute(
        "INSERT OR IGNORE INTO meta(k,v) VALUES('engagement_started_at',?)",
        (datetime.datetime.now(CST).isoformat(),),
    )


# ── 资源白名单（严格 shape，mtime_ns/size 缓存）──

def _index_path(kind: str) -> Path:
    if _static_dir is None:
        raise HTTPException(503, "资源目录暂不可用")
    return _static_dir / INDEX_FILES[kind]


def _load_index(kind: str) -> set:
    """返回该 kind 的合法 resource_id 集合；坏 shape → 503。"""
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
        ids: set[str] = set()
        if kind == "book_note":
            if "items" not in data or not isinstance(data["items"], list):
                raise ValueError("items bad shape")
            for it in data["items"]:
                if not isinstance(it, dict) or not isinstance(it.get("id"), str):
                    raise ValueError("entry bad shape")
                ids.add(it["id"])
        elif kind == "reading":
            if "entries" not in data or not isinstance(data["entries"], dict):
                raise ValueError("entries bad shape")
            for rid, it in data["entries"].items():
                if not isinstance(it, dict):
                    raise ValueError("entry bad shape")
                ids.add(rid)
        else:
            if "items" not in data or not isinstance(data["items"], list):
                raise ValueError("items bad shape")
            for it in data["items"]:
                if not isinstance(it, dict) or not isinstance(it.get("id"), str) or not isinstance(it.get("kind"), str):
                    raise ValueError("entry bad shape")
                if it["kind"] == kind:
                    ids.add(it["id"])
    except (OSError, ValueError, TypeError, AttributeError):
        raise HTTPException(503, "资源目录暂不可用")
    _index_cache[kind] = (sig, ids)
    return ids


def _resolve(kind: str, resource_id: str) -> None:
    if kind not in KINDS:
        raise HTTPException(404, "未知的资源类型")
    if not _ID_RE.fullmatch(resource_id or ""):
        raise HTTPException(404, "资源不存在")
    if resource_id not in _load_index(kind):
        raise HTTPException(404, "资源不存在")


# ── 公开统计 ──

def _since(c) -> str:
    """统计启用时间：ensure_schema 一次性登记（init_db 首跑定锚），读路径纯 SELECT。"""
    row = c.execute(
        "SELECT v FROM meta WHERE k='engagement_started_at'",
    ).fetchone()
    return row[0] if row else _today()


def _public_stats(c, kind: str, resource_id: str) -> dict:
    views = c.execute(
        "SELECT COUNT(*) FROM engagement_views WHERE kind=? AND resource_id=?",
        (kind, resource_id),
    ).fetchone()[0]
    likes = c.execute(
        "SELECT COUNT(*) FROM engagement_likes WHERE kind=? AND resource_id=?",
        (kind, resource_id),
    ).fetchone()[0]
    comments = c.execute(
        "SELECT COUNT(*) FROM comments WHERE anchor=? AND deleted=0 AND status='accepted'",
        (_ANCHOR_PREFIX[kind] + resource_id,),
    ).fetchone()[0]
    return {
        "kind": kind,
        "resource_id": resource_id,
        "views": views,
        "likes": likes,
        "comments": comments,
        "view_policy": {
            "visible_ms": 3000,
            "dedupe": "browser_day",
            "timezone": "Asia/Shanghai",
        },
        "since": _since(c),
    }


@router.get("/api/content-engagement/{kind}/{resource_id}")
def get_engagement(kind: str, resource_id: str, request: Request):
    _resolve(kind, resource_id)
    c = _db()
    try:
        return _public_stats(c, kind, resource_id)
    finally:
        c.close()


class ViewReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    visitor_id: str


@router.post("/api/content-engagement/{kind}/{resource_id}/view")
def record_view(kind: str, resource_id: str, req: ViewReq, request: Request):
    _resolve(kind, resource_id)
    if not _UUID_RE.fullmatch(req.visitor_id or ""):
        raise HTTPException(422, "visitor_id 必须是 UUID")
    # canonical lower + 域分隔（kind/resource/day）：大小写同 UUID 算同浏览器；
    # 同 hash 不能跨文章/跨日拼接匿名足迹
    vid = req.visitor_id.lower()
    day = _today()
    visitor_hash = hashlib.sha256(f"{vid}|{kind}|{resource_id}|{day}".encode()).hexdigest()
    c = _db()
    try:
        c.execute("BEGIN IMMEDIATE")
        c.execute(
            "INSERT OR IGNORE INTO engagement_views(kind,resource_id,day,visitor_hash,created_at) VALUES(?,?,?,?,?)",
            (kind, resource_id, day, visitor_hash, _now()),
        )
        c.commit()
        return _public_stats(c, kind, resource_id)
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


# ── 本人点赞 ──

class LikeReq(BaseModel):
    model_config = ConfigDict(extra="forbid")
    liked: StrictBool


@router.get("/api/me/content-engagement/{kind}/{resource_id}")
def get_my_engagement(kind: str, resource_id: str, request: Request):
    user = _member(request)
    _resolve(kind, resource_id)
    c = _db()
    try:
        row = c.execute(
            "SELECT 1 FROM engagement_likes WHERE user_id=? AND kind=? AND resource_id=?",
            (user["id"], kind, resource_id),
        ).fetchone()
        return {"liked": row is not None}
    finally:
        c.close()


@router.patch("/api/me/content-engagement/{kind}/{resource_id}")
def set_my_engagement(kind: str, resource_id: str, req: LikeReq, request: Request):
    user = _member(request)
    # 显式 null 拒收（StrictBool|None 不用；字段必选但 null 会被 pydantic 拒，双保险）
    if "liked" not in req.model_fields_set:
        raise HTTPException(422, "缺少 liked 字段")
    _resolve(kind, resource_id)
    c = _db()
    try:
        c.execute("BEGIN IMMEDIATE")
        if req.liked:
            c.execute(
                "INSERT OR IGNORE INTO engagement_likes(user_id,kind,resource_id,created_at) VALUES(?,?,?,?)",
                (user["id"], kind, resource_id, _now()),
            )
        else:
            c.execute(
                "DELETE FROM engagement_likes WHERE user_id=? AND kind=? AND resource_id=?",
                (user["id"], kind, resource_id),
            )
        c.commit()
        return {
            "liked": req.liked,
            "stats": _public_stats(c, kind, resource_id),
        }
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
