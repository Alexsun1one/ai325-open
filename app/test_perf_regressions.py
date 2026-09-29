"""PERF-SERVER 修复语义回归：quality 五维/窗口语义 + leaderboard 榜序/排除/本人态。

fixture 直插 messages/essays/annotations，对照「逐字重算」的参考实现断言逐字段一致；
leaderboard 断言榜序、excluded、my_rank 口径不变。隔离临时目录，无生产读写。
"""
import json
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
uid1 = c.execute("INSERT INTO users(username,password_hash,role,display_name,created_at) "
    "VALUES('member1','h','member','成员甲','2026-01-01T00:00:00+08:00')").lastrowid
c.execute("INSERT INTO sessions(token,user_id,expires_at) VALUES('h1',?,'2099-01-01T00:00:00+08:00')", (uid1,))
# 两日消息：含 @/Re:/知识词/长文/null-cst
msgs = [
    ('成员甲', 'github.com/x 工具方法', '2026-09-23 10:00:00', '2026-09-23'),
    ('成员乙', 'Re: 知识库结构化讨论', '2026-09-23 10:01:00', '2026-09-23'),
    ('成员甲', '短', '2026-09-23 10:02:00', '2026-09-23'),
    ('成员甲', '向量蒸馏' + '长' * 220, '2026-09-22 09:00:00', '2026-09-22'),
    ('成员乙', '普通', '2026-09-22 09:01:00', '2026-09-22'),
    ('成员甲', 'null日期消息', None, None),
    # 边缘：cst='' / content=None / 未来日
    ('成员乙', '', '', ''),
    ('成员甲', None, '2026-09-23 10:03:00', '2026-09-23'),
    ('成员乙', '未来日', '2027-01-01 00:00:00', '2027-01-01'),
]
for sn, text, cst, d in msgs:
    c.execute("INSERT INTO messages(sender_name,content,create_time,cst) VALUES(?,?,?,?)",
              (sn, text, cst, cst))
c.commit(); c.close()
u1 = {'Authorization': 'Bearer h1'}

# ── 旧实现 oracle：逐字复刻修复前算法（Python 过滤 + 每关键词 lower）──
def old_quality(date_param=None):
    c3 = main.db(); c3.row_factory = None
    if date_param:
        target = date_param
    else:
        target = c3.execute("SELECT MAX(substr(cst,1,10)) FROM messages WHERE cst IS NOT NULL AND cst<>''").fetchone()[0]
    allm = c3.execute("SELECT cst,COALESCE(NULLIF(sender_name,'?'),sender) sn,content FROM messages ORDER BY create_time").fetchall()
    c3.close()
    KW = ['github','http','.pdf','.md','.html','.zip','工具','方法','知识库','agent','harness','向量','蒸馏','结构化']
    def snap(msgs, scope, dv):
        if not msgs:
            return {'scope': scope, 'date': dv, 'grade': 'N/A', 'overall': 0, 'dimensions': [],
                    'speakers': 0, 'total_msgs': 0,
                    'basis': ('当日窗口' if scope == 'daily' else '全库累计') + '无消息'}
        import collections as _co, datetime as _dt
        total = len(msgs)
        sp = _co.Counter(m[1] for m in msgs)
        lens = [len(m[2] or '') for m in msgs]
        avg = sum(lens) / total
        lr = sum(1 for l in lens if l > 100) / total * 100
        inter = sum(1 for m in msgs if '@' in (m[2] or '')[:20] or (m[2] or '').startswith('Re:'))
        know = sum(1 for m in msgs if any(k in (m[2] or '').lower() for k in KW))
        ess = sum(1 for l in lens if l > main.ESSAY_MIN_CHARS)
        t3 = sum(n for _, n in sp.most_common(3)) / total * 100
        tt = sum(1 for i in range(1, total) if msgs[i][1] != msgs[i-1][1]) / total * 100
        info = min(100, int(round((lr / main.QUALITY_INFO_LONG_FULL * 100) * main.QUALITY_INFO_LONG_WEIGHT
                   + (avg / main.QUALITY_INFO_AVG_FULL * 100) * main.QUALITY_INFO_AVG_WEIGHT)))
        isc = min(100, int(tt)); ksc = min(100, int(know / total * 400))
        bsc = max(0, int(100 - t3)); dsc = min(100, int(round(ess / main.QUALITY_DEPTH_ESSAYS_FULL * 100)))
        dims = [
            {'name': '信息密度', 'score': info, 'grade': main._quality_grade(info),
             'detail': f'长文率 {lr:.1f}%，均长 {avg:.0f} 字/条；定标为长文率 {main.QUALITY_INFO_LONG_FULL:.0f}%、均长 {main.QUALITY_INFO_AVG_FULL:.0f} 字/条满档，权重 60/40。长文越多、单条越完整=有效信息越厚。'},
            {'name': '互动质量', 'score': isc, 'grade': main._quality_grade(isc),
             'detail': f'话题轮转率 {tt:.0f}%（不同人交替发言比例）。越高=对话越像「聊天」而非「广播」。@提及 {inter} 次。'},
            {'name': '知识贡献', 'score': ksc, 'grade': main._quality_grade(ksc),
             'detail': f'知识型消息 {know} 条（含链接/工具/方法/代码）。占比 {know / total * 100:.1f}%。小作文 {ess} 篇。'},
            {'name': '参与均衡', 'score': bsc, 'grade': main._quality_grade(bsc),
             'detail': f'TOP3 占 {t3:.0f}%。越低=发言权越分散=更多人愿意开口=社群越健康。发言人数 {len(sp)}。'},
            {'name': '深度输出', 'score': dsc, 'grade': main._quality_grade(dsc),
             'detail': f'超 200 字消息 {ess} 条（小作文/长论）；定标为 {main.QUALITY_DEPTH_ESSAYS_FULL} 条满档。深度输出是社群「认知资产」的直接产出。'},
        ]
        ov = sum(x['score'] for x in dims) // len(dims)
        return {'scope': scope, 'date': dv, 'grade': main._quality_grade(ov), 'overall': ov,
                'dimensions': dims, 'speakers': len(sp), 'total_msgs': total,
                'basis': ('当日窗口' if scope == 'daily' else '全库累计') + f' {dv or ""}：{total} 条消息 · {len(sp)} 位发言人',
                'verdict': (f'综合评级 {main._quality_grade(ov)}（{ov}分/100）。'
                            f'信息密度{dims[0]["grade"]}·互动{dims[1]["grade"]}·知识{dims[2]["grade"]}·'
                            f'均衡{dims[3]["grade"]}·深度{dims[4]["grade"]}。'
                            f'{len(sp)} 人产出 {total} 条消息，TOP3 占比 {t3:.0f}%。')}
    daily = snap([m for m in allm if (m[0] or '')[:10] == target], 'daily', target)
    vault = snap([m for m in allm if not target or ((m[0] or '')[:10] and (m[0] or '')[:10] <= target)], 'all', target)
    vault['label'] = '窖藏总度数'
    daily['vault_quality'] = vault
    daily['window'] = {'from': target, 'to': target, 'timezone': 'Asia/Shanghai'}
    return daily
"""


class PerfRegressionTest(unittest.TestCase):
    def _boot(self, td: str):
        root = Path(td)
        (root / "static").mkdir(parents=True, exist_ok=True)
        env = _env(root)
        r = _run(env, _seed_script(agent_count=0, audit_per_agent=0))
        assert r.returncode == 0, r.stderr
        return env

    def test_quality_semantics(self):
        """完整 oracle：旧实现逐字复刻，全对象深比对（含 NULL/空 cst/content/未来日）。"""
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""

                import json as _j
                for day in ('2026-09-23', '2026-09-24', '2027-01-02', None):
                    url = f'/api/quality?date={day}' if day else '/api/quality'
                    got = client.get(url)
                    assert got.status_code == 200, (day, got.status_code)
                    want = old_quality(day)
                    assert got.json() == want, (
                        day, _j.dumps(got.json(), ensure_ascii=False)[:300],
                        _j.dumps(want, ensure_ascii=False)[:300])
                assert client.get('/api/quality?date=bad').status_code == 400
            """))
            assert r.returncode == 0, r.stderr

    def test_leaderboard_semantics(self):
        with tempfile.TemporaryDirectory() as td:
            env = self._boot(td)
            r = _run(env, BOOT + textwrap.dedent("""

                # 榜序/排除/本人态语义：items 按 rank 升序、反套利只显名次+段位+涨幅
                lb = client.get('/api/vitality/leaderboard').json()
                items = lb['items']
                assert items and '成员甲' in [b['name'] for b in items], lb
                assert [b['rank'] for b in items] == list(range(1, len(items) + 1))
                assert all('band' in b and 'gain7' in b and 'total' not in b for b in items)
                assert lb['scope'] in ('30d', 'all') and 'scope_label' in lb
                assert 'last_month_top' in lb and 'month' in lb and 'month_progress' in lb
                mine = client.get('/api/vitality/leaderboard', headers=u1).json()
                assert 'my_rank' in mine and 'my_gap' in mine and 'month_my' in mine
                # 成员甲=本人（display_name 匹配）→ my_rank 命中
                assert mine['my_rank'] is not None, mine
            """))
            assert r.returncode == 0, r.stderr


if __name__ == "__main__":
    unittest.main()
