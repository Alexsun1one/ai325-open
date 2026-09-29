"""私稿/家园 API 家族全响应 no-store（含鉴权中间件提前返回与异常路径）。"""
import tempfile
import textwrap
import unittest
from pathlib import Path
from app.test_product_performance import _env, _run, _seed_script


class PrivateApiNoStoreTest(unittest.TestCase):
    def test_practice_garden_family_no_store_all_statuses(self):
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
                human = {'Authorization': 'Bearer human-test'}
                agent = {'Authorization': 'Bearer ai325_agent_perf_test_token'}

                def check(method, url, expected, **kw):
                    r = getattr(client, method)(url, **kw)
                    assert r.status_code == expected, (url, r.status_code, r.text[:200])
                    assert r.headers.get('cache-control') == 'no-store', (url, r.headers.get('cache-control'))
                    return r

                # 匿名 401（鉴权中间件提前返回，不经路由 Depends）
                check('get', '/api/practice/challenges', 401)
                check('get', '/api/garden/companion', 401)
                check('get', '/api/garden/mine', 401)
                # 登录 200
                check('get', '/api/practice/challenges', 200, headers=human)
                check('get', '/api/practice/mine', 200, headers=human)
                check('get', '/api/garden/companion', 200, headers=human)
                # Agent 403（路由 _member 拒绝，不经 auth 提前返回）
                check('get', '/api/practice/challenges', 403, headers=agent)
                check('get', '/api/garden/companion', 403, headers=agent)
                # 业务 404 / 409 / 422
                check('get', '/api/practice/mine/no-such-id', 404, headers=human)
                check('get', '/api/practice/submissions/no-such-id', 404, headers=human)
                p = check('post', '/api/practice/mine', 200, headers=human,
                          json={'title': 'no-store 验收', 'outcome': '覆盖 409 冲突'}).json()
                check('patch', f"/api/practice/mine/{p['id']}", 409, headers=human,
                      json={'revision': p['revision'] + 9, 'title': ' stale write '})
                check('post', '/api/practice/mine', 422, headers=human, json={})
                check('patch', '/api/garden/companion', 422, headers=human, json={'selected_id': 'not-a-real-pet'})
                # 非目标路径不强加 no-store
                r = client.get('/api/events')
                assert r.status_code == 200
                assert r.headers.get('cache-control') != 'no-store', r.headers
                print('NO_STORE_TEST_OK')
            '''))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('NO_STORE_TEST_OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
