"""Read-path perf slice: GETs must not write vitality_audit; numbers stay equivalent."""
import tempfile
import textwrap
import unittest
from pathlib import Path
from app.test_product_performance import _env, _run, _seed_script


class VitalityPerfTest(unittest.TestCase):
    def test_vitality_me_readonly_and_equivalent(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / 'static').mkdir()
            env = _env(Path(td))
            result = _run(env, _seed_script(agent_count=1, audit_per_agent=0))
            self.assertEqual(result.returncode, 0, result.stderr)
            result = _run(env, textwrap.dedent('''
                import datetime, main
                import reading_vitality
                from starlette.testclient import TestClient
                client = TestClient(main.app)
                c = main.db()
                uid = c.execute("INSERT INTO users(username,password_hash,role,display_name,created_at) VALUES('m1','h','member','成员一','x')").lastrowid
                c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('s1',?,'2099-01-01T00:00:00+08:00')", (uid,))
                today = datetime.date.today()
                # 连续 7 天，第 i 天 3+i 条（3..9，均低于 anomaly 阈值 ~12.5 与 cap 20）
                for i in range(7):
                    d = (today - datetime.timedelta(days=i)).isoformat() + 'T10:00:00'
                    for j in range(3 + i):
                        c.execute("INSERT INTO messages(sender_name,cst,content) VALUES('成员一',?,?)", (d, f'消息{i}-{j}'))
                c.execute("INSERT INTO annotations(user_id,username,date,anchor,quote,note,kind,status,deleted,created_at,updated_at) VALUES(?,'成员一',?,'a1','q','','highlight','accepted',0,?,?)",
                          (uid, today.isoformat(), today.isoformat()+'T09:00:00+08:00', today.isoformat()+'T09:00:00+08:00'))
                c.commit()
                audit_before = c.execute('SELECT COUNT(*) FROM vitality_audit').fetchone()[0]

                # 计数：compute_reading_parts 调用次数 + 全路径 SQL 数
                calls = [0]
                orig = reading_vitality.compute_reading_parts
                def spy(*a, **k):
                    calls[0] += 1
                    return orig(*a, **k)
                reading_vitality.compute_reading_parts = spy
                qcount = [0]
                c.set_trace_callback(lambda s: qcount.__setitem__(0, qcount[0] + 1))
                settings = main._vitality_settings(c)
                data = main.compute_vitality_for_user(c, uid, settings)
                q_compute = qcount[0]
                reading_vitality.compute_reading_parts = orig
                assert calls[0] == 1, f'compute_reading_parts 应只调用 1 次，实际 {calls[0]}'

                # 显式数值等价（默认权重）：message=sum(3..9)=42、streak=1+..+7=28、highlight=1*2
                assert data['parts']['message'] == 42, data['parts']
                assert data['parts']['streak'] == 28, data['parts']
                assert data['parts']['highlight'] == 2, data['parts']
                assert data['parts']['accepted_reply'] == 0, data['parts']
                assert data['total'] == 72 and data['net'] == 72 and data['spent'] == 0, data

                # vitality_me：stream 聚合等价 + 读路径不写审计
                me = client.get('/api/vitality/me', headers={'Authorization':'Bearer s1'})
                assert me.status_code == 200, me.text
                got = me.json()
                assert got['total'] == data['total'] and got['net'] == data['net'], got
                by_day = {s['date']: s for s in got['stream']}
                for i in range(7):
                    ds = (today - datetime.timedelta(days=i)).isoformat()
                    assert by_day[ds]['msgs'] == 3 + i, (ds, by_day)
                    assert by_day[ds]['points'] == min(3 + i, 20) * 1, (ds, by_day)
                audit_after = c.execute('SELECT COUNT(*) FROM vitality_audit').fetchone()[0]
                assert audit_after == audit_before, (audit_before, audit_after)
                c.close()
                # 幂等
                again = client.get('/api/vitality/me', headers={'Authorization':'Bearer s1'}).json()
                assert again['total'] == got['total'] and again['stream'] == got['stream']
                print('PERF compute_queries=', q_compute, 'reading_calls=', calls[0])
            '''))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
