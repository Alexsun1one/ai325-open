import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.external_curation import Pipeline, ProviderError, connect, digest, writing, score, validate_policy
from app.external_sources import parse_feed

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 7, 8, tzinfo=timezone.utc)


def item(url='https://example.com/release', source='openai-news', date='2026-10-07T01:00:00Z'):
    cfg = {'id': source, 'name': source, 'tags': []}
    xml = f'<rss><channel><item><title>Tool releases version 2</title><description>Tool version 2 adds local inference and reproducible benchmarks.</description><link>{url}</link><pubDate>{date}</pubDate></item></channel></rss>'.encode()
    return parse_feed(xml, cfg, NOW)[0]


def document(items):
    sources = []
    for sid in sorted({i['sourceId'] for i in items}):
        sources.append({'id': sid, 'name': sid, 'feedUrl': 'https://example.com/feed', 'homepage': 'https://example.com', 'tags': [], 'status': 'ok', 'lastAttemptAt': '2026-10-07T08:00:00Z', 'lastSuccessAt': '2026-10-07T08:00:00Z', 'lastError': None, 'itemCount': sum(i['sourceId'] == sid for i in items)})
    return {'schemaVersion': 1, 'updatedAt': '2026-10-07T08:00:00Z', 'sources': sources, 'items': items}


class FakeModel:
    model = 'test'
    tokens = 20
    def __init__(self):
        self.calls = []
        self.fail = None
        self.low_b = False
        self.merge = True
        self.development = False
        self.grounded = True
        self.reviewed = True
    def __call__(self, stage, prompt, payload):
        self.calls.append((stage, copy.deepcopy(payload)))
        if stage == self.fail:
            raise ProviderError('secret must not leak')
        if stage == 'prescreen':
            return {'keep': True, 'reason': '具体工具发布'}
        if stage.startswith('score-'):
            n = 10 if stage == 'score-b' and self.low_b else 22
            return {**{k: n for k in ('relevance', 'novelty', 'evidence', 'utility')}, 'reason': '可核验的工程信息'}
        if stage == 'write':
            return {'title': '工具第二版支持本地推理', 'summary': '工具第二版增加本地推理与可复现基准测试。', 'reason': '便于核对推理效果', 'evidenceQuotes': ['Tool version 2 adds local inference'], 'tags': ['本地推理']}
        if stage == 'ground':
            return {'supported': self.grounded, 'reason': '已核对'}
        if stage == 'group':
            return {'eventId': payload['candidates'][0]['id'] if self.merge else None, 'relation': ('development' if self.development else 'same') if self.merge else 'new', 'reason': '同一发布'}
        if stage == 'review-group':
            return {'confirmed': self.reviewed, 'relation': 'development' if self.development else 'same', 'reason': '独立核对'}
        raise AssertionError(stage)


class CurationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.temp.name) / 'state.db')
        self.policy = json.loads((ROOT / 'config/external-curation.json').read_text())
        self.model = FakeModel()
    def tearDown(self):
        self.db.close()
        self.temp.cleanup()
    def run_pipeline(self, items, now=NOW):
        pipeline = Pipeline(self.db, self.policy, self.model, now)
        run = pipeline.run(document(items))
        return pipeline.snapshot(run)
    def test_full_chain_replay_and_independent_scoring(self):
        result = self.run_pipeline([item()])
        self.assertEqual(result['run']['status'], 'ok')
        self.assertEqual(len(result['events']), 1)
        stages = [s for s, _ in self.model.calls]
        self.assertEqual(stages, ['prescreen', 'score-a', 'score-b', 'write', 'ground'])
        self.assertEqual(self.model.calls[1][1], self.model.calls[2][1])
        self.assertNotIn('scores', self.model.calls[2][1])
        repeat = self.run_pipeline([item()])
        self.assertEqual(repeat['run']['callsThisRun'], 0)
        self.assertEqual(result['editions'], repeat['editions'])
    def test_low_second_score_rejects(self):
        self.model.low_b = True
        result = self.run_pipeline([item()])
        self.assertEqual(result['events'], [])
        self.assertEqual(result['run']['counts']['rejected'], 1)
    def test_provider_outage_retries_cached_stages(self):
        self.model.fail = 'score-b'
        first = self.run_pipeline([item()])
        self.assertEqual(first['run']['status'], 'partial')
        self.assertEqual(first['events'], [])
        self.assertNotIn('secret', json.dumps(first))
        self.model.fail = None
        second = self.run_pipeline([item()], NOW + timedelta(hours=1))
        self.assertEqual(len(second['events']), 1)
        self.assertEqual([s for s, _ in self.model.calls].count('score-a'), 1)
        self.assertEqual([s for s, _ in self.model.calls].count('score-b'), 2)
    def test_budget_durable_and_resumable(self):
        self.policy['maxCallsPerRun'] = 2
        first = self.run_pipeline([item()])
        self.assertEqual(first['run']['status'], 'budget_limited')
        self.assertEqual(first['run']['callsThisRun'], 2)
        second = self.run_pipeline([item()])
        self.assertEqual(second['run']['callsThisRun'], 2)
        third = self.run_pipeline([item()])
        self.assertEqual(len(third['events']), 1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM calls').fetchone()[0], 5)
    def test_daily_budget_counts_failed_calls(self):
        self.policy['maxCallsPerDay'] = 1
        self.model.fail = 'prescreen'
        self.run_pipeline([item()])
        result = self.run_pipeline([item()], NOW + timedelta(hours=1))
        self.assertEqual(result['run']['status'], 'budget_limited')
        self.assertEqual(len(self.model.calls), 1)
    def test_unknown_date_not_today(self):
        result = self.run_pipeline([item(date='')])
        self.assertEqual(result['run']['counts']['undated'], 1)
        self.assertEqual(result['editions'][0]['items'], [])
        self.assertEqual(len(self.model.calls), 0)
    def test_old_article_not_selected(self):
        result = self.run_pipeline([item(date='2026-08-01T00:00:00Z')])
        self.assertEqual(result['run']['counts']['archived'], 1)
        self.assertEqual(len(self.model.calls), 0)
    def test_future_article_waits_then_runs(self):
        future = item(date='2026-10-07T09:00:00Z')
        self.assertEqual(self.run_pipeline([future])['run']['counts']['future'], 1)
        self.assertEqual(len(self.run_pipeline([future], NOW + timedelta(hours=2))['events']), 1)
    def test_grounding_failure_rejects(self):
        self.model.grounded = False
        self.assertEqual(self.run_pipeline([item()])['events'], [])
    def test_fabricated_quote_rejected(self):
        candidate = self.model('write', '', {})
        candidate['evidenceQuotes'] = ['not in the source']
        with self.assertRaises(ValueError):
            writing(candidate, item())
    def test_verified_long_quotes_are_bounded_without_changing_evidence(self):
        article = item()
        article['body'] = 'A factual original source sentence with context. ' * 8
        candidate = self.model('write', '', {})
        candidate['evidenceQuotes'] = [article['body'][:200], article['body'][:150]]
        result = writing(candidate, article)
        self.assertLessEqual(sum(map(len, result['evidenceQuotes'])), 120)
        self.assertTrue(all(q in article['body'] for q in result['evidenceQuotes']))
    def test_score_boolean_and_nan_rejected(self):
        for bad in (True, float('nan'), 26, -1):
            with self.assertRaises(ValueError):
                score({'relevance': bad})
    def test_two_publishers_merge_with_independent_review(self):
        result = self.run_pipeline([item(), item('https://example.com/other', 'github-ai')])
        self.assertEqual(len(result['events']), 1)
        self.assertEqual(result['events'][0]['independentSources'], 2)
        self.assertEqual(len(result['events'][0]['reports']), 2)
        self.assertIn('review-group', [s for s, _ in self.model.calls])
    def test_google_feeds_count_as_one_publisher(self):
        result = self.run_pipeline([item('https://example.com/a', 'deepmind-blog'), item('https://example.com/b', 'google-developers')])
        event = result['events'][0]
        self.assertEqual(event['independentSources'], 1)
        self.assertAlmostEqual(event['heat'], 2 ** (-7 / 24), places=4)
    def test_review_can_veto_merge(self):
        self.model.reviewed = False
        self.assertEqual(len(self.run_pipeline([item(), item('https://example.com/b')])['events']), 2)
    def test_heat_decays_no_refresh_inflation(self):
        first = self.run_pipeline([item()])
        second = self.run_pipeline([item()], NOW + timedelta(hours=24))
        self.assertAlmostEqual(second['events'][0]['heat'], first['events'][0]['heat'] / 2, places=3)
        last = self.run_pipeline([item()], NOW + timedelta(hours=49))
        self.assertEqual(last['events'][0]['heat'], 0)
    def test_cross_day_repeat_excluded_development_included(self):
        a = item(date='2026-10-06T01:00:00Z')
        self.run_pipeline([a], NOW - timedelta(days=1))
        b = item('https://example.com/b')
        snapshot = self.run_pipeline([a, b])
        self.assertEqual(snapshot['editions'][0]['items'], [])
        self.model.development = True
        c = item('https://example.com/c', 'github-ai')
        snapshot = self.run_pipeline([a, b, c])
        self.assertEqual(len(snapshot['editions'][0]['items']), 1)
        self.assertTrue(snapshot['editions'][0]['items'][0]['development'])
    def test_input_changes_reprocess(self):
        original = item()
        self.run_pipeline([original])
        original['title'] += ' updated'
        self.run_pipeline([original])
        self.assertEqual([s for s, _ in self.model.calls].count('score-a'), 2)
    def test_fetch_time_does_not_reprocess(self):
        original = item()
        self.run_pipeline([original])
        original['fetchedAt'] = '2026-10-07T02:00:00Z'
        self.assertEqual(self.run_pipeline([original])['run']['callsThisRun'], 0)
    def test_unmapped_source_fail_closed(self):
        with self.assertRaises(ValueError):
            self.run_pipeline([item(source='unknown')])
    def test_all_provider_requests_explicitly_request_json(self):
        from unittest.mock import patch
        from app.external_curation import Model
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'{"supported":true,"reason":"通过"}'}}]}).encode()
        class Opener:
            def open(self, request, **kwargs):
                payload = json.loads(request.data)
                self_outer.assertIn('JSON', payload['messages'][0]['content'])
                return Response()
        self_outer = self
        with patch.dict('os.environ', {'DEEPSEEK_API_KEY':'test-only'}), patch('urllib.request.build_opener', return_value=Opener()):
            result = Model(self.policy)('ground', '仅返回核对结论', {})
            self.assertTrue(result['supported'])
    def test_long_score_explanation_is_bounded_without_changing_scores(self):
        raw = {**{k: 22 for k in ('relevance','novelty','evidence','utility')}, 'reason': '有具体可核验信息。' * 80}
        result = score(raw)
        self.assertLessEqual(len(result['reason']), 300)
        self.assertEqual(result['evidence'], 22)
    def test_empty_days_within_observed_coverage_are_explicit(self):
        old = item(date='2026-10-04T01:00:00Z')
        snapshot = self.run_pipeline([old])
        dates = {d['date']:d for d in snapshot['editions']}
        self.assertEqual(dates['2026-10-05']['items'], [])
        self.assertEqual(dates['2026-10-05']['status'], 'complete')
    def test_invalid_output_gets_one_budgeted_repair(self):
        inner = self.model
        failures = []
        def model(stage, prompt, payload):
            if stage == 'write' and not failures:
                failures.append(True)
                return {'title': 'invalid'}
            return inner(stage, prompt, payload)
        self.model = model
        result = self.run_pipeline([item()])
        self.assertEqual(len(result['events']), 1)
        self.assertEqual(result['run']['callsThisRun'], 6)
        self.assertEqual(self.db.execute("SELECT count(*) FROM calls WHERE status='failed'").fetchone()[0], 1)
    def test_bad_policy_rejected(self):
        for key, value in [('maxCallsPerDay', True), ('hotHalfLifeHours', 0)]:
            p = copy.deepcopy(self.policy)
            p[key] = value
            with self.assertRaises(ValueError):
                validate_policy(p)
    def test_item_cap_reports_partial(self):
        self.policy['maxItemsPerRun'] = 1
        result = self.run_pipeline([item(), item('https://example.com/b')])
        self.assertEqual(result['run']['status'], 'partial')
        self.assertEqual(result['run']['counts']['pending'], 1)
    def test_retry_budget_recovers_automatically_next_day(self):
        self.policy['maxAttempts'] = 1
        self.model.fail = 'prescreen'
        self.run_pipeline([item()])
        self.model.fail = None
        result = self.run_pipeline([item()], NOW + timedelta(days=1))
        self.assertEqual(len(result['events']), 1)
    def test_retry_cap_does_not_fake_success(self):
        self.policy['maxAttempts'] = 1
        self.model.fail = 'prescreen'
        self.run_pipeline([item()])
        self.model.fail = None
        result = self.run_pipeline([item()], NOW + timedelta(hours=2))
        self.assertEqual(result['run']['status'], 'partial')
        self.assertEqual(result['run']['callsThisRun'], 0)

class RunnerTest(unittest.TestCase):
    def setUp(self):
        import importlib.util
        import sys
        sys.path.insert(0, str(ROOT / 'scripts/ops'))
        spec = importlib.util.spec_from_file_location('curation_runner_test', ROOT / 'scripts/ops/curate_external_sources.py')
        self.runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.runner)
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.input = self.base / 'input.json'
        self.output = self.base / 'output.json'
        self.state = self.base / 'state.db'
        current = datetime.now(timezone.utc)
        raw = item(date=(current - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ'))
        # The fixture parser's fixed now can reject dates on other execution days.
        raw['publishedAt'] = (current - timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.input.write_text(json.dumps(document([raw])))
        self.argv = ['curate', '--input', str(self.input), '--output', str(self.output), '--state', str(self.state)]
    def tearDown(self):
        self.temp.cleanup()
    def invoke(self, model):
        from unittest.mock import patch
        with patch('sys.argv', self.argv), patch.object(self.runner, 'Model', return_value=model), patch.object(self.runner, 'fetch_article', return_value='Tool version 2 adds local inference and reproducible benchmarks. ' * 4):
            return self.runner.main()
    def test_real_cli_atomic_snapshot_and_replay(self):
        model = FakeModel()
        self.assertEqual(self.invoke(model), 0)
        first = json.loads(self.output.read_text())
        self.assertEqual(len(first['events']), 1)
        self.assertEqual(self.invoke(model), 0)
        self.assertEqual(json.loads(self.output.read_text())['run']['callsThisRun'], 0)
        self.assertEqual(list(self.base.glob('*.tmp')), [])
    def test_fatal_input_marks_failure_preserves_content(self):
        self.invoke(FakeModel())
        previous = json.loads(self.output.read_text())
        self.input.write_text('{broken')
        self.assertEqual(self.invoke(FakeModel()), 2)
        current = json.loads(self.output.read_text())
        self.assertEqual(current['run']['status'], 'failed')
        self.assertEqual(current['events'], previous['events'])
        self.assertEqual(current['lastSuccessAt'], previous['lastSuccessAt'])
    def test_concurrent_lock_rejects_before_model(self):
        import fcntl
        model = FakeModel()
        with self.state.with_suffix('.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.invoke(model), 75)
        self.assertEqual(model.calls, [])


if __name__ == '__main__':
    unittest.main()
