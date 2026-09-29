"""PERF-CLOSE R1：/api/context-units latest 契约回归（真 HTTP TestClient）。

冻结契约：
- latest=true 先按身份可见 published 最新版本选最新可见日，只返该日 + selected_date；
- date+latest 同传 400；date 请求回显 selected_date=date；无参旧行为=跨日列表+selected_date null；
- latest 分页锁定选定日（cursor 到日尾仍空，不跳旧日）；空可见池 items=[]+selected_date=null。
隔离临时数据目录 + 合成会话，无生产写入。
"""
import tempfile
import textwrap
import unittest
from pathlib import Path

from app.test_product_performance import _env, _run

BOOT = textwrap.dedent("""
    import main
    from starlette.testclient import TestClient
    c = main.db()
    NOW = "2026-09-26T00:00:00+08:00"
    UNITS = [
        ("cu-20260926-0001", "2026-09-26", "draft",     "public"),
        ("cu-20260925-0001", "2026-09-25", "published", "private"),
        ("cu-20260925-0002", "2026-09-25", "published", "member"),
        ("cu-20260924-0001", "2026-09-24", "published", "public"),
        ("cu-20260924-0002", "2026-09-24", "published", "public"),
        ("cu-20260924-0003", "2026-09-24", "published", "public"),
        ("cu-20260923-0001", "2026-09-23", "published", "public"),
        ("cu-20260923-0002", "2026-09-23", "published", "public"),
    ]
    for uid, day, status, vis in UNITS:
        c.execute(
            "INSERT INTO context_units(id,version,source_date,title,summary,participants_json,"
            "message_count,visibility,status,created_at,updated_at) VALUES(?,?,?,?,?,?,1,?,?,?,?)",
            (uid, 1, day, "t-" + uid, "s", "[]", vis, status, NOW, NOW),
        )
    um = c.execute(
        "INSERT INTO users(username,password_hash,role,display_name,created_at) VALUES(?,?,?,?,?)",
        ("fxmember", "h", "member", "成员", "2026-01-01T00:00:00+08:00"),
    ).lastrowid
    ua = c.execute(
        "INSERT INTO users(username,password_hash,role,display_name,created_at) VALUES(?,?,?,?,?)",
        ("fxadmin", "h", "admin", "管理", "2026-01-01T00:00:00+08:00"),
    ).lastrowid
    c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('fx-m',?,'2099-01-01T00:00:00+08:00')", (um,))
    c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('fx-a',?,'2099-01-01T00:00:00+08:00')", (ua,))
    c.commit(); c.close()
    client = TestClient(main.app)
    H_M = {'Authorization': 'Bearer fx-m'}
    H_A = {'Authorization': 'Bearer fx-a'}
""")


class ContextUnitsLatestTest(unittest.TestCase):
    def test_latest_contract(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "static").mkdir()
            result = _run(_env(root), BOOT + textwrap.dedent("""
                # 匿名 latest：锁 09-24（member/private/draft 皆不可见），仅该日3件
                j = client.get('/api/context-units?latest=true&limit=100').json()
                assert j['selected_date'] == '2026-09-24', j['selected_date']
                assert len(j['items']) == 3 and {i['date'] for i in j['items']} == {'2026-09-24'}
                assert j['count'] == 3

                # 成员 latest：锁 09-25 仅 member 可见件
                j = client.get('/api/context-units?latest=true&limit=100', headers=H_M).json()
                assert j['selected_date'] == '2026-09-25'
                assert [i['id'] for i in j['items']] == ['cu-20260925-0002']

                # 管理员 latest：09-25 private+member 共2件
                j = client.get('/api/context-units?latest=true&limit=100', headers=H_A).json()
                assert j['selected_date'] == '2026-09-25' and len(j['items']) == 2

                # 显式 date：selected_date 回显该日
                j = client.get('/api/context-units?date=2026-09-23&limit=100').json()
                assert j['selected_date'] == '2026-09-23' and len(j['items']) == 2

                # date+latest 同传 → 400（不静默歧义）
                assert client.get('/api/context-units?date=2026-09-24&latest=true').status_code == 400

                # 显式日分页不跨日
                p1 = client.get('/api/context-units?date=2026-09-24&limit=2').json()
                assert len(p1['items']) == 2 and p1['next_cursor']
                p2 = client.get(f"/api/context-units?date=2026-09-24&limit=100&cursor={p1['next_cursor']}").json()
                assert len(p2['items']) == 1 and {i['date'] for i in p2['items']} == {'2026-09-24'}
                assert p2['next_cursor'] is None

                # latest 分页锁最新日：第二页仍 09-24 不跳 09-23
                p1 = client.get('/api/context-units?latest=true&limit=2').json()
                assert p1['selected_date'] == '2026-09-24' and p1['next_cursor']
                p2 = client.get(f"/api/context-units?latest=true&limit=100&cursor={p1['next_cursor']}").json()
                assert p2['selected_date'] == '2026-09-24'
                assert all(i['date'] == '2026-09-24' for i in p2['items']) and len(p2['items']) == 1

                # 最新日末尾 cursor：items 空不跳旧日
                p1 = client.get('/api/context-units?latest=true&limit=3').json()
                cur = p1['next_cursor']
                if not cur:
                    import base64
                    last = p1['items'][-1]
                    cur = base64.urlsafe_b64encode(f"{last['date']}|{last['id']}".encode()).decode().rstrip('=')
                p2 = client.get(f"/api/context-units?latest=true&limit=100&cursor={cur}").json()
                assert p2['items'] == [] and p2['next_cursor'] is None

                # 旧无参请求：跨日列表 DESC + selected_date null（API 不变）
                j = client.get('/api/context-units?limit=100').json()
                days = [i['date'] for i in j['items']]
                assert j['selected_date'] is None
                assert days == sorted(days, reverse=True) and '2026-09-24' in days and '2026-09-23' in days
                assert '2026-09-26' not in days and '2026-09-25' not in days

                # 匿名取 member 日：items 空但 selected_date 回显
                j = client.get('/api/context-units?date=2026-09-25&limit=100').json()
                assert j['items'] == [] and j['selected_date'] == '2026-09-25'

                # date 格式非法 → 400（旧行为）
                assert client.get('/api/context-units?date=2026-9-4').status_code == 400

                # latest 全无可见 → items=[]/selected_date=null/next_cursor=null（三种身份）
                cc = main.db()
                cc.execute("UPDATE context_units SET status='draft'"); cc.commit(); cc.close()
                for hdr in (None, H_M, H_A):
                    j = client.get('/api/context-units?latest=true&limit=100', headers=hdr or {}).json()
                    assert j['items'] == [] and j['selected_date'] is None and j['next_cursor'] is None, j
            """))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
