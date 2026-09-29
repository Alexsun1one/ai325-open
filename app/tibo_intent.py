"""Validate and publish source-bound Hermes interpretations of public posts.

Pure stdlib: the same file runs beside the VPS collector and in the API.
It validates provenance, never turns an interpretation into an account reset.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

LANGUAGES = ("zh-CN", "en", "ja", "fr", "es", "pt", "ko")
MAX_AGE = timedelta(hours=24)
MAX_BYTES = 256 * 1024
OUTLOOKS = {"reset_reported", "reset_signals", "product_teasing", "no_reset_signal", "unclear"}
INTENTS = {"completion", "promise", "compensation", "promotion", "humor", "unrelated", "ambiguous"}


def timestamp(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timezone")
    return result


def text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
        raise ValueError("text")
    return value.strip()


def localized(raw, fields):
    if not isinstance(raw, dict):
        raise ValueError("locales")
    return {lang: {field: text(raw[lang][field], 1000) for field in fields} for lang in LANGUAGES}


def validate_intent(raw, snapshot, now=None):
    """Return a public allowlist projection, or None for stale/invalid analysis."""
    now = now or datetime.now(timezone.utc)
    try:
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            return None
        if snapshot.get("health") != "ok" or raw.get("scope") != "public_posts_not_private_intent":
            return None
        generated = timestamp(raw.get("generated_at"))
        fetched = timestamp(snapshot.get("fetched_at"))
        if not timedelta(0) <= now - generated <= MAX_AGE or not timedelta(0) <= now - fetched <= MAX_AGE:
            return None
        if raw.get("source_fetched_at") != snapshot.get("fetched_at") or generated < fetched:
            return None
        outlook, confidence = raw.get("outlook"), raw.get("confidence")
        if outlook not in OUTLOOKS or confidence not in {"low", "medium", "high"}:
            return None
        posts = {post["id"]: post for post in snapshot["posts"]}
        entries = raw.get("evidence")
        if not isinstance(entries, list) or not 1 <= len(entries) <= 6:
            return None
        evidence, seen = [], set()
        for item in entries:
            post_id = item["post_id"]
            post = posts[post_id]
            quote = text(item["quote"], 200)
            if post_id in seen or quote not in post["text"]:
                return None
            if item["intent"] not in INTENTS or item["strength"] not in {"direct", "indirect"}:
                return None
            seen.add(post_id)
            evidence.append({
                "post_id": post_id, "quote": quote, "intent": item["intent"], "strength": item["strength"],
                "locales": localized(item["locales"], ("reading", "reset_relevance")),
            })
        # A complete interpretation must include the latest collected statement.
        latest = max(snapshot["posts"], key=lambda post: timestamp(post["created_at"]))
        if latest["id"] not in seen:
            return None
        return {
            "schema_version": 1, "scope": raw["scope"], "generated_at": raw["generated_at"],
            "source_fetched_at": raw["source_fetched_at"], "outlook": outlook, "confidence": confidence,
            "locales": localized(raw["locales"], ("summary", "rationale", "counter_evidence", "watch_next")),
            "evidence": evidence,
        }
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def read_json(path):
    with Path(path).open("rb") as handle:
        content = handle.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ValueError("size")
    return json.loads(content)


def load_intent(path, snapshot):
    try:
        return validate_intent(read_json(path), snapshot)
    except (OSError, ValueError, UnicodeError, RecursionError):
        return None


def publish_intent(input_path, status_path, output_path):
    snapshot = read_json(status_path)
    result = validate_intent(read_json(input_path), snapshot)
    if result is None:
        raise ValueError("invalid analysis")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as handle:
            temporary = handle.name
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        # A source update while the LLM was writing invalidates its interpretation.
        current = read_json(status_path)
        if current.get("fetched_at") != snapshot.get("fetched_at") or current.get("posts") != snapshot.get("posts"):
            raise ValueError("source changed")
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = publish_intent(args.input, args.status, args.output)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        print('{"published":false,"reason":"INVALID_OR_CHANGED_EVIDENCE"}')
        return 2
    print(json.dumps({"published": True, "evidence_count": len(result["evidence"]), "outlook": result["outlook"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
