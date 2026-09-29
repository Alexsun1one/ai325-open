"""Separate historical completion reports from source-dated future plans."""
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo

try:
    from .tibo_intent import timestamp
except ImportError:
    from tibo_intent import timestamp

PACIFIC = "America/Los_Angeles"


def source_window(post):
    """Resolve relative calendar words at publication time, not collection time."""
    day = timestamp(post["created_at"]).astimezone(ZoneInfo(PACIFIC)).replace(hour=0, minute=0, second=0, microsecond=0)
    wording = post["text"].casefold()
    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    mentioned = [i for i, name in enumerate(weekdays) if re.search(r"\b" + name + r"\b", wording)]
    if len(mentioned) == 1:
        index = mentioned[0]
        offset = (index - day.weekday()) % 7
        if offset == 0 and "next " + weekdays[index] in wording:
            offset = 7
        start = day + timedelta(days=offset)
        return start, start + timedelta(days=1)
    if len(mentioned) > 1:
        return None  # Multiple dates require more context; don't select one.
    if "next week" in wording:
        start = day + timedelta(days=7 - day.weekday())
        return start, start + timedelta(days=7)
    if "tomorrow" in wording:
        return day + timedelta(days=1), day + timedelta(days=2)
    if re.search(r"\btoday\b", wording):
        return day, day + timedelta(days=1)
    return None


def project_timeline(snapshot, prediction, now=None):
    """Called only after the public snapshot and prediction validators."""
    now = now or datetime.now(timezone.utc)
    posts = {p["id"]: p for p in snapshot.get("posts", [])}
    completed = [p for p in posts.values() if p["kind"] == "reset"]
    last = max(completed, key=lambda p: timestamp(p["created_at"]), default=None)
    next_reset = {"status": "unknown", "window_start": None, "window_end": None,
                  "time_basis": "unspecified", "timezone": PACIFIC, "source_url": None}
    result = {"last_reset": {"reported_at": last["created_at"], "source_url": last["url"]} if last else None,
              "next_reset": next_reset, "fresh": False}
    fetched = snapshot.get("fetched_at")
    if snapshot.get("health") != "ok" or not fetched or not timedelta(0) <= now - timestamp(fetched) <= timedelta(days=1):
        return result
    result["fresh"] = True
    if not prediction or prediction.get("source_fetched_at") != fetched or timestamp(prediction["window_end"]) <= now:
        return result
    signals = {s["code"]: s for s in prediction["signals"]}
    if "cancellation" in signals:
        return result
    plan = signals.get("explicit_reset_plan") or signals.get("tentative_reset")
    if plan:
        next_reset["status"] = "announced" if "explicit_reset_plan" in signals else "possible"
        next_reset["source_url"] = posts[plan["post_id"]]["url"]
        dated = signals.get("dated_window")
        window = source_window(posts[dated["post_id"]]) if dated else None
        if window and window[1] > now:
            next_reset.update(window_start=window[0].astimezone(timezone.utc).isoformat(),
                              window_end=window[1].astimezone(timezone.utc).isoformat(),
                              time_basis="source_calendar")
    else:
        context = signals.get("launch_context") or signals.get("incident_context")
        if context:
            next_reset.update(status="possible", source_url=posts[context["post_id"]]["url"])
    return result
