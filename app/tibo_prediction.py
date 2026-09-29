"""Source-bound translations and an explainable (not probabilistic) signal index."""
from __future__ import annotations
import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
try:
    from .tibo_intent import LANGUAGES, localized, text, timestamp
except ImportError:
    from tibo_intent import LANGUAGES, localized, text, timestamp

MAX_BYTES = 2 * 1024 * 1024
WEIGHTS = {"explicit_reset_plan": 60, "tentative_reset": 35, "dated_window": 20,
           "launch_context": 15, "incident_context": 20, "cancellation": -100}
MAX_AGE = timedelta(hours=24)

def source_deadline(post):
    """Bound explicit relative weekdays to the post date, never to fetch time."""
    local = timestamp(post["created_at"]).astimezone(ZoneInfo("America/Los_Angeles"))
    day = local.replace(hour=0, minute=0, second=0, microsecond=0)
    wording = post["text"].casefold()
    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    mentioned = [(index, name) for index, name in enumerate(weekdays) if re.search(r"\b" + name + r"\b", wording)]
    if len(mentioned) == 1:
        for index, name in mentioned:
            offset = (index - day.weekday()) % 7
            if offset == 0 and "next " + name in wording:
                offset = 7
            return day + timedelta(days=offset + 1)
    if "next week" in wording:
        return day + timedelta(days=14 - day.weekday())
    if "tomorrow" in wording:
        return day + timedelta(days=2)
    if re.search(r"\btoday\b", wording):
        return day + timedelta(days=1)
    return None

def read_json(path):
    with Path(path).open("rb") as handle:
        value = handle.read(MAX_BYTES + 1)
    if len(value) > MAX_BYTES:
        raise ValueError("size")
    return json.loads(value)

def project_translations(raw, snapshot):
    """Exact original text lets unchanged posts reuse previous translations."""
    result = {}
    if not isinstance(raw, dict) or not isinstance(raw.get("translations"), dict):
        return result
    for post in snapshot.get("posts", []):
        try:
            entry = raw["translations"][post["id"]]
            if entry["original_text"] != post["text"]:
                continue
            result[post["id"]] = {lang: text(entry["locales"][lang], 4000) for lang in LANGUAGES}
        except (KeyError, TypeError, ValueError):
            continue
    return result

def validate_prediction(raw, snapshot, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        if raw.get("schema_version") != 1 or snapshot.get("health") != "ok":
            return None
        fetched, generated = timestamp(snapshot["fetched_at"]), timestamp(raw["generated_at"])
        if raw["source_fetched_at"] != snapshot["fetched_at"] or generated < fetched:
            return None
        if not timedelta(0) <= now - generated <= MAX_AGE or not timedelta(0) <= now - fetched <= MAX_AGE:
            return None
        start, end = timestamp(raw["window_start"]), timestamp(raw["window_end"])
        if not generated - timedelta(days=1) <= start < end <= generated + timedelta(days=14) or end <= now:
            return None
        if raw["timezone"] != "America/Los_Angeles":
            return None
        posts = {p["id"]: p for p in snapshot["posts"]}
        if not posts or not isinstance(raw["signals"], list) or len(raw["signals"]) > len(WEIGHTS):
            return None
        signals, codes = [], set()
        for item in raw["signals"]:
            code, post_id = item["code"], item["post_id"]
            quote = text(item["quote"], 200)
            post = posts[post_id]
            if code not in WEIGHTS or code in codes or quote not in post["text"]:
                return None
            if timestamp(post["created_at"]) < generated - timedelta(days=14):
                return None
            if code == "incident_context":
                incident_at = timestamp(post["created_at"])
                # A completed later reset closes the compensation opportunity.
                if incident_at < generated - timedelta(days=3) or post.get("kind") == "reset" or any(
                    p.get("kind") == "reset" and timestamp(p["created_at"]) >= incident_at
                    for p in posts.values()
                ):
                    return None
            if code in {"explicit_reset_plan", "tentative_reset", "dated_window"} and (
                post.get("kind") == "reset" or post.get("reason") in {
                    "QUOTED_OR_REPOST", "RESET_CREDIT_EXCLUDED", "NEGATED_RESET_CLAIM"}
            ):
                return None
            # Resolve relative weekdays from the source's date, not fetch time.
            relevant_until = timestamp(item["relevant_until"])
            if code == "incident_context" and relevant_until > timestamp(post["created_at"]) + timedelta(days=3):
                return None
            if not max(start, generated) < relevant_until <= end:
                return None
            deadline = source_deadline(post)
            if deadline is not None and (deadline <= generated or relevant_until > deadline):
                return None
            codes.add(code)
            signals.append({"code": code, "post_id": post_id, "quote": quote, "points": WEIGHTS[code]})
        if "dated_window" in codes and not codes.intersection({"explicit_reset_plan", "tentative_reset"}):
            return None
        if "explicit_reset_plan" in codes and "tentative_reset" in codes:
            return None
        score = min(95, max(0, sum(item["points"] for item in signals)))
        return {"schema_version": 1, "generated_at": raw["generated_at"],
                "source_fetched_at": raw["source_fetched_at"], "score": score, "scale": 100,
                "kind": "signal_index", "methodology_version": "signals-v1",
                "window_start": raw["window_start"], "window_end": raw["window_end"],
                "timezone": raw["timezone"], "signals": signals,
                "locales": localized(raw["locales"], ("summary", "uncertainty"))}
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return None

def load_enrichment(path, snapshot):
    try:
        raw = read_json(path)
        return project_translations(raw, snapshot), validate_prediction(raw.get("prediction", {}), snapshot) if isinstance(raw, dict) else None
    except (OSError, ValueError, UnicodeError, RecursionError):
        return {}, None

def prepare(status_path, cache_path, candidate_path):
    snapshot = read_json(status_path)
    try:
        cached = read_json(cache_path)
    except (OSError, ValueError, UnicodeError, RecursionError):
        cached = {}
    reusable = project_translations(cached, snapshot)
    latest = sorted(snapshot.get("posts", []), key=lambda p: timestamp(p["created_at"]), reverse=True)[:10]
    candidate = {"schema_version": 1, "translations": {
        p["id"]: {"original_text": p["text"], "locales": reusable[p["id"]]}
        for p in snapshot.get("posts", []) if p["id"] in reusable}, "prediction": {}}
    Path(candidate_path).write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
    return {"source_fetched_at": snapshot.get("fetched_at"),
            "translation_required": [{"id": p["id"], "text": p["text"]} for p in latest if p["id"] not in reusable]}

def publish(input_path, status_path, output_path):
    snapshot, raw = read_json(status_path), read_json(input_path)
    translations = project_translations(raw, snapshot)
    latest = sorted(snapshot.get("posts", []), key=lambda p: timestamp(p["created_at"]), reverse=True)[:10]
    if not latest or any(p["id"] not in translations for p in latest):
        raise ValueError("translate all displayed posts in seven languages")
    prediction = validate_prediction(raw.get("prediction", {}), snapshot)
    if prediction is None:
        raise ValueError("invalid prediction evidence or window")
    deadlines = {item["code"]: item["relevant_until"] for item in raw["prediction"]["signals"]}
    prediction["signals"] = [{**item, "relevant_until": deadlines[item["code"]]} for item in prediction["signals"]]
    clean = {"schema_version": 1, "translations": {
        p["id"]: {"original_text": p["text"], "locales": translations[p["id"]]}
        for p in snapshot["posts"] if p["id"] in translations}, "prediction": prediction}
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as handle:
            temporary = handle.name
            json.dump(clean, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        current = read_json(status_path)
        if current.get("health") != "ok" or current.get("fetched_at") != snapshot.get("fetched_at") or current.get("posts") != snapshot.get("posts"):
            raise ValueError("source changed")
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input")
    parser.add_argument("--status", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--cache")
    args = parser.parse_args()
    if args.prepare:
        if not args.cache:
            parser.error("--prepare requires --cache")
        print(json.dumps(prepare(args.status, args.cache, args.output), ensure_ascii=False))
        return 0
    if not args.input:
        parser.error("--input required for publishing")
    try:
        publish(args.input, args.status, args.output)
    except (OSError, KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        print('{"published":false,"reason":"INVALID_ENRICHMENT_OR_CHANGED_SOURCE"}')
        return 2
    print('{"published":true,"kind":"signal_index","languages":7}')
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
