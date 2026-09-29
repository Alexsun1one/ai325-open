"""Contract tests for the public device-code Agent binding API."""
import tempfile
import textwrap
import unittest
from pathlib import Path

from app.test_product_performance import _env, _run


class AgentConnectTest(unittest.TestCase):
    def test_public_device_flow_and_terminal_states(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "static").mkdir()
            result = _run(_env(root), textwrap.dedent("""
                import hashlib
                from starlette.testclient import TestClient
                import main
                import agent_connect

                client = TestClient(main.app)
                db = main.db()
                user_id = db.execute(
                    "INSERT INTO users(username,password_hash,role,display_name,created_at,active) VALUES(?,?,?,?,?,1)",
                    ("human", "not-used", "member", "真人", "2026-01-01T00:00:00Z"),
                ).lastrowid
                db.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES(?,?,?)", ("human-session", user_id, "2099-01-01T00:00:00Z"))
                db.commit(); db.close()
                human = {"Authorization": "Bearer human-session"}

                # start and poll are intentionally anonymous despite global auth middleware.
                started = client.post("/api/agent/connect/start", json={"name":"测试 Agent", "client":"codex"})
                assert started.status_code == 200, started.text
                flow = started.json()
                assert set(flow) == {"device_code", "user_code", "verification_uri", "expires_in", "interval"}, flow
                assert flow["verification_uri"] == "/agents/join/?connect=" + flow["user_code"]
                assert client.post("/api/agent/connect/poll", json={"device_code":flow["device_code"]}).json() == {"status":"pending", "interval":flow["interval"]}
                assert client.get("/api/agent/connect/request", params={"user_code":flow["user_code"]}).status_code == 401

                shown = client.get("/api/agent/connect/request", params={"user_code":flow["user_code"]}, headers=human)
                assert shown.status_code == 200, shown.text
                view = shown.json()
                assert set(view) == {"name", "client", "user_code", "expires_in", "status"} and view["status"] == "pending", view
                assert flow["device_code"] not in shown.text and "token" not in shown.text.lower()

                approved = client.post("/api/agent/connect/approve", json={"user_code":flow["user_code"]}, headers=human)
                assert approved.status_code == 200 and approved.json() == {"status":"approved", "name":"测试 Agent"}, approved.text
                assert client.post("/api/agent/connect/approve", json={"user_code":flow["user_code"]}, headers=human).status_code == 409
                # Approval must bypass the previous pending poll's interval: a
                # user can approve immediately after the agent starts waiting.
                granted = client.post("/api/agent/connect/poll", json={"device_code":flow["device_code"]})
                assert granted.status_code == 200, granted.text
                grant = granted.json()
                assert grant["status"] == "approved" and grant["name"] == "测试 Agent" and grant["token"].startswith("ai325_agent_"), grant
                assert client.post("/api/agent/connect/poll", json={"device_code":flow["device_code"]}).status_code == 409
                who = client.get("/api/auth/me", headers={"Authorization":"Bearer " + grant["token"]})
                assert who.status_code == 200 and who.json()["auth_kind"] == "agent", who.text

                # An Agent token authenticates but cannot exercise the human-only approval endpoint.
                second = client.post("/api/agent/connect/start", json={"name":"另一个", "client":"claude"}).json()
                assert client.post("/api/agent/connect/approve", json={"user_code":second["user_code"]}, headers={"Authorization":"Bearer " + grant["token"]}).status_code == 403

                # Hash-only persistence: no device/user code or resulting plaintext token is durable.
                db = main.db()
                row = db.execute("SELECT * FROM agent_connect_requests WHERE name='测试 Agent'").fetchone()
                stored = " ".join(str(row[key]) for key in row.keys() if row[key] is not None)
                token_row = db.execute("SELECT token_hash,token_prefix FROM agent_tokens WHERE name='测试 Agent'").fetchone()
                db.commit(); db.close()
                assert flow["device_code"] not in stored and flow["user_code"] not in stored and grant["token"] not in stored
                assert token_row["token_hash"] == hashlib.sha256(grant["token"].encode()).hexdigest()
                assert grant["token"] not in token_row["token_prefix"]

                expired = client.post("/api/agent/connect/start", json={"name":"过期", "client":"cursor"}).json()
                db = main.db()
                db.execute("UPDATE agent_connect_requests SET expires_at='2000-01-01T00:00:00Z' WHERE user_code_hash=?", (hashlib.sha256(expired["user_code"].encode()).hexdigest(),))
                db.commit(); db.close()
                assert client.get("/api/agent/connect/request", params={"user_code":expired["user_code"]}, headers=human).status_code == 410
                assert client.post("/api/agent/connect/poll", json={"device_code":expired["device_code"]}).status_code == 410
                assert client.post("/api/agent/connect/poll", json={"device_code":"ai325_connect_missing_value_0123456789"}).status_code == 404

                # Unknown codes are bounded by IP only; the lookup itself stays
                # an indexed hash lookup and cannot grow a per-device rate map.
                db = main.db()
                indexes = {row[1] for row in db.execute("PRAGMA index_list(agent_connect_requests)")}
                plan = " ".join(row[3] for row in db.execute("EXPLAIN QUERY PLAN SELECT * FROM agent_connect_requests WHERE device_code_hash=?", ("unknown-hash",)))
                db.close()
                assert "idx_agent_connect_requests_device_code" in indexes, indexes
                assert "SEARCH" in plan and "SCAN" not in plan and "device_code_hash=?" in plan, plan
                unknown_headers = {"X-Forwarded-For": "203.0.113.77"}
                for _ in range(agent_connect.CONNECT_UNKNOWN_POLL_IP_LIMIT):
                    assert client.post("/api/agent/connect/poll", json={"device_code":"ai325_connect_missing_value_0123456789"}, headers=unknown_headers).status_code == 404
                assert client.post("/api/agent/connect/poll", json={"device_code":"ai325_connect_missing_value_0123456789"}, headers=unknown_headers).status_code == 429

                # A conforming poller can wait through the whole lifetime.  The
                # test advances the persisted per-device interval without a real
                # ten-minute sleep, while still exercising all HTTP requests.
                budget = client.post("/api/agent/connect/start", json={"name":"预算", "client":"desktop"}).json()
                for _ in range(agent_connect.DEVICE_EXPIRES_SECONDS // agent_connect.POLL_INTERVAL_SECONDS):
                    db = main.db()
                    db.execute("UPDATE agent_connect_requests SET last_polled_at='2000-01-01T00:00:00Z' WHERE user_code_hash=?", (hashlib.sha256(budget["user_code"].encode()).hexdigest(),))
                    db.commit(); db.close()
                    response = client.post("/api/agent/connect/poll", json={"device_code":budget["device_code"]})
                    assert response.status_code == 200 and response.json()["status"] == "pending", response.text
                db = main.db()
                assert not db.execute("SELECT 1 FROM agent_connect_requests WHERE user_code_hash=?", (hashlib.sha256(expired["user_code"].encode()).hexdigest(),)).fetchone()
                db.close()

                # Request/approve are also bounded. The Agent attempt plus the
                # successful and duplicate human calls already used three approve slots.
                for _ in range(agent_connect.CONNECT_REQUEST_LIMIT - 2):
                    assert client.get("/api/agent/connect/request", params={"user_code":flow["user_code"]}, headers=human).status_code == 200
                assert client.get("/api/agent/connect/request", params={"user_code":flow["user_code"]}, headers=human).status_code == 429
                for _ in range(agent_connect.CONNECT_APPROVE_LIMIT - 3):
                    assert client.post("/api/agent/connect/approve", json={"user_code":flow["user_code"]}, headers=human).status_code == 409
                assert client.post("/api/agent/connect/approve", json={"user_code":flow["user_code"]}, headers=human).status_code == 429

                # Valid devices use only their durable per-device timestamp;
                # start remains bounded and cannot accumulate indefinitely.
                for _ in range(agent_connect.CONNECT_START_LIMIT - 4):
                    assert client.post("/api/agent/connect/start", json={"name":"限流", "client":"none"}).status_code == 200
                blocked = client.post("/api/agent/connect/start", json={"name":"限流", "client":"none"})
                assert blocked.status_code == 429 and flow["device_code"] not in blocked.text, blocked.text
            """))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
