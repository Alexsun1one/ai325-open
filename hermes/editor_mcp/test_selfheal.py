from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server


DATE = "2026-08-23"


class SelfHealTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.root = root
        self.repo = root / "repo"
        self.ledger_home = root / "ledger"
        self.arsenal_home = root / "arsenal"
        self.harness_home = root / "harness"
        self.materials = root / "materials"
        self.logs = root / "logs"
        self.gov = root / "governed"
        self.transcript = self.materials / DATE / "transcript.txt"
        for path in (
            self.repo / "site/content/ledgers",
            self.ledger_home,
            self.arsenal_home / "candidates",
            self.harness_home,
            self.materials / DATE,
            self.logs / f"quality-work-{DATE}",
            self.gov / "ledgers",
            self.gov / "arsenal",
        ):
            path.mkdir(parents=True, exist_ok=True)
        self.transcript.write_text("[08-23 00:01] A: one\n", encoding="utf-8")
        self.settings = server.Settings(
            repo=self.repo,
            ledger_home=self.ledger_home,
            arsenal_home=self.arsenal_home,
            harness_home=self.harness_home,
            materials_root=self.materials,
            logs_dir=self.logs,
            export_log=root / "export.log",
            health_daily=root / "health.json",
            lock_file=self.logs / "editor.lock",
            server_daily=root / "server-daily.sh",
            alert_command=root / "alert.sh",
            python=sys.executable,
            arsenal_python=sys.executable,
            judge_mode="mechanical-only",
            command_timeout=5,
            governed_root=self.gov,
            db_path=root / "xf.db",
            integrity_script=Path(__file__).resolve().parents[2] / "scripts/ops/check-material-integrity.py",
            require_coverage_check=True,
            self_heal_retry_delay=0,
            self_heal_state_dir=root / "self-heal-state",
            reexport_command=("/tmp/fake-export",),
        )
        self.settings.db_path.touch()
        self.arsenal = self.settings.arsenal_artifact(DATE)
        self.arsenal.write_text("[{\"id\": \"one\"}]", encoding="utf-8")
        server.atomic_write_json(self.settings.judge_path(DATE, "arsenal"), self.judge())

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def judge(*, passed: bool = True, score: int = 82, count: int = 0) -> dict[str, object]:
        return {"passed": passed, "score": score, "grade": "B" if passed else "F", "hard_fail": [] if passed else ["bad"], "soft": [], "suggestions": ["具体化"], "redistill_count": count}

    def content(self) -> Path:
        return self.settings.ledger_artifact(DATE)

    def seed_ledger(self) -> None:
        server.atomic_write_json(self.content(), {"complete": True, "prompt_version": "ledger-v4", "quality": {"overall": 82, "grade": "B"}, "themes": [{"h": "ok"}]})
        server.atomic_write_json(self.settings.judge_path(DATE, "ledger"), self.judge())
        server.atomic_write_json(self.gov / "ledgers" / f"{DATE}.json", json.loads(self.content().read_text(encoding="utf-8")))
        server.atomic_write_json(self.gov / "arsenal" / f"{DATE}.json", [{"id": "one"}])

    async def fake_run(self, argv, *, cwd, settings, accepted=None):
        argv = list(argv)
        if "check-material-integrity.py" in " ".join(argv):
            coverage = "10.00%" if self.transcript.read_text(encoding="utf-8").count("[08-23") < 10 else "100.00%"
            return server.CommandResult(argv, 0 if coverage == "100.00%" else 1, f"transcript_messages={10 if coverage == '100.00%' else 1} db_messages=10 coverage={coverage} threshold=70.00%", "")
        if argv and argv[0] == "env" and "/tmp/fake-export" in argv:
            self.transcript.write_text("".join(f"[08-23 00:{i:02d}] A: message\n" for i in range(10)), encoding="utf-8")
            return server.CommandResult(argv, 0, "exported", "")
        if "run.sh" in argv[0]:
            output = Path(argv[argv.index("--output") + 1])
            server.atomic_write_json(output, {"complete": True, "prompt_version": "ledger-v4", "quality": {"overall": 82, "grade": "B"}, "themes": [{"h": "fixed"}]})
        elif len(argv) > 1 and argv[1].endswith("judge.py"):
            server.atomic_write_json(Path(argv[argv.index("--output") + 1]), self.judge(count=int(argv[argv.index("--redistill-count") + 1]) if "--redistill-count" in argv else 0))
        elif len(argv) > 1 and argv[1].endswith("health.py"):
            output = Path(argv[argv.index("--output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("{}", encoding="utf-8")
        elif "server-daily.sh" in " ".join(argv):
            server.atomic_write_json(self.gov / "ledgers" / f"{DATE}.json", json.loads(self.content().read_text(encoding="utf-8")))
            server.atomic_write_json(self.gov / "arsenal" / f"{DATE}.json", [{"id": "one"}])
        return server.CommandResult(argv, 0, "", "")

    async def test_missing_content_is_redistilled_and_promoted(self) -> None:
        with patch.object(server, "run_command", side_effect=self.fake_run) as mocked:
            result = await server.self_heal_core(DATE, self.settings, trigger="fixture-missing")
        self.assertTrue(result["ok"], result)
        self.assertTrue(self.content().is_file())
        self.assertTrue((self.gov / "ledgers" / f"{DATE}.json").is_file())
        calls = [call.args[0] for call in mocked.await_args_list]
        self.assertTrue(any("run.sh" in " ".join(call) for call in calls))

    async def test_sparse_transcript_reexports_once_and_redistills(self) -> None:
        self.seed_ledger()
        with patch.object(server, "run_command", side_effect=self.fake_run):
            result = await server.self_heal_core(DATE, self.settings, trigger="fixture-sparse")
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["diagnosis"]["coverage"]["passed"], result)
        self.assertEqual(self.transcript.read_text(encoding="utf-8").count("[08-23"), 10)

    async def test_missing_coverage_evidence_uses_delivery_fallback_warn(self) -> None:
        """A published page remains successful when the audit inputs rotated away."""
        self.seed_ledger()
        alert = self.root / "alert.sh"
        alert_args = self.root / "alert.args"
        alert.write_text(
            f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> {str(alert_args)!r}\nexit 0\n",
            encoding="utf-8",
        )
        alert.chmod(alert.stat().st_mode | stat.S_IXUSR)
        settings = server.Settings(**{**self.settings.__dict__, "alert_command": alert})
        page = {
            "checked": True,
            "required": True,
            "url": "https://fixture.invalid/ledger/2026-08-23/",
            "status": 200,
            "passed": True,
        }
        with patch.object(server, "_probe_public_page", return_value=page):
            result = await server.self_heal_core(DATE, settings, trigger="fixture-evidence-missing")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["status"], "WARN", result)
        self.assertFalse(result["critical"], result)
        self.assertFalse(result["diagnosis"]["coverage"]["available"], result)
        self.assertTrue(result["diagnosis"]["delivery_fallback"]["passed"], result)
        self.assertEqual([event["level"] for event in result["events"]], ["WARN"])
        self.assertIn("--no-escalate", alert_args.read_text(encoding="utf-8"))
        self.assertIn("证据缺失", settings.export_log.read_text(encoding="utf-8"))

    async def test_script_crash_is_critical_without_pipeline_retry(self) -> None:
        self.logs.joinpath(f"daily-{DATE}.log").write_text("Traceback (most recent call last):\ndeliberate crash exit=42\n", encoding="utf-8")
        with patch.object(server, "run_command", side_effect=self.fake_run) as mocked:
            result = await server.self_heal_core(DATE, self.settings, trigger="fixture-crash")
        self.assertFalse(result["ok"])
        self.assertTrue(result["critical"])
        self.assertEqual(result["failure_type"], "script_crash")
        self.assertFalse(any("run.sh" in " ".join(call.args[0]) for call in mocked.await_args_list))

    async def test_same_fault_escalates_after_two_failed_attempts(self) -> None:
        self.seed_ledger()
        settings = server.Settings(**{**self.settings.__dict__, "reexport_command": ("/tmp/export-that-does-not-fix",)})
        with patch.object(server, "run_command", side_effect=self.fake_run):
            result = await server.self_heal_core(DATE, settings, trigger="fixture-two-failures")
        self.assertFalse(result["ok"])
        self.assertTrue(result["critical"])
        state = json.loads(settings.self_heal_state_path(DATE).read_text(encoding="utf-8"))
        entry = state["incidents"][f"{DATE}:data_insufficient:transcript"]
        self.assertEqual(entry["attempts"], 2)
        self.assertEqual(entry["status"], "critical")

    def test_deadman_calls_self_heal_before_failing(self) -> None:
        ledgers = self.root / "deadman-ledgers"
        heartbeats = self.root / "deadman-heartbeats"
        ledgers.mkdir()
        heartbeats.mkdir()
        (ledgers / f"{DATE}.json").write_text(json.dumps({"quality": {"overall": 0, "grade": "待评"}}), encoding="utf-8")
        heal = self.root / "deadman-heal.sh"
        heal.write_text("#!/usr/bin/env bash\nprintf '%s\\n' '{\"quality\":{\"overall\":82,\"grade\":\"B\"}}' > \"$DEADMAN_LEDGER_DIR/$1.json\"\n", encoding="utf-8")
        heal.chmod(heal.stat().st_mode | stat.S_IXUSR)
        env = os.environ.copy()
        env["DEADMAN_LEDGER_DIR"] = str(ledgers)
        completed = subprocess.run(
            [
                "bash",
                str(Path(__file__).resolve().parents[2] / "scripts/ops/ledger-deadman.sh"),
                "--date",
                DATE,
                "--ledger-dir",
                str(ledgers),
                "--heartbeat-dir",
                str(heartbeats),
                "--no-alert",
                "--self-heal-command",
                str(heal),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("SELF-HEALED", completed.stdout)
        self.assertTrue((heartbeats / f"ledger-deadman-{DATE}.ok").is_file())


if __name__ == "__main__":
    unittest.main()
