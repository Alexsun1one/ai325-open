"""GARDEN-API R1：偷菜家园私有 API 契约回归。

覆盖：匿名401/Agent403、开通幂等+默认private、播种→(注入时钟)成熟→收获、
串门权限/邻居列表只列他人 members、每茬每人一次偷 + 保护份额上限、
client_id 幂等重放与换负载 409、换茬旧请求失效、并发偷/收不双记、
事件流与分页、落盘持久化。隔离临时 DB + 注入服务端时钟，无生产写入。
"""
import tempfile
import textwrap
import unittest
from pathlib import Path
from app.test_product_performance import _env, _run, _seed_script


BOOT = """
import datetime
import main, garden
from starlette.testclient import TestClient

NOW = {'t': datetime.datetime(2026, 9, 24, 12, 0, 0, tzinfo=main.CST)}
garden.configure(db=main.db, clock=lambda: NOW['t'])
c = main.db()
garden.ensure_schema(c)
uids = {}
for name, disp in [('member2', '成员乙'), ('member3', '成员丙'), ('member4', '成员丁')]:
    uids[name] = c.execute(
        "INSERT INTO users(username,password_hash,role,display_name,created_at) "
        "VALUES(?,?,?,?,?)",
        (name, 'h', 'member', disp, '2026-01-01T00:00:00+08:00'),
    ).lastrowid
for tok, uid in [('h1', 1), ('h2', uids['member2']), ('h3', uids['member3']), ('h4', uids['member4'])]:
    c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES(?,?,'2099-01-01T00:00:00+08:00')",
              (tok, uid))
c.commit(); c.close()
main.app.include_router(garden.router)
client = TestClient(main.app)
u1 = {'Authorization': 'Bearer h1'}
u2 = {'Authorization': 'Bearer h2'}
u3 = {'Authorization': 'Bearer h3'}
u4 = {'Authorization': 'Bearer h4'}
agent = {'Authorization': 'Bearer ai325_agent_perf_test_token'}

def advance(sec):
    NOW['t'] = NOW['t'] + datetime.timedelta(seconds=sec)

def open_garden(h, cid):
    r = client.post('/api/garden/mine', headers=h, json={'client_id': cid})
    assert r.status_code == 200, r.text
    return r.json()['garden']

def ripe_plot(gid_view, plot_id):
    return [x for x in gid_view['garden']['plots'] if x['id'] == plot_id][0]
"""


class GardenApiTest(unittest.TestCase):
    def _boot(self, td: str):
        (Path(td) / "static").mkdir()
        env = _env(Path(td))
        r = _run(env, _seed_script(agent_count=1, audit_per_agent=0))
        self.assertEqual(r.returncode, 0, r.stderr)
        return env

    def test_auth_open_and_visibility(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""
                # 匿名 401（中间件），Agent 403（handler）：9 条路由全覆盖
                for m, path, kw in [
                    ('get', '/api/garden/mine', {}),
                    ('post', '/api/garden/mine', {'json': {'client_id': 'a'}}),
                    ('patch', '/api/garden/mine', {'json': {'visibility': 'members', 'client_id': 'a'}}),
                    ('post', '/api/garden/mine/plant', {'json': {'plot_id': 1, 'crop_id': 'radish', 'client_id': 'a'}}),
                    ('post', '/api/garden/mine/harvest', {'json': {'plot_id': 1, 'cycle_id': 'x', 'client_id': 'a'}}),
                    ('get', '/api/garden/neighbors', {}),
                    ('get', '/api/garden/visit/any', {}),
                    ('post', '/api/garden/visit/any/steal', {'json': {'plot_id': 1, 'cycle_id': 'x', 'client_id': 'a'}}),
                    ('get', '/api/garden/any/events', {}),
                ]:
                    anon = getattr(client, m)(path, **kw)
                    assert anon.status_code == 401, (m, path, anon.status_code)
                    ag = getattr(client, m)(path, headers=agent, **kw)
                    assert ag.status_code == 403, (m, path, ag.status_code, ag.text)
                # 未开通 garden=null，GET 不偷建；rules/server_now 回传
                r0 = client.get('/api/garden/mine', headers=u1)
                assert r0.status_code == 200 and r0.headers['cache-control'] == 'no-store'
                body = r0.json()
                assert body['garden'] is None
                assert body['rules']['plot_count'] == 4 and body['rules']['steal_amount'] == 2
                assert [x['id'] for x in body['rules']['crops']] == ['radish', 'cabbage', 'pumpkin']
                assert 'T' in body['server_now'] and '+' in body['server_now']
                c = main.db()
                assert c.execute('SELECT COUNT(*) FROM gardens').fetchone()[0] == 0
                c.close()
                # 开通：默认 private + 4 块空地；owner 只有 name/member_key 无邮箱
                g1 = client.post('/api/garden/mine', headers=u1, json={'client_id': 'open-1'})
                assert g1.status_code == 200, g1.text
                gd = g1.json()['garden']
                assert gd['is_mine'] and gd['visibility'] == 'private' and gd['harvest_total'] == 0
                assert [p['id'] for p in gd['plots']] == [1, 2, 3, 4]
                assert all(p['state'] == 'empty' and p['can_steal'] is False
                           and p['cycle_id'] is None for p in gd['plots'])
                assert gd['owner']['name'] and 'member_key' in gd['owner'] and 'email' not in gd['owner']
                # 重复开通返回同一园（换 client_id 也同园）
                again = client.post('/api/garden/mine', headers=u1, json={'client_id': 'open-2'})
                assert again.json()['garden']['id'] == gd['id']
                # 同 client_id 换路径/负载 → 409
                assert client.post('/api/garden/mine/plant', headers=u1,
                    json={'plot_id': 1, 'crop_id': 'radish', 'client_id': 'open-1'}).status_code == 409
                assert client.patch('/api/garden/mine', headers=u1,
                    json={'visibility': 'members', 'client_id': 'open-2'}).status_code == 409
                # private：他人 visit/events 404、不进邻居列表
                assert client.get(f"/api/garden/visit/{gd['id']}", headers=u2).status_code == 404
                assert client.get(f"/api/garden/{gd['id']}/events", headers=u2).status_code == 404
                assert client.get('/api/garden/neighbors', headers=u2).json()['total'] == 0
                # 未开通就 PATCH → 404
                assert client.patch('/api/garden/mine', headers=u2,
                    json={'visibility': 'members', 'client_id': 'x'}).status_code == 404
                # 明确开放 → members：他人可 visit、进邻居；关回 → 又 404
                v = client.patch('/api/garden/mine', headers=u1,
                    json={'visibility': 'members', 'client_id': 'v-1'})
                assert v.status_code == 200 and v.json()['garden']['visibility'] == 'members'
                vis = client.get(f"/api/garden/visit/{gd['id']}", headers=u2)
                assert vis.status_code == 200 and vis.json()['garden']['is_mine'] is False
                nb = client.get('/api/garden/neighbors', headers=u2).json()
                assert nb['total'] == 1 and nb['items'][0]['id'] == gd['id']
                assert nb['items'][0]['ripe_count'] == 0 and 'server_now' in nb
                assert client.get('/api/garden/neighbors', headers=u1).json()['total'] == 0  # 不含自己
                client.patch('/api/garden/mine', headers=u1,
                    json={'visibility': 'private', 'client_id': 'v-2'})
                assert client.get(f"/api/garden/visit/{gd['id']}", headers=u2).status_code == 404
            """))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_plant_grow_harvest(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""
                gid = open_garden(u1, 'o')['id']
                # 未知作物 422；不存在地块 404；未开通用户播种 404
                assert client.post('/api/garden/mine/plant', headers=u1,
                    json={'plot_id': 1, 'crop_id': 'weed', 'client_id': 'p0'}).status_code == 422
                assert client.post('/api/garden/mine/plant', headers=u1,
                    json={'plot_id': 9, 'crop_id': 'radish', 'client_id': 'p0b'}).status_code == 404
                assert client.post('/api/garden/mine/plant', headers=u2,
                    json={'plot_id': 1, 'crop_id': 'radish', 'client_id': 'p0c'}).status_code == 404
                # 播种：growing、yield=12、保护份额 9、全新 cycle_id
                p = client.post('/api/garden/mine/plant', headers=u1,
                    json={'plot_id': 1, 'crop_id': 'radish', 'client_id': 'p1'})
                assert p.status_code == 200, p.text
                body = p.json()
                assert body['replayed'] is False and body['action']['kind'] == 'plant'
                plot = ripe_plot(body, 1)
                assert plot['state'] == 'growing' and plot['yield'] == 12
                assert plot['protected_yield'] == 9 and plot['stolen'] == 0
                assert plot['cycle_id'] and plot['can_steal'] is False
                cyc = plot['cycle_id']
                # 落盘持久化：新连接直查
                c = main.db()
                row = c.execute('SELECT * FROM garden_plots WHERE garden_id=? AND plot_id=1', (gid,)).fetchone()
                assert row['crop_id'] == 'radish' and row['cycle_id'] == cyc
                c.close()
                # 幂等重放：同 client_id 同负载 → 同 action 不再执行
                p1b = client.post('/api/garden/mine/plant', headers=u1,
                    json={'plot_id': 1, 'crop_id': 'radish', 'client_id': 'p1'})
                assert p1b.json()['action']['id'] == body['action']['id'] and p1b.json()['replayed'] is True
                # 已占地块重种 409；未成熟收获 409；错 cycle 409
                assert client.post('/api/garden/mine/plant', headers=u1,
                    json={'plot_id': 1, 'crop_id': 'cabbage', 'client_id': 'p2'}).status_code == 409
                assert client.post('/api/garden/mine/harvest', headers=u1,
                    json={'plot_id': 1, 'cycle_id': cyc, 'client_id': 'h0'}).status_code == 409
                assert client.post('/api/garden/mine/harvest', headers=u1,
                    json={'plot_id': 1, 'cycle_id': 'bogus', 'client_id': 'h0b'}).status_code == 409
                # 服务端时钟走过 120s → ripe；失败请求不占 client_id（h0 可复用）
                advance(121)
                mine = client.get('/api/garden/mine', headers=u1).json()
                assert ripe_plot(mine, 1)['state'] == 'ripe'
                h = client.post('/api/garden/mine/harvest', headers=u1,
                    json={'plot_id': 1, 'cycle_id': cyc, 'client_id': 'h0'})
                assert h.status_code == 200, h.text
                hb = h.json()
                assert hb['action']['kind'] == 'harvest' and hb['action']['amount'] == 12
                assert hb['garden']['harvest_total'] == 12
                assert ripe_plot(hb, 1)['state'] == 'empty'
                # 收获重放不加倍
                h2 = client.post('/api/garden/mine/harvest', headers=u1,
                    json={'plot_id': 1, 'cycle_id': cyc, 'client_id': 'h0'})
                assert h2.json()['action']['id'] == hb['action']['id']
                assert h2.json()['garden']['harvest_total'] == 12
                # 换茬：新 cycle_id；旧 cycle 的收获请求 409 不伤新苗
                p3 = client.post('/api/garden/mine/plant', headers=u1,
                    json={'plot_id': 1, 'crop_id': 'pumpkin', 'client_id': 'p3'})
                cyc2 = ripe_plot(p3.json(), 1)['cycle_id']
                assert cyc2 != cyc
                assert client.post('/api/garden/mine/harvest', headers=u1,
                    json={'plot_id': 1, 'cycle_id': cyc, 'client_id': 'h9'}).status_code == 409
                assert ripe_plot(client.get('/api/garden/mine', headers=u1).json(), 1)['state'] == 'growing'
                # 事件流：plant/harvest/plant 倒序，本人可见
                ev = client.get(f'/api/garden/{gid}/events', headers=u1).json()
                assert ev['total'] == 3
                assert [e['kind'] for e in ev['items']] == ['plant', 'harvest', 'plant']
                assert ev['items'][1]['amount'] == 12 and ev['items'][1]['crop_name'] == '萝卜'
                assert all(e['actor']['name'] == '管理员' for e in ev['items'])
            """))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_steal_rules(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""
                gid1 = open_garden(u1, 'o1')['id']
                client.patch('/api/garden/mine', headers=u1,
                    json={'visibility': 'members', 'client_id': 'v1'})
                client.post('/api/garden/mine/plant', headers=u1,
                    json={'plot_id': 1, 'crop_id': 'radish', 'client_id': 'p'})
                advance(121)
                gid2 = open_garden(u2, 'o2')['id']
                # 有家园的访客 can_steal=True；没开家园的 u4 False
                vis = client.get(f'/api/garden/visit/{gid1}', headers=u2).json()
                assert vis['garden']['is_mine'] is False
                plot = ripe_plot(vis, 1)
                assert plot['state'] == 'ripe' and plot['can_steal'] is True
                cyc = plot['cycle_id']
                vis4 = client.get(f'/api/garden/visit/{gid1}', headers=u4).json()
                assert ripe_plot(vis4, 1)['can_steal'] is False
                # 未开家园偷 → 409；偷自己 → 409；未成熟 → 409；错 cycle → 409
                assert client.post(f'/api/garden/visit/{gid1}/steal', headers=u4,
                    json={'plot_id': 1, 'cycle_id': cyc, 'client_id': 's4'}).status_code == 409
                assert client.post(f'/api/garden/visit/{gid1}/steal', headers=u1,
                    json={'plot_id': 1, 'cycle_id': cyc, 'client_id': 'self'}).status_code == 409
                client.post('/api/garden/mine/plant', headers=u1,
                    json={'plot_id': 2, 'crop_id': 'pumpkin', 'client_id': 'p2b'})
                cyc2 = ripe_plot(client.get('/api/garden/mine', headers=u1).json(), 2)['cycle_id']
                assert client.post(f'/api/garden/visit/{gid1}/steal', headers=u2,
                    json={'plot_id': 2, 'cycle_id': cyc2, 'client_id': 'sx'}).status_code == 409
                assert client.post(f'/api/garden/visit/{gid1}/steal', headers=u2,
                    json={'plot_id': 1, 'cycle_id': 'bogus', 'client_id': 'sb'}).status_code == 409
                # u2 偷：min(2, cap3-0)=2 入 u2 总收成；主人地块 stolen=2
                s = client.post(f'/api/garden/visit/{gid1}/steal', headers=u2,
                    json={'plot_id': 1, 'cycle_id': cyc, 'client_id': 's1'})
                assert s.status_code == 200, s.text
                sb = s.json()
                assert sb['garden']['id'] == gid1 and sb['garden']['is_mine'] is False
                assert sb['action']['kind'] == 'steal' and sb['action']['amount'] == 2
                assert ripe_plot(sb, 1)['stolen'] == 2
                assert client.get('/api/garden/mine', headers=u2).json()['garden']['harvest_total'] == 2
                # 重放同 action 不加倍；同访客换 client_id 再偷 → 409（每茬一次）
                s1b = client.post(f'/api/garden/visit/{gid1}/steal', headers=u2,
                    json={'plot_id': 1, 'cycle_id': cyc, 'client_id': 's1'})
                assert s1b.json()['action']['id'] == sb['action']['id']
                assert s1b.json()['replayed'] is True
                assert client.get('/api/garden/mine', headers=u2).json()['garden']['harvest_total'] == 2
                assert client.post(f'/api/garden/visit/{gid1}/steal', headers=u2,
                    json={'plot_id': 1, 'cycle_id': cyc, 'client_id': 's2'}).status_code == 409
                # u3 偷：保护份额只剩 cap3-2=1 → amount=1
                open_garden(u3, 'o3')
                s3 = client.post(f'/api/garden/visit/{gid1}/steal', headers=u3,
                    json={'plot_id': 1, 'cycle_id': cyc, 'client_id': 's3'})
                assert s3.json()['action']['amount'] == 1, s3.text
                # 保护穿到底：u4 开家园后再偷 → 409
                open_garden(u4, 'o4')
                assert client.post(f'/api/garden/visit/{gid1}/steal', headers=u4,
                    json={'plot_id': 1, 'cycle_id': cyc, 'client_id': 's4b'}).status_code == 409
                # 主人收获只得 12-3=9（75% 保护住）；事件流记下两笔偷
                h = client.post('/api/garden/mine/harvest', headers=u1,
                    json={'plot_id': 1, 'cycle_id': cyc, 'client_id': 'h'})
                assert h.json()['action']['amount'] == 9
                assert h.json()['garden']['harvest_total'] == 9
                ev = client.get(f'/api/garden/{gid1}/events', headers=u1).json()
                steals = [e for e in ev['items'] if e['kind'] == 'steal']
                assert len(steals) == 2 and sum(e['amount'] for e in steals) == 3
                assert {e['actor']['name'] for e in steals} == {'成员乙', '成员丙'}
                # 换茬后旧 cycle 偷不动；u2 本茬已偷记录不再影响新茬判断
                client.post('/api/garden/mine/plant', headers=u1,
                    json={'plot_id': 1, 'crop_id': 'radish', 'client_id': 'pn'})
                assert client.post(f'/api/garden/visit/{gid1}/steal', headers=u2,
                    json={'plot_id': 1, 'cycle_id': cyc, 'client_id': 's9'}).status_code == 409
                cyc_new = ripe_plot(client.get('/api/garden/mine', headers=u1).json(), 1)['cycle_id']
                vis2 = client.get(f'/api/garden/visit/{gid1}', headers=u2).json()
                assert ripe_plot(vis2, 1)['can_steal'] is False  # 新茬未成熟
                advance(121)
                vis3 = client.get(f'/api/garden/visit/{gid1}', headers=u2).json()
                assert ripe_plot(vis3, 1)['can_steal'] is True  # 新茬 u2 又可偷
            """))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_concurrent_steal_and_harvest(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""
                import concurrent.futures
                gid1 = open_garden(u1, 'o1')['id']
                client.patch('/api/garden/mine', headers=u1,
                    json={'visibility': 'members', 'client_id': 'v1'})
                open_garden(u2, 'o2'); open_garden(u3, 'o3'); open_garden(u4, 'o4')
                client.post('/api/garden/mine/plant', headers=u1,
                    json={'plot_id': 1, 'crop_id': 'radish', 'client_id': 'p'})
                client.post('/api/garden/mine/plant', headers=u1,
                    json={'plot_id': 2, 'crop_id': 'cabbage', 'client_id': 'p2'})
                client.post('/api/garden/mine/plant', headers=u1,
                    json={'plot_id': 3, 'crop_id': 'radish', 'client_id': 'p3'})
                client.post('/api/garden/mine/plant', headers=u1,
                    json={'plot_id': 4, 'crop_id': 'radish', 'client_id': 'p4'})
                advance(1801)
                mine = client.get('/api/garden/mine', headers=u1).json()
                cyc = {x['id']: x['cycle_id'] for x in mine['garden']['plots']}
                # 两访客并发偷同一地：cap=3，2+1 瓜分，总额守恒
                def steal(h, cid, pid):
                    return client.post(f'/api/garden/visit/{gid1}/steal', headers=h,
                        json={'plot_id': pid, 'cycle_id': cyc[pid], 'client_id': cid})
                with concurrent.futures.ThreadPoolExecutor(4) as ex:
                    rs = list(ex.map(lambda a: steal(*a), [(u2, 'c2', 1), (u3, 'c3', 1)]))
                assert sorted(x.status_code for x in rs) == [200, 200], [x.status_code for x in rs]
                amounts = sorted(x.json()['action']['amount'] for x in rs)
                assert amounts == [1, 2], amounts
                st = client.get(f'/api/garden/visit/{gid1}', headers=u2).json()
                assert ripe_plot(st, 1)['stolen'] == 3
                # 同访客并发双击（不同 client_id）：唯一索引兜底只成功一次
                with concurrent.futures.ThreadPoolExecutor(2) as ex:
                    rs2 = list(ex.map(lambda cid: steal(u4, cid, 3), ['d1', 'd2']))
                assert sorted(x.status_code for x in rs2) == [200, 409], [x.status_code for x in rs2]
                # 同 client_id 并发重试：一真一回放，同 action id 不加倍
                with concurrent.futures.ThreadPoolExecutor(2) as ex:
                    rs3 = list(ex.map(lambda _: steal(u4, 'dup', 4), range(2)))
                assert sorted(x.status_code for x in rs3) == [200, 200]
                ids = {x.json()['action']['id'] for x in rs3}
                assert len(ids) == 1 and ripe_plot(rs3[0].json(), 4)['stolen'] == 2
                assert client.get('/api/garden/mine', headers=u4).json()['garden']['harvest_total'] == 4
                # 收获与偷并发：谁先谁后都结算正确（18+2 或 20+0，守恒）
                def harvest():
                    return client.post('/api/garden/mine/harvest', headers=u1,
                        json={'plot_id': 2, 'cycle_id': cyc[2], 'client_id': 'hh'})
                with concurrent.futures.ThreadPoolExecutor(2) as ex:
                    fh = ex.submit(harvest); fs = ex.submit(steal, u3, 'c3b', 2)
                    rh, rsh = fh.result(), fs.result()
                g = client.get('/api/garden/mine', headers=u1).json()['garden']
                p2 = ripe_plot({'garden': g}, 2)
                # 守恒：无论谁先提交，偷得 + 收得 == 总产量 20，不双记不丢失
                amt_s = rsh.json()['action']['amount'] if rsh.status_code == 200 else 0
                assert rsh.status_code in (200, 409) and rh.status_code == 200
                amt_h = rh.json()['action']['amount']
                assert amt_s + amt_h == 20, (amt_s, amt_h)
                assert p2['state'] == 'empty' and p2['stolen'] == 0
            """))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_neighbors_pagination_and_events(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""
                gid1 = open_garden(u1, 'a')['id']
                gid2 = open_garden(u2, 'b')['id']
                gid3 = open_garden(u3, 'c')['id']
                for h, cid in [(u1, 'av'), (u2, 'bv'), (u3, 'cv')]:
                    client.patch('/api/garden/mine', headers=h,
                        json={'visibility': 'members', 'client_id': cid})
                client.post('/api/garden/mine/plant', headers=u1,
                    json={'plot_id': 1, 'crop_id': 'radish', 'client_id': 'x'})
                advance(121)
                # 邻居：只列他人 members，ripe 园排前，total 真值
                nb = client.get('/api/garden/neighbors', headers=u2).json()
                assert nb['total'] == 2 and nb['limit'] == 12 and nb['offset'] == 0
                ids = [i['id'] for i in nb['items']]
                assert gid1 in ids and gid3 in ids and gid2 not in ids
                assert nb['items'][0]['id'] == gid1 and nb['items'][0]['ripe_count'] == 1
                assert all('is_mine' not in i and 'plots' not in i for i in nb['items'])
                # limit clamp 30、offset 翻页不重复
                assert client.get('/api/garden/neighbors?limit=99', headers=u2).json()['limit'] == 30
                p1 = client.get('/api/garden/neighbors?limit=1&offset=0', headers=u2).json()
                p2 = client.get('/api/garden/neighbors?limit=1&offset=1', headers=u2).json()
                assert len(p1['items']) == 1 and p1['items'][0]['id'] != p2['items'][0]['id']
                assert p1['total'] == 2 == p2['total']
                # private 园（u4 只开通不开放）不进邻居
                gid4 = open_garden(u4, 'd')['id']
                assert client.get('/api/garden/neighbors', headers=u2).json()['total'] == 2
                # 事件：members 园他人可读；private 园他人 404 本人 200；分页真实
                ev = client.get(f'/api/garden/{gid1}/events?limit=1', headers=u3).json()
                assert ev['limit'] == 1 and ev['total'] >= 2 and len(ev['items']) == 1
                ev2 = client.get(f'/api/garden/{gid1}/events?limit=1&offset=1', headers=u3).json()
                assert ev2['items'][0]['id'] != ev['items'][0]['id']
                assert client.get(f'/api/garden/{gid4}/events', headers=u2).status_code == 404
                assert client.get(f'/api/garden/{gid4}/events', headers=u4).status_code == 200
                # visibility 事件如实记录开放/关闭方向
                kinds = [(e['kind'], e['amount']) for e in
                         client.get(f'/api/garden/{gid1}/events', headers=u1).json()['items']]
                assert ('visibility', 1) in kinds
            """))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
