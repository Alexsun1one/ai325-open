"""CONTENT-ENGAGEMENT R1：真实 main 路由回归。

覆盖冻结契约：白名单 404/目录 503、views 同日去重/跨日新增/并发幂等、
visitor 只存 hash 不落原值、likes 真人归属+显式赋值幂等+取消删行、
匿名公共读写/Agent403/no-store、评论真值筛选（accepted 且未删，回复计入）、
PATCH StrictBool/null/extra。隔离临时数据目录，无生产读写。
"""
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from app.test_product_performance import _env, _run, _seed_script

STATIC_FILES = {
    "book-notes/index.json": {"items": [{"id": "bn-aaaa00000001", "title": "书甲", "category": "c"}]},
    "readings/practice-index.json": {"entries": {"deep-work": {"source_title": "深度工作"}}},
    "discuss/directory.json": {"items": [
        {"id": "people-need-ai", "kind": "journey", "title": "人民需要AI", "anchor": "article:journey:people-need-ai"},
        {"id": "kb-01", "kind": "knowledge", "title": "知识库", "anchor": "article:knowledge:kb-01"},
        {"id": "deep-work", "kind": "reading", "title": "深度工作", "anchor": "article:reading:deep-work"},
    ]},
}

BOOT = """
import main
from starlette.testclient import TestClient
client = TestClient(main.app)
c = main.db()
uid1 = c.execute("INSERT INTO users(username,password_hash,role,display_name,created_at) "
    "VALUES('member1','h','member','成员甲','2026-01-01T00:00:00+08:00')").lastrowid
uid2 = c.execute("INSERT INTO users(username,password_hash,role,display_name,created_at) "
    "VALUES('member2','h','member','成员乙','2026-01-01T00:00:00+08:00')").lastrowid
c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('h1',?,'2099-01-01T00:00:00+08:00')", (uid1,))
c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('h2',?,'2099-01-01T00:00:00+08:00')", (uid2,))
c.commit(); c.close()
u1 = {'Authorization': 'Bearer h1'}
u2 = {'Authorization': 'Bearer h2'}
agent = {'Authorization': 'Bearer ai325_agent_perf_test_token'}
VID = 'f47ac10b-58cc-4372-a567-0e02b2c3d479'
VID2 = 'a8098c1a-f86e-11da-bd1a-0d15ecd40000'
"""


class ContentEngagementTest(unittest.TestCase):
    def _boot(self, td: str, *, with_index: bool = True):
        root = Path(td)
        (root / "static").mkdir(parents=True, exist_ok=True)
        if with_index:
            for rel, data in STATIC_FILES.items():
                p = root / "static" / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(data), encoding="utf-8")
        env = _env(root)
        r = _run(env, _seed_script(agent_count=1, audit_per_agent=0))
        assert r.returncode == 0, r.stderr
        return env

    def test_index_unavailable_503(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td, with_index=False)
            r = _run(env, BOOT + """
r = client.get('/api/content-engagement/reading/deep-work')
assert r.status_code == 503 and r.headers['cache-control'] == 'no-store', (r.status_code, r.headers)
""")
            assert r.returncode == 0, r.stderr

    def test_index_bad_shape_503(self):
        """缺键/坏容器/坏条目 → 503 而非 404/500。"""
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""

                import json as _j
                from pathlib import Path as _P
                bn = _P(main.STATIC) / 'book-notes' / 'index.json'
                pi = _P(main.STATIC) / 'readings' / 'practice-index.json'
                dd = _P(main.STATIC) / 'discuss' / 'directory.json'
                # 缺 items 键 / items 非 list / 条目非 dict
                for bad in ('{}', '{"items":42}', '{"items":["x"]}'):
                    bn.write_text(bad, encoding='utf-8')
                    r_ = client.get('/api/content-engagement/book_note/bn-aaaa00000001')
                    assert r_.status_code == 503, (bad, r_.status_code)
                # 缺 entries / entries 非 dict / entry 值非 dict
                for bad in ('{}', '{"entries":[]}', '{"entries":{"deep-work":"x"}}'):
                    pi.write_text(bad, encoding='utf-8')
                    r_ = client.get('/api/content-engagement/reading/deep-work')
                    assert r_.status_code == 503, (bad, r_.status_code)
                # directory：缺 items / 非 list / 缺 kind
                for bad in ('{}', '{"items":{}}', '{"items":[{"id":"kb-01"}]}'):
                    dd.write_text(bad, encoding='utf-8')
                    r_ = client.get('/api/content-engagement/knowledge/kb-01')
                    assert r_.status_code == 503, (bad, r_.status_code)
            """))
            assert r.returncode == 0, r.stderr

    def test_public_views_and_likes(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""

                K, R = 'reading', 'deep-work'
                # ── 匿名公共 GET：初始全0、policy/since 字段齐 ──
                g = client.get(f'/api/content-engagement/{K}/{R}')
                assert g.status_code == 200 and g.headers['cache-control'] == 'no-store'
                s = g.json()
                assert s['views'] == 0 and s['likes'] == 0 and s['comments'] == 0, s
                assert s['view_policy'] == {'visible_ms': 3000, 'dedupe': 'browser_day',
                                            'timezone': 'Asia/Shanghai'}, s
                assert s['kind'] == K and s['resource_id'] == R and s['since'], s
                # 不泄私密字段
                assert 'readers' not in s and 'liked_by' not in s and 'saved' not in s

                # ── 未知 kind/id/非法 → 404；Agent token 也能读公共统计 ──
                assert client.get('/api/content-engagement/video/x').status_code == 404
                assert client.get('/api/content-engagement/reading/nope').status_code == 404
                assert client.get('/api/content-engagement/book_note/bn-aaaa00000001').status_code == 200
                assert client.get(f'/api/content-engagement/{K}/{R}', headers=agent).status_code == 200

                # ── 匿名 POST view：同日同人幂等（含大小写 canonical）──
                v1 = client.post(f'/api/content-engagement/{K}/{R}/view', json={'visitor_id': VID})
                assert v1.status_code == 200 and v1.json()['views'] == 1, v1.text
                v2 = client.post(f'/api/content-engagement/{K}/{R}/view', json={'visitor_id': VID})
                assert v2.json()['views'] == 1, v2.text  # 重复不增
                vu = client.post(f'/api/content-engagement/{K}/{R}/view', json={'visitor_id': VID.upper()})
                assert vu.json()['views'] == 1, vu.text  # 大小写同 UUID 算同浏览器
                # 另一浏览器 +1
                v3 = client.post(f'/api/content-engagement/{K}/{R}/view', json={'visitor_id': VID2})
                assert v3.json()['views'] == 2, v3.text
                # 另一资源独立计数
                v4 = client.post('/api/content-engagement/knowledge/kb-01/view', json={'visitor_id': VID})
                assert v4.json()['views'] == 1 and v4.json()['resource_id'] == 'kb-01'
                # 非法 visitor_id / 未知字段 / null
                assert client.post(f'/api/content-engagement/{K}/{R}/view', json={'visitor_id': 'uid-42'}).status_code == 422
                assert client.post(f'/api/content-engagement/{K}/{R}/view', json={'visitor_id': VID, 'x': 1}).status_code == 422
                assert client.post(f'/api/content-engagement/{K}/{R}/view', json={'visitor_id': None}).status_code == 422
                # ── 跨日新增：伪造昨日行再 POST → views=3 ──
                c2 = main.db()
                import hashlib as _h0
                c2.execute("INSERT INTO engagement_views(kind,resource_id,day,visitor_hash,created_at) "
                           "VALUES(?,?, '2026-09-23', ?, 't')", (K, R, _h0.sha256(b'other-browser').hexdigest()))
                c2.commit(); c2.close()
                v5 = client.post(f'/api/content-engagement/{K}/{R}/view', json={'visitor_id': VID})
                assert v5.json()['views'] == 3, v5.json()  # 昨日行+今日行(已记)+昨日伪造行

                # ── 库内不存原始 visitor_id / IP / UA；hash 带域分隔 ──
                c2 = main.db()
                rows = c2.execute("SELECT visitor_hash,kind,resource_id FROM engagement_views").fetchall()
                c2.close()
                assert all(len(r[0]) == 64 and r[0] != VID for r in rows), rows
                import hashlib as _h
                import datetime as _dt
                day = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=8))).strftime('%Y-%m-%d')
                h_reading = _h.sha256(f'{VID.lower()}|reading|deep-work|{day}'.encode()).hexdigest()
                h_kb = _h.sha256(f'{VID.lower()}|knowledge|kb-01|{day}'.encode()).hexdigest()
                assert h_reading in [r[0] for r in rows] and h_kb in [r[0] for r in rows]
                assert h_reading != h_kb  # 跨资源 hash 不同，不可拼足迹
                assert _h.sha256(VID.encode()).hexdigest() not in [r[0] for r in rows]  # 非裸 hash

                # ── since 稳定：二次 GET 不变，且来自 meta 登记 ──
                s_a = client.get(f'/api/content-engagement/{K}/{R}').json()['since']
                s_b = client.get('/api/content-engagement/knowledge/kb-01').json()['since']
                assert s_a == s_b, (s_a, s_b)  # 全站同一定锚

                # ── me 端点鉴权矩阵 ──
                assert client.get(f'/api/me/content-engagement/{K}/{R}').status_code == 401
                assert client.patch(f'/api/me/content-engagement/{K}/{R}', json={'liked': True}).status_code == 401
                assert client.get(f'/api/me/content-engagement/{K}/{R}', headers=agent).status_code == 403

                # ── liked GET/PATCH 幂等/取消删行/归属隔离 ──
                me1 = client.get(f'/api/me/content-engagement/{K}/{R}', headers=u1)
                assert me1.json() == {'liked': False} and me1.headers['cache-control'] == 'no-store'
                p1 = client.patch(f'/api/me/content-engagement/{K}/{R}', headers=u1, json={'liked': True})
                assert p1.json()['liked'] is True and p1.json()['stats']['likes'] == 1, p1.text
                p1b = client.patch(f'/api/me/content-engagement/{K}/{R}', headers=u1, json={'liked': True})
                assert p1b.json()['stats']['likes'] == 1, p1b.text  # 重放不重复
                # 另一账号 liked=False；独立点赞 → likes=2
                assert client.get(f'/api/me/content-engagement/{K}/{R}', headers=u2).json() == {'liked': False}
                client.patch(f'/api/me/content-engagement/{K}/{R}', headers=u2, json={'liked': True})
                assert client.get(f'/api/content-engagement/{K}/{R}').json()['likes'] == 2
                # 取消：删本人行不影响他人
                p2 = client.patch(f'/api/me/content-engagement/{K}/{R}', headers=u1, json={'liked': False})
                assert p2.json()['liked'] is False and p2.json()['stats']['likes'] == 1, p2.text
                p2b = client.patch(f'/api/me/content-engagement/{K}/{R}', headers=u1, json={'liked': False})
                assert p2b.json()['stats']['likes'] == 1  # 再取消幂等
                # ── PATCH 校验：null/extra/字符串 ──
                assert client.patch(f'/api/me/content-engagement/{K}/{R}', headers=u1, json={'liked': None}).status_code == 422
                assert client.patch(f'/api/me/content-engagement/{K}/{R}', headers=u1, json={'liked': 'yes'}).status_code == 422
                assert client.patch(f'/api/me/content-engagement/{K}/{R}', headers=u1, json={'liked': True, 'x': 1}).status_code == 422
                assert client.patch(f'/api/me/content-engagement/{K}/{R}', headers=u1, json={}).status_code == 422
                # 未知资源 PATCH/GET-me → 404（先白名单再鉴权结果一致）
                assert client.patch('/api/me/content-engagement/reading/nope', headers=u1, json={'liked': True}).status_code == 404

                # ── 真实并发：同 UUID 两路并行 POST → 仍计 1 ──
                from concurrent.futures import ThreadPoolExecutor
                VID3 = 'c9bf9e57-1685-4c89-bafb-ff5af830be8a'
                def _post():
                    return client.post(f'/api/content-engagement/{K}/{R}/view',
                                       json={'visitor_id': VID3}).json()['views']
                base = client.get(f'/api/content-engagement/{K}/{R}').json()['views']
                with ThreadPoolExecutor(2) as ex:
                    rs = list(ex.map(lambda _: _post(), range(2)))
                after = client.get(f'/api/content-engagement/{K}/{R}').json()['views']
                assert after == base + 1 and set(rs) == {after}, (base, rs, after)

                # ── 评论真值：accepted未删计入（含回复），deleted/未审排除 ──
                c2 = main.db()
                c2.execute("INSERT INTO comments(anchor,date,user_id,username,text,created_at,deleted,status) "
                           "VALUES('article:reading:deep-work','d',?,'m','根评论','t1',0,'accepted')", (uid1,))
                c2.execute("INSERT INTO comments(anchor,date,user_id,username,text,created_at,deleted,status,reply_to) "
                           "VALUES('article:reading:deep-work','d',?,'m','回复','t2',0,'accepted',1)", (uid2,))
                c2.execute("INSERT INTO comments(anchor,date,user_id,username,text,created_at,deleted,status) "
                           "VALUES('article:reading:deep-work','d',?,'m','已删','t3',1,'accepted')", (uid1,))
                c2.execute("INSERT INTO comments(anchor,date,user_id,username,text,created_at,deleted,status) "
                           "VALUES('article:reading:deep-work','d',?,'m','待审','t4',0,'pending')", (uid1,))
                c2.commit(); c2.close()
                g2 = client.get(f'/api/content-engagement/{K}/{R}').json()
                assert g2['comments'] == 2, g2  # 根+回复；已删/待审不计
                # book_note anchor article:book_note:<id>（pS 将以该 scheme 挂 ArticleComments）
                c2 = main.db()
                c2.execute("INSERT INTO comments(anchor,date,user_id,username,text,created_at,deleted,status) "
                           "VALUES('article:book_note:bn-aaaa00000001','d',?,'m','书摘评论','t5',0,'accepted')", (uid1,))
                c2.execute("INSERT INTO comments(anchor,date,user_id,username,text,created_at,deleted,status) "
                           "VALUES('article:book_note:bn-aaaa00000001','d',?,'m','书摘已删','t6',1,'accepted')", (uid1,))
                c2.commit(); c2.close()
                assert client.get('/api/content-engagement/book_note/bn-aaaa00000001').json()['comments'] == 1
            """))
            assert r.returncode == 0, r.stderr


if __name__ == "__main__":
    unittest.main()
