import json
import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import tibo_status
from app.static_delivery import PublicStaticDeliveryMiddleware
from app.test_product_performance import _env, _run


def valid_snapshot() -> dict:
    post = {
        "id": "2077212009071075330",
        "url": "https://x.com/thsottiaux/status/2077212009071075330",
        "text": "I reset all Codex limits.",
        "created_at": "2025-09-26T11:00:00Z",
        "kind": "reset",
        "reason": "EXPLICIT_PAST_PUBLIC_CLAIM",
    }
    return {
        "schema_version": 1,
        "source": {
            "platform": "x",
            "handle": "thsottiaux",
            "url": "https://x.com/thsottiaux",
            "coverage": "public_search",
        },
        "checked_at": "2025-09-26T12:00:00Z",
        "fetched_at": "2025-09-26T12:00:00Z",
        "health": "ok",
        "posts": [post],
        "forecast": {
            "state": "reset",
            "reason": "PUBLIC_RESET_CLAIM_NOT_ACCOUNT_CONFIRMATION",
            "source_url": post["url"],
            "last_reset_at": post["created_at"],
        },
        "error_code": None,
        "private_debug": "/data/aitibo/shared/status.json",
    }


class TiboStatusTests(unittest.TestCase):
    def write_json(self, root: Path, payload: object) -> Path:
        path = root / "status.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_missing_snapshot_is_unconfigured_without_path(self):
        with tempfile.TemporaryDirectory() as directory:
            status = tibo_status.load_status(Path(directory) / "missing.json")
        self.assertEqual(status["health"], "unconfigured")
        self.assertEqual(status["posts"], [])
        self.assertEqual(status["forecast"]["state"], "unknown")
        self.assertNotIn("path", json.dumps(status))

    def test_valid_snapshot_projects_only_public_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            status = tibo_status.load_status(self.write_json(Path(directory), valid_snapshot()))
        self.assertEqual(
            set(status),
            {"schema_version", "source", "checked_at", "fetched_at", "health", "posts", "forecast", "error_code"},
        )
        self.assertEqual(status["health"], "ok")
        self.assertEqual(status["posts"][0]["kind"], "reset")
        self.assertEqual(status["forecast"]["last_reset_at"], "2025-09-26T11:00:00Z")
        self.assertNotIn("private_debug", status)

    def test_invalid_forecast_cannot_turn_other_post_into_reset(self):
        payload = valid_snapshot()
        payload["posts"][0]["kind"] = "other"
        with tempfile.TemporaryDirectory() as directory:
            status = tibo_status.load_status(self.write_json(Path(directory), payload))
        self.assertEqual(status["health"], "error")
        self.assertEqual(status["forecast"]["state"], "unknown")

    def test_last_reset_timestamp_must_belong_to_a_reset_post(self):
        payload = valid_snapshot()
        payload["forecast"]["last_reset_at"] = "2025-09-25T11:00:00Z"
        with tempfile.TemporaryDirectory() as directory:
            status = tibo_status.load_status(self.write_json(Path(directory), payload))
        self.assertEqual(status["health"], "error")
        self.assertEqual(status["forecast"]["state"], "unknown")

    def test_damaged_and_oversized_statuses_are_generic_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            broken = root / "broken.json"
            broken.write_text("{not json", encoding="utf-8")
            too_large = root / "large.json"
            too_large.write_bytes(b"x" * (tibo_status.MAX_STATUS_BYTES + 1))
            for path in (broken, too_large):
                status = tibo_status.load_status(path)
                self.assertEqual(status["health"], "error")
                self.assertEqual(status["error_code"], "STATUS_UNAVAILABLE")
                self.assertEqual(status["posts"], [])

    def test_environment_override_and_endpoint_headers(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_json(Path(directory), valid_snapshot())
            with patch.dict(os.environ, {"AITIBO_STATUS_PATH": str(path)}):
                response = tibo_status.get_status()
        body = json.loads(response.body)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(body["source"]["coverage"], "public_search")
        self.assertEqual(body["forecast"]["state"], "reset")

    def test_live_status_keeps_no_store_through_static_delivery_middleware(self):
        api = FastAPI()
        api.add_middleware(PublicStaticDeliveryMiddleware)
        api.include_router(tibo_status.router)
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_json(Path(directory), valid_snapshot())
            with patch.dict(os.environ, {"AITIBO_STATUS_PATH": str(path)}):
                response = TestClient(api).get("/api/tibo/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.json()["health"], "ok")

    def test_real_main_allows_only_anonymous_get_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "static").mkdir()
            status_path = self.write_json(root, valid_snapshot())
            env = _env(root)
            env["AITIBO_STATUS_PATH"] = str(status_path)
            result = _run(
                env,
                textwrap.dedent(
                    """
                    from starlette.testclient import TestClient
                    import main

                    client = TestClient(main.app)
                    allowed = client.get('/api/tibo/status')
                    assert allowed.status_code == 200, allowed.text
                    assert allowed.headers.get('cache-control') == 'no-store'
                    assert allowed.json()['health'] == 'ok'
                    assert client.post('/api/tibo/status').status_code == 401
                    assert client.get('/api/tibo/status/nearby').status_code == 401
                    """
                ),
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
