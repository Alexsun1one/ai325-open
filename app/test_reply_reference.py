"""reply_to reference contract: same-thread only, legacy rows null, MCP passthrough."""
import tempfile
import textwrap
import unittest
from pathlib import Path
from app.test_product_performance import _env, _run, _seed_script


class ReplyReferenceTest(unittest.TestCase):
    def test_reply_to_same_thread_only(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'static').mkdir()
            env = _env(Path(td))
            result = _run(env, _seed_script(agent_count=1, audit_per_agent=0))
            self.assertEqual(result.returncode, 0, result.stderr)
            result = _run(env, textwrap.dedent('''
                import main
                from starlette.testclient import TestClient
                client = TestClient(main.app)
                agent = {'Authorization':'Bearer ai325_agent_perf_test_token'}
                c = main.db()
                c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('h1',1,'2099-01-01T00:00:00+08:00')")
                c.commit(); c.close()
                human = {'Authorization':'Bearer h1'}
                t1 = client.post('/api/agent/threads', headers=agent,
                    json={'title':'串一','body':'内容','target':'general'}).json()
                t2 = client.post('/api/agent/threads', headers=agent,
                    json={'title':'串二','body':'内容','target':'general'}).json()
                r1 = client.post(f"/api/agent/threads/{t1['id']}/replies", headers=agent,
                    json={'text':'首条回复'}).json()
                rid1 = [r for r in r1['replies'] if r['text']=='首条回复'][0]['id']
                r2 = client.post(f"/api/agent/threads/{t2['id']}/replies", headers=agent,
                    json={'text':'串二的回复'}).json()
                rid_other = [r for r in r2['replies'] if r['text']=='串二的回复'][0]['id']
                # 同串接话成功，返回 reply_to
                ok = client.post(f"/api/agent/threads/{t1['id']}/replies", headers=human,
                    json={'text':'接住首条','reply_to':rid1})
                assert ok.status_code == 200, ok.text
                got = client.get(f"/api/agent/threads/{t1['id']}").json()
                target = [r for r in got['replies'] if r['text']=='接住首条'][0]
                assert target['reply_to'] == rid1, target
                assert [r for r in got['replies'] if r['id']==rid1][0]['reply_to'] is None  # 旧行 null
                # 跨串拒绝
                bad = client.post(f"/api/agent/threads/{t1['id']}/replies", headers=agent,
                    json={'text':'跨串','reply_to':rid_other})
                assert bad.status_code == 400, bad.text
                # 未知 id 拒绝
                assert client.post(f"/api/agent/threads/{t1['id']}/replies", headers=agent,
                    json={'text':'不存在','reply_to':99999}).status_code == 400
                # 非正数拒绝（pydantic ge=1）
                assert client.post(f"/api/agent/threads/{t1['id']}/replies", headers=agent,
                    json={'text':'零','reply_to':0}).status_code == 422
                # 匿名仍 401
                assert client.post(f"/api/agent/threads/{t1['id']}/replies",
                    json={'text':'匿名','reply_to':rid1}).status_code == 401
                # Agent 同串 reply_to 成功正例 + 审计 metadata.reply_to 真值
                ok2 = client.post(f"/api/agent/threads/{t1['id']}/replies", headers=agent,
                    json={'text':'Agent接话','reply_to':rid1})
                assert ok2.status_code == 200, ok2.text
                agent_reply = [r for r in ok2.json()['replies'] if r['text']=='Agent接话'][0]
                assert agent_reply['reply_to'] == rid1, agent_reply
                audit = client.get('/api/agent/audit', headers=agent).json()
                replies_audit = [a for a in audit['items']
                                 if a['action']=='question.reply' and str(a['target_id'])==str(t1['id'])]
                assert any((a.get('metadata') or {}).get('reply_to') == rid1
                           for a in replies_audit), replies_audit
                # closed 409 实测（隔离库直接置位）
                c = main.db()
                c.execute("UPDATE question_threads SET status='closed' WHERE id=?", (t2['id'],))
                c.commit(); c.close()
                closed = client.post(f"/api/agent/threads/{t2['id']}/replies", headers=agent,
                    json={'text':'已关闭','reply_to':rid_other})
                assert closed.status_code == 409, closed.text
            '''))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_participant_key_anonymous_stable(self):
        """participant_key：同 token 不同历史名同 key；不同 token 同名不同 key；匿名无 id。"""
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'static').mkdir()
            env = _env(Path(td))
            result = _run(env, _seed_script(agent_count=1, audit_per_agent=0))
            self.assertEqual(result.returncode, 0, result.stderr)
            result = _run(env, textwrap.dedent("""
                import main
                from starlette.testclient import TestClient
                client = TestClient(main.app)
                agent = {'Authorization':'Bearer ai325_agent_perf_test_token'}
                t = client.post('/api/agent/threads', headers=agent,
                    json={'title':'串','body':'内容','target':'general'}).json()
                # 同 token 先以旧名回复，改名后再回复 → 同一 participant_key
                client.post(f"/api/agent/threads/{t['id']}/replies", headers=agent,
                    json={'text':'旧名回复'})
                client.patch('/api/agent/profile', headers=agent, json={'display_name':'新名字'})
                client.post(f"/api/agent/threads/{t['id']}/replies", headers=agent,
                    json={'text':'新名回复'})
                # 另一个 token_id 但同名（DB 直插，测映射不猜名字）
                c = main.db()
                tok2 = c.execute("INSERT INTO agent_tokens(user_id,username,name,display_name,bio,"
                    "capabilities_json,token_hash,token_prefix,created_at,last_used_at,revoked) "
                    "VALUES(1,'mentor','agentX','新名字','','[]','hx','px','x','x',0)").lastrowid
                c.execute("INSERT INTO question_replies(thread_id,user_id,agent_token_id,author_kind,"
                    "author_name,text,created_at,agent_name,agent_display_name,agent_capabilities_json) "
                    "VALUES(?,1,?,'agent','新名字','同名他人','x','agentX','新名字','[]')", (t['id'], tok2))
                c.commit(); c.close()
                got = client.get(f"/api/agent/threads/{t['id']}").json()  # 匿名
                assert got['agent']['participant_key'] == 'a1', got['agent']
                assert 'id' not in got['agent'], got['agent']
                replies = {r['text']: r for r in got['replies']}
                assert replies['旧名回复']['agent']['participant_key'] == 'a1'
                assert replies['新名回复']['agent']['participant_key'] == 'a1'
                assert replies['同名他人']['agent']['participant_key'] == 'a2'
                for r in got['replies']:
                    if r['agent']:
                        assert 'id' not in r['agent'], r['agent']
            """))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_legacy_table_migrates_reply_to(self):
        """旧 question_replies 表（无 reply_to）启动后自动补列，旧行 null。"""
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'static').mkdir()
            env = _env(Path(td))
            pre = _run(env, textwrap.dedent('''
                import os, sqlite3
                from pathlib import Path
                db = Path(os.environ["XF_DATA_DIR"]) / "xf.db"
                c = sqlite3.connect(db)
                c.execute("""CREATE TABLE question_replies(id INTEGER PRIMARY KEY,thread_id INT,user_id INT,
                    agent_token_id INT,author_kind TEXT,author_name TEXT,text TEXT,created_at TEXT,
                    agent_name TEXT,agent_display_name TEXT,agent_capabilities_json TEXT DEFAULT '[]',
                    accepted INTEGER DEFAULT 0,accepted_by INTEGER,accepted_at TEXT)""")
                c.execute("INSERT INTO question_replies(id,thread_id,user_id,author_kind,author_name,text,created_at) VALUES(5,1,1,'agent','旧','旧回复','x')")
                c.commit(); c.close()
            '''))
            self.assertEqual(pre.returncode, 0, pre.stderr)
            result = _run(env, textwrap.dedent('''
                import main
                c = main.db()
                cols = {r[1] for r in c.execute("PRAGMA table_info(question_replies)")}
                assert 'reply_to' in cols, cols
                row = c.execute("SELECT reply_to FROM question_replies WHERE id=5").fetchone()
                assert row['reply_to'] is None, dict(row)
                c.close()
            '''))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
