# -*- coding: utf-8 -*-
"""Identity anchors: stable member_key, display names only at render time.

Allowed member_key forms (Sun 2026-08-31):
  - wxid_* / gh_*          WeChat internal / official account ids
  - qq\\d+ / Q\\d+ / digits WeChat QQ-bound legacy ids
  - Latin WeChat username  e.g. y952346088, sunwuyuan521, win591, gbw311

Forbidden as member_key:
  - CJK / punctuation display names stuffed into username (广州-Anna, 明野, …)
  - bare '?' / empty

essays.source_sender is the essay member_key. essays.author is a historical
display snapshot and must not be used for joins.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any

# Canonical WeChat machine ids
WXID_RE = re.compile(r"^wxid_[A-Za-z0-9_-]+$", re.I)
GH_RE = re.compile(r"^gh_[A-Za-z0-9_-]+$", re.I)
# QQ-bound / numeric legacy
QQ_RE = re.compile(r"^(?:qq|QQ)\d{5,}$")
DIGITS_RE = re.compile(r"^\d{5,}$")
# Custom WeChat username (incl. QQ-style like y952346088)
LATIN_USER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{2,31}$")

CJK_RE = re.compile(r"[\u3400-\u9fff]")
PLACEHOLDER_KEYS = {"", "?", "未知", "未识别", "群友", "unknown", "none", "null"}


def clean(value: object) -> str:
    return " ".join(str(value or "").strip().split())


def is_stable_member_key(value: object) -> bool:
    """True if value is a legal WeChat identity key (not a display label)."""
    key = clean(value)
    if not key or key in PLACEHOLDER_KEYS:
        return False
    if CJK_RE.search(key):
        return False
    if WXID_RE.fullmatch(key) or GH_RE.fullmatch(key):
        return True
    if QQ_RE.fullmatch(key) or DIGITS_RE.fullmatch(key):
        return True
    if LATIN_USER_RE.fullmatch(key):
        return True
    return False


def key_kind(value: object) -> str:
    key = clean(value)
    if not key or key in PLACEHOLDER_KEYS:
        return "invalid"
    if CJK_RE.search(key):
        return "display_name"
    if WXID_RE.fullmatch(key):
        return "wxid"
    if GH_RE.fullmatch(key):
        return "gh"
    if QQ_RE.fullmatch(key) or DIGITS_RE.fullmatch(key):
        return "qq_legacy"
    if LATIN_USER_RE.fullmatch(key):
        return "wechat_username"
    return "unknown"


def is_pseudo_display_key(username: object, display: object = "") -> bool:
    """username field holds a display name (Anna bug class)."""
    user = clean(username)
    disp = clean(display) or user
    if not user:
        return False
    if not is_stable_member_key(user):
        return True
    # latin username that equals the public display and is not the message sender
    # is handled by merge_candidates via legacy_display_key / twin lookup.
    return user == disp and bool(CJK_RE.search(user))


def avatar_hash(avatar: object) -> str:
    raw = str(avatar or "").strip()
    if not raw:
        return ""
    # data-url or http url — hash full payload; identical bytes ⇒ same person signal
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()


def _json_list(value: object) -> list:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return []
    return list(parsed) if isinstance(parsed, list) else []


def _merge_json_lists(*values: object) -> list:
    out: list = []
    seen: set[str] = set()
    for value in values:
        for item in _json_list(value):
            marker = json.dumps(item, ensure_ascii=False, sort_keys=True) if not isinstance(item, str) else item
            if marker in seen:
                continue
            seen.add(marker)
            out.append(item)
    return out


def resolve_display_name(conn: sqlite3.Connection, member_key: object, fallback: object = "") -> str:
    """Render-time: member_key → current members.display."""
    key = clean(member_key)
    if not key:
        return clean(fallback) or "群友"
    row = conn.execute(
        "SELECT display, nickname FROM members WHERE username=? LIMIT 1", (key,)
    ).fetchone()
    if row:
        display = clean(row["display"] if isinstance(row, sqlite3.Row) else row[0])
        nick = clean(row["nickname"] if isinstance(row, sqlite3.Row) else row[1])
        if display:
            return display
        if nick:
            return nick
    return clean(fallback) or (key if not is_stable_member_key(key) else f"群友·{key[-4:]}")


def essay_member_key(row: sqlite3.Row | dict) -> str:
    if isinstance(row, sqlite3.Row):
        keys = row.keys()
        sender = clean(row["source_sender"]) if "source_sender" in keys else ""
        author = clean(row["author"]) if "author" in keys else ""
    else:
        sender = clean(row.get("source_sender"))
        author = clean(row.get("author"))
    if sender and is_stable_member_key(sender):
        return sender
    if sender and sender not in PLACEHOLDER_KEYS and not sender.startswith("?#"):
        return sender
    return author


def merge_candidates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Find pseudo/legacy member rows that should merge into a stable twin."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(members)")}
    if "username" not in cols:
        return []
    flag_col = "identity_flags" in cols
    rows = [dict(r) for r in conn.execute("SELECT * FROM members").fetchall()]
    by_user = {clean(r["username"]): r for r in rows if clean(r.get("username"))}
    by_display: dict[str, list[dict]] = {}
    for r in rows:
        d = clean(r.get("display"))
        if d:
            by_display.setdefault(d, []).append(r)

    senders = {
        clean(r[0])
        for r in conn.execute("SELECT DISTINCT sender FROM messages")
        if clean(r[0]) and clean(r[0]) not in PLACEHOLDER_KEYS
    }

    by_avatar: dict[str, list[dict]] = {}
    for r in rows:
        h = avatar_hash(r.get("avatar"))
        if h:
            by_avatar.setdefault(h, []).append(r)

    pairs: dict[tuple[str, str], dict[str, Any]] = {}

    def remember(pseudo: dict, canonical: dict, reason: str) -> None:
        p_key = clean(pseudo["username"])
        c_key = clean(canonical["username"])
        if not p_key or not c_key or p_key == c_key:
            return
        if not is_stable_member_key(c_key):
            return
        # Prefer the key that actually sends messages
        if c_key not in senders and p_key in senders:
            return
        if is_stable_member_key(p_key) and "legacy_display_key" not in _json_list(pseudo.get("identity_flags")):
            # two stable keys — only merge via avatar when one is legacy-flagged
            if reason != "avatar_hash":
                return
        key = (p_key, c_key)
        prev = pairs.get(key)
        if prev:
            prev["reasons"] = sorted(set(prev["reasons"] + [reason]))
        else:
            pairs[key] = {
                "pseudo_username": p_key,
                "canonical_username": c_key,
                "display": clean(canonical.get("display")) or clean(pseudo.get("display")),
                "reasons": [reason],
            }

    for r in rows:
        user = clean(r.get("username"))
        disp = clean(r.get("display"))
        flags = _json_list(r.get("identity_flags")) if flag_col else []
        twins = [t for t in by_display.get(disp, []) if clean(t.get("username")) != user]
        stable_twins = [
            t for t in twins
            if is_stable_member_key(t.get("username")) and clean(t.get("username")) in senders
        ]
        if not stable_twins:
            continue
        # Prefer wxid_ over custom username
        stable_twins.sort(
            key=lambda t: (0 if WXID_RE.fullmatch(clean(t["username"])) else 1, clean(t["username"]))
        )
        canon = stable_twins[0]
        if "legacy_display_key" in flags or is_pseudo_display_key(user, disp):
            remember(r, canon, "legacy_display_key" if "legacy_display_key" in flags else "username_is_display")

    for h, group in by_avatar.items():
        if len(group) < 2:
            continue
        stable = [g for g in group if is_stable_member_key(g.get("username")) and clean(g.get("username")) in senders]
        pseudo = [
            g for g in group
            if ("legacy_display_key" in _json_list(g.get("identity_flags")) or is_pseudo_display_key(g.get("username"), g.get("display")))
        ]
        if not stable or not pseudo:
            continue
        stable.sort(key=lambda t: (0 if WXID_RE.fullmatch(clean(t["username"])) else 1, clean(t["username"])))
        for p in pseudo:
            remember(p, stable[0], "avatar_hash")

    return sorted(pairs.values(), key=lambda x: (x["display"], x["pseudo_username"]))


def merge_member_row(conn: sqlite3.Connection, pseudo_username: str, canonical_username: str) -> dict[str, Any]:
    """Absorb pseudo into canonical: history merge, msg recount, delete pseudo."""
    pseudo_username = clean(pseudo_username)
    canonical_username = clean(canonical_username)
    if not pseudo_username or not canonical_username or pseudo_username == canonical_username:
        raise ValueError("invalid merge pair")
    if not is_stable_member_key(canonical_username):
        raise ValueError(f"canonical is not a stable key: {canonical_username}")

    p = conn.execute("SELECT * FROM members WHERE username=?", (pseudo_username,)).fetchone()
    c = conn.execute("SELECT * FROM members WHERE username=?", (canonical_username,)).fetchone()
    if not p or not c:
        raise ValueError("missing member row")

    history = _merge_json_lists(c["name_history"], p["name_history"], p["display"], c["display"])
    called = _merge_json_lists(c["called_names"], p["called_names"])
    flags = [
        f for f in _merge_json_lists(c["identity_flags"], p["identity_flags"])
        if f not in {"legacy_display_key"}
    ]
    avatar = clean(c["avatar"]) or clean(p["avatar"])
    last_active = max(clean(c["last_active"]), clean(p["last_active"]))
    # Recount from messages — never sum duplicate projections
    msgs = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE sender=?", (canonical_username,)
    ).fetchone()[0]
    profile = clean(c["profile"]) or clean(p["profile"])
    tags = clean(c["tags"]) or clean(p["tags"])
    quote = clean(c["quote"]) or clean(p["quote"])
    nickname = clean(c["nickname"]) or clean(p["nickname"])
    display = clean(c["display"]) or clean(p["display"])
    name_source = clean(c["name_source"]) or "room_nickname"

    conn.execute(
        """UPDATE members SET display=?, nickname=?, avatar=?, msgs=?, last_active=?,
             profile=?, tags=?, quote=?, name_source=?, identity_flags=?,
             name_history=?, called_names=? WHERE username=?""",
        (
            display, nickname, avatar, int(msgs), last_active,
            profile, tags, quote, name_source,
            json.dumps(flags, ensure_ascii=False),
            json.dumps(history, ensure_ascii=False),
            json.dumps(called, ensure_ascii=False),
            canonical_username,
        ),
    )
    # Retarget users still bound to the pseudo key
    if "users" in {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
        user_cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
        if "member_key" in user_cols:
            conn.execute(
                "UPDATE users SET member_key=? WHERE member_key=?",
                (canonical_username, pseudo_username),
            )
    conn.execute("DELETE FROM members WHERE username=?", (pseudo_username,))
    return {
        "pseudo_username": pseudo_username,
        "canonical_username": canonical_username,
        "display": display,
        "msgs": int(msgs),
        "name_history": history,
    }


def apply_merges(conn: sqlite3.Connection, pairs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    pairs = pairs if pairs is not None else merge_candidates(conn)
    results = []
    for pair in pairs:
        results.append(merge_member_row(conn, pair["pseudo_username"], pair["canonical_username"]))
    return results


def inventory_author_anchors() -> list[dict[str, str]]:
    """Static inventory of content author anchors in this codebase/schema."""
    return [
        {"surface": "essays", "field": "source_sender", "stores": "member_key", "join": "yes", "rename_safe": "yes"},
        {"surface": "essays", "field": "author", "stores": "display_snapshot", "join": "no(was yes — bug)", "rename_safe": "no if used as join"},
        {"surface": "annotations", "field": "user_id", "stores": "users.id", "join": "yes", "rename_safe": "yes"},
        {"surface": "annotations", "field": "username", "stores": "login username snapshot", "join": "display only", "rename_safe": "n/a"},
        {"surface": "comments", "field": "user_id", "stores": "users.id", "join": "yes", "rename_safe": "yes"},
        {"surface": "favorites", "field": "user_id", "stores": "users.id", "join": "yes", "rename_safe": "yes"},
        {"surface": "submissions", "field": "user_id", "stores": "users.id", "join": "yes", "rename_safe": "yes"},
        {"surface": "users", "field": "member_key", "stores": "member_key", "join": "yes", "rename_safe": "yes"},
        {"surface": "members", "field": "username", "stores": "member_key (or pseudo display)", "join": "primary", "rename_safe": "yes if stable"},
        {"surface": "members", "field": "display", "stores": "display label", "join": "no", "rename_safe": "label only"},
        {"surface": "ledger quotes/voices", "field": "a / v.a", "stores": "display at distill time", "join": "hermes resolve", "rename_safe": "snapshot"},
        {"surface": "profiles/people.json", "field": "name", "stores": "display (no member_key yet)", "join": "by name — fragile", "rename_safe": "no"},
        {"surface": "arsenal", "field": "contributor fields", "stores": "varies", "join": "check per item", "rename_safe": "audit"},
    ]


def governed_essay_dict(conn: sqlite3.Connection, row: sqlite3.Row | dict) -> dict[str, Any]:
    """Build essay API item: member_key + render-time author."""
    if isinstance(row, sqlite3.Row):
        data = {k: row[k] for k in row.keys()}
    else:
        data = dict(row)
    key = essay_member_key(data)
    body = str(data.get("content") or "")
    author_snap = clean(data.get("author"))
    author = resolve_display_name(conn, key, author_snap)
    name = clean(data.get("name"))
    title = name or next((ln.strip() for ln in body.splitlines() if ln.strip()), "")[:40] or f"{author}的小作文"
    return {
        "title": title,
        "author": author,
        "author_snapshot": author_snap,
        "member_key": key,
        "date": str(data.get("cst") or "")[:10],
        "body": body,
        "word_count": len(re.sub(r"\s+", "", body)),
    }
