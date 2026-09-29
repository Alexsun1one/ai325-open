"""idx_msg_sender_name 索引回归：旧库幂等升级 + 三种过滤形态不走全表扫 + 榜单结果不变。

真实 init_db 升级预置旧库（缺索引）；EXPLAIN 断言 SEARCH 而非 SCAN；
同 fixture 下先无索引跑榜单、再建索引跑榜单，items 完全一致。
隔离临时数据目录，无生产读写。
"""
import json
import sqlite3
import tempfile
import textwrap
import unittest
from pathlib import Path

from app.test_product_performance import _env, _run

DAY_QUERY = """SELECT substr(cst,1,10) d, COUNT(*) n FROM messages
 WHERE cst IS NOT NULL AND substr(cst,1,10)!='' AND sender_name='成员一'
 AND substr(cst,1,10)>='2026-08-25' GROUP BY d"""
MONTH_QUERY = """SELECT substr(cst,1,10) d, COUNT(*) n FROM messages
 WHERE cst IS NOT NULL AND substr(cst,1,10)!='' AND sender_name='成员一'
 AND substr(cst,1,7)='2026-09' GROUP BY d"""
REPEAT_QUERY = """SELECT content FROM messages WHERE sender_name='成员一'
 AND substr(cst,1,10)>='2026-08-25' GROUP BY content HAVING COUNT(*)>=5"""

FIXTURE = """
import datetime, main
from starlette.testclient import TestClient
client = TestClient(main.app)
c = main.db()
today = datetime.date.today()
for i in range(6):
    d = (today - datetime.timedelta(days=i)).isoformat() + 'T10:00:00'
    for j in range(2 + i):
        c.execute("INSERT INTO messages(sender_name,cst,content) VALUES('成员一',?,?)", (d, 'm%d-%d' % (i, j)))
    c.execute("INSERT INTO messages(sender_name,cst,content) VALUES('成员二',?,?)", (d, 'n%d' % i))
c.commit()
"""


class VitalityIndexTest(unittest.TestCase):
    def test_upgrade_explain_and_equivalence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'static').mkdir()
            env = _env(root)
            # 预置旧库：messages 表无 idx_msg_sender_name（模拟升级前生产）
            dbp = root / 'xf.db'
            c = sqlite3.connect(dbp)
            c.execute("""CREATE TABLE messages(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session TEXT, local_id INT, create_time INT,
              cst TEXT, sender TEXT, sender_name TEXT, is_send INT, content TEXT)""")
            c.execute("CREATE INDEX idx_msg_time ON messages(create_time)")
            c.execute("CREATE INDEX idx_msg_sender ON messages(sender)")
            c.commit(); c.close()

            # 第一次 import main → init_db 升级旧库
            r = _run(env, textwrap.dedent('''
                import main, sqlite3
                c = main.db()
                idx = [r[0] for r in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='messages'")]
                assert 'idx_msg_sender_name' in idx, idx
                print('UPGRADED', idx)
            '''))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

            # 第二次 import → IF NOT EXISTS 幂等不炸
            r = _run(env, "import main")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

            # EXPLAIN：day/month/repeat 三形态全部 SEARCH（无 SCAN messages）
            r = _run(env, textwrap.dedent(f'''
                import main
                c = main.db()
                for label, q in [('day', {DAY_QUERY!r}), ('month', {MONTH_QUERY!r}), ('repeat', {REPEAT_QUERY!r})]:
                    plan = [tuple(x) for x in c.execute('EXPLAIN QUERY PLAN ' + q)]
                    flat = ' '.join(str(p) for p in plan)
                    assert 'SCAN messages' not in flat, (label, plan)
                    assert 'idx_msg_sender_name' in flat, (label, plan)
                print('EXPLAIN_OK')
            '''))
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

            # 同 fixture：无索引 vs 有索引榜单一致
            r = _run(env, FIXTURE + '''
c.execute('DROP INDEX idx_msg_sender_name')
c.commit()
no_idx = client.get('/api/vitality/leaderboard').json()
c.execute('CREATE INDEX idx_msg_sender_name ON messages(sender_name)')
c.commit()
with_idx = client.get('/api/vitality/leaderboard').json()
assert no_idx['items'] == with_idx['items'], (no_idx['items'], with_idx['items'])
assert no_idx['items'], 'fixture 应产出非空榜单'
print('EQUIV_OK items=', len(with_idx['items']))
''')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == '__main__':
    unittest.main()
