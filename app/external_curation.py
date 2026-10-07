"""Resumable external-news curation. No chat data, shell execution, or business DB writes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.external_sources import clean_text, validate_document

CST = ZoneInfo('Asia/Shanghai')
PROMPTS = Path(__file__).resolve().parents[1] / 'hermes/external/prompts'


def iso(dt):
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def dt(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_policy(p):
    if p.get('schemaVersion') != 1 or not isinstance(p.get('policyVersion'), str):
        raise ValueError('invalid policy')
    ranges = {'lookbackDays': (1, 60), 'maxItemsPerRun': (1, 500), 'maxCallsPerRun': (1, 5000),
              'maxCallsPerDay': (1, 20000), 'maxRuntimeSeconds': (1, 3600),
              'requestTimeoutSeconds': (1, 180), 'maxAttempts': (1, 10),
              'retryAfterMinutes': (1, 1440), 'maxOutputTokens': (128, 8000),
              'hotWindowHours': (1, 168), 'hotHalfLifeHours': (1, 168),
              'trendWindowHours': (1, 48), 'maxClusterCandidates': (1, 30),
              'digestLimit': (1, 100), 'maxScoreDisagreement': (0, 100), 'articleTimeoutSeconds': (1, 60),
              'articleMaxBytes': (1000, 3000000), 'articleMaxChars': (300, 16000)}
    for key, (lo, hi) in ranges.items():
        if type(p.get(key)) is not int or not lo <= p[key] <= hi:
            raise ValueError('invalid policy field: ' + key)
    if not isinstance(p.get('sourcePolicy'), dict) or not p['sourcePolicy']:
        raise ValueError('source policy required')
    for source in p['sourcePolicy'].values():
        if not isinstance(source.get('publisher'), str) or not source['publisher']:
            raise ValueError('publisher required')
        threshold = p['scoreThresholds'].get(source.get('tier'))
        if type(threshold) is not int or not 0 <= threshold <= 100:
            raise ValueError('invalid source tier threshold')


def connect(path):
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    db.executescript('''
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS articles(
      id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, payload TEXT NOT NULL,
      state TEXT NOT NULL, result TEXT, event_id TEXT, relation TEXT,
      attempts INTEGER NOT NULL DEFAULT 0, next_retry TEXT, error TEXT, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS article_bodies(key TEXT PRIMARY KEY, body TEXT, fetched_at TEXT);
    CREATE TABLE IF NOT EXISTS stages(key TEXT PRIMARY KEY, stage TEXT NOT NULL, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS calls(id INTEGER PRIMARY KEY, day TEXT, stage TEXT, status TEXT, tokens INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS editions(day TEXT PRIMARY KEY, fingerprint TEXT, revision INTEGER, payload TEXT);
    CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, status TEXT, counts TEXT);
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS heat(at TEXT, event_id TEXT, value REAL, PRIMARY KEY(at,event_id));
    ''')
    return db


class BudgetExceeded(Exception):
    pass


class ProviderError(Exception):
    pass


class ArticleUnavailable(Exception):
    pass


class Model:
    """Use the existing official DeepSeek provider, never discover/read credentials."""
    def __init__(self, policy):
        self.key = os.environ.get('DEEPSEEK_API_KEY', '')
        self.model = os.environ.get('EXTERNAL_CURATION_MODEL', os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat'))
        self.url = os.environ.get('DEEPSEEK_API_URL', 'https://api.deepseek.com/chat/completions')
        # Do not send credentials to a newly supplied intermediary or redirects.
        if self.url not in ('https://api.deepseek.com/chat/completions', 'https://api.deepseek.com/v1/chat/completions'):
            raise ProviderError('provider_endpoint_not_approved')
        self.policy = policy
        self.tokens = 0

    def __call__(self, stage, prompt, payload):
        if not self.key:
            raise ProviderError('provider_not_configured')
        body = json.dumps({'model': self.model, 'temperature': 0.2,
                           'max_tokens': self.policy['maxOutputTokens'],
                           'response_format': {'type': 'json_object'},
                           'messages': [{'role': 'system', 'content': 'Return only a JSON object.\n' + prompt},
                                        {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]}).encode()
        request = urllib.request.Request(self.url, data=body, headers={
            'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json'})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise ProviderError('provider_redirect_refused')
        self.tokens = 0
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=self.policy['requestTimeoutSeconds']) as response:
                raw = response.read(200001)
            if len(raw) > 200000:
                raise ProviderError('provider_response_oversize')
            data = json.loads(raw)
            self.tokens = max(0, int(data.get('usage', {}).get('total_tokens', 0)))
            if data['choices'][0].get('finish_reason') != 'stop':
                raise ProviderError('provider_response_incomplete')
            content = data['choices'][0]['message']['content'].strip()
            if content.startswith('```'):
                content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content)
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ProviderError('provider_response_shape')
            return result
        except ProviderError:
            raise
        except urllib.error.HTTPError as exc:
            raise ProviderError('provider_http_' + str(exc.code)) from None
        except (urllib.error.URLError, TimeoutError):
            raise ProviderError('provider_network_failed') from None
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError('provider_json_invalid') from None


def text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or clean_text(value, limit) != value:
        raise ValueError('invalid model text')
    return value


def decision(value, key):
    if type(value.get(key)) is not bool:
        raise ValueError('invalid model decision')
    value = {**value, 'reason': clean_text(value.get('reason'), 300)}
    text(value['reason'], 300)
    return value


def score(value):
    for key in ('relevance', 'novelty', 'evidence', 'utility'):
        if type(value.get(key)) is not int or not 0 <= value[key] <= 25:
            raise ValueError('invalid model score')
    value = {**value, 'reason': clean_text(value.get('reason'), 300)}
    text(value['reason'], 300)
    return value


def writing(value, item):
    if value.get('insufficient') is True:
        return value
    for key, limit in [('title', 80), ('summary', 300), ('reason', 120)]:
        text(value.get(key), limit)
        if not re.search('[\u4e00-\u9fff]', value[key]):
            raise ValueError('Chinese text required')
    quotes = value.get('evidenceQuotes')
    corpus = item['title'] + '\n' + item['summary'] + '\n' + item.get('body', '')
    if not isinstance(quotes, list) or not 1 <= len(quotes) <= 3 or any(not isinstance(q, str) or len(q) < 4 or q not in corpus for q in quotes) or sum(map(len, quotes)) > 2000:
        raise ValueError('unsupported evidence quote')
    # Models often return several correct but overlong quotations. Verify every
    # quote first, then keep a bounded verbatim excerpt instead of re-calling them.
    remaining, excerpts = 120, []
    for quote in quotes:
        excerpt = quote[:remaining]
        if len(quote) > remaining and ' ' in excerpt:
            excerpt = excerpt.rsplit(' ', 1)[0]
        if len(excerpt) >= 4:
            excerpts.append(excerpt)
            remaining -= len(excerpt)
        if remaining < 4:
            break
    value = {**value, 'evidenceQuotes': excerpts}
    tags = value.get('tags')
    if not isinstance(tags, list) or len(tags) > 4:
        raise ValueError('invalid tags')
    for tag in tags:
        text(tag, 30)
    return {key: value[key] for key in ('title', 'summary', 'reason', 'evidenceQuotes', 'tags')}


def grouping(value, candidates):
    event_id, relation = value.get('eventId'), value.get('relation')
    text(value.get('reason'), 300)
    if relation == 'new' and event_id is None:
        return value
    if relation not in ('same', 'development') or event_id not in {c['id'] for c in candidates}:
        raise ValueError('invalid grouping')
    return value


class Pipeline:
    def __init__(self, db, policy, model, now, enricher=None):
        validate_policy(policy)
        self.db, self.p, self.model, self.now = db, policy, model, now
        self.started = time.monotonic()
        self.call_count = 0
        self.enricher = enricher
        self.sources = {}
        self.prompts = {p.stem: p.read_text() for p in PROMPTS.glob('*.md')}
        self.policy_hash = digest([policy, self.prompts, getattr(model, 'model', 'test')])

    def call(self, stage, payload, validate, *, repair=False):
        prompt = self.prompts['score' if stage.startswith('score-') else stage]
        if repair:
            prompt += '\n上次输出未通过严格校验。请重新给出简短 JSON：标题最多60字，摘要最多220字，理由最多80字；引文必须从输入逐字复制，不用省略号替换原文；数字和布尔值必须符合要求。'
        key = digest([self.policy_hash, stage, payload])
        row = self.db.execute('SELECT value FROM stages WHERE key=?', (key,)).fetchone()
        if row:
            return validate(json.loads(row[0]))
        day = self.now.astimezone(CST).date().isoformat()
        used = self.db.execute('SELECT count(*) FROM calls WHERE day=?', (day,)).fetchone()[0]
        if self.call_count >= self.p['maxCallsPerRun'] or used >= self.p['maxCallsPerDay'] or time.monotonic() - self.started >= self.p['maxRuntimeSeconds']:
            raise BudgetExceeded()
        # Reserve before networking; failures and interruptions still consume the budget.
        cursor = self.db.execute('INSERT INTO calls(day,stage,status) VALUES(?,?,?)', (day, stage, 'started'))
        self.db.commit()
        self.call_count += 1
        try:
            value = validate(self.model(stage, prompt, payload))
            self.db.execute('INSERT OR REPLACE INTO stages VALUES(?,?,?)', (key, stage, json.dumps(value, ensure_ascii=False)))
            self.db.execute('UPDATE calls SET status=?,tokens=? WHERE id=?', ('ok', getattr(self.model, 'tokens', 0), cursor.lastrowid))
            self.db.commit()
            return value
        except Exception as exc:
            self.db.execute('UPDATE calls SET status=?,tokens=? WHERE id=?', ('failed', getattr(self.model, 'tokens', 0), cursor.lastrowid))
            self.db.commit()
            if isinstance(exc, ValueError) and not repair:
                return self.call(stage, payload, validate, repair=True)
            raise

    def candidates(self, item):
        cutoff = iso(self.now - timedelta(days=self.p['lookbackDays']))
        rows = self.db.execute("SELECT event_id,payload,result FROM articles WHERE state='selected' AND id<>?", (item['id'],)).fetchall()
        groups = {}
        for row in rows:
            raw = json.loads(row['payload'])
            if not raw['publishedAt'] or raw['publishedAt'] < cutoff:
                continue
            groups.setdefault(row['event_id'], []).append({'title': raw['title'], 'summary': raw['summary'], 'publishedAt': raw['publishedAt']})
        tokens = set(re.findall(r'\w+', (item['title'] + ' ' + item['summary']).lower()))
        def similarity(pair):
            other = set(re.findall(r'\w+', json.dumps(pair[1], ensure_ascii=False).lower()))
            return len(tokens & other) / max(1, len(tokens | other))
        return [{'id': key, 'reports': values[-3:]} for key, values in sorted(groups.items(), key=similarity, reverse=True)[:self.p['maxClusterCandidates']]]

    def process(self, item):
        item = dict(item)
        if self.enricher:
            body_key = digest([item['url'], item['title'], item['summary'], self.p['articleMaxChars']])
            cached = self.db.execute('SELECT body FROM article_bodies WHERE key=?', (body_key,)).fetchone()
            if cached:
                item['body'] = cached[0]
            else:
                try:
                    item['body'] = self.enricher(item, self.sources[item['sourceId']], self.p)
                    self.db.execute('INSERT OR REPLACE INTO article_bodies VALUES(?,?,?)', (body_key, item['body'], iso(self.now)))
                    self.db.commit()
                except Exception:
                    # A substantial feed summary may still stand alone, but missing evidence
                    # must be retried, not permanently classified as low-quality news.
                    if not item['summary'].strip():
                        raise ArticleUnavailable() from None
            item['body'] = item.get('body', '')
        evidence = {key: item[key] for key in ('title', 'summary', 'sourceName', 'publishedAt')}
        if item.get('body'):
            evidence['body'] = item['body']

        source = self.p['sourcePolicy'][item['sourceId']]
        pre = self.call('prescreen', evidence, lambda v: decision(v, 'keep'))
        if not pre['keep']:
            return 'rejected', {'reason': pre['reason']}, None, None
        # Same rubric, separate requests and cache keys. Neither score is in the other's input.
        a = self.call('score-a', evidence, score)
        b = self.call('score-b', evidence, score)
        totals = [sum(v[k] for k in ('relevance', 'novelty', 'evidence', 'utility')) for v in (a, b)]
        threshold = self.p['scoreThresholds'][source['tier']]
        scores = {'scores': totals, 'scoreDetails': [a, b], 'threshold': threshold}
        if min(totals) < threshold or abs(totals[0] - totals[1]) > self.p['maxScoreDisagreement']:
            return 'rejected', {**scores, 'reason': '未通过双评分入选标准'}, None, None
        written = self.call('write', evidence, lambda v: writing(v, item))
        if written.get('insufficient'):
            return 'rejected', {**scores, 'reason': '原始资料不足'}, None, None
        grounded = self.call('ground', {'source': evidence, 'candidate': written}, lambda v: decision(v, 'supported'))
        if not grounded['supported']:
            return 'rejected', {**scores, 'reason': '中文摘要未通过原文核对'}, None, None
        candidates = self.candidates(item)
        event_id, relation = 'event-' + digest(item['canonicalUrl'])[:20], 'new'
        if candidates:
            choice = self.call('group', {'source': evidence, 'candidates': candidates}, lambda v: grouping(v, candidates))
            if choice['eventId']:
                target = next(c for c in candidates if c['id'] == choice['eventId'])
                def review(v):
                    decision(v, 'confirmed')
                    if v.get('relation') not in ('same', 'development', 'new'):
                        raise ValueError('invalid group review')
                    return v
                reviewed = self.call('review-group', {'source': evidence, 'candidate': target}, review)
                if reviewed['confirmed'] and reviewed['relation'] in ('same', 'development'):
                    event_id, relation = choice['eventId'], reviewed['relation']
        return 'selected', {**written, **scores, 'evidenceBasis': 'article' if item.get('body') else 'feed'}, event_id, relation

    def run(self, document):
        validate_document(document)
        self.sources = {s['id']: s for s in document['sources']}
        unknown = {s['id'] for s in document['sources']} - self.p['sourcePolicy'].keys()
        if unknown:
            raise ValueError('source missing curation policy')
        started = iso(self.now)
        policy_row = self.db.execute("SELECT value FROM meta WHERE key='policy'").fetchone()
        if policy_row and policy_row[0] != self.policy_hash:
            # A changed model/prompt/threshold invalidates all previous decisions, including
            # articles which have rolled off the latest feed snapshot.
            self.db.execute("UPDATE articles SET state='pending',result=NULL,event_id=NULL,relation=NULL,attempts=0,next_retry=NULL,error=NULL")
        self.db.execute("INSERT OR REPLACE INTO meta VALUES('policy',?)", (self.policy_hash,))
        run_id = self.db.execute('INSERT INTO runs(started_at,status) VALUES(?,?)', (started, 'running')).lastrowid
        self.db.commit()
        for item in document['items']:
            # Collection time is not editorial evidence and must not invalidate decisions.
            fingerprint = digest([self.policy_hash, {k: v for k, v in item.items() if k != 'fetchedAt'}])
            old = self.db.execute('SELECT fingerprint FROM articles WHERE id=?', (item['id'],)).fetchone()
            if old and old[0] == fingerprint:
                continue
            self.db.execute('''INSERT INTO articles(id,fingerprint,payload,state,updated_at) VALUES(?,?,?,?,?)
              ON CONFLICT(id) DO UPDATE SET fingerprint=excluded.fingerprint,payload=excluded.payload,
              state='pending',result=NULL,event_id=NULL,relation=NULL,attempts=0,next_retry=NULL,error=NULL,updated_at=excluded.updated_at''',
              (item['id'], fingerprint, json.dumps(item, ensure_ascii=False), 'pending', started))
        self.db.execute("UPDATE articles SET state='pending' WHERE state='future' AND json_extract(payload,'$.publishedAt')<=?", (started,))
        self.db.commit()
        cutoff = iso(self.now - timedelta(days=self.p['lookbackDays']))
        processed, failed, exhausted, provider_failures = 0, 0, False, 0
        rows = self.db.execute("SELECT * FROM articles WHERE state IN ('pending','failed') ORDER BY json_extract(payload,'$.publishedAt') ASC,id").fetchall()
        for row in rows:
            if processed >= self.p['maxItemsPerRun']:
                break
            item = json.loads(row['payload'])
            if item['sourceId'] not in self.sources or item['sourceId'] not in self.p['sourcePolicy']:
                self.db.execute("UPDATE articles SET state='archived' WHERE id=?", (row['id'],))
                continue
            date = item['publishedAt']
            if not date or date < cutoff or date > started:
                # Unknown dates remain visible in raw feeds; never invent today's date.
                state = 'undated' if not date else ('future' if date > started else 'archived')
                self.db.execute('UPDATE articles SET state=? WHERE id=?', (state, row['id']))
                continue
            if row['attempts'] >= self.p['maxAttempts']:
                if dt(row['updated_at']).astimezone(CST).date() >= self.now.astimezone(CST).date():
                    continue
                self.db.execute('UPDATE articles SET attempts=0,next_retry=NULL WHERE id=?', (row['id'],))
            elif row['next_retry'] and row['next_retry'] > started:
                continue
            try:
                state, result, event, relation = self.process(item)
                if event:
                    self.db.execute('INSERT OR IGNORE INTO events VALUES(?,?)', (event, started))
                self.db.execute('UPDATE articles SET state=?,result=?,event_id=?,relation=?,error=NULL,next_retry=NULL,updated_at=? WHERE id=?',
                                (state, json.dumps(result, ensure_ascii=False), event, relation, started, row['id']))
                processed += 1
                provider_failures = 0
            except BudgetExceeded:
                exhausted = True
                break
            except Exception as exc:
                # Only stable error classes, never API response bodies or credentials.
                error = (str(exc) if re.fullmatch(r'provider_[a-z_0-9]+', str(exc)) else 'provider_failed') if isinstance(exc, ProviderError) else ('article_unavailable' if isinstance(exc, ArticleUnavailable) else 'validation_failed:' + (str(exc)[:80] if isinstance(exc, ValueError) else type(exc).__name__))
                self.db.execute("UPDATE articles SET state='failed',attempts=attempts+1,next_retry=?,error=?,updated_at=? WHERE id=?",
                                (iso(self.now + timedelta(minutes=self.p['retryAfterMinutes'])), error, started, row['id']))
                failed += 1
                processed += 1
                if isinstance(exc, ProviderError):
                    provider_failures += 1
                    if provider_failures >= 3:
                        break  # Stop a provider outage without blocking on one transient error.
            self.db.commit()
        counts = {r[0]: r[1] for r in self.db.execute('SELECT state,count(*) FROM articles GROUP BY state')}
        source_failed = sum(s['status'] != 'ok' for s in document['sources'])
        status = 'budget_limited' if exhausted else ('partial' if counts.get('failed') or counts.get('pending') or source_failed else 'ok')
        self.db.execute('UPDATE runs SET finished_at=?,status=?,counts=? WHERE id=?', (iso(datetime.now(timezone.utc)), status, json.dumps(counts), run_id))
        self.db.commit()
        return {'status': status, 'attemptedAt': started, 'counts': counts, 'callsThisRun': self.call_count,
                'processedThisRun': processed, 'failedThisRun': failed, 'failedSources': source_failed}

    def snapshot(self, run):
        rows = self.db.execute("SELECT * FROM articles WHERE state='selected'").fetchall()
        grouped = {}
        for row in rows:
            item, result = json.loads(row['payload']), json.loads(row['result'])
            grouped.setdefault(row['event_id'], []).append({**item, **result, 'originalTitle': item['title'], 'originalSummary': item['summary'], 'relation': row['relation'],
                'publisher': self.p['sourcePolicy'][item['sourceId']]['publisher'], 'selectedAt': row['updated_at']})
        events = []
        for event_id, reports in grouped.items():
            reports.sort(key=lambda r: (r['publishedAt'], r['id']))
            latest = reports[-1]
            if latest['publishedAt'] < iso(self.now - timedelta(days=self.p['lookbackDays'])):
                continue
            publishers = {}
            for report in reports:
                age = (self.now - dt(report['publishedAt'])).total_seconds() / 3600
                if 0 <= age <= self.p['hotWindowHours']:
                    weight = 2 ** (-age / self.p['hotHalfLifeHours'])
                    publishers[report['publisher']] = max(publishers.get(report['publisher'], 0), weight)
            heat = round(sum(publishers.values()), 4)
            baseline = self.db.execute('SELECT value FROM heat WHERE event_id=? AND at<=? ORDER BY at DESC LIMIT 1',
                                      (event_id, iso(self.now - timedelta(hours=self.p['trendWindowHours'])))).fetchone()
            events.append({'id': event_id, 'title': latest['title'], 'summary': latest['summary'],
                           'reason': latest['reason'], 'tags': latest['tags'], 'publishedAt': reports[0]['publishedAt'],
                           'updatedAt': latest['publishedAt'], 'heat': heat, 'independentSources': len(publishers),
                           'trend': 'new' if baseline is None else ('rising' if heat > baseline[0] else 'steady'),
                           'reports': reports})
            self.db.execute('INSERT OR REPLACE INTO heat VALUES(?,?,?)', (iso(self.now), event_id, heat))
        events.sort(key=lambda e: (-e['heat'], -dt(e['updatedAt']).timestamp(), e['id']))
        editions = self.editions(events, run)
        previous_ok = self.db.execute("SELECT max(started_at) FROM runs WHERE status='ok'").fetchone()[0]
        self.db.commit()
        return {'schemaVersion': 1, 'policyVersion': self.p['policyVersion'], 'generatedAt': iso(self.now),
                'lastSuccessAt': previous_ok, 'run': run,
                'rules': {k: self.p[k] for k in ('hotWindowHours', 'hotHalfLifeHours', 'digestLimit', 'maxItemsPerRun')},
                'events': events, 'editions': editions}

    def editions(self, events, run):
        today = self.now.astimezone(CST).date()
        cutoff = iso(self.now - timedelta(days=self.p['lookbackDays']))
        covered = [dt(r[0]).astimezone(CST).date().isoformat() for r in self.db.execute(
            "SELECT json_extract(payload,'$.publishedAt') FROM articles WHERE json_extract(payload,'$.publishedAt')>=? AND json_extract(payload,'$.publishedAt')<=?",
            (cutoff, iso(self.now)))]
        first_covered = min(covered, default=today.isoformat())
        # Recompute bounded days for late arrivals; revisions are explicit and deterministic.
        for offset in range(self.p['lookbackDays']):
            day = (today - timedelta(days=offset)).isoformat()
            items = []
            for event in events:
                reports = [r for r in event['reports'] if dt(r['publishedAt']).astimezone(CST).date().isoformat() == day]
                earlier = any(dt(r['publishedAt']).astimezone(CST).date().isoformat() < day for r in event['reports'])
                eligible = [r for r in reports if not earlier or r['relation'] == 'development']
                if not eligible:
                    continue
                best = max(eligible, key=lambda r: (min(r['scores']), r['publishedAt'], r['id']))
                items.append({'eventId': event['id'], 'reportId': best['id'], 'title': best['title'],
                              'summary': best['summary'], 'reason': best['reason'], 'url': best['url'],
                              'sourceName': best['sourceName'], 'scores': best['scores'], 'development': earlier})
            items.sort(key=lambda r: (-min(r['scores']), r['eventId']))
            status = 'in_progress' if offset == 0 else ('complete' if run['status'] == 'ok' else 'partial')
            payload = {'date': day, 'status': status, 'total': len(items), 'items': items[:self.p['digestLimit']]}
            fingerprint = digest(payload)
            old = self.db.execute('SELECT fingerprint,revision FROM editions WHERE day=?', (day,)).fetchone()
            revision = (old['revision'] if old else 0) + (0 if old and old['fingerprint'] == fingerprint else 1)
            payload['revision'] = revision
            # Empty prior days before first actual coverage aren't invented complete editions.
            if day >= first_covered or items or old or offset == 0:
                self.db.execute('INSERT OR REPLACE INTO editions VALUES(?,?,?,?)', (day, fingerprint, revision, json.dumps(payload, ensure_ascii=False)))
        return [json.loads(r[0]) for r in self.db.execute('SELECT payload FROM editions ORDER BY day DESC LIMIT 31')]
