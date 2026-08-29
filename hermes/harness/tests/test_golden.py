from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
HARNESS = HERE.parent
REPO = HARNESS.parents[1]
GOLDEN = HERE / "golden"

sys.path.insert(0, str(HARNESS))
import health
import judge
import stamp


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ledger = load_module("ledger_distill_for_harness", REPO / "hermes/ledger/distill_ledger.py")


def test_all_prompts_are_versioned_and_runtime_versions_match() -> None:
    prompt_dir = REPO / "hermes/prompts"
    expected = {
        "ledger-extract-v3.md": "ledger-v3",
        "ledger-skeleton-v3.md": "ledger-v3",
        "ledger-fill-v3.md": "ledger-v3",
        "arsenal-distill-v3.md": "arsenal-v3",
        "judge-v1.md": "judge-v1",
    }
    for name, version in expected.items():
        text = (prompt_dir / name).read_text(encoding="utf-8")
        assert f"prompt_version: {version}" in text
    assert ledger.PROMPT_VERSION == "ledger-v3"
    assert judge.PROMPT_VERSION == "judge-v1"


def test_ledger_dry_run_passes_runtime_schema_and_hard_self_check() -> None:
    material = ledger.load_materials(REPO / "hermes/ledger/sample")
    content = ledger.dry_run_content("2026-08-23", material["stats"], {}, "deepseek-chat")
    warnings: list[str] = []
    content = ledger.normalize_content(
        content,
        material["transcript"],
        material["stats"],
        {},
        "2026-08-23",
        "deepseek-chat",
        warnings,
    )
    ledger.validate_content(content, "2026-08-23")
    checks = ledger.self_check(content, material["transcript"], warnings)
    assert checks["quotes_verified"] >= 5
    assert content["prompt_version"] == "ledger-v3"


def test_real_0823_ledger_structure_stays_within_40_percent_of_golden() -> None:
    reference = json.loads((GOLDEN / "ledger-metrics.json").read_text(encoding="utf-8"))
    artifact = json.loads((REPO / reference["source"]).read_text(encoding="utf-8"))
    for field in ("themes", "quotes", "threads", "events", "tone_notes", "members_focus"):
        actual = len(artifact.get(field, []))
        expected = reference[field]
        deviation = abs(actual - expected) / max(1, expected)
        assert deviation <= reference["tolerance"], (field, actual, expected, deviation)


def test_arsenal_golden_has_30_candidates_and_real_output_keeps_provenance() -> None:
    candidate_rows = [
        json.loads(line)
        for line in (GOLDEN / "arsenal-candidates.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(candidate_rows) == 30
    candidate_urls = {row["url"].rstrip("/") for row in candidate_rows}
    artifact = json.loads((REPO / "site/content/arsenal/2026-08-23.json").read_text(encoding="utf-8"))
    assert 8 <= len(artifact) <= 15
    assert all(item["source"]["url"].rstrip("/") in candidate_urls for item in artifact)
    thread_ids = {
        item["id"]
        for item in json.loads((REPO / "site/content/ledgers/2026-08-23.json").read_text(encoding="utf-8"))["threads"]
    }
    with_threads = [item for item in artifact if item.get("threads")]
    hits = [item for item in with_threads if set(item["threads"]) & thread_ids]
    assert with_threads and len(hits) / len(with_threads) >= 0.5


def test_mechanical_judge_passes_deterministic_dry_ledger() -> None:
    material = ledger.load_materials(REPO / "hermes/ledger/sample")
    artifact = ledger.dry_run_content("2026-08-23", material["stats"], {}, "deepseek-chat")
    warnings: list[str] = []
    artifact = ledger.normalize_content(
        artifact, material["transcript"], material["stats"], {}, "2026-08-23", "deepseek-chat", warnings
    )
    score, hard, _soft, _suggestions, metrics, _context = judge.ledger_mechanical(
        artifact, REPO / "hermes/ledger/sample/transcript.txt", {}, []
    )
    assert not hard
    assert score >= 70
    assert metrics["quotes_verified"] == 6


def test_health_combine_alert_and_14_day_aggregate(tmp_path: Path) -> None:
    ledger_result = tmp_path / "ledger.json"
    arsenal_result = tmp_path / "arsenal.json"
    ledger_result.write_text(
        json.dumps({"passed": True, "score": 88, "grade": "A", "hard_fail": [], "soft": [], "suggestions": [], "redistill_count": 0, "elapsed_ms": 10, "token_usage": {"total_tokens": 20}, "prompt_version": "judge-v1", "artifact_prompt_version": "ledger-v3"}),
        encoding="utf-8",
    )
    arsenal_result.write_text(
        json.dumps({"passed": True, "score": 78, "grade": "B", "hard_fail": [], "soft": [], "suggestions": [], "redistill_count": 1, "elapsed_ms": 20, "token_usage": {"total_tokens": 30}, "prompt_version": "judge-v1", "artifact_prompt_version": "arsenal-v3"}),
        encoding="utf-8",
    )
    quality = tmp_path / "quality-2026-08-23.json"
    args = type("Args", (), {"date": "2026-08-23", "ledger_result": ledger_result, "arsenal_result": arsenal_result, "output": quality, "alert_file": tmp_path / "ALERT", "export_log": tmp_path / "export.log"})()
    assert health.combine(args) == 0
    merged = json.loads(quality.read_text(encoding="utf-8"))
    assert merged["passed"] is True and merged["score"] == 78 and merged["grade"] == "B"
    assert merged["redistill_count"] == 1 and merged["token_usage"]["total_tokens"] == 50
    output = tmp_path / "daily.json"
    view_args = type("Args", (), {"logs_dir": tmp_path, "output": output, "days": 14, "date": "2026-08-23"})()
    assert health.aggregate(view_args) == 0
    daily = json.loads(output.read_text(encoding="utf-8"))
    assert daily["summary"] == {"days": 1, "passed": 1, "failed": 0, "average_score": 78.0}


def test_stamp_puts_prompt_and_quality_in_visible_footer(tmp_path: Path, monkeypatch) -> None:
    ledger_path = tmp_path / "ledger.json"
    judge_path = tmp_path / "judge.json"
    ledger_path.write_text(json.dumps({"credits": {}, "footer": []}), encoding="utf-8")
    judge_path.write_text(json.dumps({"score": 78, "grade": "B", "prompt_version": "judge-v1"}), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["stamp.py", str(ledger_path), "--judge-result", str(judge_path), "--prompt-version", "ledger-v3", "--model", "deepseek-chat"])
    assert stamp.main() == 0
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert payload["credits"]["prompt_version"] == "ledger-v3"
    assert payload["quality_gate"] == {"score": 78, "grade": "B", "judge_prompt_version": "judge-v1"}
    assert "本期自检 78 分" in payload["footer"][-1]


def test_llm_judge_is_temperature_zero_json_mode_and_reports_tokens(monkeypatch) -> None:
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self) -> bytes:
            content = {
                "deep_score": 80,
                "tone_score": 81,
                "style_score": 82,
                "continuity_score": 83,
                "soft": [],
                "suggestions": [],
            }
            return json.dumps(
                {
                    "choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                }
            ).encode()

    captured = {}

    def fake_urlopen(req, timeout):
        captured["body"] = json.loads(req.data)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(judge.request, "urlopen", fake_urlopen)
    result, usage = judge.llm_judge({"title": "test"}, "key", "deepseek-chat", 12)
    assert result["style_score"] == 82
    assert usage == {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
    assert captured["body"]["temperature"] == 0
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["timeout"] == 12


def test_server_daily_blocks_build_until_both_quality_results_pass() -> None:
    script = (REPO / "scripts/server-daily.sh").read_text(encoding="utf-8")
    assert 'ARSENAL_STAGE="$QUALITY_WORK/arsenal.json"' in script
    assert "--require-llm" in script
    assert "--judge-feedback" in script
    assert "quality-$DAY.json" in script
    assert "/opt/xfsite/logs/ALERT" in script
    assert "site/public/health/daily.json" in script
    build_function = script.index("build_and_publish()")
    build_command = script.index("npm run build", build_function)
    publish_command = script.index("rsync -a --delete", build_command)
    assert build_function < build_command < publish_command

    publish_only = script.index('if [ "$MODE" = "publish-only" ]')
    publish_only_gate = script.index("if ! judge_publishable", publish_only)
    publish_only_build = script.index("build_and_publish || exit 1", publish_only_gate)
    full_gate = script.index('if [ "$QUALITY_BLOCK" -ne 0 ]', publish_only_build)
    full_build = script.index("build_and_publish || exit 1", full_gate)
    assert publish_only_gate < publish_only_build < full_gate < full_build


def test_failed_combined_gate_leaves_alert_and_export_log(tmp_path: Path) -> None:
    ledger_result = tmp_path / "ledger.json"
    arsenal_result = tmp_path / "arsenal.json"
    ledger_result.write_text(
        json.dumps({"passed": False, "score": 60, "hard_fail": ["金句失真"], "soft": [], "suggestions": ["重蒸"], "redistill_count": 1, "elapsed_ms": 10, "token_usage": {"total_tokens": 12}}),
        encoding="utf-8",
    )
    arsenal_result.write_text(
        json.dumps({"passed": True, "score": 90, "hard_fail": [], "soft": [], "suggestions": [], "redistill_count": 0, "elapsed_ms": 10, "token_usage": {"total_tokens": 8}}),
        encoding="utf-8",
    )
    alert = tmp_path / "ALERT"
    export_log = tmp_path / "export.log"
    args = type("Args", (), {"date": "2026-08-23", "ledger_result": ledger_result, "arsenal_result": arsenal_result, "output": tmp_path / "quality-2026-08-23.json", "alert_file": alert, "export_log": export_log})()
    assert health.combine(args) == 2
    assert "金句失真" in alert.read_text(encoding="utf-8")
    assert "[quality-fail]" in export_log.read_text(encoding="utf-8")
