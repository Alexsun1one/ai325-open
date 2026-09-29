"""GARDEN-MARKS R1：真实 main 路由回归。

覆盖冻结契约验收清单：鉴权矩阵、私园404、默认private快照、显式show、
实践状态撤回自动隐藏且不自动复开、上限4块、DELETE只撤木牌、
client_id幂等/冲突/重放不复活、访客严格字段、站外与不存在来源→null、
本站绝对地址归一、老库幂等升级。隔离临时数据目录，无生产读写。
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
uid1 = c.execute(
    "INSERT INTO users(username,password_hash,role,display_name,created_at) "
    "VALUES(?,?,?,?,?)",
    ("member1", "h", "member", "成员甲", "2026-01-01T00:00:00+08:00"),
).lastrowid
uid2 = c.execute(
    "INSERT INTO users(username,password_hash,role,display_name,created_at) "
    "VALUES(?,?,?,?,?)",
    ("member2", "h", "member", "成员乙", "2026-01-01T00:00:00+08:00"),
).lastrowid
c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('h1',?,'2099-01-01T00:00:00+08:00')", (uid1,))
c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('h2',?,'2099-01-01T00:00:00+08:00')", (uid2,))
# 本人花园（private 默认）+ 他人花园（members 开放）
c.execute("INSERT INTO gardens(id,owner_id,visibility,harvest_total,created_at) VALUES('gd_mine',?, 'private',0,'t')", (uid1,))
c.execute("INSERT INTO gardens(id,owner_id,visibility,harvest_total,created_at) VALUES('gd_theirs',?, 'members',0,'t')", (uid2,))
c.commit(); c.close()
u1 = {'Authorization': 'Bearer h1'}
u2 = {'Authorization': 'Bearer h2'}
agent = {'Authorization': 'Bearer ai325_agent_perf_test_token'}

def mk_practice(h, title='实践', status='completed', source_url=None, source_title=None, cid=None):
    body = {'title': title, 'outcome': '目标'}
    if source_url is not None: body['source_url'] = source_url
    if source_title is not None: body['source_title'] = source_title
    if cid: body['client_id'] = cid
    p = client.post('/api/practice/mine', headers=h, json=body)
    assert p.status_code == 200, p.text
    pid = p.json()['id']
    if status != 'active':
        q = client.get(f'/api/practice/mine/{pid}', headers=h).json()
        r = client.patch(f'/api/practice/mine/{pid}', headers=h,
            json={'revision': q['revision'], 'status': status})
        assert r.status_code == 200, r.text
    return pid
"""


class GardenMarksTest(unittest.TestCase):
    def _boot(self, td: str):
        root = Path(td)
        # 静态目录放一个真实精读页供 source_url 存在性检查
        page = root / "static" / "readings" / "kb-03"
        page.mkdir(parents=True)
        (page / "index.html").write_text("<html/>", encoding="utf-8")
        env = _env(root)
        r = _run(env, _seed_script(agent_count=1, audit_per_agent=0))
        assert r.returncode == 0, r.stderr
        return env

    def test_full_contract(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""

                # ── 鉴权矩阵：匿名401 / Agent403 / 全响应 no-store ──
                anon = client.get('/api/garden/mine/marks')
                assert anon.status_code == 401, anon.status_code
                ag = client.get('/api/garden/mine/marks', headers=agent)
                assert ag.status_code == 403, ag.status_code
                assert ag.headers['cache-control'] == 'no-store', ag.headers

                # ── 空家园 GET 仍可（garden_id=null + max_marks）──
                # 先删掉本人的花园看空态，再加回
                c2 = main.db()
                c2.execute("DELETE FROM gardens WHERE id='gd_mine'"); c2.commit(); c2.close()
                empty = client.get('/api/garden/mine/marks', headers=u1).json()
                assert empty['garden_id'] is None and empty['items'] == [] and empty['max_marks'] == 4, empty
                c2 = main.db()
                c2.execute("INSERT INTO gardens(id,owner_id,visibility,harvest_total,created_at) VALUES('gd_mine',?,'private',0,'t')", (uid1,))
                c2.commit(); c2.close()

                # ── 未开家园 POST → 409（先借 u1 有 gd_mine；造一个无家员验证）──
                c2 = main.db()
                uid3 = c2.execute("INSERT INTO users(username,password_hash,role,display_name,created_at) VALUES('m3','h','member','成员丙','x')").lastrowid
                c2.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('h3',?,'2099-01-01T00:00:00+08:00')", (uid3,))
                c2.commit(); c2.close()
                u3 = {'Authorization': 'Bearer h3'}
                p3 = mk_practice(u3)
                no_g = client.post('/api/garden/mine/marks', headers=u3,
                    json={'practice_id': p3, 'client_id': 'c-ng'})
                assert no_g.status_code == 409, no_g.status_code

                # ── 挂牌：默认 private，快照标题/来源 ──
                p1 = mk_practice(u1, title='读透拆解法', source_url='/readings/kb-03/', source_title='kb-03')
                res = client.post('/api/garden/mine/marks', headers=u1,
                    json={'practice_id': p1, 'client_id': 'c-1'})
                assert res.status_code == 200, res.text
                body = res.json()
                assert body['replayed'] is False and body['max_marks'] == 4
                m = body['items'][0]
                assert m['practice_id'] == p1 and m['shown'] is False and m['revision'] == 1
                assert m['title'] == '读透拆解法' and m['source_title'] == 'kb-03'
                assert m['source_url'] == '/readings/kb-03/'  # 存在的站内页保留
                mid = m['id']

                # 幂等重放：同 client_id 同负载 → replayed=true 且只有一块
                again = client.post('/api/garden/mine/marks', headers=u1,
                    json={'practice_id': p1, 'client_id': 'c-1'}).json()
                assert again['replayed'] is True and len(again['items']) == 1, again
                # 同实践换新 client_id → 仍一块（owner+practice 唯一），且新 key 已登记
                dup = client.post('/api/garden/mine/marks', headers=u1,
                    json={'practice_id': p1, 'client_id': 'c-1b'}).json()
                assert len(dup['items']) == 1, dup
                # 该 key 换实践重放 → 409（证明 dedupe 命中已存回执）
                key_conflict = client.post('/api/garden/mine/marks', headers=u1,
                    json={'practice_id': p3, 'client_id': 'c-1b'})
                assert key_conflict.status_code == 409, key_conflict.status_code
                # 同 client_id 换负载 → 409
                conflict = client.post('/api/garden/mine/marks', headers=u1,
                    json={'practice_id': p3, 'client_id': 'c-1'})
                assert conflict.status_code == 409, conflict.status_code
                # 他人实践 → 404
                other = client.post('/api/garden/mine/marks', headers=u2,
                    json={'practice_id': p1, 'client_id': 'c-x'})
                assert other.status_code == 404, other.status_code
                # 非 completed → 409
                pa = mk_practice(u1, status='active')
                nc = client.post('/api/garden/mine/marks', headers=u1,
                    json={'practice_id': pa, 'client_id': 'c-nc'})
                assert nc.status_code == 409, nc.status_code

                # ── 访客：私园404；members 园只见 shown+completed 严格字段 ──
                priv = client.get('/api/garden/visit/gd_mine/marks', headers=u2)
                assert priv.status_code == 404, priv.status_code
                assert priv.headers['cache-control'] == 'no-store'
                vis = client.get('/api/garden/visit/gd_theirs/marks', headers=u1)
                assert vis.status_code == 200 and vis.json()['items'] == []

                # ── PATCH 显式公开：revision 校验 + shown ──
                bad_rev = client.patch(f'/api/garden/mine/marks/{mid}', headers=u1,
                    json={'shown': True, 'revision': 99, 'client_id': 'c-p0'})
                assert bad_rev.status_code == 409, bad_rev.status_code
                show = client.patch(f'/api/garden/mine/marks/{mid}', headers=u1,
                    json={'shown': True, 'revision': 1, 'client_id': 'c-p1'})
                assert show.status_code == 200, show.text
                sm = [i for i in show.json()['items'] if i['id'] == mid][0]
                assert sm['shown'] is True and sm['revision'] == 2, sm
                # 私园仍 404——公开木牌不等于开放家园
                assert client.get('/api/garden/visit/gd_mine/marks', headers=u2).status_code == 404
                # 开放家园后访客见到严格字段
                c2 = main.db()
                c2.execute("UPDATE gardens SET visibility='members' WHERE id='gd_mine'")
                c2.commit(); c2.close()
                vis2 = client.get('/api/garden/visit/gd_mine/marks', headers=u2).json()
                assert len(vis2['items']) == 1
                vm = vis2['items'][0]
                assert set(vm.keys()) == {'id','title','source_title','source_url','created_at'}, vm

                # ── 实践离开 completed → 同事务藏牌：两个 PATCH 中间不读 marks，shown 不复活 ──
                q = client.get(f'/api/practice/mine/{p1}', headers=u1).json()
                client.patch(f'/api/practice/mine/{p1}', headers=u1,
                    json={'revision': q['revision'], 'status': 'archived'})
                # shown=true 但实践已非 completed → 409 诚实重取（不许返回成功 shown=false）
                lie = client.patch(f'/api/garden/mine/marks/{mid}', headers=u1,
                    json={'shown': True, 'revision': 3, 'client_id': 'c-p2'})
                assert lie.status_code == 409, lie.status_code
                q = client.get(f'/api/practice/mine/{p1}', headers=u1).json()
                client.patch(f'/api/practice/mine/{p1}', headers=u1,
                    json={'revision': q['revision'], 'status': 'completed'})
                # 两次 PATCH 之间无任何 marks 请求：源事务已藏，shown 不会复活
                mine = client.get('/api/garden/mine/marks', headers=u1).json()
                mm = [i for i in mine['items'] if i['id'] == mid][0]
                assert mm['shown'] is False and mm['revision'] == 3, mm
                vis3 = client.get('/api/garden/visit/gd_mine/marks', headers=u2).json()
                assert vis3['items'] == [], vis3

                # ── 上限 4 块 ──
                for i in range(3):
                    pp = mk_practice(u1)
                    rr = client.post('/api/garden/mine/marks', headers=u1,
                        json={'practice_id': pp, 'client_id': f'c-cap{i}'})
                    assert rr.status_code == 200, rr.text
                p5 = mk_practice(u1)
                over = client.post('/api/garden/mine/marks', headers=u1,
                    json={'practice_id': p5, 'client_id': 'c-cap4'})
                assert over.status_code == 409 and '撤下' in over.json()['detail'], over.text

                # ── DELETE 只撤木牌不动实践；重放不复活 ──
                d = client.request('DELETE', f'/api/garden/mine/marks/{mid}',
                    headers=u1, json={'client_id': 'c-d1'})
                assert d.status_code == 200 and mid not in [i['id'] for i in d.json()['items']], d.text
                assert client.get(f'/api/practice/mine/{p1}', headers=u1).status_code == 200
                d2 = client.request('DELETE', f'/api/garden/mine/marks/{mid}',
                    headers=u1, json={'client_id': 'c-d1'})
                assert d2.json()['replayed'] is True  # 重放返回现状不报错不复活
                re_post = client.post('/api/garden/mine/marks', headers=u1,
                    json={'practice_id': p1, 'client_id': 'c-1'}).json()
                assert re_post['replayed'] is True
                assert mid not in [i['id'] for i in re_post['items']]  # 撤掉的不复活

                # ── 来源规范化：站外/不存在 → null；ai325 绝对地址归一保留 ──
                # 用 u2 的 gd_theirs（独立 owner 计数，避开 u1 的 4 块上限）
                pe = mk_practice(u2, source_url='https://evil.example/x', source_title='站外')
                re_e = client.post('/api/garden/mine/marks', headers=u2,
                    json={'practice_id': pe, 'client_id': 'c-se'}).json()
                me_ = [i for i in re_e['items'] if i['practice_id'] == pe]
                assert me_ and me_[0]['source_url'] is None and me_[0]['source_title'] == '站外', me_
                pabs = mk_practice(u2, source_url='https://www.ai325.com/readings/kb-03/', source_title='绝对')
                re_a = client.post('/api/garden/mine/marks', headers=u2,
                    json={'practice_id': pabs, 'client_id': 'c-sa'}).json()
                ma_ = [i for i in re_a['items'] if i['practice_id'] == pabs]
                assert ma_ and ma_[0]['source_url'] == '/readings/kb-03/', ma_
                pm = mk_practice(u2, source_url='/readings/missing-99/', source_title='不存在')
                re_m = client.post('/api/garden/mine/marks', headers=u2,
                    json={'practice_id': pm, 'client_id': 'c-sm'}).json()
                mm_ = [i for i in re_m['items'] if i['practice_id'] == pm]
                assert mm_ and mm_[0]['source_url'] is None, mm_
            """))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
