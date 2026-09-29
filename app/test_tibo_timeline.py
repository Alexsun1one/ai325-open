import unittest
from datetime import datetime, timezone
from app.tibo_timeline import project_timeline, source_window

NOW = datetime(2026, 9, 27, 5, tzinfo=timezone.utc)
LAST = {"id": "1", "kind": "reset", "created_at": "2026-09-26T18:17:54Z", "url": "https://x.com/thsottiaux/status/1", "text": "Resets all propagated."}
NEXT = {"id": "2", "kind": "promise", "created_at": "2026-09-26T21:41:35Z", "url": "https://x.com/thsottiaux/status/2", "text": "Sorry Gia. More resets coming next week"}
SNAP = {"posts": [NEXT, LAST], "health": "ok", "fetched_at": NOW.isoformat()}

def prediction(*codes):
    return {"source_fetched_at": NOW.isoformat(), "window_end": "2026-10-05T07:00:00Z",
            "signals": [{"code": c, "post_id": "2"} for c in codes]}

class TimelineTests(unittest.TestCase):
    def test_last_completion_and_next_week_coexist(self):
        result = project_timeline(SNAP, prediction("explicit_reset_plan", "dated_window"), NOW)
        self.assertEqual(result["last_reset"]["reported_at"], LAST["created_at"])
        self.assertEqual(result["next_reset"]["status"], "announced")
        self.assertEqual(result["next_reset"]["window_start"], "2026-09-28T07:00:00+00:00")
        self.assertEqual(result["next_reset"]["window_end"], "2026-10-05T07:00:00+00:00")

    def test_observation_horizon_is_not_an_announced_reset_date(self):
        for codes, status in [(('launch_context',), 'possible'), (('explicit_reset_plan',), 'announced'), ((), 'unknown')]:
            result = project_timeline(SNAP, prediction(*codes), NOW)["next_reset"]
            self.assertEqual(result["status"], status)
            self.assertIsNone(result["window_start"])

    def test_stale_failed_or_changed_sources_keep_history_only(self):
        for snap in [{**SNAP, "health": "error"}, {**SNAP, "fetched_at": "2026-09-20T00:00:00Z"}]:
            result = project_timeline(snap, prediction("explicit_reset_plan"), NOW)
            self.assertFalse(result["fresh"])
            self.assertEqual(result["last_reset"]["reported_at"], LAST["created_at"])
            self.assertEqual(result["next_reset"]["status"], "unknown")
        self.assertEqual(project_timeline({**SNAP, "fetched_at": "2026-09-27T04:59:00Z"}, prediction("explicit_reset_plan"), NOW)["next_reset"]["status"], "unknown")

    def test_cancelled_future_does_not_erase_completed_history(self):
        result = project_timeline(SNAP, prediction("explicit_reset_plan", "cancellation"), NOW)
        self.assertIsNotNone(result["last_reset"])
        self.assertEqual(result["next_reset"]["status"], "unknown")

    def test_weekdays_anchor_to_publication_and_handle_dst(self):
        start, end = source_window({**NEXT, "text": "Reset next Tuesday."})
        self.assertEqual(start.isoformat(), "2026-09-29T00:00:00-07:00")
        start, end = source_window({**NEXT, "created_at": "2026-10-31T20:00:00Z"})
        self.assertEqual(start.isoformat(), "2026-11-02T00:00:00-08:00")
        self.assertIsNone(source_window({**NEXT, "text": "Monday or Tuesday, we will confirm."}))

    def test_empty_snapshot_has_no_invented_dates(self):
        result = project_timeline({"posts": [], "health": "unconfigured"}, None, NOW)
        self.assertIsNone(result["last_reset"])
        self.assertIsNone(result["next_reset"]["window_end"])

if __name__ == "__main__":
    unittest.main()
