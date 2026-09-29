"""Legacy reward_items schema drift: endpoints must not 500 on an old narrow table."""
import tempfile
import textwrap
import unittest
from pathlib import Path
from app.test_product_performance import _env, _run

LEGACY_DDL = """CREATE TABLE reward_items(id TEXT PRIMARY KEY,name TEXT NOT NULL,
    price_original INT,cost_vitality INT,stock INT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)"""


class RewardsMigrationTest(unittest.TestCase):
    def test_legacy_reward_items_migrates_and_serves(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'static').mkdir()
            env = _env(Path(td))
            # 先落线上旧形状（窄表），再 import main 触发 init_db 迁移
            pre = _run(env, textwrap.dedent(f'''
                import os, sqlite3
                from pathlib import Path
                db = Path(os.environ["XF_DATA_DIR"]) / "xf.db"
                c = sqlite3.connect(db)
                c.execute({LEGACY_DDL!r})
                c.execute("INSERT INTO reward_items VALUES('legacy-1','旧奖品',100,10,3,'2026-01-01','2026-01-01')")
                c.commit(); c.close()
            '''))
            self.assertEqual(pre.returncode, 0, pre.stderr)
            result = _run(env, textwrap.dedent('''
                import main
                from starlette.testclient import TestClient
                client = TestClient(main.app)
                c = main.db()
                cols = {r[1] for r in c.execute("PRAGMA table_info(reward_items)")}
                need = {'description','kind','require_review','dispatch_note','icon','active'}
                assert need <= cols, cols
                row = c.execute("SELECT id,active FROM reward_items WHERE id='legacy-1'").fetchone()
                assert row['active'] == 1, dict(row)  # 旧行保留，默认上架
                c.execute("INSERT INTO users(username,password_hash,role,display_name,created_at) VALUES('u','h','member','U','x')")
                uid = c.execute("SELECT id FROM users WHERE username='u'").fetchone()[0]
                c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('s',?,'2099-01-01T00:00:00+08:00')", (uid,))
                c.commit(); c.close()
                r = client.get('/api/rewards/items', headers={'Authorization':'Bearer s'})
                assert r.status_code == 200, r.text
                assert any(i['id'] == 'legacy-1' for i in r.json()['items']), r.json()
            '''))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
