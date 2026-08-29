"""治理产物正文的自动标注：黑话词条 <dfn data-term>、人名 <a data-person>。供 extract_flagship.py 与 hermes_to_ledger.py 共用。"""
import re, json, os

EMOJI = re.compile(r'[\U0001F300-\U0001FAFF☀-➿]')

def term_key(t):
    t = EMOJI.sub('', t).strip()
    return t.split('→')[0].split(' ')[0].strip()

def _replace_text_nodes(html, fn):
    parts = re.split(r'(<[^>]+>)', html)
    depth_skip = 0; out = []
    for part in parts:
        if part.startswith('<'):
            if re.match(r'<(dfn|a)\b', part): depth_skip += 1
            elif re.match(r'</(dfn|a)>', part): depth_skip = max(0, depth_skip - 1)
            out.append(part); continue
        out.append(part if depth_skip else fn(part))
    return ''.join(out)

def mark_terms(html, glossary):
    if not html: return html
    terms = [(term_key(g['term']), g['term']) for g in glossary]
    terms = [(k, f) for k, f in terms if len(k) >= 2]
    used = set()
    def fn(text):
        for k, full in terms:
            if k in used or k not in text: continue
            text = text.replace(k, f'<dfn data-term="{full}">{k}</dfn>', 1); used.add(k)
        return text
    return _replace_text_nodes(html, fn)

def load_people(path):
    try: return json.load(open(path, encoding='utf-8'))
    except Exception: return []

def mark_people(html, people, max_per_field=None):
    """把人名/别名包成 <a data-person="规范名">别名</a>。每个人在一段里只标第一次。"""
    if not html or not people: return html
    pairs = []
    for p in people:
        for a in p.get('aliases', []):
            if len(a) >= 2: pairs.append((a, p['name']))
    pairs.sort(key=lambda x: -len(x[0]))   # 长别名优先
    done = set()
    def fn(text):
        for alias, name in pairs:
            if name in done or alias not in text: continue
            # 中文名后面常直接接动词（「孙务远拉起」），所以中文别名不加 CJK 边界；
            # 两字通名（老李/大魏/队长/超儿…）只要求前面不是中文，避免「大老李」类误伤；拉丁别名要求词边界
            if re.fullmatch(r'[一-龥]+', alias):
                pat = re.compile((r'(?<![一-龥])' if len(alias) <= 2 else '') + re.escape(alias))
            else:
                pat = re.compile(r'(?<![A-Za-z0-9])' + re.escape(alias) + r'(?![A-Za-z0-9])')
            new, n = pat.subn(f'<a data-person="{name}">{alias}</a>', text, count=1)
            if n: text = new; done.add(name)
        # 单字「张」：只在独立出现时（前非中文、后接助词/标点/空格/结尾）
        if '张' not in done and any(p['name'] == '张' for p in people):
            new, n = re.subn(r'(?<![一-龥])张(?=[的给说：:，。、；（）「」 ]|$)', '<a data-person="张">张</a>', text, count=1)
            if n: text = new; done.add('张')
        return text
    return _replace_text_nodes(html, fn)
