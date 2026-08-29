#!/usr/bin/env python3
"""把 ZCode 旗舰日报 HTML（_FLAGSHIP.html）抽成网站用的治理产物 JSON。
用法: python3 scripts/extract_flagship.py <flagship.html> <avatars.json> <out_dir>
产出: <out_dir>/ledgers/2026-08-23.json  +  <out_dir>/members/profiles.json（登录墙后）"""
import sys, re, json, html, os
from bs4 import BeautifulSoup, NavigableString, Tag

src, avpath, out = sys.argv[1], sys.argv[2], sys.argv[3]
raw = open(src, encoding='utf-8').read()
soup = BeautifulSoup(raw, 'lxml')

ALLOWED = {'b', 'br', 'i', 'em', 'strong'}
def rich(el):
    """保留 b/br，去掉 style/span，返回安全的轻量 HTML 字符串"""
    if el is None: return ''
    parts = []
    for c in el.children:
        if isinstance(c, NavigableString):
            parts.append(html.escape(str(c), quote=False))
        elif isinstance(c, Tag):
            if c.name in ALLOWED:
                inner = rich(c)
                parts.append(f'<{c.name}>{inner}</{c.name}>' if c.name != 'br' else '<br>')
            elif c.name == 'span' and 'unsaid' in (c.get('class') or []):
                parts.append(f'<u>{rich(c)}</u>')   # 「没说破的」延伸段，用 <u> 标记
            elif c.name == 'small':
                continue
            else:
                parts.append(rich(c))
    return ''.join(parts).strip()

def text(el): return el.get_text(' ', strip=True) if el else ''

def grab_js(name):
    m = re.search(r'window\.' + name + r'\s*=\s*(.*?);\s*\n', raw, re.S)
    return json.loads(m.group(1)) if m else None

hours = grab_js('__HOURS') or {}
quotes = grab_js('__QUOTES') or []
members = grab_js('__MEMBERS') or []

# —— 时间线 ——
events = []
for ev in soup.select('#timeline .ev'):
    events.append({'t': text(ev.select_one('.t')), 'h': rich(ev.select_one('.h')).replace('建群日档案','').strip(), 'd': rich(ev.select_one('.d')),
                   'src': 'digest' if 'src-digest' in ev.get('class', []) else 'db'})

# —— 主题幕 ——
themes = []
for act in soup.select('#acts .act'):
    voices = []
    for v in act.select('.voices .v'):
        who = text(v.b).rstrip('：:')
        v.b.extract()
        voices.append({'a': who, 'v': rich(v)})
    themes.append({'h': text(act.h3), 'when': text(act.select_one('.when')), 'body': rich(act.find('p', recursive=False)),
                   'deep': rich(act.select_one('.deep p')), 'voices': voices})

# —— 语气鉴定 ——
tone_notes = []
for card in soup.select('#tone .card'):
    title = text(card.select_one('.nm'))
    cls = 'j' if '段子' in title else 's' if '认真' in title else 'h'
    tone_notes.append({'h': title, 'cls': cls, 'body': rich(card.find('p'))})

# —— 深潜六层 ——
insights = []
for dv in soup.select('#insight .dv'):
    insights.append({'h': text(dv.h3).replace(text(dv.h3.small), '').strip() if dv.h3.small else text(dv.h3),
                     'en': text(dv.h3.small) if dv.h3.small else '', 'body': rich(dv.find('p'))})

# —— 黑话 × 弹药 ——
glossary, arsenal = [], []
gl = soup.select_one('#glossary')
grids = gl.select('.grid')
for c in grids[0].select('.card'):
    glossary.append({'term': text(c.select_one('.nm')), 'def': rich(c.find('p'))})
for c in grids[1].select('.card'):
    arsenal.append({'h': text(c.select_one('.nm')), 'body': rich(c.find('p'))})

# —— 悬案 × 对撞 ——
docket, clashes = [], []
dk = soup.select_one('#docket')
for ev in dk.select('.tl .ev'):
    docket.append({'kind': text(ev.select_one('.t')), 'h': text(ev.select_one('.h')), 'd': rich(ev.select_one('.d')), 'status': 'open'})
for dv in dk.select('.dive .dv'):
    ps = dv.find_all('p')
    clashes.append({'h': text(dv.h3).replace(text(dv.h3.small), '').strip(), 'en': text(dv.h3.small), 'sides': rich(ps[0]), 'verdict': rich(ps[1]) if len(ps) > 1 else ''})

# —— 成长 + 行动 ——
gr = soup.select_one('#growth')
takeaways = [rich(li) for li in gr.select('ol li')]
todo = []
for td in gr.select('.todo .td'):
    todo.append({'phase': text(td.h4), 'items': [text(l.span) for l in td.select('label')]})


# —— 自动标注：黑话词条 + 人名（共享模块 scripts/markup.py）——
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from markup import mark_terms, mark_people, load_people
people = load_people(os.path.join(os.path.dirname(out), 'public', 'people.json'))
def mk(h): return mark_people(mark_terms(h, glossary), people)
for t in themes:
    t['body'] = mk(t['body']); t['deep'] = mk(t['deep'])
    for v in t['voices']: v['v'] = mark_terms(v['v'], glossary)
for it in insights: it['body'] = mk(it['body'])
for e in events: e['d'] = mk(e['d']); e['h'] = mark_people(e['h'], people)
for c in clashes: c['verdict'] = mk(c['verdict']); c['sides'] = mark_people(c['sides'], people)
for n in tone_notes: n['body'] = mk(n['body'])
# —— 成员高光（治理后的画像，去头像，头像走 members/profiles.json）——
members_focus = [{'name': m['name'], 'role': m.get('role',''), 'msgs': m.get('msgs',0), 'tone': m.get('tone','s'), 'quote': m.get('quote',''), 'tags': m.get('tags',[])} for m in members[:12]]

# 心电图说明
pulsecap = mk(rich(soup.select_one('#pulse .pulsecap')))
pulsenote = rich(soup.select_one('#pulse .note'))
lead = text(soup.select_one('.hero p.lead'))
footer = [
  '<b>这期怎么来的</b>：建群日（08-21）那部分来自星星之火整理的《群聊精华整理》（1,068 条、15 章）；08-22 15:36 起是小号设备上的完整记录（1,407 条，压缩消息都已解开）。64 位成员的头像都是真人。时间一律北京时间。记录截止 2026-08-23 18:04。',
  '<b>边界</b>：这本台账只供群内与同好学习交流。引文都是群聊原话；「没说破的」那部分是整理者的延伸，用手写体标出，不是发言人原话。个别转发、引用的归属可能有歧义（比如「像水一样」那句，两份记录里署名不同，这里按精华整理的署名并在此备注）。本期由 ZCode（GLM）蒸馏 · 2026-08-23。',
]

content = {
  'date': '2026-08-23',
  'issue': 1,
  'title': '创刊号 · 全量基线',
  'coverage': {'from': '2026-08-21', 'to': '2026-08-23', 'cutoff': '2026-08-23 18:04', 'note': '这一期覆盖三天：建群日（08-21）的内容来自星星之火整理的《群聊精华整理》，08-22 下午起是完整记录。小号每隔几小时会掉一次线，掉线那段的消息没补上，所以有几处空档——创刊号先把底打下。'},
  'complete': False,
  'lead': lead,
  'stats': {'msgs': 2486, 'speakers': 45, 'members': 64, 'essays': 29, 'essays_open': 1, 'quotes': len(quotes), 'themes': len(themes), 'decoded': 513},
  'hours': hours,
  'pulse': {'caption': pulsecap, 'note': pulsenote},
  'events': events,
  'themes': themes,
  'tone_notes': tone_notes,
  'insights': insights,
  'quotes': quotes,
  'glossary': glossary,
  'arsenal': arsenal,
  'docket': docket,
  'clashes': clashes,
  'growth': {'takeaways': takeaways, 'todo': todo},
  'members_focus': members_focus,
  'newcomers': [
      {'name': 'Mr. Tang', 'note': 'Garden Tap Factory · 传统制造业三个月 AI 路径', 't': '08-23 15:21', 'by': 'Sun 拉入', 'first_words': '「GPT 帮我分析一个客户，对方真的回复了我」'},
      {'name': 'Lee', 'note': '老李拉入 · 已被点名交作业', 't': '08-23', 'by': '老李拉入', 'first_words': ''}],
  'quality': {'overall': 76, 'grade': 'B', 'dimensions': [
      {'name': '信息密度', 'score': 100, 'grade': 'A', 'detail': '长文率 26.2%，均长 257 字/条。长文越多=有效信息占比越高，表情包刷屏拉低此分。'},
      {'name': '互动质量', 'score': 75, 'grade': 'B', 'detail': '话题轮转率 75%（不同人交替发言比例）。越高=对话越像「聊天」而非「广播」。@提及 78 次。'},
      {'name': '知识贡献', 'score': 58, 'grade': 'C', 'detail': '知识型消息 196 条（含链接/工具/方法/代码），占比 14.5%。小作文 24 篇。'},
      {'name': '参与均衡', 'score': 48, 'grade': 'C', 'detail': 'TOP3 占 51%。越低=发言权越分散=更多人愿意开口。发言人数 56。'},
      {'name': '深度输出', 'score': 100, 'grade': 'A', 'detail': '超 200 字消息 24 条（小作文/长论）。深度输出是社群「认知资产」的直接产出。'}],
      'basis': '基于原始库 1349 条消息 · 56 位发言人 · 评判于 2026-08-23'},
  'threads': [
      {'id': 'brain-swap', 'title': '换脑工程', 'theme': '第一幕 · 换脑工程', 'status': 'ongoing', 'first_issue': 1, 'prev_issue': None},
      {'id': 'knowledge-base', 'title': '知识库远征', 'theme': '第二幕 · 知识库远征', 'status': 'ongoing', 'first_issue': 1, 'prev_issue': None},
      {'id': 'sales-structuring', 'title': '销售可结构化吗', 'theme': '第三幕 · 销售结构化之夜', 'status': 'ongoing', 'first_issue': 1, 'prev_issue': None},
      {'id': 'ai-economics', 'title': 'AI 经济学', 'theme': '第四幕 · AI 经济学', 'status': 'ongoing', 'first_issue': 1, 'prev_issue': None},
      {'id': 'essays', 'title': '小作文', 'theme': '第五幕 · 小作文马拉松', 'status': 'ongoing', 'first_issue': 1, 'prev_issue': None},
      {'id': 'weflow', 'title': 'WeFlow 救援', 'theme': '第六幕 · WeFlow 之夜', 'status': 'ongoing', 'first_issue': 1, 'prev_issue': None}],
  'credits': {'distilled_by': 'ZCode × GLM', 'reviewed_by': '待 Sun 复核', 'generated_at': '2026-08-23'},
  'footer': footer,
}
json.dump(content, open(f'{out}/ledgers/2026-08-23.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# 画像（登录墙后用）
av = json.load(open(avpath)).get('avatars', {})
profiles = []
for m in members:
    profiles.append({k: m.get(k) for k in ['name','role','msgs','ct','tags','tone','quote','deep','filter','thin']} | {'avatar': av.get(m.get('avkey',''), '')})
json.dump({'generated': '2026-08-23', 'count': len(profiles), 'profiles': profiles}, open(f'{out}/members/profiles.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('ledger: events', len(events), 'themes', len(themes), 'tone', len(tone_notes), 'insights', len(insights), 'quotes', len(quotes), 'glossary', len(glossary), 'docket', len(docket), 'clashes', len(clashes), 'takeaways', len(takeaways), 'todo', sum(len(t['items']) for t in todo))
print('profiles:', len(profiles), 'with avatar:', sum(1 for p in profiles if p['avatar']))
