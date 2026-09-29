"""READING-GROWTH R1：真实 main 路由回归。

覆盖冻结契约：鉴权矩阵、未记录默认值不落库、open 只记时间不覆状态、
PATCH 显式赋值幂等/未变值不改时间、白名单 404/目录 503、列表 filter/summary/分页、
DELETE 幂等不动其他数据、两账号隔离、growth-activity 真人过滤/类型/摘要/分页/url 白名单、
下架快照 available=false。隔离临时数据目录，无生产读写。
"""
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from app.test_product_performance import _env, _run, _seed_script

BN_INDEX = {
    "generated": "t", "total": 2, "categories": ["决策商业"],
    "items": [
        {"id": "bn-aaaa00000001", "title": "测试书甲", "category": "决策商业"},
        {"id": "bn-bbbb00000002", "title": "测试书乙", "category": "文学人文"},
    ],
}
PI_INDEX = {
    "version": "t",
    "entries": {
        "thinking-fast-slow": {"source_title": "思考，快与慢", "source_url": "/readings/thinking-fast-slow/"},
        "deep-work": {"source_title": "深度工作", "source_url": "/readings/deep-work/"},
    },
}

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
c.commit(); c.close()
u1 = {'Authorization': 'Bearer h1'}
u2 = {'Authorization': 'Bearer h2'}
agent = {'Authorization': 'Bearer ai325_agent_perf_test_token'}
"""


class ReadingGrowthTest(unittest.TestCase):
    def _boot(self, td: str, *, with_index: bool = True):
        root = Path(td)
        (root / "static").mkdir(parents=True, exist_ok=True)
        if with_index:
            bn = root / "static" / "book-notes"
            bn.mkdir(parents=True)
            (bn / "index.json").write_text(json.dumps(BN_INDEX), encoding="utf-8")
            pi = root / "static" / "readings"
            pi.mkdir(parents=True)
            (pi / "practice-index.json").write_text(json.dumps(PI_INDEX), encoding="utf-8")
        env = _env(root)
        r = _run(env, _seed_script(agent_count=1, audit_per_agent=0))
        assert r.returncode == 0, r.stderr
        return env

    def test_index_unavailable_503(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td, with_index=False)
            r = _run(env, BOOT + textwrap.dedent("""
                r = client.get('/api/me/reading-progress/book_note/bn-aaaa00000001', headers=u1)
                assert r.status_code == 503, (r.status_code, r.text)
                assert r.headers['cache-control'] == 'no-store'
            """))
            assert r.returncode == 0, r.stderr

    def test_progress_contract(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""

                # ── 鉴权矩阵 ──
                assert client.get('/api/me/reading-progress', headers={}).status_code == 401
                ag = client.get('/api/me/reading-progress', headers=agent)
                assert ag.status_code == 403 and ag.headers['cache-control'] == 'no-store'

                K, R = 'book_note', 'bn-aaaa00000001'
                # ── 未记录：默认 false/null 不落库 ──
                it = client.get(f'/api/me/reading-progress/{K}/{R}', headers=u1).json()['item']
                assert it == {'kind': K, 'resource_id': R, 'title': '测试书甲',
                              'url': '/readings/books/bn-aaaa00000001/', 'category': '决策商业',
                              'available': True, 'last_opened_at': None, 'saved': False,
                              'saved_at': None, 'finished': False, 'finished_at': None,
                              'updated_at': None}, it
                c2 = main.db()
                assert c2.execute("SELECT COUNT(*) FROM reading_records").fetchone()[0] == 0
                c2.close()

                # ── 未知资源/类型/非法 id → 404 ──
                assert client.get('/api/me/reading-progress/book_note/bn-nope', headers=u1).status_code == 404
                assert client.get('/api/me/reading-progress/video/x', headers=u1).status_code == 404
                assert client.post('/api/me/reading-progress/book_note/..%2Fetc/open', headers=u1).status_code in (404, 405, 422)
                assert client.post('/api/me/reading-progress/book_note/x%20y/open', headers=u1).status_code == 404

                # ── open：只记时间 ──
                op = client.post(f'/api/me/reading-progress/{K}/{R}/open', headers=u1).json()['item']
                assert op['last_opened_at'] and op['saved'] is False and op['finished'] is False, op
                t1 = op['last_opened_at']

                # ── PATCH：saved=true 落时间；同值重试不改时间 ──
                p1 = client.patch(f'/api/me/reading-progress/{K}/{R}', headers=u1,
                    json={'saved': True}).json()['item']
                assert p1['saved'] is True and p1['saved_at'] and p1['finished'] is False, p1
                p1b = client.patch(f'/api/me/reading-progress/{K}/{R}', headers=u1,
                    json={'saved': True}).json()['item']
                assert p1b['saved_at'] == p1['saved_at'] and p1b['updated_at'] == p1['updated_at'], (p1b, p1)

                # ── finished=true；open 不覆状态 ──
                p2 = client.patch(f'/api/me/reading-progress/{K}/{R}', headers=u1,
                    json={'finished': True}).json()['item']
                assert p2['finished'] is True and p2['finished_at'], p2
                op2 = client.post(f'/api/me/reading-progress/{K}/{R}/open', headers=u1).json()['item']
                assert op2['saved'] is True and op2['finished'] is True, op2
                assert op2['last_opened_at'] >= t1, op2

                # ── PATCH 校验：空对象/未知字段/布尔外 ──
                assert client.patch(f'/api/me/reading-progress/{K}/{R}', headers=u1, json={}).status_code == 422
                assert client.patch(f'/api/me/reading-progress/{K}/{R}', headers=u1,
                    json={'saved': True, 'note': 'x'}).status_code == 422
                assert client.patch(f'/api/me/reading-progress/{K}/{R}', headers=u1,
                    json={'saved': 'banana'}).status_code == 422

                # ── 取消收藏：saved=false 清 saved_at ──
                p3 = client.patch(f'/api/me/reading-progress/{K}/{R}', headers=u1,
                    json={'saved': False}).json()['item']
                assert p3['saved'] is False and p3['saved_at'] is None and p3['finished'] is True, p3

                # ── 列表：filter/summary/分页 ──
                for rid, fin in (('bn-bbbb00000002', False),):
                    client.post(f'/api/me/reading-progress/book_note/{rid}/open', headers=u1)
                client.post('/api/me/reading-progress/reading/deep-work/open', headers=u1)
                client.patch('/api/me/reading-progress/reading/deep-work', headers=u1, json={'saved': True})
                all_ = client.get('/api/me/reading-progress', headers=u1).json()
                assert all_['total'] == 3 and all_['has_more'] is False, all_
                assert all_['summary'] == {'opened': 3, 'saved': 1, 'finished': 1}, all_['summary']
                saved_ = client.get('/api/me/reading-progress?filter=saved', headers=u1).json()
                assert saved_['total'] == 1 and saved_['items'][0]['resource_id'] == 'deep-work', saved_
                fin_ = client.get('/api/me/reading-progress?filter=finished', headers=u1).json()
                assert fin_['total'] == 1 and fin_['items'][0]['resource_id'] == R, fin_
                p_ = client.get('/api/me/reading-progress?limit=2&offset=2', headers=u1).json()
                assert len(p_['items']) == 1 and p_['has_more'] is False, p_
                assert client.get('/api/me/reading-progress?filter=bad', headers=u1).status_code == 422
                assert client.get('/api/me/reading-progress?limit=0', headers=u1).status_code == 422

                # ── 两账号隔离 ──
                assert client.get('/api/me/reading-progress', headers=u2).json()['total'] == 0
                other = client.get(f'/api/me/reading-progress/{K}/{R}', headers=u2).json()['item']
                assert other['saved'] is False and other['last_opened_at'] is None, other

                # ── DELETE 幂等，不动实践/评论 ──
                c2 = main.db()
                c2.execute("INSERT INTO practice_items(id,owner_id,title,status,created_at,updated_at) "
                           "VALUES('p1',?,'实践','active','t','t')", (uid1,))
                c2.commit(); c2.close()
                d1 = client.delete(f'/api/me/reading-progress/{K}/{R}', headers=u1)
                d2 = client.delete(f'/api/me/reading-progress/{K}/{R}', headers=u1)
                assert d1.status_code == d2.status_code == 200 and d1.json() == {'ok': True}
                c2 = main.db()
                assert c2.execute("SELECT COUNT(*) FROM practice_items WHERE owner_id=?", (uid1,)).fetchone()[0] == 1
                assert c2.execute("SELECT COUNT(*) FROM reading_records WHERE user_id=? AND kind=? AND resource_id=?",
                                  (uid1, K, R)).fetchone()[0] == 0
                c2.close()
            """))
            assert r.returncode == 0, r.stderr

    def test_unlisted_snapshot_and_activity(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""

                # ── 建记录后从索引下架 → 快照保留 available=false/url=null ──
                K, R = 'book_note', 'bn-aaaa00000001'
                client.post(f'/api/me/reading-progress/{K}/{R}/open', headers=u1)
                client.patch(f'/api/me/reading-progress/{K}/{R}', headers=u1, json={'saved': True})
                import json as _j
                from pathlib import Path as _P
                idx = _P(main.STATIC) / 'book-notes' / 'index.json'
                idx.write_text(_j.dumps({'generated': 't2', 'total': 1, 'categories': [],
                    'items': [{'id': 'bn-bbbb00000002', 'title': '测试书乙', 'category': '文学人文'}]}),
                    encoding='utf-8')
                it = client.get(f'/api/me/reading-progress/{K}/{R}', headers=u1).json()['item']
                assert it['available'] is False and it['url'] is None and it['saved'] is True, it

                # ── growth-activity：真人过滤/类型/摘要/分页/url 白名单 ──
                c2 = main.db()
                c2.execute("INSERT INTO comments(anchor,date,user_id,username,text,created_at,deleted,status) "
                           "VALUES('article:reading:thinking-fast-slow','d',?, '成员甲','真人评论正文','2026-09-01T10:00:00+08:00',0,'accepted')", (uid1,))
                c2.execute("INSERT INTO comments(anchor,date,user_id,username,text,created_at,deleted,status,via) "
                           "VALUES('article:reading:deep-work','d',?, '成员甲','Agent代发','2026-09-01T11:00:00+08:00',0,'accepted','agent')", (uid1,))
                c2.execute("INSERT INTO comments(anchor,date,user_id,username,text,created_at,deleted,status) "
                           "VALUES('x','d',?, '成员甲','已删','2026-09-01T12:00:00+08:00',1,'accepted')", (uid1,))
                c2.execute("INSERT INTO question_threads(user_id,agent_token_id,title,body,target,status,created_at,updated_at,author_kind,agent_name,agent_display_name) "
                           "VALUES(?,0,'真人问题','正文','', 'open','2026-09-02T09:00:00+08:00','2026-09-02T09:00:00+08:00','human','','')", (uid1,))
                c2.execute("INSERT INTO question_threads(user_id,agent_token_id,title,body,target,status,created_at,updated_at,author_kind,agent_name,agent_display_name) "
                           "VALUES(?,1,'Agent问题','正文','', 'open','2026-09-02T10:00:00+08:00','2026-09-02T10:00:00+08:00','agent','ag','A')", (uid1,))
                tid = c2.execute("SELECT id FROM question_threads WHERE author_kind='human'").fetchone()[0]
                c2.execute("INSERT INTO question_replies(thread_id,user_id,agent_token_id,author_kind,author_name,text,created_at) "
                           "VALUES(?,?,NULL,'human','成员甲','真人回复','2026-09-02T11:00:00+08:00')", (tid, uid1))
                c2.execute("INSERT INTO question_replies(thread_id,user_id,agent_token_id,author_kind,author_name,text,created_at) "
                           "VALUES(?,?,1,'agent','A','Agent回复','2026-09-02T12:00:00+08:00')", (tid, uid1))
                c2.execute("INSERT INTO favorites(user_id,anchor,text,section,created_at) "
                           "VALUES(?,'article:knowledge:kb-01','收藏的段落文字','章节名','2026-09-03T08:00:00+08:00')", (uid1,))
                c2.execute("INSERT INTO practice_items(id,owner_id,title,outcome,status,created_at,updated_at) "
                           "VALUES('p1',?,'我的实践','成果','completed','2026-09-04T08:00:00+08:00','2026-09-04T08:00:00+08:00')", (uid1,))
                c2.execute("INSERT INTO practice_submissions(id,practice_id,challenge_id,owner_id,title,body,practice_revision,created_at) "
                           "VALUES('s1','p1','ch1',?,'提交题','正文',1,'2026-09-04T09:00:00+08:00')", (uid1,))
                c2.execute("INSERT INTO practice_replies(id,submission_id,owner_id,text,client_id,created_at) "
                           "VALUES('r1','s1',?,'实践回复正文','k1','2026-09-04T10:00:00+08:00')", (uid1,))
                c2.commit(); c2.close()

                g = client.get('/api/me/growth-activity', headers=u1).json()
                types = {i['type'] for i in g['items']}
                assert types == {'comment','question','reply','practice','practice_reply','paragraph_saved'}, types
                texts = [i['excerpt'] for i in g['items']]
                assert 'Agent代发' not in texts and '已删' not in texts and 'Agent回复' not in texts
                assert g['summary'] == {'contributions': 4, 'practices_completed': 1, 'paragraphs_saved': 1}, g['summary']
                assert g['total'] == 6 and g['has_more'] is False, g['total']
                cm = [i for i in g['items'] if i['type'] == 'comment'][0]
                assert cm['url'] == '/readings/thinking-fast-slow/', cm
                assert cm['title'] == '思考，快与慢', cm  # 解析资源标题，不显示原始 anchor
                q = [i for i in g['items'] if i['type'] == 'question'][0]
                assert q['url'] == f'/community/?thread={tid}', q
                rp = [i for i in g['items'] if i['type'] == 'reply'][0]
                assert rp['url'] == f'/community/?thread={tid}' and rp['title'] == '真人问题', rp
                pr = [i for i in g['items'] if i['type'] == 'practice'][0]
                assert pr['url'] == '/me/?view=mine&p=p1', pr
                prp = [i for i in g['items'] if i['type'] == 'practice_reply'][0]
                assert prp['url'] == '/me/?view=challenges&s=s1' and prp['title'] == '提交题', prp
                fav = [i for i in g['items'] if i['type'] == 'paragraph_saved'][0]
                assert fav['url'] == '/learn/entries/kb-01/', fav
                assert all(len(i['excerpt']) <= 180 for i in g['items'])
                assert all(i['at'] for i in g['items'])
                # 排序：at 全局倒序
                ats = [i['at'] for i in g['items']]
                assert ats == sorted(ats, reverse=True), ats
                # 分页
                g2 = client.get('/api/me/growth-activity?limit=3&offset=3', headers=u1).json()
                assert len(g2['items']) == 3 and g2['total'] == 6 and g2['has_more'] is False, g2
                # 他人不可见
                assert client.get('/api/me/growth-activity', headers=u2).json()['total'] == 0
            """))
            assert r.returncode == 0, r.stderr

    def test_edge_regressions(self):
        """根审第5项：同timestamp分页/孤儿reply计数/恶意索引shape/缓存切目录/真假布尔。"""
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""

                import json as _j
                from pathlib import Path as _P

                # ── 同 timestamp 分页稳定：3 条同 at 记录跨页不重不漏 ──
                c2 = main.db()
                for rid in ('bn-aaaa00000001', 'bn-bbbb00000002'):
                    c2.execute("INSERT INTO reading_records(user_id,kind,resource_id,title,url,category,available,updated_at) "
                               "VALUES(?,'book_note',?,'t','u','c',1,'SAME')", (uid1, rid))
                c2.execute("INSERT INTO reading_records(user_id,kind,resource_id,title,url,category,available,updated_at) "
                           "VALUES(?,'reading','deep-work','t','u','c',1,'SAME')", (uid1,))
                c2.commit(); c2.close()
                p1 = client.get('/api/me/reading-progress?limit=2&offset=0', headers=u1).json()
                p2 = client.get('/api/me/reading-progress?limit=2&offset=2', headers=u1).json()
                ids = [(i['kind'], i['resource_id']) for i in p1['items'] + p2['items']]
                assert len(ids) == 3 and len(set(ids)) == 3 and p1['total'] == 3, (ids, p1['total'])

                # ── activity 同 at 分页 + 孤儿 reply 不计 ──
                c2 = main.db()
                for i in range(3):
                    c2.execute("INSERT INTO comments(anchor,date,user_id,username,text,created_at,deleted,status) "
                               "VALUES('x','d',?, '成员甲',?, '2026-09-05T10:00:00+08:00',0,'accepted')", (uid1, f'同刻{i}'))
                # 父 thread 已删的孤儿回复：不进 items 也不计 total
                c2.execute("INSERT INTO question_replies(thread_id,user_id,author_kind,author_name,text,created_at) "
                           "VALUES(9999,?,'human','成员甲','孤儿回复','2026-09-05T11:00:00+08:00')", (uid1,))
                c2.commit(); c2.close()
                a1 = client.get('/api/me/growth-activity?limit=2&offset=0', headers=u1).json()
                a2 = client.get('/api/me/growth-activity?limit=2&offset=2', headers=u1).json()
                aids = [i['id'] for i in a1['items'] + a2['items']]
                assert a1['total'] == 3 and len(aids) == 3 and len(set(aids)) == 3, (aids, a1['total'])
                assert '孤儿回复' not in [i['excerpt'] for i in a1['items'] + a2['items']]

                # ── 真假布尔：null/字符串/空body ──
                K, R = 'book_note', 'bn-aaaa00000001'
                assert client.patch(f'/api/me/reading-progress/{K}/{R}', headers=u1,
                    json={'saved': 'yes'}).status_code == 422
                assert client.patch(f'/api/me/reading-progress/{K}/{R}', headers=u1,
                    json={'finished': 1}).status_code == 422
                nb = client.patch(f'/api/me/reading-progress/{K}/{R}', headers=u1)
                assert nb.status_code == 422, nb.status_code
                nl = client.patch(f'/api/me/reading-progress/{K}/{R}', headers=u1, content='null')
                assert nl.status_code == 422, nl.status_code
                # 显式 null 字段 → 422（model_fields_set 区分未传）
                assert client.patch(f'/api/me/reading-progress/{K}/{R}', headers=u1,
                    json={'saved': None}).status_code == 422
                assert client.patch(f'/api/me/reading-progress/{K}/{R}', headers=u1,
                    json={'saved': True, 'finished': None}).status_code == 422

                # ── 恶意索引 shape → 503 非 500（根复现形态全覆盖）──
                bn = _P(main.STATIC) / 'book-notes' / 'index.json'
                for bad in ('[1,2,3]', '{"items":42}', '{"items":"abc"}',
                            '{"items":[1,2]}', '{"items":[{"id":"bn-x","title":5}]}',
                            '{"items":[{"id":"../etc","title":"t"}]}'):
                    bn.write_text(bad, encoding='utf-8')
                    r_ = client.get(f'/api/me/reading-progress/{K}/{R}', headers=u1)
                    assert r_.status_code == 503, (bad, r_.status_code)
                pi = _P(main.STATIC) / 'readings' / 'practice-index.json'
                for bad in ('{"entries":["bad"]}', '{"entries":{"deep-work":"bad"}}',
                            '{"entries":{"../etc":{"title":"t"}}}', '{"entries":{"ok":{"title":3}}}'):
                    pi.write_text(bad, encoding='utf-8')
                    r_ = client.get('/api/me/reading-progress/reading/deep-work', headers=u1)
                    assert r_.status_code == 503, (bad, r_.status_code)
                bn.write_text(_j.dumps(BN := {'generated':'t','total':1,'categories':[],
                    'items':[{'id':'bn-bbbb00000002','title':'书乙','category':'c'}]}), encoding='utf-8')
                pi.write_text(_j.dumps({'version':'t','entries':{'deep-work':{'source_title':'深度工作','source_url':'/readings/deep-work/'}}}), encoding='utf-8')
                ok = client.get('/api/me/reading-progress/reading/deep-work', headers=u1)
                assert ok.status_code == 200, ok.text

                # ── 缓存切目录不串：重新 configure 到另一静态目录 ──
                other = _P(main.STATIC).parent / 'static2' / 'book-notes'
                other.mkdir(parents=True)
                (other / 'index.json').write_text(_j.dumps({'items':[
                    {'id':'bn-zzzz99990000','title':'新库书','category':'x'}]}), encoding='utf-8')
                oth_pi = _P(main.STATIC).parent / 'static2' / 'readings'
                oth_pi.mkdir(parents=True)
                (oth_pi / 'practice-index.json').write_text('{"entries":{}}', encoding='utf-8')
                import reading_growth
                reading_growth.configure(db=main.db, static_dir=_P(main.STATIC).parent / 'static2')
                g2 = client.get('/api/me/reading-progress/book_note/bn-zzzz99990000', headers=u1)
                assert g2.status_code == 200 and g2.json()['item']['title'] == '新库书', g2.text
                # 旧库 id 在新索引中已下架 → 快照 available=false（证缓存真切换，非旧 sig 命中）
                gone = client.get(f'/api/me/reading-progress/{K}/{R}', headers=u1).json()['item']
                assert gone['available'] is False and gone['url'] is None, gone

                # ── ledger anchor → /ledger/<date>/#<sec> ──
                c2 = main.db()
                c2.execute("INSERT INTO favorites(user_id,anchor,text,section,created_at) "
                           "VALUES(?,'2026-09-05#读本-p2','日报段落','读本','2026-09-05T08:00:00+08:00')", (uid1,))
                c2.commit(); c2.close()
                ga = client.get('/api/me/growth-activity', headers=u1).json()
                lf = [i for i in ga['items'] if i['type'] == 'paragraph_saved' and i['title'] == '读本'][0]
                assert lf['url'] == '/ledger/2026-09-05/#读本', lf
            """))
            assert r.returncode == 0, r.stderr


if __name__ == "__main__":
    unittest.main()
