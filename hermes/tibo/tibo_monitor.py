#!/usr/bin/env python3
"""Conservative, no-model monitor for Tibo's public X posts."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
HANDLE = "thsottiaux"
PROFILE_URL = "https://x.com/thsottiaux"
SOURCE_BASE = {"platform": "x", "handle": HANDLE, "url": PROFILE_URL}
DEFAULT_COVERAGE = "public_search"
ALLOWED_COVERAGE = frozenset({"public_search", "official_timeline"})
# Public for callers and tests. Every published status has this fourth field.
SOURCE = {**SOURCE_BASE, "coverage": DEFAULT_COVERAGE}
MAX_POSTS = 50
MIN_FETCH_LIMIT = 10
MAX_FETCH_LIMIT = 50
MAX_TEXT_LENGTH = 1_000
FRESH_FOR = timedelta(hours=24)
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


class MonitorError(Exception):
    """Expected error with a frontend-safe code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: Any, field: str, now: datetime) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise MonitorError(f"{field}_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MonitorError(f"{field}_INVALID") from exc
    if parsed.tzinfo is None:
        raise MonitorError(f"{field}_INVALID")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > now:
        raise MonitorError(f"{field}_FUTURE")
    return parsed


def canonical_post_url(post_id: str) -> str:
    return f"{PROFILE_URL}/status/{post_id}"


def source_for(coverage: str) -> dict[str, str]:
    if coverage not in ALLOWED_COVERAGE:
        raise MonitorError("INPUT_SOURCE_REJECTED")
    return {**SOURCE_BASE, "coverage": coverage}


def source_coverage(source: Any, *, allow_missing: bool) -> str:
    """Validate a source without allowing a collector to widen its identity."""

    if source is None and allow_missing:
        return DEFAULT_COVERAGE
    if not isinstance(source, dict):
        raise MonitorError("INPUT_SOURCE_REJECTED")
    allowed_keys = {*SOURCE_BASE, "coverage"}
    if set(source) - allowed_keys:
        raise MonitorError("INPUT_SOURCE_REJECTED")
    if {key: source.get(key) for key in SOURCE_BASE} != SOURCE_BASE:
        raise MonitorError("INPUT_SOURCE_REJECTED")
    coverage = source.get("coverage", DEFAULT_COVERAGE)
    if coverage not in ALLOWED_COVERAGE:
        raise MonitorError("INPUT_SOURCE_REJECTED")
    return coverage


def valid_snapshot_source(source: Any) -> bool:
    try:
        coverage = source_coverage(source, allow_missing=False)
    except MonitorError:
        return False
    # v1 snapshots written before coverage existed are known local state. Keep
    # them on an error path, then republish them with the default provenance.
    return source == source_for(coverage) or source == SOURCE_BASE


def display_text(value: Any) -> str:
    if not isinstance(value, str):
        raise MonitorError("POST_TEXT_INVALID")
    text = value.replace("\x00", "").strip()
    if not text:
        raise MonitorError("POST_TEXT_EMPTY")
    if len(text) > MAX_TEXT_LENGTH:
        return text[: MAX_TEXT_LENGTH - 1] + "…"
    return text


def classify_post(text: str, raw: dict[str, Any]) -> tuple[str, str]:
    """Return a narrow public-claim category and machine-readable reason."""

    folded = text.casefold()
    reset_credit_term = r"reset[\s_-]*(?:credit|credits|coupon|coupons|voucher|vouchers|ticket|tickets)\b"
    has_reset = bool(re.search(r"\breset(?:s|ting|ted)?\b", folded)) or bool(re.search(reset_credit_term, folded)) or "重置" in text
    if not has_reset:
        return "other", "NO_RESET_TERM"
    if raw.get("quoted") is True or raw.get("is_quote") is True or re.match(r"^\s*(?:rt\s+@|quote\s*:|[“\"'])", folded):
        return "other", "QUOTED_OR_REPOST"
    # A public-search result can expose copied text, quote text, or a linked
    # reference. Treat any such reset mention as non-actionable rather than
    # guessing that it is the author's present-tense claim.
    if re.search(r"https?://\S+", text):
        return "other", "EMBEDDED_LINK_REFERENCE"
    if re.search(reset_credit_term, folded) or re.search(r"\bbanked\s+reset\b", folded) or "重置券" in text:
        return "other", "RESET_CREDIT_EXCLUDED"
    if (
        re.search(r"\b(?:no|not|never|without)\s+(?:a\s+)?reset\b", folded)
        or re.search(r"\b(?:won't|will not|didn't|did not|haven't|hasn't|isn't|aren't)\b.{0,32}\breset\b", folded)
        or re.search(r"\breset\b.{0,24}\b(?:not|never|didn't|did not)\b", folded)
        or "不是重置" in text
    ):
        return "other", "NEGATED_RESET_CLAIM"
    if "?" in text or "？" in text:
        return "other", "QUESTIONED_RESET_CLAIM"
    if (
        re.search(r"\b(?:please|pls)\b.{0,32}\breset\b", folded)
        or re.search(r"\b(?:can|could|would|will)\s+you\b.{0,32}\breset\b", folded)
        or re.search(r"\breset\b.{0,32}\b(?:please|pls)\b", folded)
    ):
        return "other", "REQUESTED_RESET"
    if re.search(r"\b(?:just kidding|joke|jk|lol|lmao)\b", folded) or "玩笑" in text:
        return "joke", "JOKE_OR_SATIRE"
    if re.search(r"\b(?:if|would|could|might|maybe|wish|imagine|hypothetically)\b", folded) or "如果" in text:
        return "other", "HYPOTHETICAL_RESET"
    # A completed propagation notice is distinct from another future reset.
    if re.search(r"(?:^|[.!]\s+)resets?\s+(?:have\s+)?(?:all\s+)?(?:propagated|completed|finished)\b", folded):
        return "reset", "EXPLICIT_PAST_PUBLIC_CLAIM"
    if re.search(r"\bi\s+(?:have\s+)?promised\s+a\s+reset\s+for\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow)\b", folded):
        return "promise", "EXPLICIT_FUTURE_PUBLIC_CLAIM"
    if re.search(r"(?:^|[.!]\s+)more\s+resets\s+(?:are\s+)?coming\s+next\s+week\b", folded):
        return "promise", "EXPLICIT_FUTURE_PUBLIC_CLAIM"
    if not re.search(r"\b(?:codex|chatgpt|usage|quotas?|limits?|allowances?)\b", folded):
        return "other", "NON_QUOTA_RESET"
    if re.search(r"\b(?:every|usually|regularly|weekly|daily|often|sometimes)\b", folded):
        return "other", "HABITUAL_RESET_MENTION"
    if re.search(r"\b(?:have|has|were|was)\s+reset\b", folded):
        return "reset", "EXPLICIT_PAST_PUBLIC_CLAIM"
    if re.search(
        r"\b(?:will|gonna|going to|plan to|soon|later|tomorrow|this afternoon)\b.{0,32}\breset\b"
        r"|\breset\b.{0,32}\b(?:soon|later|tomorrow|this afternoon)\b",
        folded,
    ):
        return "promise", "EXPLICIT_FUTURE_PUBLIC_CLAIM"
    if re.search(
        r"\b(?:i|we|they)\s+(?:have\s+)?reset(?:ted)?\b"
        r"|\b(?:have|has|were|was)\s+reset\b"
        r"|\breset\s+(?:all|the)\s+(?:codex\s+)?(?:rate\s+limits?|limits?|quotas?)\b",
        folded,
    ):
        return "reset", "EXPLICIT_PAST_PUBLIC_CLAIM"
    return "other", "AMBIGUOUS_RESET_MENTION"


def post_fields(raw: Any, now: datetime) -> dict[str, str]:
    """Validate fields shared by untrusted collector input and stored output."""

    if not isinstance(raw, dict):
        raise MonitorError("POST_INVALID")
    post_id = raw.get("id")
    if isinstance(post_id, int) and not isinstance(post_id, bool):
        post_id = str(post_id)
    if not isinstance(post_id, str) or not re.fullmatch(r"\d{1,30}", post_id):
        raise MonitorError("POST_ID_INVALID")
    if raw.get("url") != canonical_post_url(post_id):
        raise MonitorError("POST_URL_REJECTED")
    created_at = parse_iso(raw.get("created_at"), "POST_CREATED_AT", now)
    text = display_text(raw.get("text"))
    return {
        "id": post_id,
        "url": canonical_post_url(post_id),
        "text": text,
        "created_at": to_iso(created_at),
    }


def normalize_post(raw: Any, now: datetime) -> dict[str, str]:
    """Classify untrusted collector input exactly once; ignore supplied kind."""

    post = post_fields(raw, now)
    text = post["text"]
    kind, reason = classify_post(text, raw)
    return {**post, "kind": kind, "reason": reason}


def validate_published_post(raw: Any, now: datetime) -> dict[str, str]:
    """Validate a status snapshot without reclassifying lost raw metadata."""

    post = post_fields(raw, now)
    kind = raw.get("kind") if isinstance(raw, dict) else None
    reason = raw.get("reason") if isinstance(raw, dict) else None
    if kind not in POST_KINDS or reason not in POST_REASONS:
        raise MonitorError("STORED_POST_INVALID")
    # Safe narrow migration: AMBIGUOUS was emitted only after all quote/link/
    # negation guards. Never reclassify records with lost quote metadata.
    if kind == "other" and reason == "AMBIGUOUS_RESET_MENTION":
        next_kind, next_reason = classify_post(post["text"], {})
        if next_kind in {"reset", "promise"}:
            kind, reason = next_kind, next_reason
    return {**post, "kind": kind, "reason": reason}


def sort_and_bound_raw(posts: Iterable[Any], now: datetime) -> list[dict[str, str]]:
    deduped: dict[str, dict[str, str]] = {}
    for post in posts:
        checked = normalize_post(post, now)
        deduped[checked["id"]] = checked
    return sorted(
        deduped.values(),
        key=lambda post: (post["created_at"], post["id"]),
        reverse=True,
    )[:MAX_POSTS]


def sort_and_bound_published(posts: Iterable[Any], now: datetime) -> list[dict[str, str]]:
    deduped: dict[str, dict[str, str]] = {}
    for post in posts:
        checked = validate_published_post(post, now)
        deduped[checked["id"]] = checked
    return sorted(
        deduped.values(),
        key=lambda post: (post["created_at"], post["id"]),
        reverse=True,
    )[:MAX_POSTS]


def forecast_for(posts: list[dict[str, str]], now: datetime) -> dict[str, Any]:
    actionable = [post for post in posts if post["kind"] in {"reset", "promise"}]
    reset_posts = [post for post in actionable if post["kind"] == "reset"]
    last_reset_at = reset_posts[0]["created_at"] if reset_posts else None
    if not actionable:
        if posts:
            return {
                "state": "waiting",
                "reason": "NO_ACTIONABLE_PUBLIC_RESET_SIGNAL",
                "source_url": None,
                "last_reset_at": None,
            }
        return {
            "state": "unknown",
            "reason": "NO_VERIFIED_PUBLIC_SIGNAL",
            "source_url": None,
            "last_reset_at": None,
        }

    latest = actionable[0]
    if latest["kind"] == "promise":
        cancellations = [post for post in posts
                         if post["created_at"] > latest["created_at"]
                         and post["reason"] == "NEGATED_RESET_CLAIM"
                         and re.search(r"\b(?:codex|chatgpt|usage|quotas?|limits?)\b", post["text"], re.I)
                         and re.search(r"\b(?:won't|will not|not going to)\b.{0,40}\breset\b", post["text"], re.I)]
        if cancellations:
            return {"state": "waiting", "reason": "CANCELLED_PUBLIC_RESET_PLAN",
                    "source_url": cancellations[0]["url"], "last_reset_at": last_reset_at}
    age = now - parse_iso(latest["created_at"], "STORED_CREATED_AT", now)
    if age > FRESH_FOR:
        return {
            "state": "waiting",
            "reason": "PUBLIC_RESET_SIGNAL_STALE",
            "source_url": latest["url"],
            "last_reset_at": last_reset_at,
        }
    if latest["kind"] == "promise":
        return {
            "state": "soon",
            "reason": "EXPLICIT_FUTURE_PUBLIC_CLAIM",
            "source_url": latest["url"],
            "last_reset_at": last_reset_at,
        }
    return {
        "state": "reset",
        "reason": "PUBLIC_RESET_CLAIM_NOT_ACCOUNT_CONFIRMATION",
        "source_url": latest["url"],
        "last_reset_at": last_reset_at,
    }


def load_snapshot(path: Path, now: datetime) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != SCHEMA_VERSION
        or not valid_snapshot_source(payload.get("source"))
    ):
        return None
    try:
        posts = sort_and_bound_published(payload.get("posts", []), now)
        fetched_at = payload.get("fetched_at")
        if fetched_at is not None:
            fetched_at = to_iso(parse_iso(fetched_at, "STORED_FETCHED_AT", now))
    except MonitorError:
        return None
    return {
        "posts": posts,
        "fetched_at": fetched_at,
        "coverage": source_coverage(payload["source"], allow_missing=False),
    }


def parse_input(path: Path, now: datetime) -> tuple[list[dict[str, str]], str | None, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MonitorError("INPUT_NOT_FOUND") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise MonitorError("INPUT_INVALID_JSON") from exc

    fetched_at: str | None = None
    coverage = DEFAULT_COVERAGE
    if isinstance(payload, list):
        posts = payload
    elif isinstance(payload, dict):
        coverage = source_coverage(payload.get("source"), allow_missing=True)
        posts = payload.get("posts")
        if payload.get("fetched_at") is not None:
            fetched_at = to_iso(parse_iso(payload["fetched_at"], "INPUT_FETCHED_AT", now))
    else:
        raise MonitorError("INPUT_INVALID_SCHEMA")
    if not isinstance(posts, list) or len(posts) > MAX_POSTS:
        raise MonitorError("INPUT_INVALID_SCHEMA")
    return sort_and_bound_raw(posts, now), fetched_at, coverage


def request_json(url: str, token: str, timeout: float, retries: int, max_backoff: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "aitibo-monitor/1"},
    )
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise MonitorError("X_RESPONSE_INVALID")
            return payload
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                if attempt < retries:
                    try:
                        wait_for = float(exc.headers.get("Retry-After", ""))
                    except ValueError:
                        wait_for = 2**attempt
                    time.sleep(max(0.0, min(wait_for, max_backoff)))
                    continue
                raise MonitorError("X_RATE_LIMITED") from exc
            raise MonitorError(f"X_HTTP_{exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            if attempt < retries:
                time.sleep(min(2**attempt, max_backoff))
                continue
            raise MonitorError("X_NETWORK_ERROR") from exc


def fetch_official_posts(token: str, limit: int, timeout: float, retries: int, max_backoff: float, now: datetime) -> tuple[list[dict[str, str]], str]:
    user_payload = request_json(
        f"https://api.x.com/2/users/by/username/{HANDLE}",
        token,
        timeout,
        retries,
        max_backoff,
    )
    user = user_payload.get("data")
    user_id = user.get("id") if isinstance(user, dict) else None
    if not isinstance(user_id, str) or not re.fullmatch(r"\d{1,30}", user_id):
        raise MonitorError("X_USER_LOOKUP_INVALID")
    query = urllib.parse.urlencode({"max_results": limit, "tweet.fields": "created_at,referenced_tweets"})
    posts_payload = request_json(
        f"https://api.x.com/2/users/{user_id}/tweets?{query}",
        token,
        timeout,
        retries,
        max_backoff,
    )
    data = posts_payload.get("data", [])
    if not isinstance(data, list):
        raise MonitorError("X_RESPONSE_INVALID")
    raw_posts = []
    for item in data:
        if not isinstance(item, dict):
            continue
        references = item.get("referenced_tweets", [])
        is_quote = isinstance(references, list) and any(
            isinstance(reference, dict) and reference.get("type") in {"quoted", "retweeted"}
            for reference in references
        )
        raw_posts.append(
            {
                "id": item.get("id"),
                "url": canonical_post_url(str(item.get("id", ""))),
                "text": item.get("text"),
                "created_at": item.get("created_at"),
                "is_quote": is_quote,
            }
        )
    return sort_and_bound_raw(raw_posts, now), to_iso(now)


class OutputLock:
    def __init__(self, output: Path):
        self.output = output
        self.handle: Any = None

    def __enter__(self) -> "OutputLock":
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.handle = (self.output.parent / (self.output.name + ".lock")).open("a+", encoding="utf-8")
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.handle is not None:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            self.handle.close()


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
            temporary_name = temporary.name
            temporary.write(encoded)
            temporary.flush()
            os.fsync(temporary.fileno())
        # This allowlisted snapshot contains public post data only and is served by nginx.
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def publish_success(
    output: Path,
    posts: list[dict[str, str]],
    fetched_at: str | None,
    coverage: str,
    now: datetime,
) -> dict[str, Any]:
    with OutputLock(output):
        previous = load_snapshot(output, now)
        prior_posts = previous["posts"] if previous else []
        # Preserve classifications with lost quote metadata. A verified longer
        # prefix-completion may repair an earlier non-reset text excerpt only.
        previous_by_id = {post["id"]: post for post in prior_posts}
        additions = []
        for post in posts:
            old = previous_by_id.get(post["id"])
            if old is None or (old["reason"] == "NO_RESET_TERM"
                               and post["created_at"] == old["created_at"]
                               and len(post["text"]) > len(old["text"])
                               and post["text"].startswith(old["text"])):
                additions.append(post)
        merged = sort_and_bound_published([*prior_posts, *additions], now)
        status = {
            "schema_version": SCHEMA_VERSION,
            "source": source_for(coverage),
            "checked_at": to_iso(now),
            "fetched_at": fetched_at,
            "health": "ok",
            "posts": merged,
            "forecast": forecast_for(merged, now),
            "error_code": None,
        }
        atomic_write(output, status)
        return status


def publish_problem(
    output: Path,
    health: str,
    error_code: str,
    now: datetime,
    coverage: str = DEFAULT_COVERAGE,
) -> dict[str, Any]:
    with OutputLock(output):
        previous = load_snapshot(output, now)
        posts = previous["posts"] if previous else []
        fetched_at = previous["fetched_at"] if previous else None
        source_coverage_value = previous["coverage"] if previous else coverage
        status = {
            "schema_version": SCHEMA_VERSION,
            "source": source_for(source_coverage_value),
            "checked_at": to_iso(now) if health == "error" else None,
            "fetched_at": fetched_at,
            "health": health,
            "posts": posts,
            "forecast": forecast_for(posts, now),
            "error_code": error_code,
        }
        atomic_write(output, status)
        return status


def run_monitor(
    output: Path,
    input_path: Path | None,
    token: str | None,
    limit: int,
    timeout: float,
    retries: int,
    max_backoff: float,
    now: datetime | None = None,
) -> tuple[dict[str, Any], int]:
    now = now or utc_now()
    if input_path is None and not token:
        return publish_problem(output, "unconfigured", "UNCONFIGURED_NO_INPUT_OR_TOKEN", now), 0
    coverage = DEFAULT_COVERAGE
    try:
        if input_path is not None:
            posts, fetched_at, coverage = parse_input(input_path, now)
        else:
            coverage = "official_timeline"
            posts, fetched_at = fetch_official_posts(token or "", limit, timeout, retries, max_backoff, now)
        # An empty public-search run is evidence of no usable fetch, not a
        # successful statement that nothing has changed. Keep last known posts.
        if not posts:
            raise MonitorError("NO_VERIFIED_PUBLIC_POSTS")
        return publish_success(output, posts, fetched_at, coverage, now), 0
    except MonitorError as exc:
        return publish_problem(output, "error", exc.code, now, coverage), 2


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/data/aitibo/shared/status.json"))
    parser.add_argument("--input", type=Path, help="verified public X posts JSON; takes precedence over API access")
    parser.add_argument("--limit", type=int, default=20, help="official API post count, bounded to 10-50")
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--max-backoff", type=float, default=30.0)
    args = parser.parse_args(argv)
    if not MIN_FETCH_LIMIT <= args.limit <= MAX_FETCH_LIMIT:
        parser.error("--limit must be between 10 and 50")
    if args.timeout <= 0 or args.retries < 0 or args.max_backoff < 0:
        parser.error("timeout must be positive; retries and max-backoff cannot be negative")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _, exit_code = run_monitor(
        output=args.output,
        input_path=args.input,
        token=os.environ.get("AITIBO_X_BEARER_TOKEN"),
        limit=args.limit,
        timeout=args.timeout,
        retries=args.retries,
        max_backoff=args.max_backoff,
    )
    # Successful no-agent Hermes ticks stay silent; the shared JSON is the API.
    # Failures use a non-zero exit so Hermes can surface its normal error alert.
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
