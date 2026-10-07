import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('health_gap', Path(__file__).parents[1] / 'health.py')
health = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health)


class GapHealthTest(unittest.TestCase):
    def combine(self, ledger, arsenal=None, gap=True, gap_date='2026-09-30'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'ledger.json').write_text(json.dumps(ledger))
            if arsenal is not None:
                (root / 'arsenal.json').write_text(json.dumps(arsenal))
            (root / 'gap.json').write_text(json.dumps({'date': gap_date, 'degraded': True}))
            args = SimpleNamespace(date='2026-09-30', ledger_result=root/'ledger.json', arsenal_result=root/'arsenal.json', arsenal_gap=root/'gap.json' if gap else None, output=root/'quality.json', alert_file=None, export_log=None)
            with contextlib.redirect_stdout(io.StringIO()):
                code = health.combine(args)
            return code, json.loads(args.output.read_text())

    def test_explicit_gap_allows_reviewed_ledger_but_keeps_failure_visible(self):
        code, result = self.combine({'passed': True, 'score': 84, 'hard_fail': []})
        self.assertEqual(code, 0)
        self.assertTrue(result['publishable'])
        self.assertTrue(result['degraded'])
        self.assertFalse(result['passed'])
        self.assertFalse(result['artifacts']['arsenal']['passed'])

    def test_missing_or_wrong_date_gap_is_not_permission(self):
        ledger = {'passed': True, 'score': 84, 'hard_fail': []}
        self.assertEqual(self.combine(ledger, gap=False)[0], 2)
        self.assertEqual(self.combine(ledger, gap_date='2026-09-29')[0], 2)

    def test_gap_never_overrides_ledger_failure(self):
        for ledger in [{'passed': False, 'score': 84, 'hard_fail': []}, {'passed': True, 'score': 69, 'hard_fail': []}, {'passed': True, 'score': 84, 'hard_fail': ['引用不符']}]:
            with self.subTest(ledger=ledger):
                self.assertEqual(self.combine(ledger)[0], 2)

    def test_privacy_still_blocks(self):
        code, result = self.combine({'passed': True, 'score': 84, 'hard_fail': []}, {'passed': False, 'score': 80, 'hard_fail': ['命中隐私形态']})
        self.assertEqual(code, 2)
        self.assertFalse(result['publishable'])


if __name__ == '__main__':
    unittest.main()
