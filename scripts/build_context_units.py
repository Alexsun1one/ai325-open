#!/usr/bin/env python3
"""Build the deterministic 2026-08-23 context-unit slice from messages.

The script deliberately has no network/LLM dependency.  It creates the four
storage layers, public/member projections, and evidence references in one
BEGIN IMMEDIATE transaction so a rerun is idempotent.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path


CST = timezone(timedelta(hours=8))
MACHINE_ID_RE = re.compile(r"(?:wxid_[A-Za-z0-9_-]+|QQ\d{5,}|q\d{6,}|gh_[A-Za-z0-9_-]+)")
TAG_RE = re.compile(r"<[^>]+>")
ZERO_WIDTH_RE = re.compile(r"[\u0000-\u001f\u007f\u200b-\u200f\u202a-\u202e\u2060\u2066-\u2069\ufeff]")


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


def clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    text = html.unescape(text)
    text = TAG_RE.sub(" ", text)
    text = ZERO_WIDTH_RE.sub("", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) not in {"Cc", "Cf"} or ch in "\n\t")
    return " ".join(text.split()).strip()


def public_text(value: str) -> str:
    return MACHINE_ID_RE.sub("群友", clean_text(value))


def display_name(row: sqlite3.Row) -> str:
    raw = clean_text(row["sender_name"] or row["sender"] or "群友")
    return "群友" if MACHINE_ID_RE.fullmatch(raw) or not raw else raw


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
    words = set(re.findall(r"[a-z0-9_+#.-]{2,}", text))
    cjk = re.findall(r"[\u3400-\u9fff]", text)
    words.update("".join(cjk[i : i + 2]) for i in range(max(0, len(cjk) - 1)))
    return words


def should_split(previous: dict, current: dict, current_tokens: set[str], speakers: set[str], size: int) -> bool:
    gap = (current["at"] - previous["at"]).total_seconds()
    if gap > 12 * 60 or size >= 40:
        return True
    overlap = previous["tokens"] & current_tokens
    if gap > 6 * 60 and not overlap and current["sender"] not in speakers:
        return True
    return False


def chunk_messages(rows: list[sqlite3.Row]) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    current: list[dict] = []
    speakers: set[str] = set()
    for row in rows:
        item = {
            "id": row["id"],
            "session": row["session"],
            "local_id": row["local_id"],
            "sender": display_name(row),
            "text": clean_text(row["content"]),
            "public": public_text(row["content"]),
            "at": message_at(row),
        }
        item["tokens"] = topic_tokens(item["text"])
        if current and should_split(current[-1], item, item["tokens"], speakers, len(current)):
            chunks.append(current)
            current = []
            speakers = set()
        current.append(item)
        speakers.add(item["sender"])
    if current:
        chunks.append(current)
    return chunks


def first_line(value: str, limit: int) -> str:
    value = " ".join(value.split())
    return value[:limit].rstrip() + ("…" if len(value) > limit else "")


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


def build(db_path: Path, date: str, governed_dir: Path) -> dict:
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
    chunks = chunk_messages(rows)
    all_ids = [row["id"] for row in rows]
    batch_digest = hashlib.sha256(json.dumps(all_ids, separators=(",", ":")).encode()).hexdigest()
    batch_key = f"messages:{date}:{batch_digest[:16]}"
    now = datetime.now(CST).isoformat(timespec="seconds")
    ledger = load_ledger(governed_dir, date)
    units: list[dict] = []

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """INSERT INTO ingest_batches(batch_key,source_date,source_path,source_sha256,status,
                       message_count,metadata_json,created_at,completed_at)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(batch_key) DO UPDATE SET message_count=excluded.message_count,
                 status=excluded.status,completed_at=excluded.completed_at""",
            (batch_key, date, "messages", batch_digest, "ready", len(rows), "{}", now, now),
        )
        for index, messages in enumerate(chunks, 1):
            unit_id = f"cu-{date.replace('-', '')}-{index:04d}"
            digest = source_hash(messages)
            previous = conn.execute(
                "SELECT version,source_hash FROM context_units WHERE id=? ORDER BY version DESC LIMIT 1",
                (unit_id,),
            ).fetchone()
            version = previous["version"] if previous and previous["source_hash"] == digest else ((previous["version"] + 1) if previous else 1)
            title = first_line(messages[0]["public"], 60) or f"{date} 语境块 {index}"
            summary = first_line("；".join(m["public"] for m in messages[:3]), 220)
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
                (unit_id, version, date, title, summary, iso_at(messages[0]["at"]), iso_at(messages[-1]["at"]),
                 json.dumps(participants, ensure_ascii=False), len(messages), int(has_gap), "public", "published",
                 digest, batch_key, now, now),
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
    return {"date": date, "messages": len(rows), "units": len(units), "evidence": evidence_count, "batch_key": batch_key}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--date", required=True)
    parser.add_argument("--governed-dir", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        parser.error("--date must be YYYY-MM-DD")
    governed = args.governed_dir or (args.db.parent / "governed" / "ledgers")
    print(json.dumps(build(args.db, args.date, governed), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
