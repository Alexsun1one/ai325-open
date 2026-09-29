# -*- coding: utf-8 -*-
"""Reading-loop vitality: highlight / note / comment / favorite with daily caps."""
from __future__ import annotations

import collections
import datetime as dt
from typing import Any


def _weights(settings: dict) -> dict[str, int]:
    w = settings.get("weights") or {}
    return {
        "highlight": int(w.get("highlight", w.get("annotation", 2)) or 2),
        "note": int(w.get("note", 8) or 8),
        "comment": int(w.get("comment", 4) or 4),
        "favorite": int(w.get("favorite", 1) or 1),
        "multi_bonus": int(w.get("multi_highlight_bonus", 2) or 2),
        "highlight_daily_cap": int(w.get("highlight_daily_cap", 6) or 6),
        "note_daily_cap": int(w.get("note_daily_cap", 3) or 3),
        "comment_daily_cap": int(w.get("comment_daily_cap", 4) or 4),
        "favorite_daily_cap": int(w.get("favorite_daily_cap", 5) or 5),
        "reading_burst_threshold": int(w.get("reading_burst_threshold", 20) or 20),
        "reading_burst_discount": float(w.get("reading_burst_discount", 0.3) or 0.3),
    }


def _day(value: object) -> str:
    text = str(value or "")
    return text[:10] if len(text) >= 10 else ""


def compute_reading_parts(c, user_id: int, settings: dict) -> dict[str, int]:
    """Return parts: highlight, note, comment, favorite, multi_highlight.

    Rules from reading-feedback-loop design:
    - unique (user, anchor, day) for highlight/comment
    - note only when accepted + non-empty note ≥1 char (gatekeeper already accepted)
    - multi_bonus when anchor has ≥2 unique actors (any of highlight/comment/favorite)
    - daily caps; burst discount if >threshold highlights in one calendar day
    """
    w = _weights(settings)
    parts = {
        "highlight": 0,
        "note": 0,
        "comment": 0,
        "favorite": 0,
        "multi_highlight": 0,
    }

    # --- annotations (highlights + notes) ---
    ann_rows = c.execute(
        """SELECT id, anchor, note, kind, status, deleted, created_at
           FROM annotations
           WHERE user_id=? AND deleted=0 AND status='accepted'""",
        (user_id,),
    ).fetchall()
    by_day_hl: dict[str, list] = collections.defaultdict(list)
    by_day_note: dict[str, list] = collections.defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for row in ann_rows:
        day = _day(row["created_at"])
        anchor = str(row["anchor"] or "")
        note = str(row["note"] or "").strip()
        key = (day, anchor)
        if not day or not anchor or key in seen:
            continue
        seen.add(key)
        if note:
            by_day_note[day].append(row)
        else:
            by_day_hl[day].append(row)

    hl_points = 0
    for day, rows in by_day_hl.items():
        take = rows[: w["highlight_daily_cap"]]
        day_pts = len(take) * w["highlight"]
        if len(by_day_hl[day]) + len(by_day_note.get(day, [])) >= w["reading_burst_threshold"]:
            day_pts = int(day_pts * w["reading_burst_discount"])
        hl_points += day_pts
    parts["highlight"] = hl_points

    note_points = 0
    for day, rows in by_day_note.items():
        take = rows[: w["note_daily_cap"]]
        note_points += len(take) * w["note"]
    parts["note"] = note_points

    # --- comments ---
    com_rows = c.execute(
        """SELECT anchor, created_at FROM comments
           WHERE user_id=? AND deleted=0 AND status='accepted'""",
        (user_id,),
    ).fetchall()
    seen_c: set[tuple[str, str]] = set()
    by_day_c: dict[str, int] = collections.defaultdict(int)
    for row in com_rows:
        day = _day(row["created_at"])
        key = (day, str(row["anchor"] or ""))
        if key in seen_c:
            continue
        seen_c.add(key)
        if by_day_c[day] < w["comment_daily_cap"]:
            by_day_c[day] += 1
            parts["comment"] += w["comment"]

    # --- favorites ---
    fav_rows = c.execute(
        """SELECT anchor, created_at FROM favorites WHERE user_id=?""",
        (user_id,),
    ).fetchall()
    by_day_f: dict[str, int] = collections.defaultdict(int)
    for row in fav_rows:
        day = _day(row["created_at"])
        if by_day_f[day] < w["favorite_daily_cap"]:
            by_day_f[day] += 1
            parts["favorite"] += w["favorite"]

    # --- multi-person same-anchor bonus ---
    # actors = distinct users with highlight|comment|favorite on that anchor
    actor_sql = """
    SELECT anchor, user_id AS uid FROM annotations
      WHERE deleted=0 AND status='accepted'
    UNION
    SELECT anchor, user_id AS uid FROM comments
      WHERE deleted=0 AND status='accepted'
    UNION
    SELECT anchor, user_id AS uid FROM favorites
    """
    try:
        actors = c.execute(actor_sql).fetchall()
    except Exception:
        actors = []
    by_anchor: dict[str, set[int]] = collections.defaultdict(set)
    for row in actors:
        try:
            by_anchor[str(row["anchor"])].add(int(row["uid"]))
        except (TypeError, ValueError, KeyError):
            continue
    my_anchors = {str(r["anchor"] or "") for r in ann_rows}
    for anchor in my_anchors:
        if len(by_anchor.get(anchor, ())) >= 2:
            parts["multi_highlight"] += w["multi_bonus"]

    return parts


def merge_reading_into_parts(parts: dict[str, Any], reading: dict[str, int]) -> dict[str, Any]:
    out = dict(parts)
    # Replace legacy flat annotation with split reading parts
    out.pop("annotation", None)
    out.update(reading)
    return out


def build_heatmap(rows: list[Any], me_id: int | None = None) -> dict[str, Any]:
    """Public heatmap: {anchor, count, quote} only. Never note, never identity.

    count = unique user_id per anchor. quote = the sentence with the most
    unique markers in that paragraph (needed to draw the underline).
    mine is included only when me_id is set (logged in).
    """
    by_anchor_users: dict[str, set[int]] = collections.defaultdict(set)
    by_anchor_quotes: dict[str, dict[str, set[int]]] = collections.defaultdict(
        lambda: collections.defaultdict(set)
    )
    mine: list[dict[str, str]] = []
    seen_mine: set[tuple[str, str]] = set()
    for row in rows:
        anchor = str(row["anchor"] or "")
        quote = str(row["quote"] or "").strip()
        try:
            uid = int(row["user_id"])
        except (TypeError, ValueError, KeyError):
            continue
        if not anchor:
            continue
        by_anchor_users[anchor].add(uid)
        if quote:
            by_anchor_quotes[anchor][quote].add(uid)
        if me_id is not None and uid == me_id:
            key = (anchor, quote)
            if key not in seen_mine:
                seen_mine.add(key)
                mine.append({"anchor": anchor, "quote": quote})
    items: list[dict[str, Any]] = []
    for anchor, users in by_anchor_users.items():
        quotes = by_anchor_quotes.get(anchor) or {}
        best_quote = ""
        if quotes:
            best_quote = max(quotes.items(), key=lambda kv: (len(kv[1]), len(kv[0])))[0]
        item: dict[str, Any] = {"anchor": anchor, "count": len(users)}
        if best_quote:
            item["quote"] = best_quote
        items.append(item)
    items.sort(key=lambda it: (-int(it["count"]), str(it["anchor"])))
    payload: dict[str, Any] = {"items": items}
    if me_id is not None:
        payload["mine"] = mine
    return payload
