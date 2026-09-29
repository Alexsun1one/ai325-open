# -*- coding: utf-8 -*-
"""Admin ops console: queue, members, publication. Read-mostly.

Does not change /api/admin/member-accounts* behavior. Bulk claim-link
issuance is not implemented. Publish requests are recorded as a host
drop file; the API container does not exec server-daily.sh.
"""
from __future__ import annotations

import datetime
import json
try:
    import publication_schedule
except ImportError:  # pragma: no cover - package import path
    from app import publication_schedule
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

DATA_DIR = Path(os.environ.get("XF_DATA_DIR", "/data"))
DB = DATA_DIR / "xf.db"
GOVERNED_DIR = Path(os.environ.get("XF_GOVERNED_DIR", str(DATA_DIR / "governed")))
STATIC_DIR = Path(os.environ.get("XF_STATIC_DIR", "/app/static"))
HEALTH_FILE = Path(os.environ.get("XF_HEALTH_FILE", str(STATIC_DIR / "health" / "daily.json")))
PUBLISH_DROP = Path(os.environ.get("XF_OPS_PUBLISH_DROP", str(DATA_DIR / "ops-publish-requests.jsonl")))
CST = datetime.timezone(datetime.timedelta(hours=8))
QUEUE_LIMIT = 80
MEMBER_LIMIT_DEFAULT = 200
RAW_ID_RE = re.compile(
    r"(?i)(?:wxid_[A-Za-z0-9_-]+|gh_[A-Za-z0-9_-]+|QQ\d{5,}|q\d{6,}|[0-9]{8,})"
)
RAW_FULL_RE = re.compile(
    r"^(?:wxid_[A-Za-z0-9_-]+|QQ\d{5,}|q\d{6,}|gh_[A-Za-z0-9_-]+|[0-9]{5,}|\?|未知|未识别|群友)$",
    re.I,
)
UNRESOLVED_FLAG_RE = re.compile(r"unresolved|待确认|missing_wxid", re.I)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

router = APIRouter()


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def require_admin(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    role = user.get("role") if hasattr(user, "get") else (user["role"] if user else None)
    if getattr(request.state, "auth_kind", None) != "session" or role != "admin":
        raise HTTPException(403, "仅管理员登录态可操作后台")
    return user


def _json_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def is_raw_display(value: object) -> bool:
    text = str(value or "").strip()
    return not text or bool(RAW_FULL_RE.fullmatch(text)) or bool(RAW_ID_RE.search(text))


def identity_unresolved(flags: list, display: str, name_source: str) -> bool:
    blob = " ".join(str(item) for item in flags)
    if UNRESOLVED_FLAG_RE.search(blob):
        return True
    if name_source in {"masked_wxid", "", "wxid"} and is_raw_display(display):
        return True
    return is_raw_display(display)


def _day(value: object) -> str | None:
    text = str(value or "").strip()[:10]
    try:
        datetime.date.fromisoformat(text)
        return text
    except ValueError:
        return None


def _preview(value: object, limit: int = 48) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _activity(last_active: str | None, as_of: datetime.date) -> str:
    day = _day(last_active)
    if not day:
        return "quiet"
    delta = (as_of - datetime.date.fromisoformat(day)).days
    if delta <= 7:
        return "active_7d"
    if delta <= 30:
        return "active_30d"
    return "quiet"


def queue_payload(conn: sqlite3.Connection, as_of: datetime.date) -> dict[str, Any]:
    tables = _tables(conn)
    counts = {"comment": 0, "submission": 0, "redemption": 0, "identity": 0, "moderation": 0}
    items: list[dict[str, Any]] = []

    if "comments" in tables and "status" in _columns(conn, "comments"):
        where = "deleted=0 AND status='pending'" if "deleted" in _columns(conn, "comments") else "status='pending'"
        counts["comment"] = conn.execute(f"SELECT COUNT(*) FROM comments WHERE {where}").fetchone()[0]
        for row in conn.execute(
            f"SELECT id, username, text, created_at, status FROM comments WHERE {where} ORDER BY id DESC LIMIT ?",
            (QUEUE_LIMIT,),
        ):
            items.append({
                "id": row["id"], "kind": "comment", "label": "待审评论",
                "actor": row["username"], "preview": _preview(row["text"]),
                "created_at": str(row["created_at"] or "")[:19], "status": row["status"],
                "decide": None,
            })

    if "submissions" in tables:
        counts["submission"] = conn.execute("SELECT COUNT(*) FROM submissions WHERE status='pending'").fetchone()[0]
        for row in conn.execute(
            "SELECT id, username, title, created_at, status FROM submissions WHERE status='pending' ORDER BY id DESC LIMIT ?",
            (QUEUE_LIMIT,),
        ):
            items.append({
                "id": row["id"], "kind": "submission", "label": "待审投稿",
                "actor": row["username"], "preview": _preview(row["title"]),
                "created_at": str(row["created_at"] or "")[:19], "status": row["status"],
                "decide": f"/api/admin/submissions/{row['id']}/status",
            })

    if "reward_redemptions" in tables:
        counts["redemption"] = conn.execute("SELECT COUNT(*) FROM reward_redemptions WHERE status='pending'").fetchone()[0]
        for row in conn.execute(
            "SELECT id, user_id, item_id, created_at, status FROM reward_redemptions WHERE status='pending' ORDER BY id DESC LIMIT ?",
            (QUEUE_LIMIT,),
        ):
            items.append({
                "id": row["id"], "kind": "redemption", "label": "待审兑换",
                "actor": f"user:{row['user_id']}", "preview": _preview(row["item_id"]),
                "created_at": str(row["created_at"] or "")[:19], "status": row["status"],
                "decide": f"/api/admin/rewards/redemptions/{row['id']}/approve",
            })

    if "moderation_queue" in tables:
        counts["moderation"] = conn.execute(
            "SELECT COUNT(*) FROM moderation_queue WHERE status IN ('queued','processing','pending')"
        ).fetchone()[0]
        for row in conn.execute(
            """SELECT id, created_at, actor_user, action, target_type, status
               FROM moderation_queue WHERE status IN ('queued','processing','pending')
               ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END, id LIMIT ?""",
            (QUEUE_LIMIT,),
        ):
            items.append({
                "id": row["id"], "kind": "moderation", "label": "审核队列",
                "actor": row["actor_user"], "preview": _preview(f"{row['action']} · {row['target_type']}"),
                "created_at": str(row["created_at"] or "")[:19], "status": row["status"],
                "decide": f"/api/moderation/{row['id']}/decide",
            })

    if "members" in tables:
        cols = _columns(conn, "members")
        legacy = "AND identity_flags NOT LIKE '%legacy_display_key%'" if "identity_flags" in cols else ""
        rows = conn.execute(
            f"""SELECT username, display, nickname, last_active, name_source, identity_flags
                FROM members WHERE 1=1 {legacy}"""
        ).fetchall() if "identity_flags" in cols else []
        identity_items = []
        for row in rows:
            flags = _json_list(row["identity_flags"] if "identity_flags" in cols else "[]")
            display = str(row["display"] or row["nickname"] or row["username"] or "")
            source = str(row["name_source"] or "") if "name_source" in cols else ""
            if not identity_unresolved(flags, display, source):
                continue
            identity_items.append({
                "id": row["username"], "kind": "identity", "label": "身份待确认",
                "actor": display or row["username"], "preview": _preview("、".join(str(f) for f in flags) or source or "昵称未解析"),
                "created_at": str(row["last_active"] or "")[:19], "status": "待确认",
                "decide": None, "member_key": row["username"],
            })
        counts["identity"] = len(identity_items)
        items.extend(identity_items[:QUEUE_LIMIT])

    total = int(sum(counts.values()))
    return {
        "as_of": as_of.isoformat(),
        "total": total,
        "limit": QUEUE_LIMIT,
        "truncated": total > QUEUE_LIMIT,
        "counts": counts,
        "items": items[:QUEUE_LIMIT],
        "bulk_claim_links": False,
    }


def members_payload(
    conn: sqlite3.Connection,
    as_of: datetime.date,
    *,
    q: str = "",
    has_account: bool | None = None,
    unresolved: bool | None = None,
    has_agents: bool | None = None,
    activity: str | None = None,
    limit: int = MEMBER_LIMIT_DEFAULT,
) -> dict[str, Any]:
    tables = _tables(conn)
    if "members" not in tables:
        return {"as_of": as_of.isoformat(), "total": 0, "shown": 0, "truncated": False, "items": [], "filters": {}}
    cols = _columns(conn, "members")
    accounts: dict[str, dict[str, Any]] = {}
    if "users" in tables and "member_key" in _columns(conn, "users"):
        for row in conn.execute(
            "SELECT id, username, display_name, member_key, last_login, active, role FROM users WHERE member_key IS NOT NULL"
        ):
            accounts[str(row["member_key"])] = dict(row)
    agent_counts: dict[str, int] = {}
    if "agent_tokens" in tables:
        for user_id, n in conn.execute("SELECT user_id, COUNT(*) FROM agent_tokens WHERE revoked=0 GROUP BY user_id"):
            agent_counts[str(user_id)] = int(n)

    legacy = "AND identity_flags NOT LIKE '%legacy_display_key%'" if "identity_flags" in cols else ""
    rows = conn.execute(
        f"""SELECT username, display, nickname, msgs, last_active, name_source, identity_flags
            FROM members WHERE 1=1 {legacy} ORDER BY msgs DESC, username"""
    ).fetchall()

    query = q.strip().casefold()
    items: list[dict[str, Any]] = []
    filter_counts = {"has_account": 0, "no_account": 0, "unresolved": 0, "has_agents": 0, "active_7d": 0, "quiet": 0}
    for row in rows:
        flags = _json_list(row["identity_flags"])
        display = str(row["display"] or row["nickname"] or row["username"] or "")
        unresolved_flag = identity_unresolved(flags, display, str(row["name_source"] or ""))
        account = accounts.get(str(row["username"]))
        agent_n = agent_counts.get(str(account["id"]), 0) if account else 0
        bucket = _activity(row["last_active"], as_of)
        bound = bool(account)
        if bound:
            filter_counts["has_account"] += 1
        else:
            filter_counts["no_account"] += 1
        if unresolved_flag:
            filter_counts["unresolved"] += 1
        if agent_n:
            filter_counts["has_agents"] += 1
        if bucket == "active_7d":
            filter_counts["active_7d"] += 1
        if bucket == "quiet":
            filter_counts["quiet"] += 1
        if query and query not in display.casefold() and query not in str(row["username"]).casefold():
            continue
        if has_account is True and not bound:
            continue
        if has_account is False and bound:
            continue
        if unresolved is True and not unresolved_flag:
            continue
        if unresolved is False and unresolved_flag:
            continue
        if has_agents is True and not agent_n:
            continue
        if has_agents is False and agent_n:
            continue
        if activity in {"active_7d", "quiet", "active_30d"} and bucket != activity:
            continue
        items.append({
            "member_key": row["username"],
            "display": display,
            "msgs": int(row["msgs"] or 0),
            "last_active": _day(row["last_active"]),
            "has_account": bound,
            "account": {
                "id": account["id"], "username": account["username"],
                "active": bool(account["active"]), "last_login": _day(account.get("last_login")),
                "role": account.get("role"),
            } if account else None,
            "unresolved": unresolved_flag,
            "agent_count": agent_n,
            "activity": bucket,
            "name_source": str(row["name_source"] or "masked_wxid"),
            "flags": [str(flag) for flag in flags if flag != "legacy_display_key"][:6],
        })
    cap = max(1, min(int(limit), 500))
    return {
        "as_of": as_of.isoformat(),
        "total": len(items),
        "shown": min(len(items), cap),
        "truncated": len(items) > cap,
        "filters": filter_counts,
        "items": items[:cap],
        "single_actions": ["开号", "出认领链接", "绑定", "禁用"],
        "bulk_allowed": ["标记", "导出清单"],
        "bulk_forbidden": ["批量出认领链接"],
    }


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def issues_payload(now: datetime.datetime) -> dict[str, Any]:
    ledgers: dict[str, dict[str, Any]] = {}
    ledger_dir = GOVERNED_DIR / "ledgers"
    if ledger_dir.is_dir():
        for path in sorted(ledger_dir.glob("*.json")):
            day = _day(path.stem)
            if not day:
                continue
            payload = _load_json(path)
            quality = payload.get("quality") if isinstance(payload, dict) else {}
            if not isinstance(quality, dict):
                quality = {}
            degree = quality.get("overall")
            ledgers[day] = {"published": True, "degree": degree if isinstance(degree, (int, float)) else None}
    health_days: dict[str, dict[str, Any]] = {}
    health = _load_json(HEALTH_FILE)
    if isinstance(health, dict) and isinstance(health.get("days"), list):
        for row in health["days"]:
            if not isinstance(row, dict):
                continue
            day = _day(row.get("date"))
            if not day:
                continue
            fails = row.get("hard_fail") if isinstance(row.get("hard_fail"), list) else []
            health_days[day] = {
                "passed": row.get("passed"), "score": row.get("score"), "grade": row.get("grade"),
                "redistill_count": row.get("redistill_count"),
                "hard_fail": [str(item)[:72] for item in fails[:4]],
            }
    days = sorted(set(ledgers) | set(health_days))
    issues = []
    for day in days:
        gate = health_days.get(day) or {}
        pub = ledgers.get(day) or {}
        issues.append({
            "date": day,
            "published": bool(pub.get("published")),
            "degree": pub.get("degree"),
            "gate_passed": gate.get("passed"),
            "gate_score": gate.get("score"),
            "grade": gate.get("grade"),
            "redistill_count": gate.get("redistill_count"),
            "hard_fail": gate.get("hard_fail") or [],
            "needs_redistill": gate.get("passed") is False,
        })
    published = sorted(day for day, row in ledgers.items() if row.get("published"))
    streak = 0
    cursor = datetime.date.fromisoformat(published[-1]) if published else None
    published_set = set(published)
    while cursor and cursor.isoformat() in published_set:
        streak += 1
        cursor -= datetime.timedelta(days=1)
    status = publication_schedule.publication_status(now, published_set)
    return {
        "as_of": status["as_of"],
        "published_days": len(published),
        "streak_days": streak if published else None,
        "latest_date": status["latest_date"],
        "expected_latest": status["expected_latest"],
        "pending_date": status["pending_date"],
        "scheduled_for": status["scheduled_for"],
        "missing_dates": status["missing_dates"],
        "health": status["health"],
        "issues": issues,
        "alert_entry": {"href": "/me", "label": "值守台（现役在私窖；统一 /admin 导航由 p3 挂）"},
        "publish_drop": str(PUBLISH_DROP),
        "host_command": "server-daily.sh [--force-redistill] YYYY-MM-DD",
    }


@router.get("/api/admin/queue")
def admin_queue(request: Request):
    require_admin(request)
    conn = db()
    try:
        return queue_payload(conn, datetime.datetime.now(CST).date())
    finally:
        conn.close()


@router.get("/api/admin/members")
def admin_members(
    request: Request,
    q: str = "",
    has_account: bool | None = Query(default=None),
    unresolved: bool | None = Query(default=None),
    has_agents: bool | None = Query(default=None),
    activity: str | None = Query(default=None),
    limit: int = Query(default=MEMBER_LIMIT_DEFAULT, ge=1, le=500),
):
    require_admin(request)
    conn = db()
    try:
        return members_payload(
            conn, datetime.datetime.now(CST).date(),
            q=q, has_account=has_account, unresolved=unresolved,
            has_agents=has_agents, activity=activity, limit=limit,
        )
    finally:
        conn.close()


@router.get("/api/admin/ops/issues")
def admin_ops_issues(request: Request):
    require_admin(request)
    return issues_payload(datetime.datetime.now(CST))


class PublishReq(BaseModel):
    date: str
    force_redistill: bool = False


@router.post("/api/admin/ops/publish")
def admin_ops_publish(req: PublishReq, request: Request):
    """Record a host-side publish/redistill request. Does not exec the pipeline."""
    admin = require_admin(request)
    if not DATE_RE.match(req.date):
        raise HTTPException(422, "日期必须是 YYYY-MM-DD")
    try:
        datetime.date.fromisoformat(req.date)
    except ValueError as exc:
        raise HTTPException(422, "日期不合法") from exc
    now = datetime.datetime.now(CST).isoformat(timespec="seconds")
    argv = ["scripts/server-daily.sh"]
    if req.force_redistill:
        argv.append("--force-redistill")
    argv.append(req.date)
    record = {
        "ts": now,
        "date": req.date,
        "force_redistill": bool(req.force_redistill),
        "requested_by": admin.get("username"),
        "command": " ".join(argv),
        "status": "queued",
    }
    PUBLISH_DROP.parent.mkdir(parents=True, exist_ok=True)
    with PUBLISH_DROP.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {
        "ok": True,
        "queued": True,
        "applied": False,
        "command": record["command"],
        "drop": str(PUBLISH_DROP),
        "note": "已记下出刊请求。容器不直接跑 server-daily；host pickup 待接线。",
    }
