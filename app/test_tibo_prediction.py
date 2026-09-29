import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from app.tibo_prediction import LANGUAGES, load_enrichment, prepare, project_translations, publish, validate_prediction

NOW = datetime(2026, 9, 27, 4, tzinfo=timezone.utc)
STAMP = (NOW - timedelta(minutes=1)).isoformat()
POST = {"id": "123", "created_at": "2026-09-24T05:39:27Z", "text": "Can't wait for DevDay next Tuesday.", "kind": "other", "reason": "NO_RESET_TERM"}
SNAPSHOT = {"health": "ok", "fetched_at": STAMP, "posts": [POST]}

def prediction():
    return {"schema_version": 1, "generated_at": STAMP, "source_fetched_at": STAMP,
            "window_start": STAMP, "window_end": "2026-10-04T04:00:00Z", "timezone": "America/Los_Angeles",
            "signals": [{"code": "launch_context", "post_id": "123", "quote": POST["text"], "relevant_until": "2026-09-30T07:00:00Z"}],
            "locales": {lang: {"summary": "Launch context, not a reset promise", "uncertainty": "A reset is unconfirmed"} for lang in LANGUAGES}}

class PredictionTests(unittest.TestCase):
    def test_score_is_derived_and_not_model_supplied_probability(self):
        p = prediction(); p["score"] = 99; p["private"] = "hidden"
        result = validate_prediction(p, SNAPSHOT, NOW)
        self.assertEqual(result["score"], 15)
        self.assertEqual(result["kind"], "signal_index")
        self.assertNotIn("private", result)
    def test_duplicate_or_invented_evidence_cannot_inflate_score(self):
        for field, value in [("quote", "I promise a reset"), ("post_id", "999")]:
            p = prediction(); p["signals"][0][field] = value
            self.assertIsNone(validate_prediction(p, SNAPSHOT, NOW))
        p = prediction(); p["signals"] *= 2
        self.assertIsNone(validate_prediction(p, SNAPSHOT, NOW))
    def test_old_tuesday_does_not_roll_forward_when_recollected(self):
        post = {**POST, "created_at": "2026-09-22T04:31:32Z", "text": "I promised a reset for Tuesday.", "kind": "promise"}
        p = prediction(); p["signals"][0].update(code="explicit_reset_plan", quote=post["text"])
        self.assertIsNone(validate_prediction(p, {**SNAPSHOT, "posts": [post]}, NOW))
    def test_completed_reset_cannot_raise_next_reset_score(self):
        p = prediction(); p["signals"][0]["code"] = "explicit_reset_plan"
        self.assertIsNone(validate_prediction(p, {**SNAPSHOT, "posts": [{**POST, "kind": "reset"}]}, NOW))
    def test_dated_launch_is_not_a_dated_reset_promise(self):
        p = prediction(); p["signals"][0]["code"] = "dated_window"
        self.assertIsNone(validate_prediction(p, SNAPSHOT, NOW))
    def test_recent_incident_adds_context_until_a_later_reset(self):
        post = {**POST, "created_at": "2026-09-26T12:00:00Z", "text": "Codex is down; we are investigating."}
        p = prediction(); p["signals"][0].update(code="incident_context", quote=post["text"], relevant_until="2026-09-29T12:00:00Z")
        snapshot = {**SNAPSHOT, "posts": [post]}
        self.assertEqual(validate_prediction(p, snapshot, NOW)["score"], 20)
        reset = {**post, "id": "456", "kind": "reset", "created_at": "2026-09-26T18:00:00Z"}
        self.assertIsNone(validate_prediction(p, {**snapshot, "posts": [post, reset]}, NOW))
        p["signals"][0]["relevant_until"] = "2026-09-30T12:00:00Z"
        self.assertIsNone(validate_prediction(p, snapshot, NOW))
    def test_stale_failed_and_changed_sources_are_hidden(self):
        for snapshot in [{**SNAPSHOT, "health": "error"}, {**SNAPSHOT, "fetched_at": NOW.isoformat()}]:
            self.assertIsNone(validate_prediction(prediction(), snapshot, NOW))
        self.assertIsNone(validate_prediction(prediction(), SNAPSHOT, NOW + timedelta(days=2)))
    def test_translations_bind_to_text_but_survive_new_fetch(self):
        raw = {"translations": {"123": {"original_text": POST["text"], "locales": {lang: "Translated text" for lang in LANGUAGES}}}}
        self.assertEqual(len(project_translations(raw, SNAPSHOT)["123"]), 7)
        self.assertEqual(project_translations(raw, {**SNAPSHOT, "posts": [{**POST, "text": "Changed"}]}), {})
        del raw["translations"]["123"]["locales"]["ko"]
        self.assertEqual(project_translations(raw, SNAPSHOT), {})
    def test_publish_and_prepare_reuse_complete_translations(self):
        now = datetime.now(timezone.utc)
        stamp = (now-timedelta(seconds=2)).isoformat()
        post = {**POST, "text": "Upcoming product launch.", "created_at": stamp}
        snapshot = {**SNAPSHOT, "fetched_at": stamp, "posts": [post]}
        pred = prediction()
        pred.update(generated_at=stamp, source_fetched_at=stamp, window_start=stamp, window_end=(now+timedelta(days=7)).isoformat())
        pred['signals'][0].update(quote=post['text'], relevant_until=(now+timedelta(days=2)).isoformat())
        raw = {'translations': {'123': {'original_text': post['text'], 'locales': {lang: 'Translation' for lang in LANGUAGES}}}, 'prediction': pred}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'status.json').write_text(json.dumps(snapshot))
            (root/'input.json').write_text(json.dumps(raw))
            publish(root/'input.json', root/'status.json', root/'enrichment.json')
            translations, score = load_enrichment(root/'enrichment.json', snapshot)
            self.assertEqual(score['score'],15)
            self.assertEqual(len(translations['123']),7)
            required = prepare(root/'status.json', root/'enrichment.json', root/'next.json')
            self.assertEqual(required['translation_required'], [])
            raw['translations'] = {}
            (root/'input.json').write_text(json.dumps(raw))
            with self.assertRaises(ValueError):
                publish(root/'input.json', root/'status.json', root/'enrichment.json')
            self.assertTrue(load_enrichment(root/'enrichment.json',snapshot)[1])
    def test_missing_file_is_unknown_not_zero_probability(self):
        self.assertEqual(load_enrichment('/nonexistent/tibo-enrichment.json', SNAPSHOT), ({}, None))

if __name__ == "__main__":
    unittest.main()
