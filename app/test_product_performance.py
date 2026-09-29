"""PERF-B R1：Agent 端点性能与增量游标回归。

覆盖：
- /api/agent/roster 的 N+1 查询（每 agent 4 条子查询 → 固定 6 条（含总数））
- /api/agent/updates 的增量游标丢失（截断丢旧条目、同日分页与 whoami 书签推进）
- updates 按文件名跳过已学 ledger 的解析

隔离临时 DB + 临时 governed-ledger 目录；真实函数调用与真实 HTTP，无生产写入。
"""

import hashlib
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
AGENT_TOKEN = "ai325_agent_perf_test_token"


def _env(root: Path) -> dict:
    env = os.environ.copy()
    env.pop("DEEPSEEK_API_KEY", None)
    env.update(
        {
            "XF_DATA_DIR": str(root),
            "XF_STATIC_DIR": str(root / "static"),
            "XF_GOVERNED_DIR": str(root / "governed"),
            "INITIAL_ADMIN_PASS": "test-only",
            "GATEKEEPER_POLL_SECONDS": "60",
            "XF_SKIP_GATEKEEPER_WORKER": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return env


def _seed_script(agent_count: int = 4, audit_per_agent: int = 10) -> str:
    return textwrap.dedent(
        f"""
        import hashlib, json, main
        c = main.db()
        uid = c.execute(
            "INSERT INTO users(username,password_hash,role,display_name,created_at) "
            "VALUES(?,?,?,?,?)",
            ("mentor", "h", "member", "导师", "2026-01-01T00:00:00+08:00"),
        ).lastrowid
        tok_hash = hashlib.sha256({AGENT_TOKEN!r}.encode()).hexdigest()
        agent_ids = []
        for i in range({agent_count}):
            aid = c.execute(
                "INSERT INTO agent_tokens(user_id,username,name,display_name,bio,"
                "capabilities_json,token_hash,token_prefix,created_at,last_used_at,revoked) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,0)",
                (uid, "mentor", f"agent{{i}}", f"学徒{{i}}", "", '["问答"]',
                 tok_hash if i == 0 else f"h{{i}}", "ai325_agent_****",
                 "2026-08-01T00:00:00+08:00", "2026-09-01T00:00:00+08:00"),
            ).lastrowid
            agent_ids.append(aid)
            for j in range({audit_per_agent}):
                c.execute(
                    "INSERT INTO agent_action_audit(ts,agent_token_id,user_id,agent_name,"
                    "agent_display_name,capabilities_json,action,target_type,target_id,"
                    "decision,metadata_json) VALUES(?,?,?,?,?,?,?,?,?,'accepted','{{}}')",
                    (f"2026-09-0{{1+j}}T00:00:00+08:00", aid, uid, f"agent{{i}}",
                     f"学徒{{i}}", '["问答"]', "learning.sync", "learning", "c"),
                )
            # 每个 agent 一件上架军火 + 一条被采纳回复
            c.execute(
                "INSERT INTO arsenal_items(id,title,kind,collected_at,by_name,one_line,"
                "why,for_whom,contributor_user_id,contributor_username,status,created_at,"
                "updated_at,agent_token_id) VALUES(?,?,?,?,?,?,?,?,?,?,'shelved',?, ?,?)",
                (f"a{{i}}", "标题", "tool", "2026-09-01", "学徒", "o", "w", "f",
                 uid, "mentor", "2026-09-01T00:00:00+08:00", "2026-09-01T00:00:00+08:00", aid),
            )
            tid = c.execute(
                "INSERT INTO question_threads(user_id,agent_token_id,title,body,target,status,"
                "created_at,updated_at,agent_name,agent_display_name,agent_capabilities_json) "
                "VALUES(?,?,?,?,'','open',?,?,?,?,'[]')",
                (uid, aid, "q", "b", "2026-09-01T00:00:00+08:00", "2026-09-01T00:00:00+08:00",
                 f"agent{{i}}", f"学徒{{i}}"),
            ).lastrowid
            c.execute(
                "INSERT INTO question_replies(thread_id,user_id,agent_token_id,author_kind,"
                "author_name,text,created_at,accepted) VALUES(?,?,?,?,?,?,?,1)",
                (tid, uid, aid, "agent", "学徒", "r", "2026-09-01T00:00:00+08:00"),
            )
        c.commit(); c.close()
        print(json.dumps({{"agent_ids": agent_ids}}))
        """
    )


def _run(env, code: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", code], cwd=APP_DIR, env=env,
        capture_output=True, text=True, timeout=timeout,
    )


class RosterQueryCountTest(unittest.TestCase):
    """roster 查询数必须与 agent 数量无关（N+1 回归）。"""

    def _count_queries(self, agent_count: int) -> tuple[int, dict]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "static").mkdir()
            env = _env(root)
            seed = _run(env, _seed_script(agent_count=agent_count))
            self.assertEqual(seed.returncode, 0, seed.stderr)
            probe = textwrap.dedent(
                """
                import json, main
                calls = []
                real_db = main.db
                def traced():
                    conn = real_db()
                    conn.set_trace_callback(lambda s: calls.append(s))
                    return conn
                main.db = traced
                out = main.agent_roster(limit=500)
                print(json.dumps({"queries": len(calls), "items": len(out["items"])}))
                """
            )
            probe_run = _run(env, probe)
            self.assertEqual(probe_run.returncode, 0, probe_run.stderr)
            return json.loads(probe_run.stdout.strip().splitlines()[-1])

    def test_roster_query_count_is_constant(self):
        small = self._count_queries(4)
        large = self._count_queries(9)
        # 旧实现 1+4N：4 个 agent 17 条、9 个 37 条；批量化后固定 6 条（含总数）
        self.assertEqual(small["items"], 4)
        self.assertEqual(large["items"], 9)
        self.assertEqual(small["queries"], large["queries"])
        self.assertLessEqual(small["queries"], 6)


class AcademyActionsTest(unittest.TestCase):
    def test_accept_vote_and_switch_on_fresh_database(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "static").mkdir()
            env = _env(Path(td))
            seed = _run(env, _seed_script(agent_count=2, audit_per_agent=0))
            self.assertEqual(seed.returncode, 0, seed.stderr)
            result = _run(env, textwrap.dedent("""
                import main
                from starlette.testclient import TestClient
                client = TestClient(main.app)
                headers = {'Authorization': 'Bearer ai325_agent_perf_test_token'}
                assert client.get('/api/agent/weekly-vote').status_code == 200
                c = main.db()
                c.execute('UPDATE question_replies SET accepted=0')
                c.commit(); c.close()
                for i in (1, 2):
                    response = client.post(f'/api/agent/questions/{i}/accept', headers=headers, json={'reply_id': i})
                    assert response.status_code == 200, response.text
                page = client.get('/api/agent/weekly-vote', headers=headers).json()
                assert page['can_vote'] and len(page['candidates']) == 2, page
                ids = [x['id'] for x in page['candidates']]
                for candidate in ids:
                    response = client.post(f'/api/agent/weekly-vote/{candidate}', headers=headers)
                    assert response.status_code == 200, response.text
                page = client.get('/api/agent/weekly-vote', headers=headers).json()
                votes = {x['id']: x['votes'] for x in page['candidates']}
                assert votes == {ids[0]: 0, ids[1]: 1}, page
                assert page['my_votes'] == [ids[1]], page
                assert client.post(f'/api/agent/weekly-vote/{ids[0]}').status_code == 401
            """))
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


class UpdatesCursorTest(unittest.TestCase):
    """Real HTTP: independent feed checkpoints, same-day pagination and MCP flow."""

    def test_same_day_pages_and_whoami_checkpoint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "static").mkdir()
            (root / "governed" / "ledgers").mkdir(parents=True)
            dates = [f"2026-09-{i:02}" for i in range(1, 5)]
            for date in dates:
                (root / "governed" / "ledgers" / f"{date}.json").write_text(json.dumps({"date": date, "title": date}))
            env = _env(root)
            seed = _run(env, _seed_script(agent_count=4, audit_per_agent=0))
            self.assertEqual(seed.returncode, 0, seed.stderr)
            probe = _run(env, textwrap.dedent(f"""
                import json, main
                from starlette.testclient import TestClient
                client = TestClient(main.app)
                headers = {{'Authorization': 'Bearer {AGENT_TOKEN}'}}
                ledgers, arsenal = [], []
                for i in range(4):
                    identity = client.get('/api/auth/me', headers=headers)
                    assert identity.status_code == 200, identity.text
                    marker = identity.json()['learning_since']
                    response = client.get('/api/agent/updates', headers=headers, params={{'since': marker, 'limit': 1}})
                    assert response.status_code == 200, response.text
                    page = response.json()
                    ledgers.extend(item['date'] for item in page['new_ledgers'])
                    arsenal.extend(item['id'] for item in page['new_arsenal'])
                    assert page['counts']['truncated'] == (i < 3), page
                    assert client.get('/api/auth/me', headers=headers).json()['learning_since'] == page['cursor']
                empty = client.get('/api/agent/updates', headers=headers, params={{'limit': 1}}).json()
                assert empty['new_ledgers'] == [] and empty['new_arsenal'] == [], empty
                saved = client.get('/api/auth/me', headers=headers).json()['learning_since']
                backfill = client.get('/api/agent/updates', headers=headers, params={{'since': '2026-01-01', 'limit': 2}}).json()
                assert backfill['cursor'] != saved
                assert client.get('/api/auth/me', headers=headers).json()['learning_since'] == saved
                second = client.get('/api/agent/updates', headers=headers, params={{'since': backfill['cursor'], 'limit': 2}}).json()
                assert not set(x['id'] for x in backfill['new_arsenal']) & set(x['id'] for x in second['new_arsenal'])
                # A later contribution on the same day remains visible after all pages were read.
                c = main.db()
                c.execute("UPDATE arsenal_items SET created_at='2026-09-01T19:00:00+08:00' WHERE id='a0'")
                c.commit(); c.close()
                later = client.get('/api/agent/updates', headers=headers).json()
                assert [x['id'] for x in later['new_arsenal']] == ['a0'], later
                assert client.get('/api/agent/updates', headers=headers, params={{'since': 'learn1.invalid'}}).status_code == 400
                assert client.get('/api/agent/updates').status_code == 401
                print(json.dumps({{'ledgers': ledgers, 'arsenal': arsenal, 'pages': 4}}))
            """))
            self.assertEqual(probe.returncode, 0, probe.stderr + probe.stdout)
            result = json.loads(probe.stdout.strip().splitlines()[-1])
            self.assertEqual(result['ledgers'], dates)
            self.assertEqual(result['arsenal'], ['a0', 'a1', 'a2', 'a3'])


class UpdatesStemSkipTest(unittest.TestCase):
    """marker 之前的 ledger 文件连 JSON 解析都跳过。"""

    def test_old_files_not_parsed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "static").mkdir()
            (root / "governed" / "ledgers").mkdir(parents=True)
            # 两个老文件 + 一个坏文件名但日期合格的新文件
            (root / "governed" / "ledgers" / "2026-09-01.json").write_text(
                "{bad json", encoding="utf-8")  # 若被解析会炸 → 证明被跳过
            (root / "governed" / "ledgers" / "2026-09-05.json").write_text(
                json.dumps({"date": "2026-09-05", "title": "新刊"}), encoding="utf-8")
            env = _env(root)
            seed = _run(env, _seed_script(agent_count=1, audit_per_agent=0))
            self.assertEqual(seed.returncode, 0, seed.stderr)
            run = _run(env, textwrap.dedent("""
                import json, types, main
                c = main.db()
                c.execute("UPDATE agent_tokens SET last_learning_at='2026-09-03' WHERE id=1")
                c.commit(); c.close()
                from starlette.testclient import TestClient
                response = TestClient(main.app).get('/api/agent/updates', headers={'Authorization': 'Bearer ai325_agent_perf_test_token'})
                assert response.status_code == 200, response.text
                out = response.json()
                print(json.dumps({"ledgers": [x["date"] for x in out["new_ledgers"]]}))
                """))
            self.assertEqual(run.returncode, 0, run.stderr)
            data = json.loads(run.stdout.strip().splitlines()[-1])
            # 坏文件 2026-09-01 在 marker 之前 → stem 预过滤跳过，不炸且不含它
            self.assertEqual(data["ledgers"], ["2026-09-05"])


if __name__ == "__main__":
    unittest.main()
