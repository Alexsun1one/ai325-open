#!/usr/bin/env python3
"""FastMCP stdio server for the 一一 editor workflow.

The server only orchestrates the existing ledger, arsenal, harness and publish
scripts.  It does not duplicate their distillation or quality rules.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import copy
from dataclasses import dataclass
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any, AsyncIterator, Awaitable, Callable

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator


SERVER_NAME = "ai325_editor_mcp"
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DEFAULT_COMMAND_TIMEOUT = 30 * 60


class EditorError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


class DateInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    date: str = Field(description="Edition date in YYYY-MM-DD format", min_length=10, max_length=10)

    @field_validator("date")
    @classmethod
    def valid_date(cls, value: str) -> str:
        if not DATE_PATTERN.fullmatch(value):
            raise ValueError("date must use YYYY-MM-DD")
        try:
            dt.date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("date must be a real calendar date") from exc
        return value


class ThemeInput(DateInput):
    idx: int = Field(description="Zero-based themes array index", ge=0, le=20)
    feedback: str = Field(
        description="Concrete judge feedback for this theme only",
        min_length=1,
        max_length=2_000,
    )


class AlertInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    text: str = Field(description="Actionable alert for Sun", min_length=1, max_length=2_000)


@dataclass(frozen=True)
class Settings:
    repo: Path
    ledger_home: Path
    arsenal_home: Path
    harness_home: Path
    materials_root: Path
    logs_dir: Path
    export_log: Path
    health_daily: Path
    lock_file: Path
    server_daily: Path
    alert_command: Path
    python: str
    arsenal_python: str
    judge_mode: str = "require-llm"
    public_base_url: str = ""
    command_timeout: float = DEFAULT_COMMAND_TIMEOUT

    @classmethod
    def from_env(cls) -> "Settings":
        source_repo = Path(__file__).resolve().parents[2]
        repo = Path(os.environ.get("AI325_REPO", source_repo)).resolve()
        ledger_home = Path(os.environ.get("AI325_LEDGER_HOME", repo / "hermes/ledger"))
        arsenal_home = Path(os.environ.get("AI325_ARSENAL_HOME", repo / "hermes/arsenal"))
        harness_home = Path(os.environ.get("AI325_HARNESS_HOME", repo / "hermes/harness"))
        logs_default = Path("/opt/xfsite/logs") if Path("/opt/xfsite").exists() else Path("/tmp/ai325-editor/logs")
        logs_dir = Path(os.environ.get("AI325_LOGS_DIR", logs_default))
        arsenal_venv_python = arsenal_home / ".venv/bin/python"
        return cls(
            repo=repo,
            ledger_home=ledger_home,
            arsenal_home=arsenal_home,
            harness_home=harness_home,
            materials_root=Path(os.environ.get("AI325_MATERIALS_ROOT", ledger_home / "materials")),
            logs_dir=logs_dir,
            export_log=Path(os.environ.get("AI325_EXPORT_LOG", "/opt/wechat-archive/export.log")),
            health_daily=Path(os.environ.get("AI325_HEALTH_DAILY", repo / "site/public/health/daily.json")),
            lock_file=Path(os.environ.get("AI325_EDITOR_LOCK_FILE", logs_dir / "ai325-editor.lock")),
            server_daily=Path(os.environ.get("AI325_SERVER_DAILY", repo / "scripts/server-daily.sh")),
            alert_command=Path(
                os.environ.get("AI325_ALERT_COMMAND", repo / "scripts/ops/alert.sh")
            ),
            python=os.environ.get("AI325_PYTHON", sys.executable),
            arsenal_python=os.environ.get(
                "AI325_ARSENAL_PYTHON",
                str(arsenal_venv_python if arsenal_venv_python.is_file() else sys.executable),
            ),
            judge_mode=os.environ.get("AI325_JUDGE_MODE", "require-llm"),
            public_base_url=os.environ.get("AI325_PUBLIC_BASE_URL", "").rstrip("/"),
            command_timeout=float(os.environ.get("AI325_COMMAND_TIMEOUT", DEFAULT_COMMAND_TIMEOUT)),
        )

    def work_dir(self, date_value: str) -> Path:
        return self.logs_dir / f"quality-work-{date_value}"

    def ledger_artifact(self, date_value: str) -> Path:
        return self.materials_root / date_value / "content.json"

    def arsenal_artifact(self, date_value: str) -> Path:
        return self.work_dir(date_value) / "arsenal.json"

    def judge_path(self, date_value: str, kind: str) -> Path:
        return self.work_dir(date_value) / f"{kind}-judge.json"


@dataclass(frozen=True)
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EditorError("missing_file", f"缺少文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise EditorError("invalid_json", f"JSON 损坏：{path}: {exc}") from exc


def safe_tail(value: str, limit: int = 6_000) -> str:
    return value[-limit:] if len(value) > limit else value


async def run_command(
    argv: list[str],
    *,
    cwd: Path,
    settings: Settings,
    accepted: set[int] | None = None,
) -> CommandResult:
    accepted = accepted or {0}
    if not argv or not Path(argv[0]).is_file() and "/" in argv[0]:
        raise EditorError("missing_command", f"命令不存在：{argv[0] if argv else '(empty)'}")
    env = os.environ.copy()
    env_file = Path(os.environ.get("HERMES_ENV_FILE", "/data/second-brain/hermes/.env"))
    if env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in env:
                env[key] = value
    env.update(
        {
            "AI325_EDITOR_LOCK_HELD": "1",
            "AI325_EDITOR_LOCK_FILE": str(settings.lock_file),
            "XF_REPO": str(settings.repo),
            "HERMES_MATERIALS_ROOT": str(settings.materials_root),
            "HERMES_HARNESS_DIR": str(settings.harness_home),
            "HERMES_PROMPTS_DIR": str(settings.repo / "hermes/prompts"),
        }
    )
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_raw, stderr_raw = await asyncio.wait_for(
            process.communicate(), timeout=settings.command_timeout
        )
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.communicate()
        raise EditorError("command_timeout", f"命令超过 {settings.command_timeout:g} 秒：{argv[0]}") from exc
    stdout = stdout_raw.decode("utf-8", errors="replace")
    stderr = stderr_raw.decode("utf-8", errors="replace")
    result = CommandResult(argv, process.returncode or 0, safe_tail(stdout), safe_tail(stderr))
    if result.returncode not in accepted:
        detail = result.stderr.strip() or result.stdout.strip() or "无输出"
        raise EditorError(
            "command_failed",
            f"命令失败 rc={result.returncode}：{Path(argv[0]).name}\n{safe_tail(detail)}",
        )
    return result


@asynccontextmanager
async def exclusive_editor_lock(settings: Settings) -> AsyncIterator[None]:
    settings.lock_file.parent.mkdir(parents=True, exist_ok=True)
    handle = settings.lock_file.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise EditorError(
                "editor_busy",
                f"一一总编或 23:55 兜底正在运行；锁：{settings.lock_file}",
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} at={dt.datetime.now(dt.timezone.utc).isoformat()}\n")
        handle.flush()
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def judge_summary(path: Path, artifact: Path) -> dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise EditorError("invalid_judge", f"judge 顶层不是对象：{path}")
    hard = [str(item) for item in payload.get("hard_fail", []) if isinstance(item, str)]
    soft = [str(item) for item in payload.get("soft", []) if isinstance(item, str)]
    suggestions = [str(item) for item in payload.get("suggestions", []) if isinstance(item, str)]
    score = int(payload.get("score", 0) or 0)
    passed = payload.get("passed") is True and score >= 70 and not hard
    return {
        "ok": True,
        "passed": passed,
        "publishable": passed,
        "score": score,
        "grade": str(payload.get("grade", "F")),
        "hard": hard,
        "soft": soft,
        "suggestions": suggestions,
        "artifact": str(artifact),
        "judge": str(path),
        "redistill_count": int(payload.get("redistill_count", 0) or 0),
    }


def artifact_complete(path: Path) -> bool:
    try:
        payload = load_json(path)
    except EditorError:
        return False
    return isinstance(payload, dict) and payload.get("complete") is True


def cached_result(settings: Settings, date_value: str, kind: str, artifact: Path) -> dict[str, Any] | None:
    judge = settings.judge_path(date_value, kind)
    if not artifact.is_file() or not judge.is_file():
        return None
    summary = judge_summary(judge, artifact)
    if not summary["passed"] or (kind == "ledger" and not artifact_complete(artifact)):
        return None
    summary["cached"] = True
    if kind == "arsenal":
        payload = load_json(artifact)
        summary["new_items"] = len(payload) if isinstance(payload, list) else 0
    return summary


def judge_argv(
    settings: Settings,
    date_value: str,
    kind: str,
    artifact: Path,
    *,
    redistill_count: int = 0,
) -> list[str]:
    argv = [
        settings.python,
        str(settings.harness_home / "judge.py"),
        str(artifact),
        "--kind",
        kind,
        "--date",
        date_value,
        "--previous-dir",
        str(settings.repo / "site/content/ledgers"),
        "--artifact-prompt-version",
        "ledger-v4" if kind == "ledger" else "arsenal-v3",
        "--output",
        str(settings.judge_path(date_value, kind)),
        "--redistill-count",
        str(redistill_count),
    ]
    if settings.judge_mode == "mechanical-only":
        argv.append("--mechanical-only")
    else:
        argv.append("--require-llm")
    if kind == "ledger":
        material = settings.materials_root / date_value
        argv.extend(["--transcript", str(material / "transcript.txt")])
        newcomers = material / "newcomers.json"
        usage = material / "distill-usage.json"
        if newcomers.is_file():
            argv.extend(["--newcomers", str(newcomers)])
        if usage.is_file():
            argv.extend(["--upstream-usage", str(usage)])
    else:
        argv.extend(["--candidates", str(settings.arsenal_home / "candidates" / f"{date_value}.jsonl")])
        usage = settings.work_dir(date_value) / "arsenal-usage.json"
        if usage.is_file():
            argv.extend(["--upstream-usage", str(usage)])
    return argv


async def run_judge(
    settings: Settings,
    date_value: str,
    kind: str,
    artifact: Path,
    *,
    redistill_count: int = 0,
) -> dict[str, Any]:
    settings.work_dir(date_value).mkdir(parents=True, exist_ok=True)
    await run_command(
        judge_argv(settings, date_value, kind, artifact, redistill_count=redistill_count),
        cwd=settings.repo,
        settings=settings,
        accepted={0, 2},
    )
    return judge_summary(settings.judge_path(date_value, kind), artifact)


async def refresh_health(settings: Settings, date_value: str) -> str | None:
    quality = settings.logs_dir / f"quality-{date_value}.json"
    try:
        await run_command(
            [
                settings.python,
                str(settings.harness_home / "health.py"),
                "combine",
                "--date",
                date_value,
                "--ledger-result",
                str(settings.judge_path(date_value, "ledger")),
                "--arsenal-result",
                str(settings.judge_path(date_value, "arsenal")),
                "--output",
                str(quality),
                "--alert-file",
                str(settings.logs_dir / "ALERT"),
                "--export-log",
                str(settings.export_log),
            ],
            cwd=settings.repo,
            settings=settings,
            accepted={0, 2},
        )
        await run_command(
            [
                settings.python,
                str(settings.harness_home / "health.py"),
                "aggregate",
                "--logs-dir",
                str(settings.logs_dir),
                "--output",
                str(settings.health_daily),
                "--days",
                "14",
                "--date",
                date_value,
            ],
            cwd=settings.repo,
            settings=settings,
        )
    except EditorError as exc:
        return exc.detail
    return None


async def run_ledger_core(date_value: str, settings: Settings) -> dict[str, Any]:
    cached = cached_result(settings, date_value, "ledger", settings.ledger_artifact(date_value))
    if cached:
        return cached
    async with exclusive_editor_lock(settings):
        material = settings.materials_root / date_value
        transcript = material / "transcript.txt"
        if not transcript.is_file():
            raise EditorError("missing_material", f"缺少日报材料：{transcript}")
        artifact = settings.ledger_artifact(date_value)
        settings.work_dir(date_value).mkdir(parents=True, exist_ok=True)
        await run_command(
            [str(settings.ledger_home / "run.sh"), date_value, "--output", str(artifact)],
            cwd=settings.ledger_home,
            settings=settings,
        )
        summary = await run_judge(settings, date_value, "ledger", artifact)
        summary["cached"] = False
        if not artifact_complete(artifact):
            summary["passed"] = False
            summary["publishable"] = False
            summary["hard"] = list(summary["hard"]) + ["content.complete 不是 true（partial 不可发布）"]
        warning = await refresh_health(settings, date_value)
        if warning:
            summary["health_warning"] = warning
        return summary


async def run_arsenal_core(date_value: str, settings: Settings) -> dict[str, Any]:
    artifact = settings.arsenal_artifact(date_value)
    cached = cached_result(settings, date_value, "arsenal", artifact)
    if cached:
        return cached
    prior_judge = settings.judge_path(date_value, "arsenal")
    retry_only = False
    if artifact.is_file() and prior_judge.is_file():
        previous = judge_summary(prior_judge, artifact)
        if previous["redistill_count"] >= 1:
            previous["cached"] = True
            previous["retry_exhausted"] = True
            payload = load_json(artifact)
            previous["new_items"] = len(payload) if isinstance(payload, list) else 0
            return previous
        retry_only = True
    async with exclusive_editor_lock(settings):
        work = settings.work_dir(date_value)
        work.mkdir(parents=True, exist_ok=True)
        candidates = settings.arsenal_home / "candidates" / f"{date_value}.jsonl"
        if not retry_only:
            await run_command(
                [
                    settings.arsenal_python,
                    str(settings.arsenal_home / "collect.py"),
                    "--date",
                    date_value,
                    "--output",
                    str(candidates),
                ],
                cwd=settings.arsenal_home,
                settings=settings,
            )
        distill_argv = [
            settings.arsenal_python,
            str(settings.arsenal_home / "distill.py"),
            "--date",
            date_value,
            "--candidates",
            str(candidates),
            "--ledger-dir",
            str(settings.repo / "site/content/ledgers"),
            "--output",
            str(artifact),
            "--usage-output",
            str(work / ("arsenal-usage-1.json" if retry_only else "arsenal-usage.json")),
        ]
        if retry_only:
            distill_argv.extend(["--judge-feedback", str(prior_judge)])
        await run_command(
            distill_argv,
            cwd=settings.arsenal_home,
            settings=settings,
        )
        summary = await run_judge(
            settings,
            date_value,
            "arsenal",
            artifact,
            redistill_count=1 if retry_only else 0,
        )
        payload = load_json(artifact)
        summary.update(
            {
                "cached": False,
                "redistilled": retry_only,
                "new_items": len(payload) if isinstance(payload, list) else 0,
            }
        )
        warning = await refresh_health(settings, date_value)
        if warning:
            summary["health_warning"] = warning
        return summary


async def redistill_theme_core(
    date_value: str,
    idx: int,
    feedback: str,
    settings: Settings,
) -> dict[str, Any]:
    async with exclusive_editor_lock(settings):
        artifact = settings.ledger_artifact(date_value)
        prior_judge = settings.judge_path(date_value, "ledger")
        if prior_judge.is_file():
            prior = judge_summary(prior_judge, artifact)
            if prior["redistill_count"] >= 1:
                raise EditorError(
                    "redistill_exhausted",
                    f"{date_value} 日报已经重蒸 1 次；按总编铁律不得再次重蒸",
                )
        original = load_json(artifact)
        if not isinstance(original, dict) or not isinstance(original.get("themes"), list):
            raise EditorError("invalid_artifact", f"日报 themes 不可用：{artifact}")
        if idx >= len(original["themes"]):
            raise EditorError("theme_out_of_range", f"themes[{idx}] 不存在；当前共 {len(original['themes'])} 幕")
        work = settings.work_dir(date_value)
        work.mkdir(parents=True, exist_ok=True)
        feedback_path = work / f"editor-theme-feedback-{idx}.json"
        candidate_path = work / f"ledger-theme-{idx}.json"
        atomic_write_json(
            feedback_path,
            {
                "hard_fail": [],
                "suggestions": [f"只改 themes[{idx}]：{feedback}"],
                "source": "一一总编 redistill_theme",
            },
        )
        await run_command(
            [
                str(settings.ledger_home / "run.sh"),
                date_value,
                "--output",
                str(candidate_path),
                "--judge-feedback",
                str(feedback_path),
            ],
            cwd=settings.ledger_home,
            settings=settings,
        )
        candidate = load_json(candidate_path)
        if not isinstance(candidate, dict) or not isinstance(candidate.get("themes"), list) or idx >= len(candidate["themes"]):
            raise EditorError("invalid_redistill", f"局部重蒸没有返回 themes[{idx}]")
        merged = copy.deepcopy(original)
        merged["themes"][idx] = candidate["themes"][idx]
        atomic_write_json(artifact, merged)
        try:
            await run_command(
                [
                    settings.python,
                    str(settings.ledger_home / "distill_ledger.py"),
                    str(settings.materials_root / date_value),
                    "--date",
                    date_value,
                    "--ledger-dir",
                    str(settings.repo / "site/content/ledgers"),
                    "--validate-only",
                    str(artifact),
                ],
                cwd=settings.ledger_home,
                settings=settings,
            )
        except EditorError:
            atomic_write_json(artifact, original)
            raise
        summary = await run_judge(
            settings, date_value, "ledger", artifact, redistill_count=1
        )
        summary.update({"theme_index": idx, "feedback": feedback, "cached": False})
        if not artifact_complete(artifact):
            summary["passed"] = False
            summary["publishable"] = False
            summary["hard"] = list(summary["hard"]) + ["content.complete 不是 true（partial 不可发布）"]
        warning = await refresh_health(settings, date_value)
        if warning:
            summary["health_warning"] = warning
        return summary


def publish_fingerprint(settings: Settings, date_value: str) -> str:
    paths = [
        settings.ledger_artifact(date_value),
        settings.arsenal_artifact(date_value),
        settings.judge_path(date_value, "ledger"),
        settings.judge_path(date_value, "arsenal"),
    ]
    digest = hashlib.sha256()
    for path in paths:
        if not path.is_file():
            raise EditorError("missing_publish_input", f"发布输入缺失：{path}")
        digest.update(str(path).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def assert_publishable(settings: Settings, date_value: str) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger = judge_summary(
        settings.judge_path(date_value, "ledger"), settings.ledger_artifact(date_value)
    )
    arsenal = judge_summary(
        settings.judge_path(date_value, "arsenal"), settings.arsenal_artifact(date_value)
    )
    failures: list[str] = []
    for kind, result in (("ledger", ledger), ("arsenal", arsenal)):
        if not result["publishable"]:
            failures.append(
                f"{kind} 不可发布：score={result['score']} hard={' | '.join(result['hard']) or '(none)'}"
            )
    if not artifact_complete(settings.ledger_artifact(date_value)):
        failures.append("ledger content.complete 不是 true（partial 不可发布）")
    arsenal_payload = load_json(settings.arsenal_artifact(date_value))
    if not isinstance(arsenal_payload, list) or not arsenal_payload:
        failures.append("arsenal staging 不是非空数组")
    if failures:
        raise EditorError("quality_gate_blocked", "；".join(failures))
    return ledger, arsenal


async def publish_core(date_value: str, settings: Settings) -> dict[str, Any]:
    async with exclusive_editor_lock(settings):
        ledger, arsenal = assert_publishable(settings, date_value)
        fingerprint = publish_fingerprint(settings, date_value)
        marker = settings.logs_dir / f"editor-publish-{date_value}.json"
        if marker.is_file():
            previous = load_json(marker)
            if isinstance(previous, dict) and previous.get("ok") is True and previous.get("fingerprint") == fingerprint:
                return {
                    "ok": True,
                    "published": True,
                    "idempotent": True,
                    "date": date_value,
                    "ledger_score": ledger["score"],
                    "arsenal_score": arsenal["score"],
                    "marker": str(marker),
                }
        await run_command(
            ["/bin/bash", str(settings.server_daily), date_value, "--publish-only"],
            cwd=settings.repo,
            settings=settings,
        )
        payload = {
            "ok": True,
            "published": True,
            "idempotent": False,
            "date": date_value,
            "ledger_score": ledger["score"],
            "arsenal_score": arsenal["score"],
            "fingerprint": fingerprint,
            "published_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
        atomic_write_json(marker, payload)
        payload["marker"] = str(marker)
        if settings.public_base_url:
            payload["links"] = {
                "ledger": f"{settings.public_base_url}/ledger/{date_value}",
                "arsenal": f"{settings.public_base_url}/arsenal",
                "health": f"{settings.public_base_url}/health/daily.json",
            }
        return payload


def status_core(date_value: str, settings: Settings) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": True, "date": date_value}
    for kind, artifact in (
        ("ledger", settings.ledger_artifact(date_value)),
        ("arsenal", settings.arsenal_artifact(date_value)),
    ):
        judge = settings.judge_path(date_value, kind)
        if judge.is_file() and artifact.is_file():
            result[kind] = judge_summary(judge, artifact)
        else:
            result[kind] = {
                "passed": False,
                "artifact_exists": artifact.is_file(),
                "judge_exists": judge.is_file(),
                "artifact": str(artifact),
                "judge": str(judge),
            }
    quality = settings.logs_dir / f"quality-{date_value}.json"
    result["quality"] = load_json(quality) if quality.is_file() else None
    marker = settings.logs_dir / f"editor-publish-{date_value}.json"
    result["publish"] = load_json(marker) if marker.is_file() else None
    alert_path = settings.logs_dir / "ALERT"
    result["alert"] = safe_tail(alert_path.read_text(encoding="utf-8"), 2_000) if alert_path.is_file() else None
    result["health_daily"] = str(settings.health_daily)
    return result


async def alert_core(text: str, settings: Settings) -> dict[str, Any]:
    async with exclusive_editor_lock(settings):
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        payload = {"at": now, "source": "一一总编", "message": text}
        atomic_write_json(settings.logs_dir / "ALERT", payload)
        settings.export_log.parent.mkdir(parents=True, exist_ok=True)
        with settings.export_log.open("a", encoding="utf-8") as handle:
            handle.write(f"[{now}] [editor-alert] {text.replace(chr(10), ' ')}\n")
        delivery = await run_command(
            [
                str(settings.alert_command),
                "ERROR",
                "hermes-editor",
                text,
                "--key",
                "hermes-editor",
                "--cooldown",
                "1800",
            ],
            cwd=settings.repo,
            settings=settings,
        )
        return {
            "ok": True,
            "alert": str(settings.logs_dir / "ALERT"),
            "export_log": str(settings.export_log),
            "delivery": "queued_or_sent",
            "delivery_status": delivery.stdout.strip(),
        }


async def tool_call(
    action: str, operation: Callable[[], Awaitable[dict[str, Any]]]
) -> dict[str, Any]:
    try:
        return await operation()
    except EditorError as exc:
        return {"ok": False, "action": action, "error_code": exc.code, "error": exc.detail}
    except OSError as exc:
        return {"ok": False, "action": action, "error_code": "os_error", "error": str(exc)}


mcp = FastMCP(SERVER_NAME)


@mcp.tool(
    name="run_ledger",
    annotations={
        "title": "Distill and Judge Ledger",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def run_ledger(date: str) -> dict[str, Any]:
    """Distill and judge one Ledger edition without publishing it.

    Input: date in YYYY-MM-DD. Output includes score, hard/soft findings,
    suggestions, publishability and artifact/judge paths. A prior passing result
    is returned idempotently. This tool never builds, rsyncs, commits or pushes.
    """
    params = DateInput(date=date)
    settings = Settings.from_env()
    return await tool_call("run_ledger", lambda: run_ledger_core(params.date, settings))


@mcp.tool(
    name="run_arsenal",
    annotations={
        "title": "Collect, Distill and Judge Arsenal",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def run_arsenal(date: str) -> dict[str, Any]:
    """Collect, distill and judge one Arsenal edition without publishing it.

    Input: date in YYYY-MM-DD. Output includes score, findings, suggestions,
    staged artifact path and new item count. A passing stage is reused.
    """
    params = DateInput(date=date)
    settings = Settings.from_env()
    return await tool_call("run_arsenal", lambda: run_arsenal_core(params.date, settings))


@mcp.tool(
    name="redistill_theme",
    annotations={
        "title": "Redistill One Ledger Theme",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def redistill_theme(date: str, idx: int, feedback: str) -> dict[str, Any]:
    """Redistill and replace only one zero-based Ledger theme, then rejudge.

    The current artifact is restored if merged validation fails. The editor
    workflow may invoke this at most once per edition; this tool never publishes.
    """
    params = ThemeInput(date=date, idx=idx, feedback=feedback)
    settings = Settings.from_env()
    return await tool_call(
        "redistill_theme",
        lambda: redistill_theme_core(params.date, params.idx, params.feedback, settings),
    )


@mcp.tool(
    name="publish",
    annotations={
        "title": "Publish Passing Daily Edition",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def publish(date: str) -> dict[str, Any]:
    """Publish only when Ledger and Arsenal both pass score 70 with no hard failures.

    The tool also rejects partial Ledger content. It invokes the existing
    server-daily build/publish segment and fingerprints inputs for idempotence.
    """
    params = DateInput(date=date)
    settings = Settings.from_env()
    return await tool_call("publish", lambda: publish_core(params.date, settings))


@mcp.tool(
    name="status",
    annotations={
        "title": "Read Editor Quality Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def status(date: str) -> dict[str, Any]:
    """Read judge, artifact, quality, alert and publish-marker status for a date."""
    params = DateInput(date=date)
    try:
        return status_core(params.date, Settings.from_env())
    except EditorError as exc:
        return {"ok": False, "action": "status", "error_code": exc.code, "error": exc.detail}


@mcp.tool(
    name="alert",
    annotations={
        "title": "Write Editor Alert",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def alert(text: str) -> dict[str, Any]:
    """Write an actionable ALERT and append export.log without exposing secrets."""
    params = AlertInput(text=text)
    settings = Settings.from_env()
    return await tool_call("alert", lambda: alert_core(params.text, settings))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list-tools", action="store_true", help="Print tool names and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_tools:
        print(json.dumps({"server": SERVER_NAME, "tools": ["run_ledger", "run_arsenal", "redistill_theme", "publish", "status", "alert"]}, ensure_ascii=False))
        return 0
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
