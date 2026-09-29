import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import tibo_monitor as monitor


NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def raw_post(post_id="2077212009071075330", text="I reset the limits.", created_at="2026-09-26T11:00:00Z"):
    return {
        "id": post_id,
        "url": f"https://x.com/thsottiaux/status/{post_id}",
        "text": text,
        "created_at": created_at,
    }


class TiboMonitorTests(unittest.TestCase):
    def test_next_week_reply_is_future_and_preserves_completed_reset(self):
        reply = "@giadotai Sorry Gia. More resets coming next week"
        self.assertEqual(monitor.classify_post(reply, {})[0], "promise")
        self.assertEqual(monitor.classify_post(reply, {"quoted": True})[1], "QUOTED_OR_REPOST")
        self.assertNotEqual(monitor.classify_post(reply + "?", {})[0], "promise")

    def test_propagation_is_completion_but_not_future_or_negated(self):
        for content in ["Resets all propagated. That will be all.", "Resets have all completed."]:
            self.assertEqual(monitor.classify_post(content, {})[0], "reset")
        for content in ["Resets have not all propagated.", "Resets will all propagate soon.", "Have resets all propagated?", "If resets all propagated, we would be done."]:
            self.assertNotEqual(monitor.classify_post(content, {})[0], "reset")

    def test_promise_and_banked_credit_are_different(self):
        self.assertEqual(monitor.classify_post("I promised a reset for Tuesday. See you soon.", {})[0], "promise")
        self.assertEqual(monitor.classify_post("We have added a banked reset to everyone's account.", {})[1], "RESET_CREDIT_EXCLUDED")

    def test_legacy_ambiguous_can_upgrade_but_quoted_cannot(self):
        post = {**raw_post(text="Resets all propagated."), "kind":"other", "reason":"AMBIGUOUS_RESET_MENTION"}
        self.assertEqual(monitor.validate_published_post(post,NOW)["kind"], "reset")
        post["reason"] = "QUOTED_OR_REPOST"
        self.assertEqual(monitor.validate_published_post(post,NOW)["kind"], "other")

    def test_negated_reset_is_not_reset(self):
        post = monitor.normalize_post(raw_post(text="I did not reset anything."), NOW)
        self.assertEqual(post["kind"], "other")
        self.assertEqual(post["reason"], "NEGATED_RESET_CLAIM")

    def test_reset_credit_is_excluded(self):
        post = monitor.normalize_post(raw_post(text="We issued reset credits today."), NOW)
        self.assertEqual(post["kind"], "other")
        self.assertEqual(post["reason"], "RESET_CREDIT_EXCLUDED")

    def test_compound_promised_reset_coupon_is_excluded(self):
        post = monitor.normalize_post(raw_post(text="That promisedresetcoupon is unavailable."), NOW)
        self.assertEqual(post["kind"], "other")
        self.assertEqual(post["reason"], "RESET_CREDIT_EXCLUDED")

    def test_quoted_text_is_excluded(self):
        post = monitor.normalize_post(raw_post(text="“I reset all limits”", created_at="2026-09-26T10:00:00Z"), NOW)
        self.assertEqual(post["kind"], "other")
        self.assertEqual(post["reason"], "QUOTED_OR_REPOST")

    def test_question_and_habitual_reset_are_excluded(self):
        question = monitor.normalize_post(raw_post(text="Did I reset all Codex limits?"), NOW)
        habitual = monitor.normalize_post(raw_post(text="I reset all Codex limits every Sunday."), NOW)
        usual = monitor.normalize_post(raw_post(text="I usually reset the limits after maintenance."), NOW)
        self.assertEqual(question["reason"], "QUESTIONED_RESET_CLAIM")
        self.assertEqual(habitual["reason"], "HABITUAL_RESET_MENTION")
        self.assertEqual(usual["reason"], "HABITUAL_RESET_MENTION")

    def test_requested_reset_is_excluded(self):
        post = monitor.normalize_post(raw_post(text="Please reset all Codex limits."), NOW)
        self.assertEqual(post["kind"], "other")
        self.assertEqual(post["reason"], "REQUESTED_RESET")

    def test_reset_with_embedded_link_is_a_reference(self):
        post = monitor.normalize_post(raw_post(text="See https://example.test/post: I reset all limits."), NOW)
        self.assertEqual(post["kind"], "other")
        self.assertEqual(post["reason"], "EMBEDDED_LINK_REFERENCE")

    def test_malicious_link_is_rejected(self):
        post = raw_post()
        post["url"] = "https://evil.example/x.com/thsottiaux/status/2077212009071075330"
        with self.assertRaisesRegex(monitor.MonitorError, "POST_URL_REJECTED"):
            monitor.normalize_post(post, NOW)

    def test_future_post_is_rejected(self):
        future = (NOW + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
        with self.assertRaisesRegex(monitor.MonitorError, "POST_CREATED_AT_FUTURE"):
            monitor.normalize_post(raw_post(created_at=future), NOW)

    def test_no_input_or_token_is_unconfigured_without_posts(self):
        with tempfile.TemporaryDirectory() as directory:
            status, exit_code = monitor.run_monitor(Path(directory) / "status.json", None, None, 20, 1, 0, 0, NOW)
        self.assertEqual(exit_code, 0)
        self.assertEqual(status["health"], "unconfigured")
        self.assertEqual(status["posts"], [])
        self.assertEqual(status["error_code"], "UNCONFIGURED_NO_INPUT_OR_TOKEN")

    def test_failure_retains_last_valid_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "status.json"
            good_input = root / "good.json"
            good_input.write_text(
                json.dumps({"source": monitor.SOURCE, "fetched_at": "2026-09-26T11:30:00Z", "posts": [raw_post()]}),
                encoding="utf-8",
            )
            success, success_exit = monitor.run_monitor(output, good_input, None, 20, 1, 0, 0, NOW)
            self.assertEqual(success_exit, 0)
            self.assertEqual(success["health"], "ok")

            failed, failed_exit = monitor.run_monitor(output, root / "missing.json", None, 20, 1, 0, 0, NOW)
            self.assertEqual(failed_exit, 2)
            self.assertEqual(failed["health"], "error")
            self.assertEqual(failed["error_code"], "INPUT_NOT_FOUND")
            self.assertEqual(failed["posts"][0]["id"], "2077212009071075330")

    def test_quote_metadata_is_classified_once_and_survives_snapshot_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "status.json"
            quote_input = root / "quote.json"
            quoted = raw_post(text="I reset all Codex limits.")
            quoted["is_quote"] = True
            quote_input.write_text(json.dumps({"source": monitor.SOURCE, "posts": [quoted]}), encoding="utf-8")

            published, published_exit = monitor.run_monitor(output, quote_input, None, 20, 1, 0, 0, NOW)
            reloaded, reloaded_exit = monitor.run_monitor(output, root / "missing.json", None, 20, 1, 0, 0, NOW)

        self.assertEqual(published_exit, 0)
        self.assertEqual(published["posts"][0]["kind"], "other")
        self.assertEqual(published["posts"][0]["reason"], "QUOTED_OR_REPOST")
        self.assertEqual(reloaded_exit, 2)
        self.assertEqual(reloaded["posts"][0]["kind"], "other")
        self.assertEqual(reloaded["posts"][0]["reason"], "QUOTED_OR_REPOST")

    def test_collector_supplied_kind_is_ignored(self):
        raw = raw_post(text="I will reset the limits later today.")
        raw["kind"] = "reset"
        raw["reason"] = "EXPLICIT_PAST_PUBLIC_CLAIM"
        post = monitor.normalize_post(raw, NOW)
        self.assertEqual(post["kind"], "promise")
        self.assertEqual(post["reason"], "EXPLICIT_FUTURE_PUBLIC_CLAIM")

    def test_empty_public_search_is_error_and_retains_last_post(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "status.json"
            good_input = root / "good.json"
            good_input.write_text(
                json.dumps({"source": monitor.SOURCE, "posts": [raw_post()]}),
                encoding="utf-8",
            )
            monitor.run_monitor(output, good_input, None, 20, 1, 0, 0, NOW)

            empty_input = root / "empty.json"
            empty_input.write_text(
                json.dumps({"source": monitor.SOURCE, "fetched_at": "2026-09-26T12:00:00Z", "posts": []}),
                encoding="utf-8",
            )
            failed, failed_exit = monitor.run_monitor(output, empty_input, None, 20, 1, 0, 0, NOW)

        self.assertEqual(failed_exit, 2)
        self.assertEqual(failed["health"], "error")
        self.assertEqual(failed["error_code"], "NO_VERIFIED_PUBLIC_POSTS")
        self.assertEqual(failed["posts"][0]["id"], "2077212009071075330")
        self.assertEqual(failed["source"]["coverage"], "public_search")

    def test_input_default_and_official_timeline_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            public_output = root / "public-status.json"
            public_input = root / "public.json"
            public_input.write_text(json.dumps({"posts": [raw_post()]}), encoding="utf-8")
            public_status, public_exit = monitor.run_monitor(public_output, public_input, None, 20, 1, 0, 0, NOW)

            official_output = root / "official-status.json"
            official_input = root / "official.json"
            official_input.write_text(
                json.dumps({"source": {**monitor.SOURCE_BASE, "coverage": "official_timeline"}, "posts": [raw_post()]}),
                encoding="utf-8",
            )
            official_status, official_exit = monitor.run_monitor(official_output, official_input, None, 20, 1, 0, 0, NOW)

        self.assertEqual(public_exit, 0)
        self.assertEqual(public_status["source"]["coverage"], "public_search")
        self.assertEqual(official_exit, 0)
        self.assertEqual(official_status["source"]["coverage"], "official_timeline")

    def test_stale_public_claim_does_not_keep_reset_state(self):
        post = monitor.normalize_post(
            raw_post(created_at="2026-09-24T11:00:00Z", text="I reset all Codex limits."),
            NOW,
        )
        forecast = monitor.forecast_for([post], NOW)
        self.assertEqual(forecast["state"], "waiting")
        self.assertEqual(forecast["reason"], "PUBLIC_RESET_SIGNAL_STALE")
        self.assertEqual(forecast["last_reset_at"], "2026-09-24T11:00:00Z")

    def test_fresh_promise_is_soon_not_reset(self):
        post = monitor.normalize_post(raw_post(text="I will reset the limits later today."), NOW)
        forecast = monitor.forecast_for([post], NOW)
        self.assertEqual(post["kind"], "promise")
        self.assertEqual(forecast["state"], "soon")


class PredictionAuditRegressionTests(unittest.TestCase):
    def test_verified_full_text_can_complete_an_old_non_reset_excerpt(self):
        prefix = 'New models are out. And one more thing.'
        old = monitor.normalize_post(raw_post(text=prefix), NOW)
        full = monitor.normalize_post(raw_post(text=prefix+' We are adding a banked reset to all paid accounts.'), NOW)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'status.json'
            monitor.publish_success(output, [old], monitor.to_iso(NOW), 'public_search', NOW)
            updated = monitor.publish_success(output, [full], monitor.to_iso(NOW), 'public_search', NOW)
        self.assertEqual(updated['posts'][0]['text'], full['text'])
        self.assertEqual(updated['posts'][0]['reason'], 'RESET_CREDIT_EXCLUDED')

    def test_unrelated_reset_is_not_a_quota_claim(self):
        post = monitor.normalize_post(raw_post(text="I reset my router."), NOW)
        self.assertEqual(post['kind'], 'other')

    def test_completed_today_is_not_a_future_promise(self):
        post = monitor.normalize_post(raw_post(text="We have reset all Codex limits today."), NOW)
        self.assertEqual(post['kind'], 'reset')

    def test_explicit_cancellation_supersedes_older_promise(self):
        promise = monitor.normalize_post(raw_post(text="We will reset Codex limits tomorrow.", created_at=(NOW-timedelta(hours=1)).isoformat()), NOW)
        cancel = monitor.normalize_post({**raw_post(text="We will not reset Codex limits tomorrow.", created_at=(NOW-timedelta(minutes=1)).isoformat()), 'id':'2', 'url':monitor.canonical_post_url('2')}, NOW)
        forecast = monitor.forecast_for([cancel, promise], NOW)
        self.assertEqual(forecast['state'], 'waiting')
        self.assertEqual(forecast['reason'], 'CANCELLED_PUBLIC_RESET_PLAN')

    def test_not_completed_yet_does_not_cancel_a_promise(self):
        promise = monitor.normalize_post(raw_post(text="We will reset Codex limits tomorrow.", created_at=(NOW-timedelta(hours=1)).isoformat()), NOW)
        update = monitor.normalize_post({**raw_post(text="We have not reset Codex limits yet.", created_at=(NOW-timedelta(minutes=1)).isoformat()), 'id':'2', 'url':monitor.canonical_post_url('2')}, NOW)
        self.assertEqual(monitor.forecast_for([update, promise], NOW)['state'], 'soon')

if __name__ == "__main__":
    unittest.main()
