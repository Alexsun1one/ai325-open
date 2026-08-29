# -*- coding: utf-8 -*-
"""实时内容治理引擎。

写入端先把已创建的对象登记到 ``moderation_queue``，daemon 再做规则层和
DeepSeek 层审核。模块只依赖 Python 标准库，可在 API 进程和单独脚本中共用。
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DECISIONS = {"accepted", "pending", "rejected"}
QUEUE_STATES = {"queued", "processing", *DECISIONS}
URL_RE = re.compile(r"(?i)(?:https?://|www\.)\S+")
SECRET_PATTERNS = (
    (re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{4,}"), "内容中疑似包含 API 密钥，请删除后重试"),
    (re.compile(r"(?<![A-Z0-9])AKIA[A-Z0-9]{12,20}(?![A-Z0-9])"), "内容中疑似包含云端访问密钥，请删除后重试"),
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "内容中疑似包含手机号，请确认隐私后再发布"),
    (re.compile(r"(?<!\d)\d{6}(?:18|19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"),
     "内容中疑似包含身份证号，请删除后重试"),
)
DEFAULT_BANNED_WORDS = ("操你妈", "草你妈", "傻逼", "死全家", "去死吧")

_WORKERS: dict[str, threading.Thread] = {}
_WORKERS_LOCK = threading.Lock()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _connect(db_path: str | os.PathLike[str]) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone() is not None


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if not _table_exists(conn, table):
        return
    columns = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
    if column not in columns:
        conn.execute(f'ALTER TABLE "{table}" ADD COLUMN {ddl}')


def ensure_gatekeeper_schema(db_path: str | os.PathLike[str]) -> None:
    """幂等创建审核表，并为已有业务表补齐状态列。"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = _connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS moderation_queue(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              processed_at TEXT,
              actor_user TEXT NOT NULL,
              actor_agent TEXT,
              action TEXT NOT NULL,
              target_type TEXT NOT NULL,
              target_id TEXT NOT NULL,
              content TEXT NOT NULL DEFAULT '',
              anchor TEXT,
              thread_id TEXT,
              metadata TEXT NOT NULL DEFAULT '{}',
              status TEXT NOT NULL DEFAULT 'queued',
              decision TEXT,
              reason TEXT,
              moderation TEXT,
              attempts INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_moderation_queue_state
              ON moderation_queue(status, id);
            CREATE INDEX IF NOT EXISTS idx_moderation_queue_actor_time
              ON moderation_queue(actor_user, created_at);
            CREATE INDEX IF NOT EXISTS idx_moderation_queue_anchor_time
              ON moderation_queue(actor_user, anchor, created_at);

            CREATE TABLE IF NOT EXISTS audit(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts TEXT NOT NULL,
              actor_user TEXT,
              actor_agent TEXT,
              action TEXT NOT NULL,
              target TEXT NOT NULL,
              decision TEXT,
              reason TEXT,
              queue_id INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit(ts DESC, id DESC);
            CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit(actor_user, actor_agent, ts DESC);
            """
        )
        # 历史内容视为已发布；新写入由 main 显式指定 pending。
        _ensure_column(conn, "comments", "status", "status TEXT NOT NULL DEFAULT 'accepted'")
        _ensure_column(conn, "comments", "moderation", "moderation TEXT")
        _ensure_column(conn, "submissions", "status", "status TEXT NOT NULL DEFAULT 'accepted'")
        _ensure_column(conn, "submissions", "moderation", "moderation TEXT")
        _ensure_column(conn, "submission_votes", "status", "status TEXT NOT NULL DEFAULT 'accepted'")
        _ensure_column(conn, "submission_votes", "moderation", "moderation TEXT")
        _ensure_column(conn, "annotations", "status", "status TEXT NOT NULL DEFAULT 'accepted'")
        _ensure_column(conn, "annotations", "moderation", "moderation TEXT")
        _ensure_column(conn, "arsenal_items", "moderation", "moderation TEXT")
        _ensure_column(conn, "audit", "queue_id", "queue_id INTEGER")
        conn.commit()
    finally:
        conn.close()


def enqueue_action(
    db_path: str | os.PathLike[str],
    *,
    actor_user: Any,
    actor_agent: Any,
    action: str,
    target_type: str,
    target_id: Any,
    content: str = "",
    anchor: str | None = None,
    thread_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    """登记待审动作并写入不含原文的 audit 记录，返回队列 ID。"""
    ensure_gatekeeper_schema(db_path)
    created_at = _now()
    actor = "" if actor_user is None else str(actor_user).strip()
    agent = None if actor_agent is None else str(actor_agent).strip() or None
    action = str(action).strip()
    target_type = str(target_type).strip().lower()
    target = str(target_id).strip()
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """INSERT INTO moderation_queue(
                 created_at,updated_at,actor_user,actor_agent,action,target_type,target_id,
                 content,anchor,thread_id,metadata,status
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,'queued')""",
            (
                created_at, created_at, actor, agent, action, target_type, target,
                str(content or ""), anchor, thread_id, _json(metadata or {}),
            ),
        )
        queue_id = int(cursor.lastrowid)
        conn.execute(
            """INSERT INTO audit(ts,actor_user,actor_agent,action,target,decision,reason,queue_id)
               VALUES(?,?,?,?,?,'queued',?,?)""",
            (created_at, actor, agent, action, f"{target_type}:{target}", "已进入实时治理队列", queue_id),
        )
        conn.commit()
        return queue_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    result["metadata"] = _loads(result.get("metadata"), {})
    result["moderation"] = _loads(result.get("moderation"), None)
    # 管理队列不回显可能包含密钥的原文，只给预览。
    content = result.pop("content", "") or ""
    result["content_preview"] = content[:240]
    return result


def list_pending(db_path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """返回等待人工处理的项，也包括还未被 worker 取走的新项。"""
    ensure_gatekeeper_schema(db_path)
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """SELECT * FROM moderation_queue
               WHERE status IN ('queued','processing','pending')
               ORDER BY CASE status WHEN 'pending' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END,
                        id"""
        ).fetchall()
        return [_row_dict(row) for row in rows]
    finally:
        conn.close()


def _resolve_user(conn: sqlite3.Connection, actor_user: str) -> sqlite3.Row | None:
    if not actor_user or not _table_exists(conn, "users"):
        return None
    row = conn.execute(
        "SELECT id,username,role FROM users WHERE username=?", (actor_user,)
    ).fetchone()
    if row is None and actor_user.isdigit():
        row = conn.execute(
            "SELECT id,username,role FROM users WHERE id=?", (int(actor_user),)
        ).fetchone()
    return row


def _identity_error(conn: sqlite3.Connection, row: sqlite3.Row, metadata: dict[str, Any]) -> str | None:
    user = _resolve_user(conn, row["actor_user"])
    if user is None:
        return "未找到有效成员身份，请重新登录后再试"
    auth_kind = str(metadata.get("auth_kind") or "").lower()
    agent = row["actor_agent"]
    if auth_kind == "agent" and not agent:
        return "Agent 身份不完整，请重新配置 Agent token"
    if agent:
        if not _table_exists(conn, "agent_tokens"):
            return "Agent token 无法验证，请重新授权"
        valid = conn.execute(
            """SELECT 1 FROM agent_tokens
               WHERE name=? AND user_id=? AND username=? AND revoked=0""",
            (agent, user["id"], user["username"]),
        ).fetchone()
        if valid is None:
            return "Agent token 已失效或与成员不匹配，请重新授权"
    return None


def _banned_words() -> tuple[str, ...]:
    configured = tuple(
        word.strip() for word in os.environ.get("GATEKEEPER_BANNED_WORDS", "").split(",")
        if word.strip()
    )
    return configured or DEFAULT_BANNED_WORDS


def _rule_decision(conn: sqlite3.Connection, row: sqlite3.Row) -> tuple[str, str, dict[str, Any]]:
    content = row["content"] or ""
    metadata = _loads(row["metadata"], {})
    checks: dict[str, Any] = {"identity": "ok", "content": "ok", "rate": "ok"}

    identity_error = _identity_error(conn, row, metadata)
    if identity_error:
        checks["identity"] = "failed"
        return "rejected", identity_error, checks

    for pattern, reason in SECRET_PATTERNS:
        if pattern.search(content):
            checks["content"] = "sensitive_pattern"
            return "rejected", reason, checks

    lowered = content.casefold()
    if any(word.casefold() in lowered for word in _banned_words()):
        checks["content"] = "banned_word"
        return "rejected", "内容包含不适合公开发布的攻击性表达，请修改后重试", checks

    action = (row["action"] or "").lower()
    if "comment" in action:
        minimum, maximum = 1, 500
    elif "submission" in action and "vote" not in action:
        minimum, maximum = 1, 4161
    elif "vote" in action:
        minimum, maximum = 0, 0
    elif "annotation" in action:
        minimum, maximum = 1, 1000
    elif "arsenal" in action:
        minimum, maximum = 1, 50000
    else:
        minimum, maximum = 0, 4000
    length = len(content)
    if length < minimum or length > maximum:
        checks["content"] = "invalid_length"
        return "rejected", f"内容长度需在 {minimum}–{maximum} 字之间，请调整后重试", checks
    link_count = len(URL_RE.findall(content))
    if link_count > 2:
        checks["content"] = "too_many_links"
        return "rejected", "一次最多发布 2 个链接，请精简后重试", checks

    created = dt.datetime.fromisoformat(row["created_at"])
    ten_seconds_ago = (created - dt.timedelta(seconds=10)).isoformat(timespec="microseconds")
    recent = conn.execute(
        """SELECT 1 FROM moderation_queue
           WHERE actor_user=? AND id<? AND created_at>? LIMIT 1""",
        (row["actor_user"], row["id"], ten_seconds_ago),
    ).fetchone()
    if recent is not None:
        checks["rate"] = "ten_seconds"
        return "rejected", "操作太快，同一成员每 10 秒最多发布 1 条，请稍后再试", checks

    if row["anchor"]:
        minute_ago = (created - dt.timedelta(minutes=1)).isoformat(timespec="microseconds")
        anchor_count = conn.execute(
            """SELECT COUNT(*) FROM moderation_queue
               WHERE actor_user=? AND anchor=? AND id<? AND created_at>?""",
            (row["actor_user"], row["anchor"], row["id"], minute_ago),
        ).fetchone()[0]
        if anchor_count >= 3:
            checks["rate"] = "anchor_per_minute"
            return "rejected", "同一段落每分钟最多发布 3 条，请稍后再试", checks

    checks["links"] = link_count
    checks["length"] = length
    return "accepted", "规则层检查通过", checks


def _ledger_paths(db_path: str | os.PathLike[str]) -> list[Path]:
    roots: list[Path] = []
    for value in (
        os.environ.get("GATEKEEPER_LEDGER_DIR"),
        os.environ.get("XF_GOVERNED_LEDGER_DIR"),
    ):
        if value:
            roots.append(Path(value))
    database_parent = Path(db_path).resolve().parent
    roots.extend(
        (
            database_parent / "governed" / "ledgers",
            database_parent / "governed",
            Path.cwd() / "site" / "content" / "ledgers",
        )
    )
    seen: set[Path] = set()
    paths: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json")):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                paths.append(path)
    return paths


def _reference_context(
    conn: sqlite3.Connection,
    db_path: str | os.PathLike[str],
    anchor: str | None,
    thread_id: str | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"anchor": anchor, "thread_id": thread_id}
    if anchor and anchor.startswith("event:") and _table_exists(conn, "events"):
        slug = anchor.split(":", 1)[1]
        result["anchor_exists"] = conn.execute(
            "SELECT 1 FROM events WHERE slug=?", (slug,)
        ).fetchone() is not None
    elif anchor and anchor.startswith("submission:") and _table_exists(conn, "submissions"):
        target = anchor.split(":", 1)[1]
        result["anchor_exists"] = target.isdigit() and conn.execute(
            "SELECT 1 FROM submissions WHERE id=?", (int(target),)
        ).fetchone() is not None

    terms = [term for term in (anchor, thread_id) if term]
    for path in _ledger_paths(db_path):
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for term in terms:
            if term in raw:
                result[f"{('anchor' if term == anchor else 'thread')}_exists"] = True
                index = raw.find(term)
                result["ledger_excerpt"] = raw[max(0, index - 300):index + 900]
        # 稳定段落锚点是前端由日报日期和结构位置生成，不会原样出现在 JSON。
        if anchor:
            match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})#[A-Za-z0-9_-]+", anchor)
            if match and f'"date": "{match.group(1)}"' in raw:
                result["anchor_exists"] = True
                result.setdefault("ledger_excerpt", raw[:1200])
    if anchor and "anchor_exists" not in result:
        result["anchor_exists"] = False
    if thread_id and "thread_exists" not in result:
        result["thread_exists"] = False
    return result


def _extract_llm_json(text: str) -> dict[str, Any]:
    value = text.strip()
    if value.startswith("```"):
        value = re.sub(r"^```(?:json)?\s*|\s*```$", "", value, flags=re.I)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", value)
        if not match:
            raise ValueError("LLM 未返回 JSON")
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise ValueError("LLM 返回不是对象")
    return parsed


def _llm_decision(
    conn: sqlite3.Connection,
    db_path: str | os.PathLike[str],
    row: sqlite3.Row,
) -> tuple[str, str, str, dict[str, Any]]:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return "accepted", "规则层通过；LLM 审核未配置，已跳过", "skipped", {}

    reference = _reference_context(conn, db_path, row["anchor"], row["thread_id"])
    prompt = {
        "action": row["action"],
        "content": row["content"],
        "reference_check": reference,
    }
    body = _json(
        {
            "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是『人民需要AI』社区的守门员。检查内容是否对题、是否辱骂他人、"
                        "是否泄露隐私，以及对日报段落/跨期线索的引用是否与 reference_check 一致。"
                        "只返回 JSON：{\"decision\":\"accepted|pending|rejected\",\"reason\":\"一句人话\"}。"
                        "证据不足或无法确认引用时用 pending，明确恶意、辱骂或隐私泄露用 rejected。"
                    ),
                },
                {"role": "user", "content": _json(prompt)},
            ],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions"),
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=float(os.environ.get("GATEKEEPER_LLM_TIMEOUT", "15"))
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        answer = payload["choices"][0]["message"]["content"]
        parsed = _extract_llm_json(answer)
        decision = str(parsed.get("decision") or "").lower()
        reason = str(parsed.get("reason") or "").strip()
        if decision not in DECISIONS or not reason:
            raise ValueError("LLM 决策字段无效")
        return decision, reason[:500], "completed", reference
    except (OSError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        # 不在审核数据中写入 key、返回原文或完整网络异常。
        return "pending", "LLM 审核暂时不可用，已转人工复核", "failed", {
            "error_type": type(exc).__name__, **reference,
        }


def _vote_identity(
    conn: sqlite3.Connection, row: sqlite3.Row, metadata: dict[str, Any]
) -> tuple[int, int] | None:
    try:
        submission_id = int(metadata.get("submission_id") or row["target_id"])
    except (TypeError, ValueError):
        return None
    user_id = metadata.get("user_id")
    if user_id is None:
        user = _resolve_user(conn, row["actor_user"])
        user_id = user["id"] if user else None
    try:
        return submission_id, int(user_id)
    except (TypeError, ValueError):
        return None


def _apply_target_decision(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    decision: str,
    moderation: str,
) -> bool:
    target_type = (row["target_type"] or "").lower()
    if target_type in {"comment", "comments"} and _table_exists(conn, "comments"):
        cursor = conn.execute(
            "UPDATE comments SET status=?,moderation=? WHERE id=?",
            (decision, moderation, row["target_id"]),
        )
        return cursor.rowcount == 1
    if target_type in {"submission", "submissions"} and _table_exists(conn, "submissions"):
        cursor = conn.execute(
            "UPDATE submissions SET status=?,moderation=? WHERE id=?",
            (decision, moderation, row["target_id"]),
        )
        return cursor.rowcount == 1
    if target_type in {"annotation", "annotations"} and _table_exists(conn, "annotations"):
        cursor = conn.execute(
            "UPDATE annotations SET status=?,moderation=? WHERE id=?",
            (decision, moderation, row["target_id"]),
        )
        return cursor.rowcount == 1
    if target_type in {"arsenal", "arsenal_item", "arsenal_items"} and _table_exists(conn, "arsenal_items"):
        # 自动审核通过后仍需管理员上架；只有拒绝会直接关闭条目。
        cursor = conn.execute(
            """UPDATE arsenal_items
               SET status=CASE WHEN ?='rejected' THEN 'rejected'
                               WHEN status='rejected' THEN 'pending' ELSE status END,
                   moderation=?,updated_at=? WHERE id=?""",
            (decision, moderation, _now(), row["target_id"]),
        )
        return cursor.rowcount == 1
    if target_type in {"vote", "submission_vote", "submission_votes"}:
        if not (_table_exists(conn, "submission_votes") and _table_exists(conn, "submissions")):
            return False
        identity = _vote_identity(conn, row, _loads(row["metadata"], {}))
        if identity is None:
            return False
        submission_id, user_id = identity
        previous = conn.execute(
            "SELECT status FROM submission_votes WHERE submission_id=? AND user_id=?",
            (submission_id, user_id),
        ).fetchone()
        if previous is None:
            return False
        old_status = previous["status"]
        conn.execute(
            """UPDATE submission_votes SET status=?,moderation=?
               WHERE submission_id=? AND user_id=?""",
            (decision, moderation, submission_id, user_id),
        )
        if old_status != "accepted" and decision == "accepted":
            conn.execute(
                "UPDATE submissions SET votes=votes+1 WHERE id=?", (submission_id,)
            )
        elif old_status == "accepted" and decision != "accepted":
            conn.execute(
                "UPDATE submissions SET votes=MAX(votes-1,0) WHERE id=?", (submission_id,)
            )
        return True
    # Agent 动作可以只需 audit，不一定有业务表行需回写。
    if target_type in {"agent", "agent_action", "audit"}:
        return True
    return False


def _finalize(
    db_path: str | os.PathLike[str],
    queue_id: int,
    decision: str,
    reason: str,
    moderation_data: dict[str, Any],
    *,
    expected_state: str | None,
    audit_action: str,
    audit_actor: str | None = None,
) -> dict[str, Any]:
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM moderation_queue WHERE id=?", (queue_id,)
        ).fetchone()
        if row is None:
            raise KeyError(queue_id)
        if expected_state is not None and row["status"] != expected_state:
            conn.rollback()
            return _row_dict(row)
        timestamp = _now()
        moderation_data = {
            **moderation_data,
            "decision": decision,
            "reason": reason,
            "decided_at": timestamp,
        }
        moderation = _json(moderation_data)
        if not _apply_target_decision(conn, row, decision, moderation):
            decision = "pending"
            reason = "未找到对应的业务记录，需要人工复核"
            moderation_data.update({"decision": decision, "reason": reason})
            moderation = _json(moderation_data)
        conn.execute(
            """UPDATE moderation_queue
               SET status=?,decision=?,reason=?,moderation=?,updated_at=?,processed_at=?
               WHERE id=?""",
            (decision, decision, reason, moderation, timestamp, timestamp, queue_id),
        )
        conn.execute(
            """INSERT INTO audit(ts,actor_user,actor_agent,action,target,decision,reason,queue_id)
               VALUES(?,?,?,?,?,?,?,?)""",
            (
                timestamp,
                audit_actor if audit_actor is not None else row["actor_user"],
                None if audit_actor is not None else row["actor_agent"],
                audit_action,
                f'{row["target_type"]}:{row["target_id"]}',
                decision,
                reason,
                queue_id,
            ),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM moderation_queue WHERE id=?", (queue_id,)
        ).fetchone()
        return _row_dict(updated)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _claim_next(db_path: str | os.PathLike[str]) -> sqlite3.Row | None:
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        stale_before = (
            dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)
        ).isoformat(timespec="microseconds")
        conn.execute(
            """UPDATE moderation_queue SET status='queued',updated_at=?
               WHERE status='processing' AND updated_at<?""",
            (_now(), stale_before),
        )
        row = conn.execute(
            "SELECT * FROM moderation_queue WHERE status='queued' ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            conn.commit()
            return None
        conn.execute(
            """UPDATE moderation_queue
               SET status='processing',updated_at=?,attempts=attempts+1 WHERE id=?""",
            (_now(), row["id"]),
        )
        conn.commit()
        return conn.execute(
            "SELECT * FROM moderation_queue WHERE id=?", (row["id"],)
        ).fetchone()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def process_pending(
    db_path: str | os.PathLike[str], limit: int = 100
) -> list[dict[str, Any]]:
    """同步 drain 最多 ``limit`` 个 queued 动作；可用于测试和单次任务。"""
    ensure_gatekeeper_schema(db_path)
    results: list[dict[str, Any]] = []
    for _ in range(max(0, int(limit))):
        row = _claim_next(db_path)
        if row is None:
            break
        rule_decision = "pending"
        conn = _connect(db_path)
        try:
            rule_decision, rule_reason, checks = _rule_decision(conn, row)
            if rule_decision == "rejected":
                decision, reason, llm_state, reference = (
                    "rejected", rule_reason, "not_run", {},
                )
            else:
                decision, reason, llm_state, reference = _llm_decision(conn, db_path, row)
        except Exception as exc:  # 单条损坏不得阻断队列中的其他动作。
            decision = "pending"
            reason = "自动审核暂时失败，已转人工复核"
            llm_state = "not_run"
            checks = {"engine": "failed", "error_type": type(exc).__name__}
            reference = {}
        finally:
            conn.close()
        results.append(
            _finalize(
                db_path,
                row["id"],
                decision,
                reason,
                {
                    "source": "gatekeeper",
                    "rules": {"decision": rule_decision if 'rule_decision' in locals() else "pending", "checks": checks},
                    "llm": llm_state,
                    "reference": reference,
                },
                expected_state="processing",
                audit_action=f'{row["action"]}.moderated',
            )
        )
    return results


def decide(
    db_path: str | os.PathLike[str],
    queue_id: int,
    decision: str,
    reason: str,
    actor_user: Any,
) -> dict[str, Any]:
    """管理员人工改判；对已通过投票的改判会回退票数。"""
    ensure_gatekeeper_schema(db_path)
    normalized = str(decision).strip().lower()
    if normalized not in DECISIONS:
        raise ValueError("决策必须是 accepted、pending 或 rejected")
    human_reason = str(reason).strip()
    if not human_reason:
        raise ValueError("人工改判必须说明理由")
    return _finalize(
        db_path,
        int(queue_id),
        normalized,
        human_reason[:500],
        {"source": "admin", "rules": {"decision": "overridden"}, "llm": "overridden"},
        expected_state=None,
        audit_action="moderation.decide",
        audit_actor=str(actor_user),
    )


def _worker_loop(db_path: str) -> None:
    interval = max(0.1, float(os.environ.get("GATEKEEPER_POLL_SECONDS", "0.5")))
    while True:
        try:
            processed = process_pending(db_path, limit=25)
        except Exception:
            processed = []
        # Event.wait 不持有 SQLite 连接，也便于日后加停止信号。
        threading.Event().wait(0 if len(processed) == 25 else interval)


def start_gatekeeper_worker(db_path: str | os.PathLike[str]) -> threading.Thread:
    """每个数据库路径只启动一个 daemon worker，反复调用安全。"""
    ensure_gatekeeper_schema(db_path)
    resolved = str(Path(db_path).resolve())
    with _WORKERS_LOCK:
        existing = _WORKERS.get(resolved)
        if existing is not None and existing.is_alive():
            return existing
        worker = threading.Thread(
            target=_worker_loop,
            args=(resolved,),
            name=f"gatekeeper-{Path(resolved).stem}",
            daemon=True,
        )
        _WORKERS[resolved] = worker
        worker.start()
        return worker


__all__ = [
    "ensure_gatekeeper_schema",
    "start_gatekeeper_worker",
    "enqueue_action",
    "list_pending",
    "decide",
    "process_pending",
]
