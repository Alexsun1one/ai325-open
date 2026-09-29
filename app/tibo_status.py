"""Read-only public projection of the AITIBO monitor snapshot."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
try:
    from .tibo_intent import load_intent
    from .tibo_prediction import load_enrichment
    from .tibo_timeline import project_timeline
except ImportError:
    from tibo_intent import load_intent
    from tibo_prediction import load_enrichment
    from tibo_timeline import project_timeline


router = APIRouter(prefix="/api/tibo", tags=["public"])

DEFAULT_STATUS_PATH = Path("/tibo-data/status.json")
MAX_STATUS_BYTES = 512 * 1024
HANDLE = "thsottiaux"
PROFILE_URL = "https://x.com/thsottiaux"
SOURCE_BASE = {"platform": "x", "handle": HANDLE, "url": PROFILE_URL}
DEFAULT_COVERAGE = "public_search"
ALLOWED_COVERAGE = frozenset({"public_search", "official_timeline"})
POST_KINDS = frozenset({"reset", "promise", "joke", "other"})
POST_REASONS = frozenset(
    {
        "NO_RESET_TERM",
        "NON_QUOTA_RESET",
        "QUOTED_OR_REPOST",
        "EMBEDDED_LINK_REFERENCE",
        "RESET_CREDIT_EXCLUDED",
        "NEGATED_RESET_CLAIM",
        "QUESTIONED_RESET_CLAIM",
        "REQUESTED_RESET",
        "JOKE_OR_SATIRE",
        "HYPOTHETICAL_RESET",
        "HABITUAL_RESET_MENTION",
        "EXPLICIT_FUTURE_PUBLIC_CLAIM",
        "EXPLICIT_PAST_PUBLIC_CLAIM",
        "AMBIGUOUS_RESET_MENTION",
    }
)
FORECAST_REASONS = frozenset(
    {
        "NO_VERIFIED_PUBLIC_SIGNAL",
        "NO_ACTIONABLE_PUBLIC_RESET_SIGNAL",
        "PUBLIC_RESET_SIGNAL_STALE",
        "EXPLICIT_FUTURE_PUBLIC_CLAIM",
        "PUBLIC_RESET_CLAIM_NOT_ACCOUNT_CONFIRMATION",
        "CANCELLED_PUBLIC_RESET_PLAN",
    }
)
CANONICAL_POST_URL = re.compile(r"^https://x\.com/thsottiaux/status/([0-9]{1,30})$")
CODE = re.compile(r"^[A-Z0-9_]{1,128}$")


class SnapshotInvalid(ValueError):
    """Private validation marker; it is never returned to a caller."""


def configured_status_path() -> Path:
    return Path(os.environ.get("AITIBO_STATUS_PATH") or DEFAULT_STATUS_PATH)


def _source() -> dict[str, str]:
    return {**SOURCE_BASE, "coverage": DEFAULT_COVERAGE}


def _unknown(health: str, error_code: str | None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source": _source(),
        "checked_at": None,
        "fetched_at": None,
        "health": health,
        "posts": [],
        "forecast": {
            "state": "unknown",
            "reason": "NO_VERIFIED_PUBLIC_SIGNAL",
            "source_url": None,
            "last_reset_at": None,
        },
        "error_code": error_code,
    }


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise SnapshotInvalid
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotInvalid from exc
    if parsed.tzinfo is None or parsed.astimezone(timezone.utc) > datetime.now(timezone.utc):
        raise SnapshotInvalid
    return value


def _post_url(value: Any, post_id: str | None = None) -> str:
    if not isinstance(value, str):
        raise SnapshotInvalid
    match = CANONICAL_POST_URL.fullmatch(value)
    if not match or (post_id is not None and match.group(1) != post_id):
        raise SnapshotInvalid
    return value


def _project_source(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or {key: value.get(key) for key in SOURCE_BASE} != SOURCE_BASE:
        raise SnapshotInvalid
    coverage = value.get("coverage", DEFAULT_COVERAGE)
    if coverage not in ALLOWED_COVERAGE:
        raise SnapshotInvalid
    return {**SOURCE_BASE, "coverage": coverage}


def _project_posts(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > 50:
        raise SnapshotInvalid
    posts: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise SnapshotInvalid
        post_id = raw.get("id")
        text = raw.get("text")
        kind = raw.get("kind")
        reason = raw.get("reason")
        if (
            not isinstance(post_id, str)
            or not re.fullmatch(r"[0-9]{1,30}", post_id)
            or post_id in seen
            or not isinstance(text, str)
            or not text.strip()
            or len(text) > 1_000
            or "\x00" in text
            or kind not in POST_KINDS
            or reason not in POST_REASONS
        ):
            raise SnapshotInvalid
        posts.append(
            {
                "id": post_id,
                "url": _post_url(raw.get("url"), post_id),
                "text": text,
                "created_at": _timestamp(raw.get("created_at")) or _invalid(),
                "kind": kind,
                "reason": reason,
            }
        )
        seen.add(post_id)
    return posts


def _invalid() -> str:
    raise SnapshotInvalid


def _project_forecast(value: Any, posts: list[dict[str, str]]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SnapshotInvalid
    state = value.get("state")
    reason = value.get("reason")
    if state not in {"unknown", "waiting", "soon", "reset"} or reason not in FORECAST_REASONS:
        raise SnapshotInvalid
    source_url = value.get("source_url")
    if source_url is not None:
        source_url = _post_url(source_url)
    last_reset_at = _timestamp(value.get("last_reset_at"))
    by_url = {post["url"]: post for post in posts}
    source_post = by_url.get(source_url) if source_url else None
    reset_timestamps = {post["created_at"] for post in posts if post["kind"] == "reset"}
    if last_reset_at is not None and last_reset_at not in reset_timestamps:
        raise SnapshotInvalid

    if state == "unknown":
        if reason != "NO_VERIFIED_PUBLIC_SIGNAL" or source_url is not None or last_reset_at is not None:
            raise SnapshotInvalid
    elif state == "waiting":
        if reason == "NO_ACTIONABLE_PUBLIC_RESET_SIGNAL":
            if source_url is not None or last_reset_at is not None:
                raise SnapshotInvalid
        elif reason == "PUBLIC_RESET_SIGNAL_STALE":
            if source_post is None or source_post["kind"] not in {"reset", "promise"}:
                raise SnapshotInvalid
        elif reason == "CANCELLED_PUBLIC_RESET_PLAN":
            if source_post is None or source_post["reason"] != "NEGATED_RESET_CLAIM":
                raise SnapshotInvalid
        else:
            raise SnapshotInvalid
    elif state == "soon":
        if reason != "EXPLICIT_FUTURE_PUBLIC_CLAIM" or source_post is None or source_post["kind"] != "promise":
            raise SnapshotInvalid
    elif reason != "PUBLIC_RESET_CLAIM_NOT_ACCOUNT_CONFIRMATION" or source_post is None or source_post["kind"] != "reset":
        raise SnapshotInvalid

    return {
        "state": state,
        "reason": reason,
        "source_url": source_url,
        "last_reset_at": last_reset_at,
    }


def _project_snapshot(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        raise SnapshotInvalid
    health = raw.get("health")
    if health not in {"ok", "unconfigured", "error"}:
        raise SnapshotInvalid
    error_code = raw.get("error_code")
    if error_code is not None and (not isinstance(error_code, str) or not CODE.fullmatch(error_code)):
        raise SnapshotInvalid
    posts = _project_posts(raw.get("posts"))
    return {
        "schema_version": 1,
        "source": _project_source(raw.get("source")),
        "checked_at": _timestamp(raw.get("checked_at")),
        "fetched_at": _timestamp(raw.get("fetched_at")),
        "health": health,
        "posts": posts,
        "forecast": _project_forecast(raw.get("forecast"), posts),
        "error_code": error_code,
    }


def load_status(path: Path | None = None) -> dict[str, Any]:
    """Return only the public v1 contract; never expose filesystem failures."""

    target = path or configured_status_path()
    try:
        with target.open("rb") as handle:
            raw_bytes = handle.read(MAX_STATUS_BYTES + 1)
    except FileNotFoundError:
        return _unknown("unconfigured", "STATUS_UNCONFIGURED")
    except OSError:
        return _unknown("error", "STATUS_UNAVAILABLE")
    if len(raw_bytes) > MAX_STATUS_BYTES:
        return _unknown("error", "STATUS_UNAVAILABLE")
    try:
        return _project_snapshot(json.loads(raw_bytes.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, SnapshotInvalid, TypeError, ValueError):
        return _unknown("error", "STATUS_UNAVAILABLE")


@router.get("/status")
def get_status() -> JSONResponse:
    status = load_status()
    status["intent_analysis"] = load_intent(configured_status_path().with_name("intent.json"), status)
    status["post_translations"], status["prediction"] = load_enrichment(
        configured_status_path().with_name("enrichment.json"), status)
    status["reset_timeline"] = project_timeline(status, status["prediction"])
    return JSONResponse(status, headers={"Cache-Control": "no-store"})
