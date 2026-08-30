import json
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent


class AgentFirstRealHttpSmokeTest(unittest.TestCase):
    def test_first_boot_requires_explicit_admin_password(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            static_dir = root / "static"
            static_dir.mkdir()
            env = os.environ.copy()
            env.pop("DEEPSEEK_API_KEY", None)
            env.pop("INITIAL_ADMIN_PASS", None)
            env.pop("AUTH_PASS", None)
            env.update(
                {
                    "XF_DATA_DIR": str(root / "data"),
                    "XF_STATIC_DIR": str(static_dir),
                    "XF_SKIP_GATEKEEPER_WORKER": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            result = subprocess.run(
                [sys.executable, "-c", "import main"],
                cwd=APP_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("INITIAL_ADMIN_PASS", result.stdout + result.stderr)

    def test_public_activity_and_questions_use_real_http(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            static_dir = root / "static"
            static_dir.mkdir()
            env = os.environ.copy()
            env.pop("DEEPSEEK_API_KEY", None)
            env.update(
                {
                    "XF_DATA_DIR": str(root / "data"),
                    "XF_STATIC_DIR": str(static_dir),
                    "INITIAL_ADMIN_PASS": "test-only",
                    "GATEKEEPER_POLL_SECONDS": "60",
                    "XF_SKIP_GATEKEEPER_WORKER": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            seed = textwrap.dedent(
                """
                import hashlib
                import json
                import main

                c = main.db()
                user_id = c.execute(
                    "INSERT INTO users(username,password_hash,role,display_name,created_at) "
                    "VALUES(?,?,?,?,?)",
                    ("mentor", "hash", "member", "导师甲", "2026-08-29T08:00:00+08:00"),
                ).lastrowid
                agent_id = c.execute(
                    "INSERT INTO agent_tokens("
                    "user_id,username,name,display_name,bio,capabilities_json,token_hash,"
                    "token_prefix,created_at,revoked) VALUES(?,?,?,?,?,?,?,?,?,0)",
                    (
                        user_id, "mentor", "helper", "学徒甲", "", '["问答"]',
                        hashlib.sha256(b"ai325_agent_http_test_token").hexdigest(),
                        "ai325_agent_****test",
                        "2026-08-29T08:00:00+08:00",
                    ),
                ).lastrowid
                thread_old = c.execute(
                    "INSERT INTO question_threads("
                    "user_id,agent_token_id,title,body,target,status,created_at,updated_at,"
                    "agent_name,agent_display_name,agent_capabilities_json) "
                    "VALUES(?,?,?,?,?,'open',?,?,?,?,?)",
                    (
                        user_id, agent_id, "旧问题", "旧问题正文", "工坊",
                        "2026-08-29T08:00:00+08:00", "2026-08-29T08:10:00+08:00",
                        "helper", "学徒甲", '["问答"]',
                    ),
                ).lastrowid
                thread_new = c.execute(
                    "INSERT INTO question_threads("
                    "user_id,agent_token_id,title,body,target,status,created_at,updated_at,"
                    "agent_name,agent_display_name,agent_capabilities_json) "
                    "VALUES(?,?,?,?,?,'open',?,?,?,?,?)",
                    (
                        user_id, agent_id, "新问题", "新问题正文", "工坊",
                        "2026-08-29T09:00:00+08:00", "2026-08-29T09:30:00+08:00",
                        "helper", "学徒甲", '["问答"]',
                    ),
                ).lastrowid
                c.execute(
                    "INSERT INTO question_replies("
                    "thread_id,user_id,agent_token_id,author_kind,author_name,text,created_at,"
                    "agent_name,agent_display_name,agent_capabilities_json) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        thread_new, user_id, agent_id, "agent", "学徒甲", "补充回答",
                        "2026-08-29T09:30:00+08:00", "helper", "学徒甲", '["问答"]',
                    ),
                )
                audit_rows = (
                    ("2026-08-29T10:00:00+08:00", "question.reply", "question_thread", str(thread_new)),
                    ("2026-08-29T09:00:00+08:00", "comment.create", "comment", "8"),
                    ("2026-08-29T11:00:00+08:00", "learning.sync", "learning", "cursor"),
                )
                for at, action, target_type, target_id in audit_rows:
                    c.execute(
                        "INSERT INTO agent_action_audit("
                        "ts,agent_token_id,user_id,agent_name,agent_display_name,capabilities_json,"
                        "action,target_type,target_id,decision,metadata_json) "
                        "VALUES(?,?,?,?,?,?,?,?,?,'accepted','{}')",
                        (
                            at, agent_id, user_id, "helper", "学徒甲", '["问答"]',
                            action, target_type, target_id,
                        ),
                    )
                c.commit()
                print(json.dumps({"old": thread_old, "new": thread_new}))
                c.close()
                """
            )
            seeded = subprocess.run(
                [sys.executable, "-c", seed],
                cwd=APP_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(seeded.returncode, 0, seeded.stdout + seeded.stderr)
            thread_ids = json.loads(seeded.stdout.strip().splitlines()[-1])

            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--log-level",
                    "warning",
                ],
                cwd=APP_DIR,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            base = f"http://127.0.0.1:{port}"
            try:
                for _ in range(100):
                    try:
                        with urllib.request.urlopen(
                            base + "/api/agent/manifest", timeout=0.5
                        ) as response:
                            if response.status == 200:
                                break
                    except (OSError, urllib.error.URLError):
                        time.sleep(0.05)
                else:
                    self.fail("uvicorn did not become ready")

                with urllib.request.urlopen(base + "/api/agent/activity?limit=2") as response:
                    self.assertEqual(response.status, 200)
                    activity = json.load(response)
                self.assertEqual(activity["count"], 2)
                self.assertEqual(activity["limit"], 2)
                self.assertEqual(
                    [item["what"] for item in activity["items"]],
                    ["追问了一个提问串", "留下一条学徒批注"],
                )
                self.assertEqual(activity["items"][0]["agent_display_name"], "学徒甲")
                self.assertEqual(activity["items"][0]["mentor_display"], "导师甲")
                self.assertEqual(activity["items"][0]["what"], "追问了一个提问串")
                self.assertEqual(
                    set(activity["items"][0]),
                    {"agent_display_name", "mentor_display", "what", "at"},
                )

                with urllib.request.urlopen(base + "/api/agent/threads?status=all") as response:
                    self.assertEqual(response.status, 200)
                    threads = json.load(response)
                self.assertEqual([item["title"] for item in threads["items"]], ["新问题", "旧问题"])
                self.assertEqual(threads["items"][0]["reply_count"], 1)
                self.assertEqual(threads["items"][0]["agent"]["mentor"]["username"], "mentor")
                self.assertEqual(threads["items"][0]["agent"]["mentor"]["display_name"], "导师甲")
                self.assertNotIn("id", threads["items"][0]["agent"])
                self.assertNotIn("user_id", threads["items"][0]["agent"]["mentor"])

                with urllib.request.urlopen(
                    base + f"/api/agent/threads/{thread_ids['new']}"
                ) as response:
                    detail = json.load(response)
                self.assertEqual(detail["reply_count"], 1)
                self.assertEqual(detail["replies"][0]["text"], "补充回答")
                self.assertNotIn("id", detail["agent"])
                self.assertNotIn("id", detail["replies"][0]["agent"])

                with self.assertRaises(urllib.error.HTTPError) as mine_error:
                    urllib.request.urlopen(base + "/api/agent/threads?mine=true")
                self.assertEqual(mine_error.exception.code, 401)
                mine_error.exception.close()

                anonymous_reply = urllib.request.Request(
                    base + f"/api/agent/threads/{thread_ids['new']}/replies",
                    data=json.dumps({"text": "匿名不应写入"}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as reply_error:
                    urllib.request.urlopen(anonymous_reply)
                self.assertEqual(reply_error.exception.code, 401)
                reply_error.exception.close()

                authenticated_create = urllib.request.Request(
                    base + "/api/agent/threads",
                    data=json.dumps({
                        "title": "已认证提问",
                        "body": "真实 HTTP 写入",
                        "target": "工坊",
                    }).encode(),
                    headers={
                        "Authorization": "Bearer ai325_agent_http_test_token",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(authenticated_create) as response:
                    self.assertEqual(response.status, 200)
                    created = json.load(response)
                self.assertEqual(created["title"], "已认证提问")
                self.assertIn("id", created["agent"])

                request = urllib.request.Request(
                    base + "/api/agent/threads",
                    data=b'{}',
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(request)
                self.assertEqual(caught.exception.code, 401)
                caught.exception.close()
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=5)
                if server.returncode not in (0, -15):
                    output = server.stdout.read() if server.stdout else ""
                    self.fail(f"uvicorn exited unexpectedly: {server.returncode}\n{output}")
                if server.stdout:
                    server.stdout.close()


if __name__ == "__main__":
    unittest.main()
