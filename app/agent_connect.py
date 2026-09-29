"""One-command Agent device authorization endpoints.

Device and user codes are short-lived bearer secrets.  This module stores only
their SHA-256 hashes; the resulting Agent token is returned exactly once from
the approved poll and is likewise only stored as a hash in ``agent_tokens``.
"""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import re
import secrets
import threading
import time
from typing import Any, Callable

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["agent-connect"])

DEVICE_EXPIRES_SECONDS = 10 * 60
POLL_INTERVAL_SECONDS = 3
CONNECT_START_LIMIT = 10
CONNECT_REQUEST_LIMIT = 60
CONNECT_APPROVE_LIMIT = 20
# Unknown codes are never allowed to create per-device process state.  Known
# devices use their persisted timestamp throttle below, so many valid devices
# behind one NAT can complete a full ten-minute wait.
CONNECT_UNKNOWN_POLL_IP_LIMIT = 120
CONNECT_RATE_WINDOW_SECONDS = 10 * 60
EXPIRED_RETENTION_SECONDS = 24 * 60 * 60
MAX_RATE_KEYS = 2_048
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CONTROL = re.compile(r"[\x00-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
_rate_lock = threading.Lock()
_attempts: dict[tuple[str, str], collections.deque[float]] = {}
_db: Callable[[], Any] | None = None
_require_human_session: Callable[[Request], dict[str, Any]] | None = None
_request_ip: Callable[[Request], str] | None = None


class ConnectStartReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    client: str = Field(..., min_length=1, max_length=40)


class ConnectApproveReq(BaseModel):
    user_code: str = Field(..., min_length=1, max_length=16)


class ConnectPollReq(BaseModel):
    device_code: str = Field(..., min_length=20, max_length=256)


def configure(*, db: Callable[[], Any], require_human_session: Callable[[Request], dict[str, Any]], request_ip: Callable[[Request], str]) -> None:
    """Wire existing application auth/database helpers without a circular import."""
    global _db, _require_human_session, _request_ip
    _db = db
    _require_human_session = require_human_session
    _request_ip = request_ip


def ensure_schema(connection: Any) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent_connect_requests(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          device_code_hash TEXT UNIQUE NOT NULL,
          user_code_hash TEXT UNIQUE NOT NULL,
          name TEXT NOT NULL,
          client TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          created_at TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          approved_by_user_id INTEGER,
          approved_at TEXT,
          consumed_at TEXT,
          last_polled_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_agent_connect_requests_user_code
          ON agent_connect_requests(user_code_hash, status, expires_at);
        CREATE INDEX IF NOT EXISTS idx_agent_connect_requests_device_code
          ON agent_connect_requests(device_code_hash, status, expires_at);
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(agent_connect_requests)")}
    if "last_polled_at" not in columns:
        connection.execute("ALTER TABLE agent_connect_requests ADD COLUMN last_polled_at TEXT")


def _configured() -> tuple[Callable[[], Any], Callable[[Request], dict[str, Any]], Callable[[Request], str]]:
    if _db is None or _require_human_session is None or _request_ip is None:
        raise RuntimeError("agent connect module is not configured")
    return _db, _require_human_session, _request_ip


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _iso(value: dt.datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _expires_in(expires_at: str) -> int:
    try:
        expiry = dt.datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return max(0, int((expiry - _now()).total_seconds()))


def _parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _clean(value: str, limit: int, label: str) -> str:
    cleaned = _CONTROL.sub("", value).strip()
    if not cleaned:
        raise HTTPException(422, f"{label}不能为空")
    if len(cleaned) > limit:
        raise HTTPException(422, f"{label}不能超过 {limit} 字")
    return cleaned


def _user_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4)) + "-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))


def _rate_limit(kind: str, request: Request) -> None:
    _, _, request_ip = _configured()
    key = (kind, request_ip(request))
    limit = {
        "start": CONNECT_START_LIMIT,
        "request": CONNECT_REQUEST_LIMIT,
        "approve": CONNECT_APPROVE_LIMIT,
        "poll_unknown": CONNECT_UNKNOWN_POLL_IP_LIMIT,
    }[kind]
    now = time.monotonic()
    with _rate_lock:
        # Do not let spoofed/rotating client addresses grow the process map
        # forever. Existing active keys retain their normal accounting.
        if key not in _attempts and len(_attempts) >= MAX_RATE_KEYS:
            stale = [candidate for candidate, values in _attempts.items() if not values or values[-1] <= now - CONNECT_RATE_WINDOW_SECONDS]
            for candidate in stale:
                _attempts.pop(candidate, None)
            if len(_attempts) >= MAX_RATE_KEYS:
                raise HTTPException(429, "连接请求过于频繁，请稍后重试", headers={"Retry-After": str(CONNECT_RATE_WINDOW_SECONDS)})
        events = _attempts.setdefault(key, collections.deque())
        while events and events[0] <= now - CONNECT_RATE_WINDOW_SECONDS:
            events.popleft()
        if len(events) >= limit:
            raise HTTPException(429, "连接请求过于频繁，请稍后重试", headers={"Retry-After": str(CONNECT_RATE_WINDOW_SECONDS)})
        events.append(now)


def _request_by_user_code(connection: Any, user_code: str) -> Any:
    return connection.execute(
        "SELECT * FROM agent_connect_requests WHERE user_code_hash=?", (_hash(user_code.upper()),)
    ).fetchone()


def _expired(row: Any) -> bool:
    return _expires_in(row["expires_at"]) <= 0


def _cleanup_expired(connection: Any, now: dt.datetime) -> None:
    cutoff = _iso(now - dt.timedelta(seconds=EXPIRED_RETENTION_SECONDS))
    connection.execute("DELETE FROM agent_connect_requests WHERE expires_at < ?", (cutoff,))


@router.post("/api/agent/connect/start")
def start(req: ConnectStartReq, request: Request):
    _rate_limit("start", request)
    db, _, _ = _configured()
    name = _clean(req.name, 80, "Agent 名")
    client = _clean(req.client, 40, "客户端")
    now = _now()
    expires_at = _iso(now + dt.timedelta(seconds=DEVICE_EXPIRES_SECONDS))
    # Collision probability is negligible, but the unique user-code index is
    # authoritative: retry only a collision and do not leak the conflicting code.
    for _ in range(5):
        device_code = f"ai325_connect_{secrets.token_urlsafe(32)}"
        user_code = _user_code()
        connection = db()
        try:
            _cleanup_expired(connection, now)
            connection.execute(
                """INSERT INTO agent_connect_requests(
                   device_code_hash,user_code_hash,name,client,status,created_at,expires_at)
                   VALUES(?,?,?,?, 'pending', ?, ?)""",
                (_hash(device_code), _hash(user_code), name, client, _iso(now), expires_at),
            )
            connection.commit()
            return {
                "device_code": device_code,
                "user_code": user_code,
                "verification_uri": f"/agents/join/?connect={user_code}",
                "expires_in": DEVICE_EXPIRES_SECONDS,
                "interval": POLL_INTERVAL_SECONDS,
            }
        except Exception as error:
            connection.rollback()
            if "UNIQUE constraint failed" not in str(error):
                raise
        finally:
            connection.close()
    raise HTTPException(503, "暂时无法生成连接码，请重试")


@router.get("/api/agent/connect/request")
def request_detail(user_code: str, request: Request):
    _rate_limit("request", request)
    db, require_human_session, _ = _configured()
    require_human_session(request)
    normalized = _clean(user_code, 16, "用户码").upper()
    connection = db()
    try:
        row = _request_by_user_code(connection, normalized)
        if not row:
            raise HTTPException(404, "连接请求不存在")
        if _expired(row):
            raise HTTPException(410, "连接请求已过期")
        return {"name": row["name"], "client": row["client"], "user_code": normalized, "expires_in": _expires_in(row["expires_at"]), "status": row["status"]}
    finally:
        connection.close()


@router.post("/api/agent/connect/approve")
def approve(req: ConnectApproveReq, request: Request):
    _rate_limit("approve", request)
    db, require_human_session, _ = _configured()
    user = require_human_session(request)
    user_code = _clean(req.user_code, 16, "用户码").upper()
    connection = db()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = _request_by_user_code(connection, user_code)
        if not row:
            raise HTTPException(404, "连接请求不存在")
        if _expired(row):
            raise HTTPException(410, "连接请求已过期")
        if row["status"] != "pending":
            raise HTTPException(409, "连接请求已处理，不能重复批准")
        changed = connection.execute(
            """UPDATE agent_connect_requests
               SET status='approved',approved_by_user_id=?,approved_at=?
               WHERE id=? AND status='pending'""",
            (user["id"], _iso(_now()), row["id"]),
        ).rowcount
        if changed != 1:
            raise HTTPException(409, "连接请求状态已变化，请刷新后重试")
        connection.commit()
        return {"status": "approved", "name": row["name"]}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@router.post("/api/agent/connect/poll")
def poll(req: ConnectPollReq, request: Request):
    db, _, _ = _configured()
    device_code = req.device_code.strip()
    connection = db()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM agent_connect_requests WHERE device_code_hash=?", (_hash(device_code),)
        ).fetchone()
        if not row:
            _rate_limit("poll_unknown", request)
            raise HTTPException(404, "连接请求不存在")
        if _expired(row):
            raise HTTPException(410, "连接请求已过期")
        if row["status"] == "consumed":
            raise HTTPException(409, "连接凭证已被取走")
        if row["status"] != "approved":
            last_polled = _parse_time(row["last_polled_at"])
            now_dt = _now()
            if last_polled and (now_dt - last_polled).total_seconds() < POLL_INTERVAL_SECONDS:
                connection.commit()
                return {"status": "pending", "interval": POLL_INTERVAL_SECONDS}
            connection.execute("UPDATE agent_connect_requests SET last_polled_at=? WHERE id=?", (_iso(now_dt), row["id"]))
            connection.commit()
            return {"status": "pending", "interval": POLL_INTERVAL_SECONDS}
        token = f"ai325_agent_{secrets.token_urlsafe(32)}"
        now = _iso(_now())
        cursor = connection.execute(
            """INSERT INTO agent_tokens(
               user_id,username,name,display_name,bio,capabilities_json,
               token_hash,token_prefix,created_at,revoked)
               SELECT u.id,u.username,?,?,'','[]',?,?,?,0
               FROM users u WHERE u.id=? AND u.active=1""",
            (row["name"], row["name"], _hash(token), f"ai325_agent_****{token[-4:]}", now, row["approved_by_user_id"]),
        )
        if cursor.rowcount != 1:
            raise HTTPException(403, "批准用户不可用，请重新发起连接")
        changed = connection.execute(
            """UPDATE agent_connect_requests SET status='consumed',consumed_at=?
               WHERE id=? AND status='approved'""",
            (now, row["id"]),
        ).rowcount
        if changed != 1:
            raise HTTPException(409, "连接凭证已被取走")
        connection.commit()
        return {"status": "approved", "token": token, "name": row["name"]}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
