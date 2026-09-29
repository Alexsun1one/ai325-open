"""创建实践幂等回归（GARDEN-MARKS 契约 §创建实践幂等）。

client_id 可选兼容旧前端：同账号同负载重放返当前 Practice；
同 client_id 换负载 409；同 owner 同站内 source_url 的 active 练习返回既存；
空/站外来源不强制唯一；旧库无新表也能幂等升级。
隔离临时数据目录，无生产写入。
"""
import sqlite3
import tempfile
import textwrap
import unittest
from pathlib import Path

from app.test_product_performance import _env, _run

BOOT = """
import main
from starlette.testclient import TestClient
client = TestClient(main.app)
c = main.db()
uid = c.execute(
    "INSERT INTO users(username,password_hash,role,display_name,created_at) "
    "VALUES(?,?,?,?,?)",
    ("member1", "h", "member", "成员甲", "2026-01-01T00:00:00+08:00"),
).lastrowid
c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('h1',?,'2099-01-01T00:00:00+08:00')", (uid,))
c.commit(); c.close()
u1 = {'Authorization': 'Bearer h1'}
"""


class PracticeCreateTest(unittest.TestCase):
    def _env_only(self, td: str):
        (Path(td) / "static").mkdir()
        return _env(Path(td))

    def test_client_id_replay_and_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._env_only(td)
            r = _run(env, BOOT + textwrap.dedent("""
                body = {'title': '拆书第一章', 'outcome': '三条方法', 'client_id': 'cid-1'}
                p1 = client.post('/api/practice/mine', headers=u1, json=body)
                assert p1.status_code == 200, p1.text
                # 同 client_id 同负载 → 同一实践，不加倍
                p2 = client.post('/api/practice/mine', headers=u1, json=body)
                assert p2.json()['id'] == p1.json()['id'], (p1.json(), p2.json())
                # 同 client_id 换负载 → 409
                diff = client.post('/api/practice/mine', headers=u1,
                    json={'title': '换标题', 'outcome': '三条方法', 'client_id': 'cid-1'})
                assert diff.status_code == 409, diff.status_code
                # 不带 client_id（旧前端）→ 每次新建，兼容不回 422
                a = client.post('/api/practice/mine', headers=u1, json={'title': '无id一', 'outcome': 'o'})
                b = client.post('/api/practice/mine', headers=u1, json={'title': '无id二', 'outcome': 'o'})
                assert a.status_code == 200 and b.status_code == 200
                assert a.json()['id'] != b.json()['id']
                # 列表只一份 cid-1 实践
                items = client.get('/api/practice/mine', headers=u1).json()['items']
                same = [i for i in items if i['title'] == '拆书第一章']
                assert len(same) == 1, same
            """))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_site_source_dedupe_and_external_free(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._env_only(td)
            r = _run(env, BOOT + textwrap.dedent("""
                # 站内来源同 owner 的 active 练习 → 返回既存（响应字段不变）
                s1 = client.post('/api/practice/mine', headers=u1,
                    json={'title': '一', 'outcome': 'o', 'source_url': '/readings/kb-03/'})
                s2 = client.post('/api/practice/mine', headers=u1,
                    json={'title': '二', 'outcome': 'o', 'source_url': '/readings/kb-03/'})
                assert s2.json()['id'] == s1.json()['id'], (s1.json(), s2.json())
                assert s2.json()['title'] == '一'  # 既存原样返回，不加字段不覆盖
                # archived 不占位：归档后同源可新建
                q = client.get(f"/api/practice/mine/{s1.json()['id']}", headers=u1).json()
                client.patch(f"/api/practice/mine/{s1.json()['id']}", headers=u1,
                    json={'revision': q['revision'], 'status': 'archived'})
                s3 = client.post('/api/practice/mine', headers=u1,
                    json={'title': '三', 'outcome': 'o', 'source_url': '/readings/kb-03/'})
                assert s3.json()['id'] != s1.json()['id']
                # dedupe 命中也登记 client_id 回执：既存归档后同 key 重试不新建
                d1 = client.post('/api/practice/mine', headers=u1,
                    json={'title': '四', 'outcome': 'o', 'source_url': '/readings/kb-03/',
                          'client_id': 'ck-dup'})
                assert d1.json()['id'] == s3.json()['id']  # dedupe 命中
                q3 = client.get(f"/api/practice/mine/{s3.json()['id']}", headers=u1).json()
                client.patch(f"/api/practice/mine/{s3.json()['id']}", headers=u1,
                    json={'revision': q3['revision'], 'status': 'archived'})
                d2 = client.post('/api/practice/mine', headers=u1,
                    json={'title': '四', 'outcome': 'o', 'source_url': '/readings/kb-03/',
                          'client_id': 'ck-dup'})
                assert d2.json()['id'] == s3.json()['id'], d2.json()  # 回执指向既存，不新建
                d3 = client.post('/api/practice/mine', headers=u1,
                    json={'title': '五', 'outcome': 'o', 'source_url': '/readings/kb-03/',
                          'client_id': 'ck-dup'})
                assert d3.status_code == 409, d3.status_code  # 同 key 换负载
                # 空来源与站外来源不强制唯一
                e1 = client.post('/api/practice/mine', headers=u1, json={'title': 'e1', 'outcome': 'o'})
                e2 = client.post('/api/practice/mine', headers=u1, json={'title': 'e2', 'outcome': 'o'})
                assert e1.json()['id'] != e2.json()['id']
                x1 = client.post('/api/practice/mine', headers=u1,
                    json={'title': 'x1', 'outcome': 'o', 'source_url': 'https://example.com/a'})
                x2 = client.post('/api/practice/mine', headers=u1,
                    json={'title': 'x2', 'outcome': 'o', 'source_url': 'https://example.com/a'})
                assert x1.json()['id'] != x2.json()['id']
            """))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_old_db_upgrade_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "static").mkdir()
            env = _env(root)
            # 旧库：practice_items 无 practice_create_actions 表
            c = sqlite3.connect(root / "xf.db")
            c.execute("""CREATE TABLE practice_items(
              id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL,
              title TEXT NOT NULL, outcome TEXT NOT NULL DEFAULT '',
              next_step TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
              result_url TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '',
              source_title TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
              revision INTEGER NOT NULL DEFAULT 1, challenge_id TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            c.commit(); c.close()
            # init_db 升级出幂等表；再 import 幂等不炸
            r = _run(env, "import main")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            c = sqlite3.connect(root / "xf.db")
            tables = {x[0] for x in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert 'practice_create_actions' in tables, tables
            c.close()
            r = _run(env, "import main")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
