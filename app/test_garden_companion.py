"""GARDEN-COMPANION R1：护法/图鉴/成就足迹回归。

覆盖：匿名401/Agent403、新账号全0且GET不建园、播种/收获后累计、偷菜不冒充种植、
UTC+8 跨日、设置保存/取消/非法422、护法提示随真实地块变化、他人数据隔离、schema 幂等。
隔离临时 DB + 注入服务端时钟。
"""
import tempfile
import textwrap
import unittest
from pathlib import Path
from app.test_product_performance import _env, _run, _seed_script


BOOT = """
import datetime
import main, garden, garden_companion
from starlette.testclient import TestClient

NOW = {'t': datetime.datetime(2026, 9, 24, 12, 0, 0, tzinfo=main.CST)}
garden.configure(db=main.db, clock=lambda: NOW['t'])  # 时钟注入；db/schema/路由均来自真实 main
c = main.db()
uids = {}
for name, disp in [('member2', '成员乙'), ('member3', '成员丙')]:
    uids[name] = c.execute(
        "INSERT INTO users(username,password_hash,role,display_name,created_at) VALUES(?,?,?,?,?)",
        (name, 'h', 'member', disp, '2026-01-01T00:00:00+08:00'),
    ).lastrowid
for tok, uid in [('h1', 1), ('h2', uids['member2']), ('h3', uids['member3'])]:
    c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES(?,?,'2099-01-01T00:00:00+08:00')", (tok, uid))
c.commit(); c.close()
# 路由由真实 main 挂载（SPA mount 之前），测试不手动 include
client = TestClient(main.app)
u1 = {'Authorization': 'Bearer h1'}
u2 = {'Authorization': 'Bearer h2'}
u3 = {'Authorization': 'Bearer h3'}
agent = {'Authorization': 'Bearer ai325_agent_perf_test_token'}
_n = {'i': 0}

def cid():
    _n['i'] += 1
    return 'cid-%d' % _n['i']

def advance(sec):
    NOW['t'] = NOW['t'] + datetime.timedelta(seconds=sec)

def open_garden(h):
    r = client.post('/api/garden/mine', headers=h, json={'client_id': cid()})
    assert r.status_code == 200, r.text
    return r.json()['garden']

def plant(h, plot, crop):
    r = client.post('/api/garden/mine/plant', headers=h, json={'plot_id': plot, 'crop_id': crop, 'client_id': cid()})
    assert r.status_code == 200, r.text
    return r.json()

def harvest(h, plot, cycle):
    r = client.post('/api/garden/mine/harvest', headers=h, json={'plot_id': plot, 'cycle_id': cycle, 'client_id': cid()})
    assert r.status_code == 200, r.text
    return r.json()

def comp(h):
    r = client.get('/api/garden/companion', headers=h)
    assert r.status_code == 200, r.text
    assert r.headers['cache-control'] == 'no-store'
    return r.json()

def crop(view, cid_):
    return [x for x in view['codex']['crops'] if x['id'] == cid_][0]

def ms(view, mid):
    return [x for x in view['milestones']['items'] if x['id'] == mid][0]
"""


class GardenCompanionTest(unittest.TestCase):
    def _boot(self, td: str):
        (Path(td) / "static").mkdir()
        env = _env(Path(td))
        r = _run(env, _seed_script(agent_count=1, audit_per_agent=0))
        self.assertEqual(r.returncode, 0, r.stderr)
        return env

    def _go(self, body: str):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent(body))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_auth_and_new_account_is_zero(self):
        self._go("""
            for m, kw in [('get', {}), ('patch', {'json': {'guardian_id': None}})]:
                assert getattr(client, m)('/api/garden/companion', **kw).status_code == 401
                assert getattr(client, m)('/api/garden/companion', headers=agent, **kw).status_code == 403
            v = comp(u1)
            assert v['garden_open'] is False
            c = main.db()
            assert c.execute('SELECT COUNT(*) FROM gardens').fetchone()[0] == 0  # GET 不建园
            assert c.execute('SELECT COUNT(*) FROM garden_companion_preferences').fetchone()[0] == 0
            c.close()
            assert v['codex']['unlocked'] == 0 and v['codex']['total'] == 3
            assert all(x['status'] == 'locked' and x['planted'] == 0 and x['harvested'] == 0
                       for x in v['codex']['crops'])
            assert v['milestones']['unlocked'] == 0
            assert all(i['unlocked'] is False and i['unlocked_at'] is None and i['value'] == 0
                       for i in v['milestones']['items'])
            days = v['footprint']['days']
            assert len(days) == 7 and days[-1]['date'] == '2026-09-24' and days[0]['date'] == '2026-09-18'
            assert all(d['planted'] == 0 and d['harvested'] == 0 and d['harvested_amount'] == 0 for d in days)
            assert v['footprint']['timezone'] == 'UTC+8'
            assert v['guardian']['selected_id'] is None and v['guardian']['watch'] is None
            assert 1 <= len(v['guardian']['options']) <= 3 and v['guardian']['note']
            assert v['protection'] == {'steal_fraction': 0.25, 'steal_amount': 2}
        """)

    def test_plant_harvest_accumulate_and_steal_is_not_planting(self):
        self._go("""
            open_garden(u1); open_garden(u2)
            r = plant(u1, 1, 'radish')
            cy = r['garden']['plots'][0]['cycle_id']
            v = comp(u1)
            assert crop(v, 'radish')['status'] == 'planted' and crop(v, 'radish')['planted'] == 1
            assert crop(v, 'radish')['first_planted_at'] == '2026-09-24T12:00:00+08:00'
            assert v['codex']['unlocked'] == 1
            fp1 = ms(v, 'first-plant')
            assert fp1['unlocked'] and fp1['unlocked_at'] == '2026-09-24T12:00:00+08:00'
            assert not ms(v, 'first-harvest')['unlocked']
            advance(121)
            h = harvest(u1, 1, cy)
            gain = h['action']['amount']
            assert gain == 12
            v = comp(u1)
            assert crop(v, 'radish')['status'] == 'harvested' and crop(v, 'radish')['harvested'] == 1
            assert crop(v, 'radish')['harvested_amount'] == 12
            fh = ms(v, 'first-harvest')
            assert fh['unlocked'] and fh['unlocked_at'] == '2026-09-24T12:02:01+08:00'
            assert ms(v, 'harvest-50')['value'] == 12 and not ms(v, 'harvest-50')['unlocked']
            assert v['footprint']['totals'] == {'planted': 1, 'harvested': 1, 'harvested_amount': 12}
            assert v['footprint']['days'][-1]['planted'] == 1 and v['footprint']['days'][-1]['harvested'] == 1
            # u2 种白菜，u1 去偷：u1 的图鉴不出现白菜、不增种植、不增收获数
            p2 = plant(u2, 1, 'cabbage')
            cy2 = p2['garden']['plots'][0]['cycle_id']
            assert client.patch('/api/garden/mine', headers=u2,
                json={'visibility': 'members', 'client_id': cid()}).status_code == 200
            advance(700)
            gid2 = client.get('/api/garden/mine', headers=u2).json()['garden']['id']
            s = client.post('/api/garden/visit/%s/steal' % gid2, headers=u1,
                json={'plot_id': 1, 'cycle_id': cy2, 'client_id': cid()})
            assert s.status_code == 200, s.text
            v = comp(u1)
            assert crop(v, 'cabbage')['status'] == 'locked' and crop(v, 'cabbage')['planted'] == 0
            assert v['codex']['unlocked'] == 1
            assert v['footprint']['totals']['planted'] == 1 and v['footprint']['totals']['harvested'] == 1
            assert ms(v, 'harvest-50')['value'] == 12  # 偷来的不进累计收成
            # 被偷的主人 u2 自己的种植统计不受偷菜事件污染
            v2 = comp(u2)
            assert crop(v2, 'cabbage')['planted'] == 1 and crop(v2, 'cabbage')['harvested'] == 0
            assert v2['footprint']['totals']['planted'] == 1 and v2['footprint']['totals']['harvested'] == 0
        """)

    def test_cross_day_utc8_milestones_and_days(self):
        self._go("""
            open_garden(u1)
            NOW['t'] = datetime.datetime(2026, 9, 24, 23, 59, 0, tzinfo=main.CST)
            cy = plant(u1, 1, 'radish')['garden']['plots'][0]['cycle_id']
            advance(120)   # 2026-09-25 00:01 CST，仍是 09-24 16:01 UTC
            harvest(u1, 1, cy)
            NOW['t'] = datetime.datetime(2026, 9, 25, 9, 0, 0, tzinfo=main.CST)
            plant(u1, 2, 'cabbage')
            plant(u1, 3, 'pumpkin')
            v = comp(u1)
            byd = {d['date']: d for d in v['footprint']['days']}
            assert byd['2026-09-24']['planted'] == 1 and byd['2026-09-24']['harvested'] == 0
            assert byd['2026-09-25']['planted'] == 2 and byd['2026-09-25']['harvested'] == 1
            assert v['footprint']['days'][-1]['date'] == '2026-09-25'
            assert ms(v, 'days-3')['value'] == 2 and not ms(v, 'days-3')['unlocked']
            assert ms(v, 'crops-3')['unlocked'] and ms(v, 'crops-3')['unlocked_at'] == '2026-09-25T09:00:00+08:00'
            # UTC 存储的事件按 UTC+8 归日：16:30 UTC == 次日 00:30 CST
            c = main.db()
            c.execute("INSERT INTO garden_events(id,garden_id,kind,actor_id,plot_id,cycle_id,crop_name,amount,created_at) "
                      "VALUES('ev_utc','x','plant',1,1,'cy_utc','萝卜',0,'2026-09-24T16:30:00+00:00')")
            c.commit(); c.close()
            v = comp(u1)
            byd = {d['date']: d for d in v['footprint']['days']}
            assert byd['2026-09-25']['planted'] == 3 and byd['2026-09-24']['planted'] == 1
            # 窗口滚动：前进 7 天，旧日不在窗口且总数只算窗口内
            NOW['t'] = datetime.datetime(2026, 10, 2, 9, 0, 0, tzinfo=main.CST)
            v = comp(u1)
            assert v['footprint']['days'][0]['date'] == '2026-09-26'
            assert v['footprint']['totals'] == {'planted': 0, 'harvested': 0, 'harvested_amount': 0}
            assert v['codex']['unlocked'] == 3   # 图鉴是累计，不随窗口消失
        """)

    def test_guardian_preference_and_watch(self):
        self._go("""
            opts = comp(u1)['guardian']['options']
            gid = opts[0]['id']
            r = client.patch('/api/garden/companion', headers=u1, json={'guardian_id': gid})
            assert r.status_code == 200 and r.json()['guardian']['selected_id'] == gid
            assert r.json()['guardian']['watch']['kind'] == 'no_garden'
            assert r.json()['garden_open'] is False
            # 幂等重复保存 + 持久化
            client.patch('/api/garden/companion', headers=u1, json={'guardian_id': gid})
            assert comp(u1)['guardian']['selected_id'] == gid
            c = main.db()
            assert c.execute('SELECT COUNT(*) FROM garden_companion_preferences').fetchone()[0] == 1
            assert c.execute('SELECT COUNT(*) FROM gardens').fetchone()[0] == 0
            c.close()
            # 他人不受影响，只写本人
            assert comp(u2)['guardian']['selected_id'] is None
            # 非法 id / 缺字段 / 多余字段 / 类型 → 422，原选择不变
            for body in [{'guardian_id': 'nope'}, {}, {'guardian_id': 1}, {'guardian_id': gid, 'owner_id': 2}]:
                assert client.patch('/api/garden/companion', headers=u1, json=body).status_code == 422, body
            assert comp(u1)['guardian']['selected_id'] == gid
            # 开园后按真实地块：全空 → empty
            open_garden(u1)
            w = comp(u1)['guardian']['watch']
            assert w['kind'] == 'empty' and w['situation']['empty'] == 4 and w['situation']['ripe'] == 0
            assert '4' in w['message']
            cy = plant(u1, 1, 'radish')['garden']['plots'][0]['cycle_id']
            for p in (2, 3, 4):
                plant(u1, p, 'pumpkin')
            w = comp(u1)['guardian']['watch']
            assert w['kind'] == 'waiting' and w['situation']['growing'] == 4
            assert w['situation']['next_ripe_at'] == '2026-09-24T12:02:00+08:00'
            advance(121)
            w = comp(u1)['guardian']['watch']
            assert w['kind'] == 'ripe' and w['situation']['ripe'] == 1 and w['situation']['growing'] == 3
            # 护法不自动收割、不改数据：收成与地块未变
            g = client.get('/api/garden/mine', headers=u1).json()['garden']
            assert g['harvest_total'] == 0 and g['plots'][0]['state'] == 'ripe'
            # 取消护法
            r = client.patch('/api/garden/companion', headers=u1, json={'guardian_id': None})
            assert r.status_code == 200 and r.json()['guardian']['selected_id'] is None
            assert r.json()['guardian']['watch'] is None
            # 库里存了已下线的 id：视为未选
            c = main.db()
            c.execute("UPDATE garden_companion_preferences SET guardian_id='gone' WHERE owner_id=1")
            c.commit(); c.close()
            assert comp(u1)['guardian']['selected_id'] is None
        """)

    def test_routes_mounted_by_real_main_before_spa(self):
        self._go("""
            paths = [getattr(r, 'path', '') for r in main.app.router.routes]
            i = paths.index('/api/garden/companion')
            mount = [k for k, r in enumerate(main.app.router.routes) if type(r).__name__ == 'Mount' and r.path == '']
            assert mount and i < mount[0]
            assert paths.count('/api/garden/companion') == 2   # GET + PATCH
            c = main.db()
            assert c.execute("SELECT name FROM sqlite_master WHERE name='garden_companion_preferences'").fetchone()
            c.close()
        """)

    def test_isolation_and_schema_idempotent(self):
        self._go("""
            open_garden(u1); open_garden(u3)
            plant(u3, 1, 'radish')
            assert comp(u1)['codex']['unlocked'] == 0     # u3 的种植不进 u1
            assert comp(u3)['codex']['unlocked'] == 1
            # 不支持查询他人：多余 query 参数被忽略，仍只返回本人
            r = client.get('/api/garden/companion?owner_id=%d' % 3, headers=u1)
            assert r.status_code == 200 and r.json()['codex']['unlocked'] == 0
            c = main.db()
            for _ in range(2):
                garden_companion.ensure_schema(c)
            idx = [r[1] for r in c.execute("PRAGMA index_list(garden_events)")]
            assert 'garden_events_actor_created' in idx
            cols = [r[1] for r in c.execute("PRAGMA table_info(garden_companion_preferences)")]
            assert cols == ['owner_id', 'guardian_id', 'updated_at']
            c.close()
        """)


if __name__ == "__main__":
    unittest.main()
