#!/usr/bin/env python3
"""Hermes content.json（_hermes_spec.md §4/§4b）→ 网站 Ledger JSON（site/content/ledgers/<date>.json）
用法: python3 scripts/hermes_to_ledger.py <materials/YYYY-MM-DD/> <site/content/ledgers/> [--quality-json <path>] [--docket-evidence <path>]
- 线索承接：用上一期 ledger 的 threads 做匹配（theme.thread_id 优先；否则标题关键词重合）
- 悬案顺延：上一期 docket 里 status=open 且本期未声明 closed 的，自动带入并标 carried_from
- 行动顺延：上一期 todo 原样带入 growth.carried（前端可选显示）
- 悬案事实：可用 scripts/ops/docket-verify.sh 生成的 evidence JSON 对唯一事实匹配项自动闭案；不传参数则保持旧行为
- 质量五维：--quality-json 给 /api/quality 的输出；缺省写 null，前端显示「待评判」
"""
import json, os, sys, glob, re, datetime, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from markup import mark_terms, mark_people, load_people

mat, out_dir = sys.argv[1], sys.argv[2]


def _optional_arg(name):
    if name not in sys.argv:
        return None
    index = sys.argv.index(name)
    if index + 1 >= len(sys.argv) or sys.argv[index + 1].startswith('--'):
        raise SystemExit(f'{name} 缺少路径参数')
    return sys.argv[index + 1]


qpath = _optional_arg('--quality-json')
evidence_path = _optional_arg('--docket-evidence')
c = json.load(open(os.path.join(mat, 'content.json'), encoding='utf-8'))
stats = json.load(open(os.path.join(mat, 'stats.json'), encoding='utf-8')) if os.path.exists(os.path.join(mat, 'stats.json')) else {}
date = c['date']

prev_files = sorted(f for f in glob.glob(os.path.join(out_dir, '*.json')) if os.path.basename(f) < f'{date}.json')
prev = json.load(open(prev_files[-1], encoding='utf-8')) if prev_files else None
issue = (prev['issue'] + 1) if prev else 1

def slug(s, fallback): return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-') or fallback
def grams(s):
    s = re.sub(r'^第.幕\s*·\s*', '', s); s = re.sub(r'[^一-龥A-Za-z0-9]', '', s)
    return {s[i:i+2] for i in range(len(s) - 1)}


def _optional_int(mapping, key):
    """content.json 显式给值时允许覆盖；缺省/NULL 才走数据库真值。"""
    if key not in mapping or mapping.get(key) is None or isinstance(mapping.get(key), bool):
        return None
    try:
        value = int(mapping[key])
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _load_docket_evidence(path):
    if not path:
        return {}
    try:
        payload = json.load(open(path, encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f'无法读取悬案事实证据 {path}: {exc}')
    if not isinstance(payload, dict) or not isinstance(payload.get('closures'), list):
        raise SystemExit(f'悬案事实证据格式错误（需要 closures 数组）: {path}')
    if payload.get('date') not in (None, date):
        raise SystemExit(f'悬案事实证据日期不匹配: expected={date} got={payload.get("date")!r}')
    if prev and payload.get('previous_date') not in (None, prev.get('date')):
        raise SystemExit(
            f'悬案事实证据上一期不匹配: expected={prev.get("date")} '
            f'got={payload.get("previous_date")!r}'
        )
    result = {}
    for proof in payload['closures']:
        if not isinstance(proof, dict) or proof.get('status') != 'closed' or not proof.get('h'):
            continue
        evidence = proof.get('evidence')
        if not isinstance(evidence, dict) or not evidence.get('matches'):
            continue
        key = str(proof['h'])
        if key in result:
            raise SystemExit(f'悬案事实证据重复 heading: {key}')
        result[key] = proof
    return result


_RAW_MEMBER = re.compile(r'^(?:wxid_[A-Za-z0-9_-]+|QQ\d{5,}|q\d{6,}|gh_[A-Za-z0-9_-]+)$', re.I)
_DISPLAY_SUFFIX = re.compile(r'[②③④⑤⑥⑦⑧⑨⑩]$|\(\d+\)$')


def _member_text(value):
    return ''.join(ch for ch in str(value or '') if ord(ch) not in range(0, 32) and ord(ch) != 127).strip()


def _member_base(value):
    return _DISPLAY_SUFFIX.sub('', _member_text(value))


def _identity_rows():
    db_path = os.environ.get('XF_DB') or os.path.join(os.environ.get('XF_DATA_DIR', '/opt/xfsite/data'), 'xf.db')
    if not os.path.isfile(db_path):
        return [], None
    conn = None
    try:
        conn = sqlite3.connect(f'file:{os.path.abspath(db_path)}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT username,display,name_source,called_names FROM members').fetchall()
        return [dict(row) for row in rows], db_path
    except (OSError, sqlite3.Error):
        return [], db_path
    finally:
        if conn is not None:
            conn.close()


def _quote_author(author, quote_text, day):
    """Prefer called-name display; append a wxid tail only on a real collision."""
    author = _member_text(author)
    rows, db_path = _identity_rows()
    if not rows:
        return author
    by_username = {str(row.get('username') or ''): row for row in rows}
    candidates = [row for row in rows if _member_base(row.get('display')) == _member_base(author)]
    if author in by_username:
        candidates = [by_username[author]]
    if _RAW_MEMBER.fullmatch(author):
        row = by_username.get(author)
        if row and _member_text(row.get('display')) and not _RAW_MEMBER.fullmatch(_member_text(row.get('display'))):
            author = _member_text(row['display'])
            candidates = [row]
    if len(candidates) <= 1:
        return author
    # Resolve the particular quote to a sender before adding a suffix.  If the
    # evidence is not unique, keep the ambiguity visible instead of guessing.
    matched = []
    if db_path and quote_text:
        conn = None
        try:
            conn = sqlite3.connect(f'file:{os.path.abspath(db_path)}?mode=ro', uri=True)
            rows2 = conn.execute(
                'SELECT DISTINCT sender FROM messages WHERE substr(COALESCE(cst,\'\'),1,10)=? AND content LIKE ?',
                (day, f'%{quote_text[:120]}%'),
            ).fetchall()
            matched = [by_username[str(row[0])] for row in rows2 if str(row[0]) in by_username and by_username[str(row[0])] in candidates]
        except (OSError, sqlite3.Error):
            matched = []
        finally:
            if conn is not None:
                conn.close()
    chosen = matched[0] if len(matched) == 1 else None
    if not chosen:
        return f'{author}·待核'
    username = _member_text(chosen.get('username'))
    tail = re.sub(r'[^A-Za-z0-9]', '', username)[-4:] or '未知'
    return f'{_member_base(author)}·{tail}'


def _essay_db_truth(day):
    """读库中与 rebuild_essays 同一 essays 派生表的日增/累计数及活动挂账数。

    出刊脚本可能在本地 dry-run（无库），因此所有数据库错误都降级为空结果，
    由调用方回退到 content/上一期值；不会阻断日报转换。
    """
    db_path = os.environ.get('XF_DB') or os.path.join(os.environ.get('XF_DATA_DIR', '/opt/xfsite/data'), 'xf.db')
    if not os.path.isfile(db_path):
        return {}
    connection = None
    try:
        connection = sqlite3.connect(f'file:{os.path.abspath(db_path)}?mode=ro', uri=True)
        tables = {
            row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if 'essays' not in tables:
            return {}
        daily = connection.execute(
            "SELECT COUNT(*) FROM essays WHERE substr(COALESCE(cst,''),1,10)=?", (day,)
        ).fetchone()[0]
        cumulative = connection.execute(
            "SELECT COUNT(*) FROM essays WHERE substr(COALESCE(cst,''),1,10)<=?", (day,)
        ).fetchone()[0]
        open_count = 0
        if 'events' in tables:
            event = connection.execute(
                "SELECT id,status FROM events WHERE slug='onboarding-essay'"
            ).fetchone()
            if event and event[1] == 'open':
                if 'essay_activity_items' in tables:
                    open_count = connection.execute(
                        """SELECT COUNT(*) FROM essay_activity_items
                           WHERE event_id=? AND status IN ('open','pending')""",
                        (event[0],),
                    ).fetchone()[0]
                elif 'submissions' in tables:
                    # 旧库尚未有独立挂账表时，只把该活动仍待审核的投稿视为挂账。
                    open_count = connection.execute(
                        """SELECT COUNT(*) FROM submissions
                           WHERE event_id=? AND status IN ('open','pending')""",
                        (event[0],),
                    ).fetchone()[0]
        return {'daily': daily, 'cumulative': cumulative, 'open': open_count}
    except (OSError, sqlite3.Error):
        return {}
    finally:
        if connection is not None:
            connection.close()


def _daily_db_truth(day):
    """Return the same date-window speaker truth used by /api/quality.

    speakers is the daily distinct display identity count. members is the
    cumulative distinct display identity count through that day. A missing
    database/date deliberately falls back to the stamped materials.
    """
    db_path = os.environ.get('XF_DB') or os.path.join(
        os.environ.get('XF_DATA_DIR', '/opt/xfsite/data'), 'xf.db'
    )
    if not os.path.isfile(db_path):
        return {}
    connection = None
    identity = "COALESCE(NULLIF(sender_name,'?'),sender)"
    try:
        connection = sqlite3.connect(f'file:{os.path.abspath(db_path)}?mode=ro', uri=True)
        tables = {
            row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if 'messages' not in tables:
            return {}
        daily = int(
            connection.execute(
                f"""SELECT COUNT(DISTINCT {identity}) FROM messages
                    WHERE substr(COALESCE(cst,''),1,10)=?""",
                (day,),
            ).fetchone()[0]
        )
        if daily <= 0:
            return {}
        cumulative = int(
            connection.execute(
                f"""SELECT COUNT(DISTINCT {identity}) FROM messages
                    WHERE substr(COALESCE(cst,''),1,10)<=?""",
                (day,),
            ).fetchone()[0]
        )
        msgs = int(
            connection.execute(
                "SELECT COUNT(*) FROM messages WHERE substr(COALESCE(cst,''),1,10)=?",
                (day,),
            ).fetchone()[0]
        )
        readable = int(
            connection.execute(
                "SELECT COUNT(*) FROM messages WHERE substr(COALESCE(cst,''),1,10)=? AND content<>''",
                (day,),
            ).fetchone()[0]
        )
        hours = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT substr(COALESCE(cst,''),12,2) AS hh, COUNT(*) FROM messages "
                "WHERE substr(COALESCE(cst,''),1,10)=? GROUP BY hh",
                (day,),
            ).fetchall()
        }
        return {'speakers': daily, 'members': cumulative, 'msgs': msgs, 'readable': readable, 'hours': hours}
    except (OSError, sqlite3.Error):
        return {}
    finally:
        if connection is not None:
            connection.close()


# —— 线索承接 ——
prev_threads = {t['id']: t for t in (prev or {}).get('threads', [])}
threads = []
for t in c.get('themes', []):
    tid = t.get('thread_id')
    if not tid and prev:
        g = grams(t.get('thread_title') or t['h'])
        scored = [(len(g & (grams(x['title']) | grams(x['theme']))), x) for x in prev['threads']]
        best = max(scored, key=lambda p: p[0], default=(0, None))
        if best[0] >= 2: tid = best[1]['id']
    if not tid: tid = slug(t.get('thread_title') or t['h'], f"t{issue:03d}-{len(threads)+1}")
    base = prev_threads.get(tid, {})
    threads.append({'id': tid, 'title': t.get('thread_title') or base.get('title') or re.sub(r'^第.幕\s*·\s*', '', t['h']), 'theme': t['h'],
                    'status': t.get('thread_status', 'ongoing'), 'first_issue': base.get('first_issue', prev['issue'] if tid in prev_threads else issue), 'prev_issue': prev['issue'] if tid in prev_threads else None})

# —— 悬案顺延 ——
closed = {d['h'] for d in c.get('docket', []) if d.get('status') == 'closed'}
docket = [dict(d, status=d.get('status', 'open')) for d in c.get('docket', [])]
for d in (prev or {}).get('docket', []):
    if d['status'] == 'open' and d['h'] not in closed and all(d['h'] != x['h'] for x in docket):
        docket.append(dict(d, status='open', carried_from=d.get('carried_from', prev['issue'])))

# 事实核验在蒸馏前由 ops/docket-verify.sh 生成；这里只消费带唯一证据的闭案结果。
docket_evidence = _load_docket_evidence(evidence_path)
for index, item in enumerate(docket):
    proof = docket_evidence.get(str(item.get('h')))
    if not proof or item.get('status') != 'open' or '承诺未兑' not in str(item.get('kind') or ''):
        continue
    docket[index] = dict(
        item,
        status='closed',
        closed_at=proof.get('closed_at') or date,
        closed_by=proof.get('closed_by') or 'docket-verifier-v1',
        evidence=proof['evidence'],
    )

quality = json.load(open(qpath, encoding='utf-8')) if qpath else None
if quality:
    quality_payload = {
        'overall': quality['overall'],
        'grade': quality['grade'],
        'dimensions': quality['dimensions'],
        'basis': f"基于当日窗口 {date}：{quality.get('total_msgs','?')} 条消息 · {quality.get('speakers','?')} 位发言人",
    }
    if quality.get('scope'):
        quality_payload['scope'] = quality['scope']
    if quality.get('date'):
        quality_payload['date'] = quality['date']
    # 全库累计分不参与本期平均，只作为「窖藏总度数」背景值交给 /quality 页。
    if isinstance(quality.get('vault_quality'), dict):
        quality_payload['vault_quality'] = quality['vault_quality']
    if isinstance(quality.get('window'), dict):
        quality_payload['window'] = quality['window']
    quality = quality_payload

essay_db = _essay_db_truth(date)
previous_stats = (prev or {}).get('stats', {})
content_essay_total = _optional_int(c, 'essays_total')
content_essay_open = _optional_int(c, 'essays_open')
essay_total = content_essay_total
if essay_total is None:
    essay_total = essay_db.get('cumulative', previous_stats.get('essays', 0))
essay_open = content_essay_open
if essay_open is None:
    essay_open = essay_db.get('open', previous_stats.get('essays_open', 0))
essay_daily = essay_db.get('daily', essay_total)
essay_cumulative = essay_db.get('cumulative', essay_total)
daily_db = _daily_db_truth(date)
stats_override = c.get('stats_override') if isinstance(c.get('stats_override'), dict) else {}
speaker_total = daily_db.get('speakers')
if speaker_total is None:
    speaker_total = _optional_int(stats, 'speaker_count')
if speaker_total is None:
    speaker_total = _optional_int(stats_override, 'active')
if speaker_total is None:
    speaker_total = len(stats.get('speakers', [])) if isinstance(stats.get('speakers'), list) else 0
members_total = daily_db.get('members')
if members_total is None:
    members_total = _optional_int(stats, 'members_total')
if members_total is None:
    members_total = _optional_int(c, 'members_total')
if members_total is None:
    members_total = previous_stats.get('members', 0)

ledger = {
  'date': date, 'issue': issue, 'title': c.get('title') or f'第 {issue:03d} 批',
  'coverage': c.get('coverage') or {'from': date, 'to': date, 'cutoff': f'{date} 23:59', 'note': '这一期记的是这一天。小号每隔几小时会掉一次线，掉线那段的消息没补上——曲线上空着的那几格就是。'},
  'complete': c.get('complete', True), 'lead': c.get('lead', ''),
  'stats': {'msgs': daily_db.get('msgs') or stats_override.get('msgs') or stats.get('msgs', 0), 'speakers': speaker_total,
            'members': members_total, 'essays': essay_total,
            'essays_daily': essay_daily, 'essays_cumulative': essay_cumulative, 'essays_open': essay_open,
            'quotes': len(c.get('quotes', [])), 'themes': len(c.get('themes', [])),
            'decoded': daily_db.get('readable') or stats.get('readable', 0)},
  'hours': c.get('hours') or daily_db.get('hours') or stats.get('hours', {}),
  'pulse': c.get('pulse', {'caption': '', 'note': ''}),
  'events': c.get('events', []), 'themes': [{k: v for k, v in t.items() if k not in ('thread_id', 'thread_title', 'thread_status')} for t in c.get('themes', [])],
  'tone_notes': c.get('tone_notes', []), 'insights': c.get('insights', []), 'quotes': c.get('quotes', []),
  'glossary': c.get('glossary', (prev or {}).get('glossary', [])), 'arsenal': c.get('arsenal', []),
  'docket': docket, 'clashes': c.get('clashes', []),
  'growth': {'takeaways': c.get('growth', {}).get('takeaways', []), 'todo': c.get('growth', {}).get('todo', []), 'carried': (prev or {}).get('growth', {}).get('todo', [])},
  'members_focus': c.get('members_focus', []), 'newcomers': c.get('newcomers', []),
  'quality': quality or {'overall': 0, 'grade': '待评', 'dimensions': [], 'basis': '本批质量评判尚未接线'},
  'threads': threads,
  'credits': {'distilled_by': c.get('distilled_by', '一一（Hermes × DeepSeek）'), 'reviewed_by': c.get('reviewed_by', '待复核'), 'generated_at': datetime.date.today().isoformat()},
  'footer': c.get('footer', []),
}
# 署名是展示层；身份判断仍以 sender/wxid 证据为锚。
for quote in ledger['quotes']:
    if isinstance(quote, dict) and quote.get('a'):
        quote['a'] = _quote_author(quote.get('a'), quote.get('t') or quote.get('text') or '', date)
# —— 自动标注黑话与人名 ——
people = load_people(os.path.join(os.path.dirname(out_dir.rstrip('/')), '..', 'public', 'people.json')) or load_people(os.path.join(os.path.dirname(os.path.dirname(out_dir.rstrip('/'))), 'public', 'people.json'))
gl = ledger['glossary']
def mk(h): return mark_people(mark_terms(h or '', gl), people)
for t in ledger['themes']: t['body'] = mk(t.get('body')); t['deep'] = mk(t.get('deep'))
for it in ledger['insights']: it['body'] = mk(it.get('body'))
for e in ledger['events']: e['d'] = mk(e.get('d'))
for c in ledger['clashes']: c['verdict'] = mk(c.get('verdict'))
for n in ledger['tone_notes']: n['body'] = mk(n.get('body'))
os.makedirs(out_dir, exist_ok=True)
json.dump(ledger, open(os.path.join(out_dir, f'{date}.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('ledger →', os.path.join(out_dir, f'{date}.json'), '| issue', issue, '| threads', len(threads), '| docket', len(docket))
