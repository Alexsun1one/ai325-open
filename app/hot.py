# -*- coding: utf-8 -*-
"""AI Hot 信息聚合 + 邮件订阅"""
import json, os, re, sqlite3, datetime, urllib.request, urllib.parse, ssl, hashlib
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

DATA_DIR = Path(os.environ.get('XF_DATA_DIR', '/data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = DATA_DIR / 'xf.db'
CST = datetime.timezone(datetime.timedelta(hours=8))

router = APIRouter()

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_hot_tables():
    c = db()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS ai_hot(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source TEXT, title TEXT, url TEXT, summary TEXT,
      score REAL DEFAULT 0, tags TEXT, published TEXT,
      fetched_at TEXT, UNIQUE(url)
    );
    CREATE TABLE IF NOT EXISTS subscribers(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE NOT NULL,
      name TEXT DEFAULT '',
      active INT DEFAULT 1,
      subscribed_at TEXT,
      unsubscribed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS email_log(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      subscriber_id INT, subject TEXT, sent_at TEXT, status TEXT
    );
    ''')
    c.commit(); c.close()

# ── AI Hot 抓取 ──
def fetch_url(url, timeout=8):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.read().decode('utf-8', 'replace')
    except Exception:
        return ''

def fetch_hn():
    """Hacker News AI 相关热帖"""
    try:
        raw = fetch_url('https://hacker-news.firebaseio.com/v0/topstories.json')
        ids = json.loads(raw)[:30]
        items = []
        for id_ in ids:
            try:
                d = json.loads(fetch_url(f'https://hacker-news.firebaseio.com/v0/item/{id_}.json', 5))
                if d and d.get('title'):
                    title = d['title']
                    if any(k in title.lower() for k in ['ai', 'llm', 'gpt', 'claude', 'openai', 'agent', 'anthropic', 'model', 'neural', 'ml ', 'machine learning', 'chatbot', 'copilot', 'gemini', 'deepseek']):
                        items.append({'source': 'HackerNews', 'title': title,
                                     'url': d.get('url', f'https://news.ycombinator.com/item?id={id_}'),
                                     'summary': f"HN 热帖 · {d.get('score', 0)} 分 · {d.get('descendants', 0)} 评论",
                                     'score': min(100, d.get('score', 0) / 5),
                                     'tags': 'hn,tech'})
            except: continue
        return items[:15]
    except: return []

def fetch_github_trending():
    """GitHub Trending AI/LLM"""
    html = fetch_url('https://github.com/trending?since=daily')
    items = []
    for m in re.finditer(r'<h2 class="h3.*?href="/([^"]+)".*?</h2>.*?(?:<p[^>]*>([^<]+)</p>)?', html, re.S):
        repo = m.group(1).strip()
        desc = (m.group(2) or '').strip()[:120]
        if any(k in (repo + desc).lower() for k in ['ai', 'llm', 'gpt', 'agent', 'chat', 'model', 'neural', 'rag', 'vector', 'embedding']):
            items.append({'source': 'GitHub', 'title': repo,
                         'url': f'https://github.com/{repo}',
                         'summary': desc or 'Trending AI repo',
                         'score': 70, 'tags': 'github,code'})
    return items[:10]

def fetch_arxiv():
    """arxiv AI 最新论文"""
    try:
        raw = fetch_url('http://export.arxiv.org/api/query?search_query=cat:cs.AI+OR+cat:cs.CL+OR+cat:cs.LG&sortBy=submittedDate&sortOrder=descending&max_results=10')
        items = []
        for m in re.finditer(r'<title>([^<]+)</title>\s*<summary>([^<]+)</summary>\s*<id>([^<]+)</id>', raw):
            title = m.group(1).strip().replace('\n', ' ')
            summary = m.group(2).strip().replace('\n', ' ')[:150]
            url = m.group(3).strip()
            if not title.startswith('Recent'):  # 跳过 header
                items.append({'source': 'arXiv', 'title': title, 'url': url,
                             'summary': summary, 'score': 50, 'tags': 'paper,research'})
        return items[:10]
    except: return []

def fetch_rss(feed_url, source_name):
    """通用 RSS 解析"""
    raw = fetch_url(feed_url)
    items = []
    for m in re.finditer(r'<title>(?:<!\[CDATA\[)?([^<\]]+)(?:\]\]>)?</title>.*?<link>([^<]+)</link>', raw, re.S):
        items.append({'source': source_name, 'title': m.group(1).strip(),
                     'url': m.group(2).strip(), 'summary': '', 'score': 40, 'tags': source_name.lower()})
    return items[:8]

def refresh_hot():
    """聚合所有源"""
    all_items = []
    all_items += fetch_hn()
    all_items += fetch_github_trending()
    all_items += fetch_arxiv()
    # RSS 源
    for url, name in [
        ('https://news.ycombinator.com/rss', 'HackerNews'),
        ('https://www.jiqizhixin.com/rss', '机器之心'),
        ('https://rsshub.app/36kr/motif/452080', '36氪AI'),
    ]:
        all_items += fetch_rss(url, name)
    c = db()
    now = datetime.datetime.now(CST).isoformat()
    for item in all_items:
        try:
            c.execute('''INSERT OR IGNORE INTO ai_hot(source,title,url,summary,score,tags,fetched_at)
                        VALUES(?,?,?,?,?,?,?)''',
                      (item['source'], item['title'], item['url'], item.get('summary', ''),
                       item.get('score', 0), item.get('tags', ''), now))
        except: pass
    c.commit()
    count = c.execute('SELECT COUNT(*) FROM ai_hot WHERE fetched_at > ?', (now[:10],)).fetchone()[0]
    c.close()
    return count

# ── API ──
@router.get('/api/hot', deprecated=True)
def get_hot(limit: int = 30):
    c = db()
    rows = c.execute('''SELECT source,title,url,summary,score,tags,fetched_at
                        FROM ai_hot ORDER BY score DESC, fetched_at DESC LIMIT ?''', (limit,)).fetchall()
    last = c.execute('SELECT MAX(fetched_at) FROM ai_hot').fetchone()[0]
    c.close()
    return {'items': [dict(r) for r in rows], 'last_fetch': last}

@router.post('/api/hot/refresh', deprecated=True)
def hot_refresh():
    n = refresh_hot()
    return {'fetched': n}

# ── 邮件订阅 ──
class SubscribeReq(BaseModel):
    email: str
    name: str = ''

@router.post('/api/subscribe', deprecated=True)
def subscribe(req: SubscribeReq):
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', req.email):
        raise HTTPException(400, '邮箱格式不对')
    c = db()
    now = datetime.datetime.now(CST).isoformat()
    try:
        c.execute('INSERT INTO subscribers(email,name,subscribed_at) VALUES(?,?,?)',
                  (req.email, req.name, now))
        c.commit()
    except sqlite3.IntegrityError:
        pass  # 已订阅
    finally:
        c.close()
    return {'ok': True, 'message': '订阅成功！每天早上 8:00 收到群聊精华蒸馏日报。'}

@router.get('/api/subscribe/status', deprecated=True)
def sub_status():
    c = db()
    count = c.execute('SELECT COUNT(*) FROM subscribers WHERE active=1').fetchone()[0]
    c.close()
    return {'subscribers': count}

@router.post('/api/unsubscribe', deprecated=True)
def unsubscribe(email: str):
    c = db()
    c.execute('UPDATE subscribers SET active=0, unsubscribed_at=? WHERE email=?',
              (datetime.datetime.now(CST).isoformat(), email))
    c.commit(); c.close()
    return {'ok': True}

init_hot_tables()
