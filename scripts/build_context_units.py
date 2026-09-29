#!/usr/bin/env python3
"""Build context-unit slices with governed cleaning and Hermes title distillation.

The optional title pass reuses the same DeepSeek channel as Hermes Ledger.  If
that channel is unavailable or the response fails validation, the title falls
back to a deterministic first-long-message/neutral label.  Storage writes stay
inside one ``BEGIN IMMEDIATE`` transaction so a rerun is auditable and
idempotent.
"""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import hashlib
import html
import json
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path


CST = timezone(timedelta(hours=8))
RAW_ACCOUNT_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:"
    r"wxid_[A-Za-z0-9_-]+|QQ\d{5,}|q\d{6,}|gh_[A-Za-z0-9_-]+|"
    r"[A-Za-z][A-Za-z0-9_.-]{5,}\d{3,}"
    r")(?![A-Za-z0-9_.-])",
    re.IGNORECASE,
)
MACHINE_ID_RE = RAW_ACCOUNT_RE
TAG_RE = re.compile(r"<[^>]+>")
BLOCK_TAG_RE = re.compile(r"<\s*(?:br\s*/?|/p\s*|/div\s*|/li\s*|/datadesc\s*|/dataitem\s*)>", re.I)
WECHAT_URL_RE = re.compile(r"https?://\S+", re.I)
WECHAT_PLACEHOLDER_RE = re.compile(
    r"\[(?:图片|表情|动画表情|视频|语音|链接|文件|小程序|音乐|位置|转账|红包|名片|引用|聊天记录|接龙|拍一拍[^\]]*|表情包[^\]]*)\]\s*"
)
WECHAT_B64_RE = re.compile(r"\beyJ[A-Za-z0-9+/=_]{20,}\b")
WECHAT_PIPE_TOKEN_RE = re.compile(r"\S{10,}\|\S{2,}")
WECHAT_LONG_TOKEN_RE = re.compile(r"(?=.*\d)(?=.*[a-z])[A-Za-z0-9+/=_|.-]{40,}", re.I)
WECHAT_HASH_TAIL_RE = re.compile(r"\s+[a-z0-9]{16,}\s*$", re.I)
WECHAT_DATE_RE = re.compile(r"\s+\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}(?::\d{2})?)?")
WECHAT_VIEW_COUNT_RE = re.compile(r"\s*view\s+\d+(?:\s+[\d-]+)*", re.I)
WECHAT_CHATROOM_TAIL_RE = re.compile(r"\s+\d{9,11}\s+[^\s]+\s+\S+@chatroom\s*$", re.I)
WECHAT_CHATROOM_INLINE_RE = re.compile(
    r"\b\d{8,}@chatroom(?:\s+群友)?(?:\s+[A-Za-z][A-Za-z0-9_.-]{2,24})?",
    re.I,
)
WECHAT_LONG_ID_RE = re.compile(r"(?<![\w-])\d{13,}(?![\w-])")
WECHAT_OPENIM_RE = re.compile(r"\d+@openim[:：]?\s*|@所有人")
WECHAT_OPENIM_TOKEN_RE = re.compile(r"(?<![\w])@openim\b", re.I)
WECHAT_FLAG_COUNT_RE = re.compile(r"\b(?:true|false)\s+(?:-?\d+\s+){1,}-?\d+\b", re.I)
WECHAT_TRUNCATED_TOKEN_RE = re.compile(r"(?<![\w])eyJ[A-Za-z0-9+/=_-]{2,}…", re.I)
WECHAT_UNSUPPORTED_RE = re.compile(r"当前(?:微信)?版本不支持展示该内容，请升级至最新版本。?")
WECHAT_COUNT_CLUSTER_RE = re.compile(
    r"(?<![\w-])(?:\d{1,24}\s+){2,}\d{1,24}(?:\s+[a-z][a-z0-9_-]{2,24})?(?![\w-])",
    re.I,
)
WECHAT_SHORT_COUNT_CLUSTER_RE = re.compile(
    r"(?<![\w-])(?:\d{1,6}\s+){1,}\d{1,6}(?=\s+(?:群友|[A-Za-z][A-Za-z0-9_.-]{2,24})?\b|$)",
    re.I,
)
WECHAT_NOISE_LINE_RE = re.compile(
    r"^\s*\d+(?:[\s\d]*\d)?(?:\s+[^\s。！？!?，,；;]{1,12})?\s*$",
    re.I,
)
WECHAT_TRAIL_NOISE_RE = re.compile(
    r"(?:\s+(?:\d{1,24}|[a-z][a-z0-9_-]{2,24})){2,}\s*$",
    re.I,
)
WECHAT_LEAD_COUNT_RE = re.compile(
    r"^\s*\d+(?:[\s\d]*\d)?(?:\s+[^\s。！？!?，,；;]{1,12})?\s+",
    re.I,
)
WECHAT_PHONE_RE = re.compile(r"1[3-9]\d{9}")
BRACKET_TOKEN_RE = re.compile(r"\[[^\]\n]{1,32}\]")
MEANINGFUL_CHAR_RE = re.compile(r"[\u3400-\u9fffA-Za-z0-9]")

CLEANER_VERSION = "context-units-v3"
MIN_MESSAGES = 3
MIN_CHARS = 50
MAX_CHUNK_MESSAGES = 80
TOPIC_GAP_SECONDS = 18 * 60
HARD_GAP_SECONDS = 35 * 60

DEFAULT_TITLE_MODEL = "deepseek-chat"
DEFAULT_TITLE_TIMEOUT = 30.0
DEFAULT_TITLE_RETRIES = 2
TITLE_MIN_CHARS = 6
TITLE_MAX_CHARS = 16
TITLE_LENGTH_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[\u3400-\u9fff]")
TITLE_BAD_FRAGMENTS = ("的时", "在这", "辈子")
TITLE_FRAGMENT_PUNCT_RE = re.compile(r"[\[\]{}<>「」『』、，,。！？!?；;：:|/\\·…]")

TITLE_STOPWORDS = {
    "这个", "那个", "这些", "那些", "我们", "你们", "他们", "大家", "自己", "现在", "今天", "明天",
    "昨天", "时候", "地方", "东西", "问题", "一下", "什么", "怎么", "就是", "还是", "因为", "所以",
    "如果", "已经", "比较", "真的", "可能", "需要", "应该", "没有", "不是", "还有", "可以", "然后",
    "感觉", "看到", "觉得", "知道", "一个", "一些", "一下", "哈哈", "哈哈哈", "好的", "啊", "哦", "嗯",
    "the", "and", "that", "this", "with", "from", "have", "just", "you", "are", "for", "not",
}


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ingest_batches(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_key TEXT UNIQUE NOT NULL,
  source_date TEXT NOT NULL,
  source_path TEXT,
  source_sha256 TEXT,
  status TEXT NOT NULL DEFAULT 'ready',
  message_count INT NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ingest_batches_date
  ON ingest_batches(source_date, created_at DESC);
CREATE TABLE IF NOT EXISTS context_units(
  id TEXT NOT NULL,
  version INT NOT NULL DEFAULT 1,
  source_date TEXT NOT NULL,
  title TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  start_at TEXT,
  end_at TEXT,
  participants_json TEXT NOT NULL DEFAULT '[]',
  message_count INT NOT NULL DEFAULT 0,
  has_gap INT NOT NULL DEFAULT 0,
  visibility TEXT NOT NULL DEFAULT 'public',
  status TEXT NOT NULL DEFAULT 'draft',
  source_hash TEXT NOT NULL DEFAULT '',
  source_batch TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(id, version)
);
CREATE INDEX IF NOT EXISTS idx_context_units_date_status
  ON context_units(source_date, status, visibility, version DESC);
CREATE INDEX IF NOT EXISTS idx_context_units_current
  ON context_units(id, version DESC);
CREATE TABLE IF NOT EXISTS context_unit_messages(
  unit_id TEXT NOT NULL,
  unit_version INT NOT NULL,
  message_id INT NOT NULL,
  ordinal INT NOT NULL,
  source_session TEXT,
  source_local_id INT,
  PRIMARY KEY(unit_id, unit_version, ordinal),
  UNIQUE(unit_id, unit_version, message_id)
);
CREATE INDEX IF NOT EXISTS idx_context_unit_messages_message
  ON context_unit_messages(message_id);
CREATE INDEX IF NOT EXISTS idx_context_unit_messages_unit
  ON context_unit_messages(unit_id, unit_version, ordinal);
CREATE TABLE IF NOT EXISTS context_public_projection(
  unit_id TEXT NOT NULL,
  version INT NOT NULL,
  visibility TEXT NOT NULL,
  public_text TEXT NOT NULL DEFAULT '[]',
  public_participants_json TEXT NOT NULL DEFAULT '[]',
  redaction_json TEXT NOT NULL DEFAULT '{}',
  member_text TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  PRIMARY KEY(unit_id, version, visibility)
);
CREATE INDEX IF NOT EXISTS idx_context_projection_visibility
  ON context_public_projection(visibility, unit_id, version);
CREATE TABLE IF NOT EXISTS evidence_refs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  unit_id TEXT NOT NULL,
  unit_version INT NOT NULL,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  source_date TEXT NOT NULL,
  message_ids_json TEXT NOT NULL DEFAULT '[]',
  ordinal_start INT,
  ordinal_end INT,
  quote_hash TEXT,
  source_batch TEXT,
  url TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(unit_id, unit_version, source_type, source_id)
);
CREATE INDEX IF NOT EXISTS idx_evidence_refs_unit
  ON evidence_refs(unit_id, unit_version, source_date);
CREATE INDEX IF NOT EXISTS idx_evidence_refs_source
  ON evidence_refs(source_type, source_id);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
    try:
        conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS context_unit_fts USING fts5(
                 unit_id UNINDEXED, version UNINDEXED, visibility UNINDEXED,
                 status UNINDEXED, date UNINDEXED, title, summary, public_text,
                 tokenize='trigram')"""
        )
    except sqlite3.OperationalError:
        # A minimal SQLite build may not ship trigram.  The API has a LIKE
        # fallback, while a normal production build uses the trigram index.
        conn.execute(
            """CREATE VIRTUAL TABLE IF NOT EXISTS context_unit_fts USING fts5(
                 unit_id UNINDEXED, version UNINDEXED, visibility UNINDEXED,
                 status UNINDEXED, date UNINDEXED, title, summary, public_text)"""
        )


def _plain_text(value: object) -> str:
    """Unwrap the lightweight HTML/XML envelopes left by WeChat imports."""
    text = str(value or "")
    for _ in range(3):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    text = text.replace("<![CDATA[", "").replace("]]>", "")
    text = text.replace("\r", "\n")
    text = BLOCK_TAG_RE.sub("\n", text)
    text = TAG_RE.sub(" ", text)
    text = "".join(
        ch for ch in text
        if unicodedata.category(ch) not in {"Cc", "Cf"} or ch in "\n\t"
    )
    return text


def _scrub_wechat_artifacts(value: object) -> str:
    """Remove transport metadata without deleting ordinary human numbers."""
    text = str(value or "")
    text = WECHAT_URL_RE.sub(" ", text)
    text = WECHAT_PLACEHOLDER_RE.sub(" ", text)
    text = WECHAT_B64_RE.sub(" ", text)
    text = WECHAT_LONG_TOKEN_RE.sub(" ", text)
    text = WECHAT_PIPE_TOKEN_RE.sub(" ", text)
    text = WECHAT_CHATROOM_TAIL_RE.sub(" ", text)
    text = WECHAT_CHATROOM_INLINE_RE.sub(" ", text)
    text = WECHAT_LONG_ID_RE.sub(" ", text)
    text = WECHAT_OPENIM_RE.sub(" ", text)
    text = WECHAT_OPENIM_TOKEN_RE.sub(" ", text)
    text = WECHAT_FLAG_COUNT_RE.sub(" ", text)
    text = WECHAT_TRUNCATED_TOKEN_RE.sub(" ", text)
    text = WECHAT_UNSUPPORTED_RE.sub(" ", text)
    text = WECHAT_VIEW_COUNT_RE.sub(" ", text)
    kept: list[str] = []
    for raw_line in text.splitlines() or [text]:
        line = " ".join(raw_line.split())
        if not line:
            continue
        line = WECHAT_COUNT_CLUSTER_RE.sub(" ", line)
        line = WECHAT_SHORT_COUNT_CLUSTER_RE.sub(" ", line)
        line = WECHAT_LEAD_COUNT_RE.sub("", line)
        line = WECHAT_TRAIL_NOISE_RE.sub("", line)
        line = WECHAT_HASH_TAIL_RE.sub("", line)
        line = WECHAT_DATE_RE.sub("", line)
        line = WECHAT_PHONE_RE.sub("", line)
        line = " ".join(line.split())
        if not line or WECHAT_NOISE_LINE_RE.fullmatch(line):
            continue
        if not MEANINGFUL_CHAR_RE.search(BRACKET_TOKEN_RE.sub(" ", line)):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def clean_text(value: object) -> str:
    return _scrub_wechat_artifacts(_plain_text(value))


def public_text(value: object) -> str:
    return RAW_ACCOUNT_RE.sub("群友", clean_text(value))


def _is_raw_account(value: object) -> bool:
    candidate = clean_text(value)
    return bool(candidate and RAW_ACCOUNT_RE.fullmatch(candidate))


def _safe_display(value: object, raw_username: str = "") -> str | None:
    candidate = clean_text(value).strip(" -_·")
    candidate = RAW_ACCOUNT_RE.sub("群友", candidate)
    if not candidate or candidate.casefold() in {"?", "unknown", "none", "null", "未知", "未识别", "群友"}:
        return None
    if candidate.startswith("群友·") or _is_raw_account(candidate):
        return None
    if raw_username and candidate.casefold() == raw_username.casefold() and (
        _is_raw_account(raw_username)
        or bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{5,}", raw_username))
    ):
        return None
    if not MEANINGFUL_CHAR_RE.search(candidate):
        return None
    return candidate[:80]


def _json_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def _stable_called_names(value: object) -> list[str]:
    parsed = _json_value(value)
    if not isinstance(parsed, list):
        return []
    names: list[str] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        try:
            count = int(item.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        sources = item.get("sources") or []
        if isinstance(sources, str):
            sources = [sources]
        if count < 2 and not any("称呼" in str(source) or "验证" in str(source) for source in sources):
            continue
        name = _safe_display(item.get("name"))
        if name and name not in names:
            names.append(name)
    return names


def _candidate_values(value: object) -> list[object]:
    parsed = _json_value(value)
    if isinstance(parsed, list):
        values: list[object] = []
        for item in parsed:
            if isinstance(item, dict):
                values.extend(item.get(key) for key in ("name", "display", "display_name", "nickname"))
            else:
                values.append(item)
        return values
    if isinstance(parsed, dict):
        return [parsed.get(key) for key in ("name", "display", "display_name", "nickname")]
    return [parsed]


def _load_json_file(path: Path | None) -> object:
    if not path or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取身份映射 {path}: {exc}") from exc


def _identity_aliases(profiles_path: Path | None) -> tuple[dict[str, str], dict[str, str]]:
    """Return raw-account → name and alias → canonical indexes from profiles."""
    raw_map: dict[str, str] = {}
    alias_map: dict[str, str] = {}
    payload = _load_json_file(profiles_path)
    profiles = payload.get("profiles") if isinstance(payload, dict) else payload
    if not isinstance(profiles, list):
        return raw_map, alias_map
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        canonical = next(
            (_safe_display(profile.get(key)) for key in ("name", "display", "display_name", "nickname") if profile.get(key)),
            None,
        )
        if not canonical:
            continue
        values = [profile.get(key) for key in ("username", "sender", "display", "display_name", "nickname", "name")]
        aliases = profile.get("aliases") or []
        values.extend(aliases if isinstance(aliases, list) else [aliases])
        for value in values:
            key = clean_text(value).casefold()
            if not key:
                continue
            alias_map.setdefault(key, canonical)
            if _is_raw_account(value):
                raw_map.setdefault(key, canonical)
    return raw_map, alias_map


def load_identity_map(
    conn: sqlite3.Connection,
    nicknames_path: Path | None = None,
    profiles_path: Path | None = None,
) -> dict[str, str]:
    """Resolve sender IDs via members, nicknames, and stable called-name profiles."""
    mapping, aliases = _identity_aliases(profiles_path)
    nickname_payload = _load_json_file(nicknames_path)
    nicknames = (
        {clean_text(key).casefold(): value for key, value in nickname_payload.items()}
        if isinstance(nickname_payload, dict)
        else {}
    )
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "members" not in tables:
        return mapping
    columns = {row[1] for row in conn.execute("PRAGMA table_info(members)")}
    selected = ["username"]
    for column in ("display", "nickname", "called_names", "name_history"):
        selected.append(column if column in columns else f"'' AS {column}")
    for row in conn.execute(f"SELECT {','.join(selected)} FROM members"):
        username = clean_text(row["username"])
        if not username:
            continue
        candidates: list[object] = [row["display"], row["nickname"]]
        candidates.extend(_candidate_values(nicknames.get(username.casefold())))
        candidates.extend(_stable_called_names(row["called_names"]))
        candidates.extend(_candidate_values(row["name_history"]))
        candidates.extend([aliases.get(username.casefold()), mapping.get(username.casefold())])
        resolved = next((_safe_display(value, username) or aliases.get(clean_text(value).casefold()) for value in candidates if clean_text(value)), None)
        if resolved:
            mapping.setdefault(username.casefold(), resolved)
    return mapping


def display_name(row: sqlite3.Row, identity: dict[str, str] | None = None) -> str:
    sender = clean_text(row["sender"] or "")
    if identity:
        mapped = identity.get(sender.casefold())
        if mapped:
            return mapped
    for value in (row["sender_name"], sender):
        candidate = _safe_display(value, sender)
        if candidate:
            return candidate
    return "群友"


def message_at(row: sqlite3.Row) -> datetime:
    cst = clean_text(row["cst"])
    if cst:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(cst, fmt).replace(tzinfo=CST)
            except ValueError:
                pass
    epoch = int(row["create_time"] or 0)
    return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(CST)


def iso_at(value: datetime) -> str:
    return value.astimezone(CST).isoformat(timespec="seconds")


def topic_tokens(text: str) -> set[str]:
    text = public_text(text).lower()
    words = {
        word for word in re.findall(r"[a-z0-9_+#.-]{2,}", text)
        if word not in TITLE_STOPWORDS
    }
    for run in re.findall(r"[\u3400-\u9fff]{2,}", text):
        for width in (2, 3):
            words.update(
                run[index : index + width]
                for index in range(max(0, len(run) - width + 1))
                if run[index : index + width] not in TITLE_STOPWORDS
            )
    return words


def should_split(
    previous: dict,
    current: dict,
    current_tokens: set[str],
    speakers: set[str],
    size: int,
    chunk_tokens: set[str] | None = None,
) -> bool:
    gap = (current["at"] - previous["at"]).total_seconds()
    if gap > HARD_GAP_SECONDS or size >= MAX_CHUNK_MESSAGES:
        return True
    overlap = (chunk_tokens or previous["tokens"]) & current_tokens
    speaker_key = current.get("speaker_key", current["sender"])
    if gap > TOPIC_GAP_SECONDS and not overlap and speaker_key not in speakers:
        return True
    return False


def _is_effective_message(text: str) -> bool:
    if not text:
        return False
    if _is_raw_account(text):
        return False
    without_brackets = BRACKET_TOKEN_RE.sub(" ", text)
    return bool(MEANINGFUL_CHAR_RE.search(without_brackets))


def chunk_messages(
    rows: list[sqlite3.Row],
    identity: dict[str, str] | None = None,
) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    current: list[dict] = []
    speakers: set[str] = set()
    chunk_tokens: set[str] = set()
    for row in rows:
        text = clean_text(row["content"])
        if not _is_effective_message(text):
            continue
        public = public_text(text)
        if not _is_effective_message(public):
            continue
        item = {
            "id": row["id"],
            "session": row["session"],
            "local_id": row["local_id"],
            "sender": display_name(row, identity),
            "speaker_key": clean_text(row["sender"] or row["sender_name"] or "群友").casefold(),
            "text": text,
            "public": public,
            "at": message_at(row),
        }
        item["tokens"] = topic_tokens(item["text"])
        if current and should_split(current[-1], item, item["tokens"], speakers, len(current), chunk_tokens):
            chunks.append(current)
            current = []
            speakers = set()
            chunk_tokens = set()
        current.append(item)
        speakers.add(item["speaker_key"])
        chunk_tokens.update(item["tokens"])
    if current:
        chunks.append(current)
    return chunks


def _chunk_char_count(chunk: list[dict]) -> int:
    return sum(len(re.sub(r"\s+", "", item["text"])) for item in chunk)


def _chunk_is_small(chunk: list[dict]) -> bool:
    return len(chunk) < MIN_MESSAGES or _chunk_char_count(chunk) < MIN_CHARS


def merge_small_chunks(chunks: list[list[dict]]) -> list[list[dict]]:
    """Fold tiny fragments into a neighboring topic; discard only an isolated tiny day."""
    merged = [list(chunk) for chunk in chunks if chunk]
    while len(merged) > 1:
        small_index = next((index for index, chunk in enumerate(merged) if _chunk_is_small(chunk)), None)
        if small_index is None:
            break
        if small_index == 0:
            target = 1
            merged[target] = merged[small_index] + merged[target]
            del merged[small_index]
            continue
        if small_index == len(merged) - 1:
            target = small_index - 1
            merged[target] = merged[target] + merged[small_index]
            del merged[small_index]
            continue
        previous_gap = (merged[small_index][0]["at"] - merged[small_index - 1][-1]["at"]).total_seconds()
        next_gap = (merged[small_index + 1][0]["at"] - merged[small_index][-1]["at"]).total_seconds()
        if previous_gap <= next_gap:
            merged[small_index - 1] = merged[small_index - 1] + merged[small_index]
            del merged[small_index]
        else:
            merged[small_index + 1] = merged[small_index] + merged[small_index + 1]
            del merged[small_index]
    return [chunk for chunk in merged if not _chunk_is_small(chunk)]


def first_line(value: str, limit: int) -> str:
    value = " ".join(value.split())
    return value[:limit].rstrip() + ("…" if len(value) > limit else "")


def _load_hermes_env() -> None:
    """Load only the shared DeepSeek knobs from Hermes' dotenv, without logging secrets."""
    path = Path(os.environ.get("HERMES_ENV_FILE", "/data/second-brain/hermes/.env"))
    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    allowed = {"DEEPSEEK_API_KEY", "DEEPSEEK_API_URL", "DEEPSEEK_MODEL", "DEEPSEEK_SEED"}
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in allowed or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def _title_input(messages: list[dict]) -> str:
    rows: list[str] = []
    remaining = 18_000
    for ordinal, message in enumerate(messages, 1):
        text = " ".join(str(message.get("public") or "").split())
        if not text:
            continue
        row = f"{ordinal}. {message.get('sender') or '群友'}：{text}"
        if len(row) > remaining:
            rows.append("（后续消息已截断，仅用于控制提示长度）")
            break
        rows.append(row)
        remaining -= len(row)
    return "\n".join(rows)


def title_length(value: str) -> int:
    """Count readable title units: one CJK character or one ASCII word/number run."""
    return len(TITLE_LENGTH_TOKEN_RE.findall("".join(str(value or "").split())))


def _parse_title_response(raw: str) -> str:
    text = str(raw or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    payload = json.loads(text)
    if not isinstance(payload, dict) or not isinstance(payload.get("title"), str):
        raise ValueError("title JSON 字段缺失")
    return payload["title"]


def _title_is_valid(title: str, messages: list[dict]) -> bool:
    candidate = " ".join(str(title or "").replace("\n", " ").split()).strip(" \"'“”‘’")
    compact = re.sub(r"\s+", "", candidate)
    if not (TITLE_MIN_CHARS <= title_length(compact) <= TITLE_MAX_CHARS):
        return False
    if TITLE_FRAGMENT_PUNCT_RE.search(candidate) or RAW_ACCOUNT_RE.search(candidate):
        return False
    if any(fragment in compact for fragment in TITLE_BAD_FRAGMENTS):
        return False
    if not re.search(r"[\u3400-\u9fffA-Za-z]", compact):
        return False
    cjk_runs = re.findall(r"[\u3400-\u9fff]+", compact)
    if len(cjk_runs) >= 3 and all(len(run) <= 2 for run in cjk_runs):
        return False
    if re.search(r"(.)\1{2,}", compact):
        return False
    if re.match(r"^关于[\u300c\"'「]", candidate):
        return False
    summary = "".join("".join(str(message.get("public") or "").split()) for message in messages)
    if len(compact) >= 8:
        for segment in re.split(r"[。！？!?；;\n]+", summary):
            if not segment:
                continue
            ratio = SequenceMatcher(None, compact, segment[: max(len(compact) * 2, 32)]).ratio()
            if compact in segment and ratio >= 0.72:
                return False
    return True


def fallback_title(messages: list[dict]) -> str:
    """Use a plain first-long-message label; never synthesize a keyword list."""
    for message in messages:
        text = "".join(str(message.get("public") or "").split())
        if len(text) < 12:
            continue
        prefix = text[:12].rstrip("，,。！？!?；;：:")
        if prefix:
            return f"{prefix}…"
    participants = len({str(message.get("sender") or "群友") for message in messages})
    return f"某时段的讨论({participants}人 · {len(messages)}条)"


def _llm_title(
    messages: list[dict],
    *,
    model: str,
    timeout: float,
    retries: int,
) -> tuple[str | None, str]:
    _load_hermes_env()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        return None, "missing_key"
    try:
        from hermes.ledger.distill_ledger import deepseek_request
    except Exception:
        return None, "hermes_channel_unavailable"
    system = (
        "你是群聊编辑。根据整块消息提炼一个真正的话题标题，必须只输出 JSON："
        '{"title":"..."}。标题 6-16 个可读字符，写成一句自然中文短句；要概括讨论对象/动作/转折，'
        "不要摘抄第一句，不要把词频片段用顿号拼起来，不要出现元数据、账号、引号、括号或列表。"
        "可以混用必要的英文词。示例：深夜聊知识库该不该给 Agent 优化；从抖音电商聊到 AI 出海。"
    )
    history = [
        {"role": "system", "content": system},
        {"role": "user", "content": "块内消息：\n" + _title_input(messages)},
    ]
    api_url = os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
    for _attempt in range(max(1, retries)):
        raw = ""
        try:
            raw = deepseek_request(history, api_key, model, api_url, timeout, stage="原浆标题提炼")
            candidate = _parse_title_response(raw)
            normalized = " ".join(candidate.replace("\n", " ").split()).strip(" \"'“”‘’")
            if _title_is_valid(normalized, messages):
                return normalized, "llm"
            reason = "invalid_title"
            compact_length = title_length(normalized)
            if compact_length > TITLE_MAX_CHARS:
                feedback = f"上一版有{compact_length}字，请删减到不超过{TITLE_MAX_CHARS}字"
            elif compact_length < TITLE_MIN_CHARS:
                feedback = f"上一版只有{compact_length}字，请补足到{TITLE_MIN_CHARS}-{TITLE_MAX_CHARS}字"
            elif TITLE_FRAGMENT_PUNCT_RE.search(normalized):
                feedback = "上一版含标点，请全部删掉标点"
            else:
                feedback = "上一版与原句过近，请换一个概括角度"
        except Exception:
            reason = "request_failed"
            feedback = "上一版响应无效，请重新生成"
        if raw:
            history.append({"role": "assistant", "content": raw})
        history.append(
            {
                "role": "user",
                "content": (
                    f"上一版标题未通过自检，{feedback}。请换一个全新的概括角度，"
                    "不要复述块内任何单条原句，不要沿用上一版的连续名词组合；"
                    f"改成 {TITLE_MIN_CHARS}-{TITLE_MAX_CHARS} 字自然话题短句，"
                    "禁止顿号/列表/半截词/摘要式拼接/任何标点，只输出 {\"title\":\"...\"}。"
                ),
            }
        )
    return None, reason


def generate_title(
    messages: list[dict],
    *,
    model: str = DEFAULT_TITLE_MODEL,
    timeout: float = DEFAULT_TITLE_TIMEOUT,
    retries: int = DEFAULT_TITLE_RETRIES,
) -> tuple[str, str]:
    title, source = _llm_title(messages, model=model, timeout=timeout, retries=retries)
    if title:
        return title, source
    return fallback_title(messages), f"fallback:{source}"


def source_hash(messages: list[dict]) -> str:
    payload = [
        {"id": item["id"], "sender": item["sender"], "text": item["text"], "at": iso_at(item["at"])}
        for item in messages
    ]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load_ledger(path: Path, date: str) -> dict:
    candidate = path / f"{date}.json"
    if not candidate.is_file():
        return {}
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def evidence_candidates(data: dict, date: str):
    for index, item in enumerate(data.get("quotes") or [], 1):
        if not isinstance(item, dict):
            continue
        text = item.get("t") or item.get("text") or item.get("quote") or ""
        if clean_text(text):
            yield "ledger_quote", f"{date}#quote-{index}", clean_text(text), hashlib.sha256(clean_text(text).encode()).hexdigest()
    for index, item in enumerate(data.get("themes") or [], 1):
        if not isinstance(item, dict):
            continue
        text = item.get("body") or item.get("deep") or item.get("h") or item.get("title") or ""
        if clean_text(text):
            value = clean_text(text)
            yield "ledger_theme", f"{date}#theme-{index}", value, hashlib.sha256(value.encode()).hexdigest()


def find_evidence(units: list[dict], data: dict, date: str):
    for source_type, source_id, quote, quote_hash in evidence_candidates(data, date):
        if len(quote) < 8:
            continue
        needle = public_text(quote)
        for unit in units:
            matched = [m for m in unit["messages"] if needle in m["public"] or needle in m["text"]]
            if not matched:
                continue
            ordinals = [m["ordinal"] for m in matched]
            yield {
                "unit_id": unit["id"],
                "version": unit["version"],
                "source_type": source_type,
                "source_id": source_id,
                "source_date": date,
                "message_ids": [m["id"] for m in matched],
                "ordinal_start": min(ordinals),
                "ordinal_end": max(ordinals),
                "quote_hash": f"sha256:{quote_hash}",
                "url": f"/ledger/{date}/#{source_id.split('#', 1)[-1]}",
            }


def build(
    db_path: Path,
    date: str,
    governed_dir: Path,
    nicknames_path: Path | None = None,
    profiles_path: Path | None = None,
    *,
    title_model: str = DEFAULT_TITLE_MODEL,
    title_timeout: float = DEFAULT_TITLE_TIMEOUT,
    title_retries: int = DEFAULT_TITLE_RETRIES,
    force: bool = False,
    require_llm_titles: bool = False,
) -> dict:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    ensure_schema(conn)
    rows = conn.execute(
        """SELECT id,session,local_id,create_time,cst,sender,sender_name,content
           FROM messages
           WHERE substr(COALESCE(cst,''),1,10)=?
              OR (COALESCE(cst,'')='' AND date(create_time,'unixepoch','+8 hours')=?)
           ORDER BY COALESCE(create_time,0),id""",
        (date, date),
    ).fetchall()
    identity = load_identity_map(conn, nicknames_path, profiles_path)
    initial_chunks = chunk_messages(rows, identity)
    chunks = merge_small_chunks(initial_chunks)
    all_ids = [row["id"] for row in rows]
    batch_digest = hashlib.sha256(json.dumps(all_ids, separators=(",", ":")).encode()).hexdigest()
    batch_key = f"messages:{date}:{batch_digest[:16]}"
    now = datetime.now(CST).isoformat(timespec="seconds")
    ledger = load_ledger(governed_dir, date)
    units: list[dict] = []
    unit_ids = [f"cu-{date.replace('-', '')}-{index:04d}" for index in range(1, len(chunks) + 1)]
    effective_message_count = sum(len(chunk) for chunk in chunks)
    dropped_message_count = len(rows) - effective_message_count
    small_fragment_count = sum(1 for chunk in initial_chunks if _chunk_is_small(chunk))
    existing_ids = {
        row[0]
        for row in conn.execute("SELECT DISTINCT id FROM context_units WHERE source_date=?", (date,))
    }
    stale_ids = sorted(existing_ids - set(unit_ids))
    generated_titles: dict[str, str] = {}
    title_sources: dict[str, int] = {"llm": 0, "fallback": 0}
    title_failures: dict[str, int] = {}
    for unit_id, messages in zip(unit_ids, chunks):
        title, source = generate_title(
            messages,
            model=title_model,
            timeout=title_timeout,
            retries=title_retries,
        )
        generated_titles[unit_id] = title
        if source == "llm":
            title_sources["llm"] += 1
        else:
            title_sources["fallback"] += 1
            failure = source.removeprefix("fallback:")
            title_failures[failure] = title_failures.get(failure, 0) + 1

    if require_llm_titles and title_sources["fallback"]:
        conn.close()
        raise RuntimeError(
            "LLM 标题闸门未通过："
            f"fallback={title_sources['fallback']} llm={title_sources['llm']} "
            f"failures={title_failures}"
        )

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """INSERT INTO ingest_batches(batch_key,source_date,source_path,source_sha256,status,
                       message_count,metadata_json,created_at,completed_at)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(batch_key) DO UPDATE SET message_count=excluded.message_count,
                 status=excluded.status,metadata_json=excluded.metadata_json,completed_at=excluded.completed_at""",
            (
                batch_key,
                date,
                "messages",
                batch_digest,
                "ready",
                len(rows),
                json.dumps(
                    {
                        "cleaner": CLEANER_VERSION,
                        "raw_messages": len(rows),
                        "effective_messages": effective_message_count,
                        "dropped_messages": dropped_message_count,
                        "initial_small_fragments": small_fragment_count,
                        "units": len(chunks),
                        "title_sources": title_sources,
                        "title_failures": title_failures,
                        "force": force,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                now,
                now,
            ),
        )
        if force:
            for stale_id in stale_ids:
                conn.execute("DELETE FROM evidence_refs WHERE unit_id=?", (stale_id,))
                conn.execute("DELETE FROM context_unit_messages WHERE unit_id=?", (stale_id,))
                conn.execute("DELETE FROM context_public_projection WHERE unit_id=?", (stale_id,))
                try:
                    conn.execute("DELETE FROM context_unit_fts WHERE unit_id=?", (stale_id,))
                except sqlite3.Error:
                    pass
                conn.execute("DELETE FROM context_units WHERE id=?", (stale_id,))
        elif unit_ids:
            placeholders = ",".join("?" for _ in unit_ids)
            conn.execute(
                f"""UPDATE context_units SET status='superseded',updated_at=?
                    WHERE source_date=? AND status='published' AND id NOT IN ({placeholders})""",
                (now, date, *unit_ids),
            )
        else:
            conn.execute(
                "UPDATE context_units SET status='superseded',updated_at=? WHERE source_date=? AND status='published'",
                (now, date),
            )
        for index, messages in enumerate(chunks, 1):
            unit_id = unit_ids[index - 1]
            digest = source_hash(messages)
            previous = conn.execute(
                "SELECT version,source_hash FROM context_units WHERE id=? ORDER BY version DESC LIMIT 1",
                (unit_id,),
            ).fetchone()
            version = (
                previous["version"]
                if previous and previous["source_hash"] == digest and not force
                else ((previous["version"] + 1) if previous else 1)
            )
            title = generated_titles[unit_id]
            summary_messages = [
                message for message in messages
                if len(re.sub(r"\s+", "", message["public"])) >= 8
            ] or messages
            summary = first_line("；".join(m["public"] for m in summary_messages[:3]), 220) or "某时段的闲聊"
            participants = list(dict.fromkeys(m["sender"] for m in messages))
            member_projection = [
                {"ordinal": n, "message_id": m["id"], "at": iso_at(m["at"]), "sender_name": m["sender"],
                 "text": m["text"], "comment_anchor": f"atom:{unit_id}:{n}"}
                for n, m in enumerate(messages, 1)
            ]
            public_projection = [
                {"ordinal": n, "message_id": m["id"], "at": iso_at(m["at"]), "sender_name": public_text(m["sender"]),
                 "text": m["public"], "comment_anchor": f"atom:{unit_id}:{n}"}
                for n, m in enumerate(messages, 1)
            ]
            has_gap = any((messages[i]["at"] - messages[i - 1]["at"]).total_seconds() > 5 * 60 for i in range(1, len(messages)))
            conn.execute(
                """INSERT INTO context_units(id,version,source_date,title,summary,start_at,end_at,
                     participants_json,message_count,has_gap,visibility,status,source_hash,source_batch,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id,version) DO UPDATE SET source_date=excluded.source_date,title=excluded.title,
                     summary=excluded.summary,start_at=excluded.start_at,end_at=excluded.end_at,
                     participants_json=excluded.participants_json,message_count=excluded.message_count,
                     has_gap=excluded.has_gap,visibility=excluded.visibility,status=excluded.status,
                     source_hash=excluded.source_hash,source_batch=excluded.source_batch,updated_at=excluded.updated_at""",
                (
                    unit_id,
                    version,
                    date,
                    title,
                    summary,
                    iso_at(messages[0]["at"]),
                    iso_at(messages[-1]["at"]),
                    json.dumps(participants, ensure_ascii=False),
                    len(messages),
                    int(has_gap),
                    "public",
                    "published",
                    digest,
                    batch_key,
                    now,
                    now,
                ),
            )
            conn.execute("DELETE FROM context_unit_messages WHERE unit_id=? AND unit_version=?", (unit_id, version))
            conn.execute("DELETE FROM context_public_projection WHERE unit_id=? AND version=?", (unit_id, version))
            conn.execute("DELETE FROM evidence_refs WHERE unit_id=? AND unit_version=?", (unit_id, version))
            try:
                conn.execute("DELETE FROM context_unit_fts WHERE unit_id=? AND version=?", (unit_id, version))
            except sqlite3.Error:
                pass
            for ordinal, message in enumerate(messages, 1):
                conn.execute(
                    """INSERT INTO context_unit_messages(unit_id,unit_version,message_id,ordinal,source_session,source_local_id)
                       VALUES(?,?,?,?,?,?)""",
                    (unit_id, version, message["id"], ordinal, message["session"], message["local_id"]),
                )
            public_json = json.dumps(public_projection, ensure_ascii=False)
            member_json = json.dumps(member_projection, ensure_ascii=False)
            redaction = json.dumps({"machine_ids": "群友", "xml": "stripped", "controls": "stripped"}, ensure_ascii=False)
            for projection_visibility in ("public", "member"):
                conn.execute(
                    """INSERT INTO context_public_projection(unit_id,version,visibility,public_text,
                         public_participants_json,redaction_json,member_text,created_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (unit_id, version, projection_visibility, public_json,
                     json.dumps(list(dict.fromkeys(public_text(p) for p in participants)), ensure_ascii=False),
                     redaction, member_json, now),
                )
            try:
                conn.execute(
                    """INSERT INTO context_unit_fts(unit_id,version,visibility,status,date,title,summary,public_text)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (unit_id, version, "public", "published", date, title, summary, public_json),
                )
            except sqlite3.Error:
                pass
            unit = {"id": unit_id, "version": version, "messages": [dict(m, ordinal=n) for n, m in enumerate(messages, 1)]}
            units.append(unit)
        evidence_count = 0
        for evidence in find_evidence(units, ledger, date):
            conn.execute(
                """INSERT INTO evidence_refs(unit_id,unit_version,source_type,source_id,source_date,
                     message_ids_json,ordinal_start,ordinal_end,quote_hash,source_batch,url,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(unit_id,unit_version,source_type,source_id) DO UPDATE SET
                     message_ids_json=excluded.message_ids_json,ordinal_start=excluded.ordinal_start,
                     ordinal_end=excluded.ordinal_end,quote_hash=excluded.quote_hash,source_batch=excluded.source_batch,
                     url=excluded.url""",
                (evidence["unit_id"], evidence["version"], evidence["source_type"], evidence["source_id"],
                 evidence["source_date"], json.dumps(evidence["message_ids"]), evidence["ordinal_start"],
                 evidence["ordinal_end"], evidence["quote_hash"], batch_key, evidence["url"], now),
            )
            evidence_count += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {
        "date": date,
        "messages": len(rows),
        "raw_messages": len(rows),
        "effective_messages": effective_message_count,
        "dropped_messages": dropped_message_count,
        "units": len(units),
        "initial_units": len(initial_chunks),
        "small_fragments_merged": small_fragment_count,
        "stale_units_removed": len(stale_ids) if force else 0,
        "title_sources": title_sources,
        "title_failures": title_failures,
        "force": force,
        "evidence": evidence_count,
        "batch_key": batch_key,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--governed-dir", type=Path)
    parser.add_argument("--nicknames", type=Path)
    parser.add_argument("--profiles", type=Path)
    parser.add_argument("--title-model", default=os.environ.get("DEEPSEEK_MODEL", DEFAULT_TITLE_MODEL))
    parser.add_argument("--title-timeout", type=float, default=DEFAULT_TITLE_TIMEOUT)
    parser.add_argument("--title-retries", type=int, default=DEFAULT_TITLE_RETRIES)
    parser.add_argument("--force", action="store_true", help="清除目标日旧块后重新生成；保留同 ID 的历史版本")
    parser.add_argument("--require-llm-titles", action="store_true", help="LLM 标题失败时拒绝写入原浆块")
    args = parser.parse_args()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        parser.error("--date must be YYYY-MM-DD")
    governed = args.governed_dir or (args.db.parent / "governed" / "ledgers")
    nicknames = args.nicknames
    if nicknames is None:
        for candidate in (Path("/opt/hermes-ledger/nicknames.json"), args.db.parent / "nicknames.json"):
            if candidate.is_file():
                nicknames = candidate
                break
    profiles = args.profiles
    if profiles is None:
        for candidate in (
            governed.parent / "members" / "profiles.json",
            Path(__file__).resolve().parents[1] / "site" / "content" / "members" / "profiles.json",
        ):
            if candidate.is_file():
                profiles = candidate
                break
    if args.title_timeout <= 0 or args.title_retries < 1:
        parser.error("--title-timeout 必须 > 0，--title-retries 必须 >= 1")
    print(
        json.dumps(
            build(
                args.db,
                args.date,
                governed,
                nicknames,
                profiles,
                title_model=args.title_model,
                title_timeout=args.title_timeout,
                title_retries=args.title_retries,
                force=args.force,
                require_llm_titles=args.require_llm_titles,
            ),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
