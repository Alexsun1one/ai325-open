"""Regression coverage for the public vitality leaderboard hot path."""
from __future__ import annotations

import datetime
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from app.test_product_performance import _env, _run


class VitalityLeaderboardTest(unittest.TestCase):
    def test_public_board_reads_ledgers_once_per_scope_without_auditing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "static").mkdir()
            ledgers = root / "governed" / "ledgers"
            ledgers.mkdir(parents=True)
            today = datetime.date.today()
            for offset in range(31):
                day = today - datetime.timedelta(days=offset)
                (ledgers / f"{day.isoformat()}.json").write_text(
                    json.dumps({"quotes": [{"a": "成员0"}, {"a": "成员1"}]})
                )
            result = _run(_env(root), textwrap.dedent("""
                import datetime
                import json
                import time
                from starlette.testclient import TestClient
                import main

                c = main.db()
                today = datetime.date.today()
                for index in range(99):
                    for message in range(150):
                        day = today - datetime.timedelta(days=message % 31)
                        content = "复读内容" if index == 0 and message < 10 else f"有效发言{index}-{message}"
                        c.execute(
                            "INSERT INTO messages(sender_name,cst,content) VALUES(?,?,?)",
                            (f"成员{index}", day.isoformat() + "T09:00:00+08:00", content),
                        )
                for message in range(10):
                    c.execute(
                        "INSERT INTO messages(sender_name,cst,content) VALUES(?,?,?)",
                        ("异常成员", today.isoformat() + "T11:00:00+08:00", f"异常发言{message}"),
                    )
                c.execute(
                    "INSERT INTO messages(sender_name,cst,content) VALUES(?,?,?)",
                    ("异常成员", (today - datetime.timedelta(days=1)).isoformat() + "T11:00:00+08:00", "昨日发言"),
                )
                c.commit()

                settings = main._vitality_settings(c)
                settings["weights"] = dict(settings.get("weights") or {}, anomaly_sigma=0.5, repeat_threshold=2)
                audits_before_direct = c.execute("SELECT COUNT(*) FROM vitality_audit").fetchone()[0]
                main.compute_vitality_for_member(c, "成员0", settings, record_audit=True)
                main.compute_vitality_for_member(c, "异常成员", settings, record_audit=True)
                audits_before_get = c.execute("SELECT COUNT(*) FROM vitality_audit").fetchone()[0]
                assert audits_before_get >= audits_before_direct + 2, (audits_before_direct, audits_before_get)
                c.commit()

                calls = 0
                real = main._vitality_quote_counts
                def counted(*args, **kwargs):
                    global calls
                    calls += 1
                    return real(*args, **kwargs)
                main._vitality_quote_counts = counted
                started = time.monotonic()
                response = TestClient(main.app).get("/api/vitality/leaderboard")
                elapsed = time.monotonic() - started
                assert response.status_code == 200, response.text
                board = response.json()
                audits_after_get = c.execute("SELECT COUNT(*) FROM vitality_audit").fetchone()[0]
                c.close()
                assert board["count"] == 100 and len(board["items"]) == 10, board
                assert board["items"][0]["gain7"] >= 1, board
                assert calls == 3, calls
                assert audits_after_get == audits_before_get, (audits_before_get, audits_after_get)
                assert elapsed < 8, elapsed
                print(json.dumps({"count": board["count"], "ledger_scopes": calls, "audits": audits_after_get, "elapsed": elapsed}))
            """))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('"ledger_scopes": 3', result.stdout)


if __name__ == "__main__":
    unittest.main()
