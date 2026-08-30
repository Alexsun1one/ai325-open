from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server


class EditorMcpTests(unittest.IsolatedAsyncioTestCase):
    def settings(self, root: Path) -> server.Settings:
        repo = root / "repo"
        ledger = root / "ledger"
        arsenal = root / "arsenal"
        harness = root / "harness"
        materials = ledger / "materials"
        logs = root / "logs"
        for path in (repo / "site/content/ledgers", ledger, arsenal / "candidates", harness, materials, logs):
            path.mkdir(parents=True, exist_ok=True)
        return server.Settings(
            repo=repo,
            ledger_home=ledger,
            arsenal_home=arsenal,
            harness_home=harness,
            materials_root=materials,
            logs_dir=logs,
            export_log=root / "export.log",
            health_daily=repo / "site/public/health/daily.json",
            lock_file=logs / "editor.lock",
            server_daily=repo / "scripts/server-daily.sh",
            alert_command=repo / "scripts/ops/alert.sh",
            python=sys.executable,
            arsenal_python=sys.executable,
            judge_mode="mechanical-only",
            command_timeout=5,
        )

    @staticmethod
    def write_json(path: Path, payload: object) -> None:
        server.atomic_write_json(path, payload)

    @staticmethod
    def judge(*, score: int = 80, passed: bool = True, hard: list[str] | None = None) -> dict:
        hard = hard or []
        return {
            "passed": passed,
            "score": score,
            "grade": "B" if passed else "F",
            "hard_fail": hard,
            "soft": [],
            "suggestions": ["改具体一点"],
            "redistill_count": 0,
        }

    def seed_publishable(self, settings: server.Settings, date_value: str) -> None:
        self.write_json(settings.ledger_artifact(date_value), {"complete": True, "themes": [{"h": "A"}]})
        self.write_json(settings.arsenal_artifact(date_value), [{"id": "item-1"}])
        self.write_json(settings.judge_path(date_value, "ledger"), self.judge(score=78))
        self.write_json(settings.judge_path(date_value, "arsenal"), self.judge(score=82))

    def test_date_input_rejects_fake_calendar_date(self) -> None:
        with self.assertRaises(ValueError):
            server.DateInput(date="2026-02-31")

    def test_publish_gate_rejects_low_score_and_partial(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.settings(Path(temp_dir))
            date_value = "2026-08-23"
            self.seed_publishable(settings, date_value)
            self.write_json(settings.judge_path(date_value, "ledger"), self.judge(score=69, passed=False))
            artifact = json.loads(settings.ledger_artifact(date_value).read_text(encoding="utf-8"))
            artifact["complete"] = False
            self.write_json(settings.ledger_artifact(date_value), artifact)
            with self.assertRaises(server.EditorError) as raised:
                server.assert_publishable(settings, date_value)
            self.assertEqual(raised.exception.code, "quality_gate_blocked")
            self.assertIn("score=69", raised.exception.detail)
            self.assertIn("partial", raised.exception.detail)

    async def test_publish_is_idempotent_for_same_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.settings(Path(temp_dir))
            date_value = "2026-08-23"
            self.seed_publishable(settings, date_value)
            fingerprint = server.publish_fingerprint(settings, date_value)
            marker = settings.logs_dir / f"editor-publish-{date_value}.json"
            self.write_json(marker, {"ok": True, "fingerprint": fingerprint})
            with patch.object(server, "run_command") as mocked:
                result = await server.publish_core(date_value, settings)
            mocked.assert_not_called()
            self.assertTrue(result["published"])
            self.assertTrue(result["idempotent"])

    async def test_alert_writes_alert_and_export_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.settings(Path(temp_dir))
            delivery = server.CommandResult(
                [str(settings.alert_command)], 0, "[alert] queued event=test", ""
            )
            with patch.object(server, "run_command", return_value=delivery) as mocked:
                result = await server.alert_core("日报 68 分，不发布", settings)
            alert = json.loads(Path(result["alert"]).read_text(encoding="utf-8"))
            self.assertEqual(alert["source"], "一一总编")
            self.assertIn("不发布", alert["message"])
            self.assertIn("[editor-alert]", settings.export_log.read_text(encoding="utf-8"))
            self.assertEqual(result["delivery"], "queued_or_sent")
            argv = mocked.await_args.args[0]
            self.assertEqual(argv[:3], [str(settings.alert_command), "ERROR", "hermes-editor"])

    async def test_redistill_replaces_only_selected_theme_then_rejudges(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.settings(Path(temp_dir))
            date_value = "2026-08-23"
            material = settings.materials_root / date_value
            material.mkdir(parents=True)
            (material / "transcript.txt").write_text("[08-23 00:01] A: 原话一\n", encoding="utf-8")
            original = {
                "complete": True,
                "themes": [{"h": "不动0"}, {"h": "旧1"}, {"h": "不动2"}],
            }
            self.write_json(settings.ledger_artifact(date_value), original)

            async def fake_run(argv, *, cwd, settings, accepted=None):
                if "run.sh" in argv[0]:
                    output = Path(argv[argv.index("--output") + 1])
                    candidate = {"complete": True, "themes": [{"h": "乱改0"}, {"h": "新1"}, {"h": "乱改2"}]}
                    self.write_json(output, candidate)
                elif argv[1].endswith("judge.py"):
                    output = Path(argv[argv.index("--output") + 1])
                    self.write_json(output, self.judge(score=81))
                return server.CommandResult(list(argv), 0, "", "")

            with patch.object(server, "run_command", side_effect=fake_run):
                result = await server.redistill_theme_core(
                    date_value, 1, "补足没说破但不要编造", settings
                )
            merged = json.loads(settings.ledger_artifact(date_value).read_text(encoding="utf-8"))
            self.assertEqual([theme["h"] for theme in merged["themes"]], ["不动0", "新1", "不动2"])
            self.assertEqual(result["theme_index"], 1)
            self.assertEqual(result["score"], 81)

    async def test_ledger_redistill_is_hard_limited_to_one(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.settings(Path(temp_dir))
            date_value = "2026-08-23"
            self.write_json(
                settings.ledger_artifact(date_value),
                {"complete": True, "themes": [{"h": "A"}]},
            )
            judged = self.judge(score=68, passed=False)
            judged["redistill_count"] = 1
            self.write_json(settings.judge_path(date_value, "ledger"), judged)
            with self.assertRaises(server.EditorError) as raised:
                await server.redistill_theme_core(date_value, 0, "再试一次", settings)
            self.assertEqual(raised.exception.code, "redistill_exhausted")

    async def test_second_arsenal_run_uses_judge_feedback_once_without_recollecting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.settings(Path(temp_dir))
            date_value = "2026-08-23"
            artifact = settings.arsenal_artifact(date_value)
            candidates = settings.arsenal_home / "candidates" / f"{date_value}.jsonl"
            candidates.write_text('{"url":"https://example.com"}\n', encoding="utf-8")
            self.write_json(artifact, [{"id": "old"}])
            self.write_json(
                settings.judge_path(date_value, "arsenal"),
                self.judge(score=66, passed=False),
            )
            seen: list[list[str]] = []

            async def fake_run(argv, *, cwd, settings, accepted=None):
                seen.append(list(argv))
                if argv[1].endswith("distill.py"):
                    self.write_json(artifact, [{"id": "improved"}, {"id": "new"}])
                elif argv[1].endswith("judge.py"):
                    output = Path(argv[argv.index("--output") + 1])
                    payload = self.judge(score=76)
                    payload["redistill_count"] = 1
                    self.write_json(output, payload)
                return server.CommandResult(list(argv), 0, "", "")

            with patch.object(server, "run_command", side_effect=fake_run):
                result = await server.run_arsenal_core(date_value, settings)
            flattened = [item for argv in seen for item in argv]
            self.assertNotIn(str(settings.arsenal_home / "collect.py"), flattened)
            distill = next(argv for argv in seen if len(argv) > 1 and argv[1].endswith("distill.py"))
            self.assertIn("--judge-feedback", distill)
            self.assertEqual(result["redistill_count"], 1)
            self.assertTrue(result["redistilled"])
            self.assertEqual(result["new_items"], 2)

    def test_status_summarizes_judges_and_publish_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.settings(Path(temp_dir))
            date_value = "2026-08-23"
            self.seed_publishable(settings, date_value)
            self.write_json(settings.logs_dir / f"editor-publish-{date_value}.json", {"ok": True})
            result = server.status_core(date_value, settings)
            self.assertTrue(result["ok"])
            self.assertEqual(result["ledger"]["score"], 78)
            self.assertEqual(result["arsenal"]["score"], 82)
            self.assertTrue(result["publish"]["ok"])


if __name__ == "__main__":
    unittest.main()
