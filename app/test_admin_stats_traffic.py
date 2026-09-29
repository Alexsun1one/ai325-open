"""TRAFFIC-UI R1：/api/admin/stats 真 HTTP 回归（合成临时 analytics.db）。

覆盖冻结契约：窗口 UV=COUNT(DISTINCT uv_hash) 跨日去重、proxy_masked>0→uv=null、
as_of=北京今日而数据截至另读 coverage.last_day、has_data 区分无数据与零、
uv_reason 区分无记录/代理遮蔽、鉴权 401/403/200、admin 响应 no-store。
隔离临时数据目录；fixture 数字是合成值，不代替真实生产流量。
"""
import tempfile
import textwrap
import unittest
from pathlib import Path

from app.test_product_performance import _env, _run

BOOT = """
import datetime, json, sqlite3, main
from starlette.testclient import TestClient
client = TestClient(main.app)
c = main.db()
uidA = c.execute("INSERT INTO users(username,password_hash,role,display_name,created_at) "
    "VALUES('adm','h','admin','群主','2026-01-01T00:00:00+08:00')").lastrowid
uidM = c.execute("INSERT INTO users(username,password_hash,role,display_name,created_at) "
    "VALUES('mem','h','member','成员','2026-01-01T00:00:00+08:00')").lastrowid
c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('a1',?,'2099-01-01T00:00:00+08:00')", (uidA,))
c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('m1',?,'2099-01-01T00:00:00+08:00')", (uidM,))
c.commit(); c.close()
ADMIN = {'Authorization': 'Bearer a1'}
MEMBER = {'Authorization': 'Bearer m1'}
TODAY = datetime.datetime.now(main.CST).date()

def seed_analytics(event_rows, uv_rows=(), meta=None):
    a = sqlite3.connect(str(main.ANALYTICS_DB))
    a.execute('CREATE TABLE IF NOT EXISTS analytics_event_day('
              'day TEXT PRIMARY KEY, parsed INT, bots INT, internal INT, '
              'pv INT, observed_pv INT, proxy_masked INT)')
    a.execute('CREATE TABLE IF NOT EXISTS analytics_uv_day(day TEXT, uv_hash TEXT)')
    a.execute('CREATE TABLE IF NOT EXISTS analytics_meta(k TEXT PRIMARY KEY, v TEXT)')
    for r in event_rows:
        a.execute('INSERT INTO analytics_event_day VALUES(?,?,?,?,?,?,?)', r)
    for r in uv_rows:
        a.execute('INSERT INTO analytics_uv_day VALUES(?,?)', r)
    for k, v in (meta or {}).items():
        a.execute('INSERT OR REPLACE INTO analytics_meta VALUES(?,?)', (k, json.dumps(v)))
    a.commit(); a.close()

def stats(headers=ADMIN, path='/api/admin/stats?days=30'):
    main._ADMIN_STATS_CACHE.clear()
    return client.get(path, headers=headers)
"""


class AdminStatsTrafficTest(unittest.TestCase):
    def _boot(self) -> dict:
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        root = Path(td.name)
        (root / "static").mkdir(parents=True, exist_ok=True)
        return _env(root)

    def _run_case(self, env, code: str):
        r = _run(env, BOOT + textwrap.dedent(code))
        self.assertEqual(r.returncode, 0, f"stdout={r.stdout}\nstderr={r.stderr}")

    def test_uv_distinct_across_days_and_coverage(self):
        """同访客跨天只算一次；as_of=今日；coverage 报聚合库真实起止。"""
        self._run_case(self._boot(), """
            d0, d1, d2 = TODAY.isoformat(), (TODAY - datetime.timedelta(days=1)).isoformat(), (TODAY - datetime.timedelta(days=2)).isoformat()
            d_old = (TODAY - datetime.timedelta(days=40)).isoformat()
            seed_analytics(
                [(d2, 30, 2, 1, 10, 12, 0), (d1, 30, 0, 0, 8, 9, 0), (d0, 20, 0, 0, 5, 5, 0), (d_old, 10, 0, 0, 3, 3, 0)],
                [(d2, 'hA'), (d1, 'hA'), (d0, 'hB'), (d_old, 'hZ')],
            )
            p = stats().json()
            assert p['as_of'] == TODAY.isoformat(), p['as_of']
            cov = p['ingest']['coverage']
            assert (cov['first_day'], cov['last_day'], cov['days']) == (d_old, d0, 4), cov
            assert p['traffic']['windows']['7d']['uv'] == 2, p['traffic']['windows']
            # 40 天前的 hZ 在 30d 窗口外，不计；同访客 hA 跨 d1/d2 只算一次。
            assert p['traffic']['windows']['30d']['uv'] == 2
            assert p['traffic']['windows']['today']['uv'] == 1
            assert p['traffic']['windows']['7d']['has_data'] is True
            assert p['traffic']['uv_available'] is True and p['traffic']['uv_reason'] is None
            print('OK')
        """)

    def test_proxy_masked_uv_null(self):
        """窗口 proxy_masked>0 → uv=null、uv_available=false、reason 指代理。"""
        self._run_case(self._boot(), """
            d0 = TODAY.isoformat()
            seed_analytics([(d0, 10, 0, 0, 4, 600, 590)], [(d0, 'hA')])
            p = stats().json()
            w = p['traffic']['windows']['today']
            assert w['has_data'] is True and w['uv'] is None and w['pv'] == 4, w
            assert p['traffic']['uv_available'] is False
            assert '代理' in p['traffic']['uv_reason'], p['traffic']['uv_reason']
            print('OK')
        """)

    def test_stale_data_as_of_and_has_data(self):
        """数据截至十天前：as_of 仍今日，today/7d has_data=false、30d 有数据去重 UV。"""
        self._run_case(self._boot(), """
            d_stale = (TODAY - datetime.timedelta(days=10)).isoformat()
            seed_analytics([(d_stale, 10, 0, 0, 7, 7, 0)], [(d_stale, 'hA'), (d_stale, 'hB')])
            p = stats().json()
            assert p['as_of'] == TODAY.isoformat()
            assert p['ingest']['coverage']['last_day'] == d_stale
            w = p['traffic']['windows']
            assert w['today']['has_data'] is False and w['today']['uv'] is None
            assert w['7d']['has_data'] is False
            assert w['30d']['has_data'] is True and w['30d']['uv'] == 2
            assert p['traffic']['uv_available'] is False
            assert '暂无聚合记录' in p['traffic']['uv_reason'], p['traffic']['uv_reason']
            print('OK')
        """)

    def test_no_db_and_auth_matrix(self):
        """无库：traffic.available=false；admin200/member403/匿名401 且均 no-store。"""
        self._run_case(self._boot(), """
            r_adm = stats(); assert r_adm.status_code == 200, r_adm.status_code
            assert r_adm.headers.get('cache-control') == 'no-store', r_adm.headers.get('cache-control')
            p = r_adm.json()
            assert p['traffic']['available'] is False and p['traffic']['uv_available'] is False
            r_mem = stats(MEMBER); assert r_mem.status_code == 403, r_mem.status_code
            assert r_mem.headers.get('cache-control') == 'no-store'
            r_anon = client.get('/api/admin/stats'); assert r_anon.status_code == 401, r_anon.status_code
            assert r_anon.headers.get('cache-control') == 'no-store'
            r_tr = stats(path='/api/admin/stats/traffic?days=30')
            assert r_tr.status_code == 200 and r_tr.headers.get('cache-control') == 'no-store'
            tr = r_tr.json()
            assert 'ingest' in tr and 'traffic' in tr, tr.keys()
            print('OK')
        """)


if __name__ == '__main__':
    unittest.main()
