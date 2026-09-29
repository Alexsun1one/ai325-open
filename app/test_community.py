"""Human and Agent discussion through the same authenticated HTTP surface."""
import tempfile
import textwrap
import unittest
from pathlib import Path
from app.test_product_performance import _env, _run, _seed_script

class CommunityTest(unittest.TestCase):
    def test_human_agent_discussion_and_filters(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'static').mkdir()
            env = _env(Path(td))
            result = _run(env, _seed_script(agent_count=1, audit_per_agent=0))
            self.assertEqual(result.returncode, 0, result.stderr)
            result = _run(env, textwrap.dedent('''
                import main
                from starlette.testclient import TestClient
                client = TestClient(main.app)
                c = main.db()
                c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('human-test',1,'2099-01-01T00:00:00+08:00')")
                c.commit(); c.close()
                human = {'Authorization':'Bearer human-test'}
                agent = {'Authorization':'Bearer ai325_agent_perf_test_token'}
                payload = {'title':'验证先行的实践','body':'我有一项实测反例，希望一起核验。','target':'evidence-first'}
                assert client.post('/api/agent/threads', json=payload).status_code == 401
                response = client.post('/api/agent/threads', headers=human, json=payload)
                assert response.status_code == 200, response.text
                thread = response.json()
                assert thread['author_kind'] == 'human' and thread['agent'] is None, thread
                tid = thread['id']
                response = client.post(f'/api/agent/threads/{tid}/replies', headers=agent, json={'text':'Agent 实践证据和适用边界。'})
                assert response.status_code == 200, response.text
                detail = client.get(f'/api/agent/threads/{tid}', headers=human).json()
                assert detail['is_mine'] and detail['replies'][0]['author_kind'] == 'agent', detail
                assert client.get(f'/api/agent/threads/{tid}', headers=agent).json()['is_mine'] is False
                response = client.get('/api/agent/threads', params={'target':'evidence-first','q':'验证','limit':1})
                page = response.json()
                assert page['total'] == 1 and page['count'] == 1 and not page['has_more'], page
                assert client.get('/api/agent/threads', params={'target':'other'}).json()['total'] == 0
                assert client.get('/api/agent/threads?mine=true', headers=human).status_code == 200
                own = client.post('/api/agent/threads', headers=agent, json=payload).json()
                assert own['author_kind'] == 'agent' and own['agent'], own
                assert client.get(f"/api/agent/threads/{own['id']}", headers=agent).json()['is_mine']
                page = client.get('/api/agent/threads', params={'target':'evidence-first','limit':1,'offset':1}).json()
                assert page['total'] == 2 and page['count'] == 1 and not page['has_more'], page
            '''))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_multiline_body_and_reply_preserved(self):
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
                body = '第一段实践。\\r\\n\\r\\n第二段结果。\\t与\\u200b零宽'
                thread = client.post('/api/agent/threads', headers=agent,
                    json={'title':'多行验证','body':body,'target':'evidence-first'}).json()
                assert thread['body'] == '第一段实践。\\n\\n第二段结果。与零宽', thread['body']
                client.post(f"/api/agent/threads/{thread['id']}/replies", headers=agent,
                    json={'text':'行一\\r行二\\x00清掉'})
                got = client.get(f"/api/agent/threads/{thread['id']}").json()
                assert got['replies'][-1]['text'] == '行一\\n行二清掉', got['replies']
                # 单行身份字段仍整段清控制字符（含换行）
                one = main.clean_agent_text('名\\n字', 40)
                assert one == '名字', one
            '''))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_public_agent_answers(self):
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
                assert client.get('/api/agent/answers').status_code == 200  # 匿名可读
                t1 = client.post('/api/agent/threads', headers=agent,
                    json={'title':'问题一','body':'内容','target':'evidence-first'}).json()
                client.post(f"/api/agent/threads/{t1['id']}/replies", headers=agent, json={'text':'短回答'})
                client.post(f"/api/agent/threads/{t1['id']}/replies", headers=agent,
                    json={'text':'长\\n' + '答'*500})
                page = client.get('/api/agent/answers?limit=3').json()
                # 种子数据自带 1 条 agent 回复；新增 2 条 → 共 3
                assert page['total'] == 3 and page['count'] == 3 and page['limit'] == 3, page
                first, second = page['items'][0], page['items'][1]
                assert first['reply_id'] > second['reply_id'] and second['thread_id'] == t1['id'], page['items']
                assert first['truncated'] and len(first['excerpt']) == 400 and '\\n' in first['excerpt'], first
                assert first['question_title'] == '问题一' and first['thread_id'] == t1['id'], first
                banned = {'user_id','agent_token_id','username','token','author_kind','agent_name'}
                assert not banned & set(first), first.keys()
                assert client.get('/api/agent/answers?limit=0').status_code == 422
                assert client.get('/api/agent/answers?limit=13').status_code == 422
                assert client.get('/api/agent/answers?limit=1').json()['count'] == 1
                # 人类回复 / NULL token / revoked / user_id 错配 / 失效用户都不计入
                c = main.db()
                c.execute("INSERT INTO question_replies(thread_id,user_id,agent_token_id,author_kind,author_name,text,created_at) VALUES(?,1,NULL,'human','群友','人类回复','2026-09-23T00:00:00+08:00')", (t1['id'],))
                c.execute("INSERT INTO question_replies(thread_id,user_id,agent_token_id,author_kind,author_name,text,created_at) VALUES(?,1,NULL,'agent','孤儿','空token','2026-09-23T00:00:01+08:00')", (t1['id'],))
                c.execute("INSERT INTO users(username,display_name,role,active,password_hash,password_set) VALUES('ghost','Ghost','member',0,'x',1)")
                ghost_uid = c.execute("SELECT id FROM users WHERE username='ghost'").fetchone()[0]
                c.execute("INSERT INTO agent_tokens(user_id,username,name,display_name,token_hash,token_prefix,created_at,revoked) VALUES(?,'ghosttok','g','Ghost Agent','gh','gh','x',0)", (ghost_uid,))
                ghost_tok = c.execute("SELECT id FROM agent_tokens WHERE username='ghosttok'").fetchone()[0]
                # user_id=1(active) 但 token 属 ghost → 错配行必须被 JOIN 排除
                c.execute("INSERT INTO question_replies(thread_id,user_id,agent_token_id,author_kind,author_name,text,created_at) VALUES(?,1,?,'agent','错配','user_id对不上token','2026-09-23T00:00:02+08:00')", (t1['id'], ghost_tok))
                c.execute("INSERT INTO question_replies(thread_id,user_id,agent_token_id,author_kind,author_name,text,created_at) VALUES(?,?,?,'agent','Ghost Agent','失效用户','2026-09-23T00:00:03+08:00')", (t1['id'], ghost_uid, ghost_tok))
                c.execute("UPDATE agent_tokens SET revoked=1 WHERE username='mentor'")  # 种子 agent token 的 username 是 mentor
                c.commit(); c.close()
                page = client.get('/api/agent/answers').json()
                assert page['total'] == 0 and page['items'] == [], page
            '''))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
