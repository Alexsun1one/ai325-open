#!/usr/bin/env python3
"""profiles.json → site/public/people.json（公开名片：名字/别名/角色/条数/语气/一句话/头像路径）+ site/public/avatars/<slug>.webp（96px）。
用法: python3 scripts/build_people.py site/content/members/profiles.json site/public"""
import sys, json, base64, re, io, os, hashlib
from PIL import Image
src, pub = sys.argv[1], sys.argv[2]
d = json.load(open(src, encoding='utf-8'))
MANUAL = {
 '高博文 owen': ['高博文'], '徐志剑（灯哥）': ['徐志剑', '灯哥'], '老李（大麦）': ['老李', '大麦'], 'Mr. Tang（老唐）': ['Mr. Tang', '老唐'],
 '阿彬SEO-GEO': ['阿彬'], '中高职教育建设': ['中高职'], '队长 wongkeng': ['队长'], '聂燕青': ['聂燕青', 'Leo 聂'], '闻 Wen': ['闻 Wen'],
 'Anna': ['Anna', '广州-Anna'], 'Sean.Wang': ['Sean.Wang', 'Sean'], '孙务远': ['孙务远'], '星星之火': ['星星之火'], '二宝·老板AI社群': ['二宝'],
}
def slug(name):
    s = re.sub(r'[^A-Za-z0-9]+', '-', name).strip('-').lower()
    return s or 'p' + hashlib.md5(name.encode()).hexdigest()[:6]
os.makedirs(f'{pub}/avatars', exist_ok=True)
people = []
for p in d['profiles']:
    name = p['name']
    aliases = MANUAL.get(name) or []
    base = re.sub(r'[（(].*?[）)]', '', name).strip()
    for cand in {name, base, name.split(' ')[0]}:
        if cand and cand not in aliases and len(cand) >= 2 or cand == '张': aliases.append(cand)
    sl = slug(name); av = None
    if p.get('avatar', '').startswith('data:image'):
        b = base64.b64decode(p['avatar'].split(',', 1)[1])
        try:
            im = Image.open(io.BytesIO(b)).convert('RGB'); im.thumbnail((96, 96)); im.save(f'{pub}/avatars/{sl}.webp', 'WEBP', quality=82); av = f'/avatars/{sl}.webp'
        except Exception as e: print('avatar fail', name, e)
    people.append({'name': name, 'slug': sl, 'aliases': aliases, 'role': p.get('role', ''), 'msgs': p.get('msgs', 0), 'tone': p.get('tone', 's'), 'quote': p.get('quote', ''), 'tags': p.get('tags', [])[:4], 'avatar': av})
json.dump(people, open(f'{pub}/people.json', 'w', encoding='utf-8'), ensure_ascii=False)
print('people', len(people), 'avatars', sum(1 for x in people if x['avatar']), '→', f'{pub}/people.json')
