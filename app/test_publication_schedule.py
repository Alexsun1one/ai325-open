"""出刊 deadline 判定：共用函数边界 + admin 端点/字段接线回归。"""
import tempfile
import textwrap
import unittest
from pathlib import Path
from app.test_product_performance import _env, _run, _seed_script


class PublicationScheduleTest(unittest.TestCase):
    def test_deadline_boundaries(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'static').mkdir()
            env = _env(Path(td))
            result = _run(env, _seed_script(agent_count=0, audit_per_agent=0))
            self.assertEqual(result.returncode, 0, result.stderr)
            result = _run(env, textwrap.dedent('''
                import datetime
                import publication_schedule as ps
                CST = ps.CST
                def at(y, m, d, hh, mm, ss=0):
                    return datetime.datetime(y, m, d, hh, mm, ss, tzinfo=CST)
                published = {'2026-09-22'}  # 已出 22 期，23 期未到
                # 凌晨 01:06（未到 08:30）：expected=22，无 gap
                s = ps.publication_status(at(2026,9,24,1,6), published)
                assert s['expected_latest'] == '2026-09-22' and s['missing_dates'] == [] and s['health'] == 'ok', s
                # pending=制作中的 09-23 期，到期时刻是次日 09-24 08:30
                assert s['pending_date'] == '2026-09-23' and s['scheduled_for'] == '2026-09-24T08:30:00+08:00', s
                # 08:29:59 同判定
                s = ps.publication_status(at(2026,9,24,8,29,59), published)
                assert s['expected_latest'] == '2026-09-22' and s['missing_dates'] == [], s
                # 08:30 整：expected=23 → 缺 23 即 gap
                s = ps.publication_status(at(2026,9,24,8,30), published)
                assert s['expected_latest'] == '2026-09-23' and s['missing_dates'] == ['2026-09-23'] and s['health'] == 'gap', s
                # 截止后 pending=09-24 期 → 09-25 08:30 到期
                assert s['pending_date'] == '2026-09-24' and s['scheduled_for'] == '2026-09-25T08:30:00+08:00', s
                # 已提前有 23 但 22 缺失 → 仍报 22（latest>expected 不忽略当期应交）
                s = ps.publication_status(at(2026,9,24,1,6), {'2026-09-23'})
                assert s['expected_latest'] == '2026-09-22' and s['missing_dates'] == ['2026-09-22'] and s['health'] == 'gap', s
                # 中间断档同样照报：有 20 和 23，缺 21/22
                s = ps.publication_status(at(2026,9,24,1,6), {'2026-09-20','2026-09-23'})
                assert s['missing_dates'] == ['2026-09-21','2026-09-22'], s
                # 凌晨连 22 也没出 → gap 22（不藏更早断刊）
                s = ps.publication_status(at(2026,9,24,1,6), set())
                assert s['expected_latest'] == '2026-09-22' and s['missing_dates'] == ['2026-09-22'] and s['health'] == 'gap', s
                # 提前已有 23 → 截止后无 gap
                s = ps.publication_status(at(2026,9,24,8,30), {'2026-09-22','2026-09-23'})
                assert s['missing_dates'] == [] and s['health'] == 'ok', s
                # UTC 17:06 == 北京次日 01:06，等价判定
                utc = datetime.datetime(2026,9,23,17,6, tzinfo=datetime.timezone.utc)
                s = ps.publication_status(utc, published)
                assert s['expected_latest'] == '2026-09-22' and s['missing_dates'] == [], s
                # 跨年边界：北京 2027-01-01 02:00 → expected 2026-12-30；08:30 后 → 2026-12-31
                s = ps.publication_status(at(2027,1,1,2,0), {'2026-12-30'})
                assert s['expected_latest'] == '2026-12-30' and s['missing_dates'] == [], s
                s = ps.publication_status(at(2027,1,1,8,30), {'2026-12-30'})
                assert s['expected_latest'] == '2026-12-31' and s['missing_dates'] == ['2026-12-31'], s
                # 环境变量覆盖截止时刻：10:00 时 09:30 仍看前天
                import os
                os.environ['XF_PUBLICATION_DEADLINE'] = '10:00'
                s = ps.publication_status(at(2026,9,24,9,30), published)
                assert s['expected_latest'] == '2026-09-22' and s['missing_dates'] == [], s
                del os.environ['XF_PUBLICATION_DEADLINE']
            '''))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_admin_endpoints_use_shared_status(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'static').mkdir()
            env = _env(Path(td))
            result = _run(env, _seed_script(agent_count=1, audit_per_agent=0))
            self.assertEqual(result.returncode, 0, result.stderr)
            result = _run(env, textwrap.dedent('''
                import datetime, json, os
                import main, publication_schedule as ps
                from starlette.testclient import TestClient
                client = TestClient(main.app)
                c = main.db()
                admin_uid = c.execute("SELECT id FROM users WHERE role='admin' LIMIT 1").fetchone()[0]
                c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('adm',?,'2099-01-01T00:00:00+08:00')", (admin_uid,))
                c.commit(); c.close()
                admin = {'Authorization':'Bearer adm'}
                agent = {'Authorization':'Bearer ai325_agent_perf_test_token'}
                # 真实已出刊文件：2026-09-22
                ledgers = main.GOVERNED_LEDGER_DIR
                ledgers.mkdir(parents=True, exist_ok=True)
                (ledgers / '2026-09-22.json').write_text(json.dumps({'date':'2026-09-22','title':'期22'}), encoding='utf-8')
                (ledgers / '2026-99-99.json').write_text('{}', encoding='utf-8')  # 伪日期必须被忽略
                assert main._published_ledger_dates() == {'2026-09-22'}

                real_dt = datetime.datetime
                class FrozenDT(real_dt):
                    current = real_dt(2026,9,24,1,6, tzinfo=ps.CST)
                    @classmethod
                    def now(cls, tz=None):
                        return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)
                datetime.datetime = FrozenDT
                try:
                    # 01:06：三端点都应 expected=09-22、missing=[]、无断更误报
                    gap = client.get('/api/admin/alerts', headers=admin).json()['publication_gap']
                    assert gap['expected_latest'] == '2026-09-22', gap
                    assert gap['missing_dates'] == [] and gap['health'] == 'ok', gap
                    assert gap['pending_date'] == '2026-09-23', gap
                    assert gap['scheduled_for'] == '2026-09-24T08:30:00+08:00', gap
                    pub = client.get('/api/admin/stats', headers=admin).json()['publication']
                    assert pub['expected_latest'] == '2026-09-22' and pub['missing_dates'] == [], pub
                    assert pub['pending_date'] == '2026-09-23' and pub['health'] == 'ok', pub
                    ops = client.get('/api/admin/ops/issues', headers=admin)
                    assert ops.status_code == 200, ops.text
                    body = ops.json()
                    assert body['expected_latest'] == '2026-09-22' and body['missing_dates'] == [], body
                    assert body['pending_date'] == '2026-09-23' and body['health'] == 'ok', body
                    # 08:30：expected=09-23、missing=[23]、gap
                    FrozenDT.current = real_dt(2026,9,24,8,30, tzinfo=ps.CST)
                    main._ADMIN_STATS_CACHE.clear()
                    gap = client.get('/api/admin/alerts', headers=admin).json()['publication_gap']
                    assert gap['expected_latest'] == '2026-09-23', gap
                    assert gap['missing_dates'] == ['2026-09-23'] and gap['health'] == 'gap', gap
                    assert gap['pending_date'] == '2026-09-24' and gap['scheduled_for'] == '2026-09-25T08:30:00+08:00', gap
                    pub = client.get('/api/admin/stats', headers=admin).json()['publication']
                    assert pub['expected_latest'] == '2026-09-23' and pub['missing_dates'] == ['2026-09-23'], pub
                    body = client.get('/api/admin/ops/issues', headers=admin).json()
                    assert body['expected_latest'] == '2026-09-23' and body['missing_dates'] == ['2026-09-23'] and body['health'] == 'gap', body
                finally:
                    datetime.datetime = real_dt
                # Agent token 不能用 admin 接口
                for path in ('/api/admin/alerts','/api/admin/stats','/api/admin/ops/issues'):
                    assert client.get(path, headers=agent).status_code in (401, 403), path
            '''))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
