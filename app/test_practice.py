"""GROWTH-API R1：实践与共练私有 API 契约回归。

覆盖：匿名401/Agent403/他人404、创建→读取→PATCH revision冲突、共练 join 幂等、
提交快照隔离与重复提交幂等、回复 client_id 幂等、分页 total、URL 白名单、
PATCH 字段白名单、no-store 头、种子共练真实加载。隔离临时 DB，无生产写入。
"""
import tempfile
import textwrap
import unittest
from pathlib import Path
from app.test_product_performance import _env, _run, _seed_script


BOOT = """
import main
from starlette.testclient import TestClient
client = TestClient(main.app)
c = main.db()
uid2 = c.execute(
    "INSERT INTO users(username,password_hash,role,display_name,created_at) "
    "VALUES(?,?,?,?,?)",
    ("member2", "h", "member", "成员乙", "2026-01-01T00:00:00+08:00"),
).lastrowid
c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('h1',1,'2099-01-01T00:00:00+08:00')")
c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('h2',?,'2099-01-01T00:00:00+08:00')", (uid2,))
c.commit(); c.close()
u1 = {'Authorization': 'Bearer h1'}
u2 = {'Authorization': 'Bearer h2'}
agent = {'Authorization': 'Bearer ai325_agent_perf_test_token'}
"""


class PracticeApiTest(unittest.TestCase):
    def _boot(self, td: str):
        (Path(td) / "static").mkdir()
        env = _env(Path(td))
        r = _run(env, _seed_script(agent_count=1, audit_per_agent=0))
        self.assertEqual(r.returncode, 0, r.stderr)
        return env

    def test_auth_matrix_and_seeds(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""
                # 种子常设共练真实加载（3 项，open，无编造参与者）
                ch = client.get('/api/practice/challenges', headers=u1)
                assert ch.status_code == 200, ch.text
                assert ch.headers['cache-control'] == 'no-store', ch.headers
                items = ch.json()['items']
                assert len(items) >= 3, items
                assert all(i['status'] == 'open' and i['submission_count'] == 0
                           and i['my_practice_id'] is None and i['instructions'] for i in items), items
                assert ch.json()['total'] == len(items)
                # 匿名 401（中间件），Agent 403（handler）
                for m, path, kw in [
                    ('get', '/api/practice/mine', {}),
                    ('post', '/api/practice/mine', {'json': {'title': 't', 'outcome': 'o'}}),
                    ('get', '/api/practice/challenges', {}),
                    ('post', '/api/practice/challenges/x/join', {'json': {}}),
                    ('get', '/api/practice/submissions?challenge_id=x', {}),
                    ('post', '/api/practice/submissions/x/replies', {'json': {'text': 't', 'client_id': 'c'}}),
                ]:
                    anon = getattr(client, m)(path, **kw)
                    assert anon.status_code == 401, (m, path, anon.status_code)
                    ag = getattr(client, m)(path, headers=agent, **kw)
                    assert ag.status_code == 403, (m, path, ag.status_code, ag.text)
            """))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_crud_revision_and_privacy(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""
                # 创建：私稿不自动公开，无 challenge_id
                p = client.post('/api/practice/mine', headers=u1,
                    json={'title': '读完拆书笔记一章', 'outcome': '提炼三条可用方法',
                          'next_step': '今晚读 30 分钟', 'source_url': '/learn/entries/kb-03/',
                          'source_title': '知识库条目'})
                assert p.status_code == 200, p.text
                pr = p.json()
                assert pr['status'] == 'active' and pr['revision'] == 1 and pr['challenge_id'] is None
                assert 'owner_id' not in pr
                assert 'T' in pr['created_at'] and '+' in pr['created_at']
                pid = pr['id']
                # 列表与详情只给本人
                mine = client.get('/api/practice/mine', headers=u1).json()
                assert mine['total'] == 1 and mine['items'][0]['id'] == pid
                assert client.get(f'/api/practice/mine/{pid}', headers=u2).status_code == 404
                assert client.get('/api/practice/mine', headers=u2).json()['total'] == 0
                # PATCH 乐观并发：正常升 revision，旧版 409，越权字段 422
                ok = client.patch(f'/api/practice/mine/{pid}', headers=u1,
                    json={'revision': 1, 'notes': '第一\\n行\\n第二行', 'status': 'completed'})
                assert ok.status_code == 200, ok.text
                assert ok.json()['revision'] == 2 and ok.json()['notes'] == '第一\\n行\\n第二行'  # LF 保留
                stale = client.patch(f'/api/practice/mine/{pid}', headers=u1,
                    json={'revision': 1, 'title': '覆盖'})
                assert stale.status_code == 409, stale.text
                extra = client.patch(f'/api/practice/mine/{pid}', headers=u1,
                    json={'revision': 2, 'owner_id': uid2})
                assert extra.status_code == 422, extra.text
                bad_status = client.patch(f'/api/practice/mine/{pid}', headers=u1,
                    json={'revision': 2, 'status': 'deleted'})
                assert bad_status.status_code == 422
                # 完成可恢复 active；archive 不删记录
                back = client.patch(f'/api/practice/mine/{pid}', headers=u1,
                    json={'revision': 2, 'status': 'active'})
                assert back.json()['status'] == 'active' and back.json()['revision'] == 3
                arch = client.patch(f'/api/practice/mine/{pid}', headers=u1,
                    json={'revision': 3, 'status': 'archived'})
                assert arch.json()['status'] == 'archived'
                assert client.get('/api/practice/mine?status=archived', headers=u1).json()['total'] == 1
                # 他人 PATCH 404；显式 null 是 422 不是 500（NOT NULL 列不落库）
                assert client.patch(f'/api/practice/mine/{pid}', headers=u2,
                    json={'revision': 4, 'title': 'x'}).status_code == 404
                for null_field in ('status', 'title', 'notes', 'result_url'):
                    nr = client.patch(f'/api/practice/mine/{pid}', headers=u1,
                        json={'revision': 4, null_field: None})
                    assert nr.status_code == 422, (null_field, nr.status_code, nr.text)
                # URL 白名单：控制字节、空主机、协议相对、反斜杠、非 http(s) 全拒
                for bad in ['javascript:alert(1)', 'data:text/html,x', '//evil.com/x', 'a\\\\b', 'ftp://x',
                            '/\\t/host', 'https://', 'https:///path', 'https://?q=1', 'HTTP://']:
                    bad_resp = client.post('/api/practice/mine', headers=u1,
                        json={'title': 't', 'outcome': 'o', 'source_url': bad})
                    assert bad_resp.status_code == 422, (bad, bad_resp.status_code)
                # 合法 URL 仍放行
                for good in ['https://example.com/a?b=1', 'http://x.io', '/learn/entries/kb-03/', '']:
                    ok_resp = client.post('/api/practice/mine', headers=u1,
                        json={'title': 't', 'outcome': 'o', 'source_url': good})
                    assert ok_resp.status_code == 200, (good, ok_resp.status_code, ok_resp.text)
            """))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_join_submit_snapshot_replies(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""
                chid = client.get('/api/practice/challenges', headers=u1).json()['items'][0]['id']
                # join 幂等：两次返回同一实践
                j1 = client.post(f'/api/practice/challenges/{chid}/join', headers=u1, json={})
                assert j1.status_code == 200, j1.text
                j2 = client.post(f'/api/practice/challenges/{chid}/join', headers=u1, json={})
                assert j2.json()['id'] == j1.json()['id']
                pid = j1.json()['id']
                assert j1.json()['challenge_id'] == chid
                lst = client.get('/api/practice/challenges', headers=u1).json()
                assert [i for i in lst['items'] if i['id'] == chid][0]['my_practice_id'] == pid
                # 未关联共练的私稿不能提交
                free = client.post('/api/practice/mine', headers=u1,
                    json={'title': '私稿', 'outcome': 'o'}).json()
                assert client.post(f"/api/practice/mine/{free['id']}/submit", headers=u1,
                    json={'revision': 1, 'body': 'b'}).status_code == 422
                # revision 不符 409；正式提交拿到快照
                assert client.post(f'/api/practice/mine/{pid}/submit', headers=u1,
                    json={'revision': 99, 'body': 'b'}).status_code == 409
                s1 = client.post(f'/api/practice/mine/{pid}/submit', headers=u1,
                    json={'revision': 1, 'body': '做完了\\n第二步记录', 'result_url': 'https://example.com/r'})
                assert s1.status_code == 200, s1.text
                sub = s1.json()
                assert sub['practice_id'] == pid and sub['is_mine'] and sub['revision'] == 1
                assert sub['body'] == '做完了\\n第二步记录'
                # 同 practice 同 revision 重复提交 → 同一快照不加倍
                s1b = client.post(f'/api/practice/mine/{pid}/submit', headers=u1,
                    json={'revision': 1, 'body': '不同的正文不该覆盖'})
                assert s1b.json()['id'] == sub['id'] and s1b.json()['body'] == sub['body']
                # 私稿后续修改不污染已发快照（join 后 revision=1，submit 不涨实践版本）
                client.patch(f'/api/practice/mine/{pid}', headers=u1, json={'revision': 1, 'title': '改名后的实践'})
                got = client.get(f"/api/practice/submissions/{sub['id']}", headers=u1).json()
                assert got['title'] != '改名后的实践' and got['body'] == '做完了\\n第二步记录'
                # 新 revision 可再提交 → 新快照
                s2 = client.post(f'/api/practice/mine/{pid}/submit', headers=u1,
                    json={'revision': 2, 'body': '第二版'})
                assert s2.json()['id'] != sub['id'] and s2.json()['revision'] == 2
                # 隐私：私人实践带 result_url，共享提交留空 → 快照 result_url 必须是空
                # （提交预览只给用户看将发布的内容，暗带私人链接属泄露）
                client.patch(f'/api/practice/mine/{pid}', headers=u1,
                    json={'revision': 2, 'result_url': 'https://private.example/internal-notes'})
                s3 = client.post(f'/api/practice/mine/{pid}/submit', headers=u1,
                    json={'revision': 3, 'body': '第三版'})
                assert s3.status_code == 200, s3.text
                assert s3.json()['result_url'] == '', s3.json()
                # 且对他人公开视图里同样是空（快照里就没存）
                other3 = [i for i in client.get(
                    f'/api/practice/submissions?challenge_id={chid}', headers=u2
                ).json()['items'] if i['id'] == s3.json()['id']][0]
                assert other3['result_url'] == '', other3
                # 提交列表：challenge_id 必填；他人看 practice_id=null、is_mine=false
                assert client.get('/api/practice/submissions', headers=u1).status_code == 422
                pub = client.get(f'/api/practice/submissions?challenge_id={chid}', headers=u2).json()
                assert pub['total'] == 3
                other_view = [i for i in pub['items'] if i['id'] == sub['id']][0]
                assert other_view['practice_id'] is None and other_view['is_mine'] is False
                assert other_view['author']['kind'] == 'human' and other_view['author']['name']
                # 回复：幂等 client_id + 分页 total 真实
                r1 = client.post(f"/api/practice/submissions/{sub['id']}/replies", headers=u2,
                    json={'text': '这个卡点我也遇到过', 'client_id': 'u2-c1'})
                assert r1.status_code == 200, r1.text
                r1b = client.post(f"/api/practice/submissions/{sub['id']}/replies", headers=u2,
                    json={'text': '重试不应重复', 'client_id': 'u2-c1'})
                assert r1b.json()['id'] == r1.json()['id']
                reps = client.get(f"/api/practice/submissions/{sub['id']}/replies", headers=u1).json()
                assert reps['total'] == 1 and reps['items'][0]['author']['name'] == '成员乙'
                # 提交数实时真值
                lst2 = client.get('/api/practice/challenges', headers=u1).json()
                assert [i for i in lst2['items'] if i['id'] == chid][0]['submission_count'] == 3
            """))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_pagination_and_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""
                for i in range(25):
                    client.post('/api/practice/mine', headers=u1,
                        json={'title': f'第{i}件', 'outcome': 'o'})
                page1 = client.get('/api/practice/mine?limit=20&offset=0', headers=u1).json()
                assert page1['total'] == 25 and len(page1['items']) == 20 and page1['limit'] == 20
                page2 = client.get('/api/practice/mine?limit=99&offset=20', headers=u1).json()
                assert page2['limit'] == 50 and len(page2['items']) == 5
                # 同一连接库直查持久化：行确实落盘不是内存态
                c = main.db()
                n = c.execute('SELECT COUNT(*) FROM practice_items WHERE owner_id=1').fetchone()[0]
                c.close()
                assert n == 25, n
            """))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
