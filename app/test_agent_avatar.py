"""avatar_key contract: whitelist, persistence, current-avatar reads, cross-user denial."""
import tempfile
import textwrap
import unittest
from pathlib import Path
from app.test_product_performance import _env, _run, _seed_script


class AgentAvatarTest(unittest.TestCase):
    def test_avatar_key_end_to_end(self):
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
                # 默认空串出现在各输出面
                prof = client.get('/api/auth/me', headers=agent).json()['agent_profile']
                assert prof['avatar_key'] == '', prof
                roster = client.get('/api/agent/roster').json()
                assert roster['items'][0]['avatar_key'] == '', roster['items'][0]
                # 非法值被拒
                assert client.patch('/api/agent/profile', headers=agent, json={'avatar_key':'http://x'}).status_code == 422
                assert client.patch('/api/agent/profile', headers=agent, json={'avatar_key':'nope'}).status_code == 422
                # Agent 自改成功 + 审计
                r = client.patch('/api/agent/profile', headers=agent, json={'avatar_key':'owl','display_name':'换名学徒'})
                assert r.status_code == 200 and r.json()['avatar_key'] == 'owl', r.text
                prof = client.get('/api/auth/me', headers=agent).json()['agent_profile']
                assert prof['avatar_key'] == 'owl' and prof['display_name'] == '换名学徒', prof
                audit = client.get('/api/agent/audit', headers=agent).json()
                assert any(a['action'] == 'agent.profile_update' for a in audit['items']), audit
                # 历史内容动态读当前头像：发帖/回复/评论/roster/answers 全部跟随 owl
                t1 = client.post('/api/agent/threads', headers=agent,
                    json={'title':'头像测试','body':'正文','target':'general'}).json()
                client.post(f"/api/agent/threads/{t1['id']}/replies", headers=agent, json={'text':'回'})
                detail = client.get(f"/api/agent/threads/{t1['id']}").json()
                assert detail['agent']['avatar_key'] == 'owl', detail['agent']
                assert detail['replies'][0]['agent']['avatar_key'] == 'owl', detail['replies']
                lst = client.get('/api/agent/threads?status=all').json()
                assert lst['items'][0]['agent']['avatar_key'] == 'owl', lst['items']
                ans = client.get('/api/agent/answers').json()
                assert ans['items'][0]['avatar_key'] == 'owl', ans['items'][0]
                roster = client.get('/api/agent/roster').json()
                assert roster['items'][0]['avatar_key'] == 'owl', roster['items'][0]
                # 评论面
                c = main.db()
                uid = c.execute("SELECT user_id FROM agent_tokens WHERE name='agent0'").fetchone()[0]
                tok_id0 = c.execute("SELECT id FROM agent_tokens WHERE name='agent0'").fetchone()[0]
                c.execute("INSERT INTO comments(anchor,date,user_id,username,text,created_at,status,agent_token_id,agent_display_name) VALUES('article:test','2026-09-23',?,'mentor','评论','2026-09-23T00:00:00+08:00','accepted',?,'换名学徒')", (uid, tok_id0))
                c.commit(); c.close()
                cm = client.get('/api/comments?anchor=article:test').json()
                assert cm['items'][0]['agent']['avatar_key'] == 'owl', cm['items']
                # 改回 spark 后历史行跟随新头像（当前头像动态读）
                client.patch('/api/agent/profile', headers=agent, json={'avatar_key':'spark'})
                assert client.get(f"/api/agent/threads/{t1['id']}").json()['replies'][0]['agent']['avatar_key'] == 'spark'
                # session PATCH tokens 也接受 avatar_key；跨用户 token id 拒绝
                c = main.db()
                c.execute("INSERT INTO users(username,password_hash,role,display_name,created_at) VALUES('other','h','member','别人','x')")
                oid = c.execute("SELECT id FROM users WHERE username='other'").fetchone()[0]
                c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('other-s',?,'2099-01-01T00:00:00+08:00')", (oid,))
                mid = c.execute("SELECT user_id FROM agent_tokens WHERE name='agent0'").fetchone()[0]
                c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('mentor-s',?,'2099-01-01T00:00:00+08:00')", (mid,))
                tok_id = c.execute("SELECT id FROM agent_tokens WHERE name='agent0'").fetchone()[0]
                c.commit(); c.close()
                assert client.patch(f'/api/agent/tokens/{tok_id}', headers={'Authorization':'Bearer other-s'},
                    json={'avatar_key':'fox'}).status_code == 404  # 不是自己的 token
                r = client.patch(f'/api/agent/tokens/{tok_id}', headers={'Authorization':'Bearer mentor-s'},
                    json={'avatar_key':'fox'})
                assert r.status_code == 200 and r.json()['avatar_key'] == 'fox', r.text
                # 人类 session 不能调 agent/profile
                assert client.patch('/api/agent/profile', headers={'Authorization':'Bearer mentor-s'},
                    json={'avatar_key':'cat'}).status_code == 401
            '''))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


    def test_comment_article_anchor_contract(self):
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
                client.patch('/api/agent/profile', headers=agent, json={'avatar_key':'owl'})
                # 匿名 POST 401
                assert client.post('/api/comments', json={
                    'anchor':'article:journey:people-need-ai','date':'2026-09-22','text':'匿名'}).status_code == 401
                # 501 字拒
                assert client.post('/api/comments', headers=agent, json={
                    'anchor':'article:journey:people-need-ai','date':'2026-09-22','text':'x'*501}).status_code == 400
                # 真实 POST：Markdown 正文 + article 锚点 → 200 pending + 当前头像
                md = '**加粗** 与 `code` 与 [链接](https://example.com)\\n- 列表项'
                r = client.post('/api/comments', headers=agent, json={
                    'anchor':'article:journey:people-need-ai','date':'2026-09-22','text':md})
                assert r.status_code == 200, r.text
                item = r.json()
                assert item['status'] == 'pending' and item['agent']['avatar_key'] == 'owl', item
                # 匿名 GET 不外露 pending
                pub = client.get('/api/comments?anchor=article:journey:people-need-ai').json()
                assert pub['count'] == 0 and pub['items'] == [], pub
                # 另一条锚点的评论做 reply_to 父级 → 跨锚点 400
                other = client.post('/api/comments', headers=agent, json={
                    'anchor':'article:knowledge:k1','date':'2026-09-23','text':'别处'}).json()
                r = client.post('/api/comments', headers=agent, json={
                    'anchor':'article:journey:people-need-ai','date':'2026-09-22',
                    'text':'跨锚点回复','reply_to':other['id']})
                assert r.status_code == 400, r.text
            '''))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

if __name__ == '__main__':
    unittest.main()

