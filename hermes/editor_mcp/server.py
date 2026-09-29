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
import shlex
import sys
import tempfile
import traceback
from typing import Any, AsyncIterator, Awaitable, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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


class IncidentInput(DateInput):
    found: str = Field(description="故障发现描述", min_length=1, max_length=500)
    action: str = Field(description="尝试的自愈动作", min_length=1, max_length=500)
    result: str = Field(description="动作结果", min_length=1, max_length=1_000)
    level: str = Field(default="INFO", min_length=4, max_length=8)
    incident: str = Field(default="manual", min_length=1, max_length=120)
    attempt: int = Field(default=0, ge=0, le=99)

    @field_validator("level")
    @classmethod
    def valid_level(cls, value: str) -> str:
        value = value.upper()
        if value not in {"INFO", "WARN", "ERROR", "CRITICAL"}:
            raise ValueError("level must be INFO, WARN, ERROR or CRITICAL")
        return value


class SelfHealInput(DateInput):
    trigger: str = Field(default="manual", min_length=1, max_length=40)


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
    governed_root: Path | None = None
    db_path: Path | None = None
    integrity_script: Path | None = None
    self_check_enabled: bool = False
    require_coverage_check: bool = False
    require_page_check: bool = False
    coverage_min: float = 0.70
    public_timeout: float = 10.0
    reexport_command: tuple[str, ...] = ()
    rematerialize_command: tuple[str, ...] = ()
    self_heal_state_dir: Path | None = None
    self_heal_retry_delay: float = 600.0
    self_heal_max_attempts: int = 2
    collection_max_attempts: int = 1
    script_crash_window: float = 3600.0

    @classmethod
    def from_env(cls) -> "Settings":
        source_repo = Path(__file__).resolve().parents[2]
        repo = Path(os.environ.get("AI325_REPO", source_repo)).resolve()
        production = Path("/opt/xfsite").exists()
        ledger_home = Path(os.environ.get("AI325_LEDGER_HOME", repo / "hermes/ledger"))
        arsenal_home = Path(os.environ.get("AI325_ARSENAL_HOME", repo / "hermes/arsenal"))
        harness_home = Path(os.environ.get("AI325_HARNESS_HOME", repo / "hermes/harness"))
        materials_default = (
            Path("/opt/hermes-ledger/materials")
            if production
            else ledger_home / "materials"
        )
        materials_value = os.environ.get("AI325_MATERIALS_ROOT", "").strip()
        logs_default = Path("/opt/xfsite/logs") if Path("/opt/xfsite").exists() else Path("/tmp/ai325-editor/logs")
        logs_dir = Path(os.environ.get("AI325_LOGS_DIR", logs_default))
        arsenal_venv_python = arsenal_home / ".venv/bin/python"
        public_base_url = os.environ.get(
            "AI325_PUBLIC_BASE_URL",
            "https://www.ai325.com" if production else "",
        ).rstrip("/")

        def env_bool(name: str, default: bool) -> bool:
            value = os.environ.get(name)
            if value is None:
                return default
            return value.strip().lower() in {"1", "true", "yes", "on"}

        def env_command(name: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
            value = os.environ.get(name, "").strip()
            return tuple(shlex.split(value)) if value else default

        return cls(
            repo=repo,
            ledger_home=ledger_home,
            arsenal_home=arsenal_home,
            harness_home=harness_home,
            materials_root=Path(materials_value) if materials_value else materials_default,
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
            public_base_url=public_base_url,
            command_timeout=float(os.environ.get("AI325_COMMAND_TIMEOUT", DEFAULT_COMMAND_TIMEOUT)),
            governed_root=Path(
                os.environ.get(
                    "XF_GOVERNED",
                    "/opt/xfsite/data/governed" if production else str(repo / "site/content"),
                )
            ),
            db_path=Path(os.environ.get("XF_DB", "/opt/xfsite/data/xf.db")) if production or os.environ.get("XF_DB") else None,
            integrity_script=Path(os.environ.get("AI325_INTEGRITY_SCRIPT", repo / "scripts/ops/check-material-integrity.py")),
            self_check_enabled=env_bool("AI325_SELF_CHECK_ENABLED", production),
            require_coverage_check=env_bool("AI325_REQUIRE_COVERAGE_CHECK", production),
            require_page_check=env_bool("AI325_REQUIRE_PAGE_CHECK", production),
            coverage_min=float(os.environ.get("XF_TRANSCRIPT_COVERAGE_MIN", "0.70")),
            public_timeout=float(os.environ.get("AI325_PUBLIC_TIMEOUT", "10")),
            reexport_command=env_command(
                "AI325_SELF_HEAL_EXPORT_CMD",
                (str(repo / "scripts/morning-chain.sh"),),
            ),
            rematerialize_command=env_command("AI325_SELF_HEAL_MATERIAL_CMD"),
            self_heal_state_dir=Path(
                os.environ.get("AI325_SELF_HEAL_STATE_DIR", logs_dir / "self-heal")
            ),
            self_heal_retry_delay=float(os.environ.get("AI325_SELF_HEAL_RETRY_DELAY_SECONDS", "600")),
            self_heal_max_attempts=max(1, int(os.environ.get("AI325_SELF_HEAL_MAX_ATTEMPTS", "2"))),
            collection_max_attempts=max(1, int(os.environ.get("AI325_SELF_HEAL_COLLECTION_ATTEMPTS", "1"))),
            script_crash_window=float(os.environ.get("AI325_SCRIPT_CRASH_WINDOW_SECONDS", "3600")),
        )

    def work_dir(self, date_value: str) -> Path:
        return self.logs_dir / f"quality-work-{date_value}"

    def ledger_artifact(self, date_value: str) -> Path:
        return self.materials_root / date_value / "content.json"

    def arsenal_artifact(self, date_value: str) -> Path:
        return self.work_dir(date_value) / "arsenal.json"

    def judge_path(self, date_value: str, kind: str) -> Path:
        return self.work_dir(date_value) / f"{kind}-judge.json"

    def governed_ledger(self, date_value: str) -> Path:
        root = self.governed_root or (self.repo / "site/content")
        return root / "ledgers" / f"{date_value}.json"

    def governed_arsenal(self, date_value: str) -> Path:
        root = self.governed_root or (self.repo / "site/content")
        return root / "arsenal" / f"{date_value}.json"

    def self_heal_state_path(self, date_value: str) -> Path:
        root = self.self_heal_state_dir or (self.logs_dir / "self-heal")
        return root / f"{date_value}.json"


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
            "AI325_REPO": str(settings.repo),
            "AI325_LEDGER_HOME": str(settings.ledger_home),
            "AI325_ARSENAL_HOME": str(settings.arsenal_home),
            "AI325_HARNESS_HOME": str(settings.harness_home),
            "AI325_MATERIALS_ROOT": str(settings.materials_root),
            "AI325_LOGS_DIR": str(settings.logs_dir),
            "AI325_EXPORT_LOG": str(settings.export_log),
            "HERMES_MATERIALS_ROOT": str(settings.materials_root),
            "HERMES_HARNESS_DIR": str(settings.harness_home),
            "HERMES_PROMPTS_DIR": str(settings.repo / "hermes/prompts"),
            # server-daily/daily-publish have a post-publish hook.  Calls made
            # by the MCP self-heal core already run their own check and must
            # not recurse through that shell hook.
            "AI325_SELF_HEAL_SKIP_POST": "1",
        }
    )
    if settings.db_path is not None:
        env["XF_DB"] = str(settings.db_path)
    if settings.governed_root is not None:
        env["XF_GOVERNED"] = str(settings.governed_root)
    if settings.public_base_url:
        env["AI325_PUBLIC_BASE_URL"] = settings.public_base_url
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


async def material_integrity(
    date_value: str,
    settings: Settings,
    *,
    required: bool | None = None,
) -> dict[str, Any]:
    """Run the repository's authoritative transcript/DB coverage gate.

    The checker deliberately remains a separate script so the shell fallback
    and the editor MCP use exactly the same counting semantics.  A missing
    database is reported as unavailable in local/test profiles, while a
    production profile (or an explicit ``required`` flag) fails closed.
    """
    required = settings.require_coverage_check if required is None else required
    transcript = settings.materials_root / date_value / "transcript.txt"
    db_path = settings.db_path
    script = settings.integrity_script
    if script is None or not script.is_file():
        script = settings.repo / "scripts/ops/check-material-integrity.py"
    missing: list[str] = []
    if db_path is None:
        missing.append("db 配置")
    elif not db_path.is_file():
        missing.append("db 文件")
    if not transcript.is_file():
        missing.append("transcript 文件")
    if not script.is_file():
        missing.append("完整性脚本")
    if missing:
        detail = {
            "available": False,
            "required": required,
            "db": str(db_path) if db_path else None,
            "transcript": str(transcript),
            "script": str(script),
            "missing": missing,
            "reason": "evidence_missing",
        }
        if required:
            detail["error"] = "coverage gate inputs unavailable"
        return detail
    try:
        result = await run_command(
            [
                settings.python,
                str(script),
                "--db",
                str(db_path),
                "--date",
                date_value,
                "--transcript",
                str(transcript),
                "--min-ratio",
                f"{settings.coverage_min:.6f}",
            ],
            cwd=settings.repo,
            settings=settings,
            accepted={0, 1},
        )
    except EditorError as exc:
        return {
            "available": False,
            "required": required,
            "db": str(db_path),
            "transcript": str(transcript),
            "script": str(script),
            "reason": "checker_failed",
            "error": exc.detail,
        }
    output = f"{result.stdout}\n{result.stderr}"
    match = re.search(
        r"transcript_messages=(?P<transcript>\d+)\s+"
        r"db_messages=(?P<db>\d+)\s+coverage=(?P<coverage>[0-9.]+)%\s+"
        r"threshold=(?P<threshold>[0-9.]+)%",
        output,
    )
    if not match:
        return {
            "available": False,
            "required": required,
            "db": str(db_path),
            "transcript": str(transcript),
            "script": str(script),
            "reason": "unparseable_checker_output",
            "error": f"完整性脚本输出无法解析：{safe_tail(output, 1_000)}",
        }
    transcript_messages = int(match.group("transcript"))
    db_messages = int(match.group("db"))
    ratio = transcript_messages / db_messages if db_messages else 0.0
    return {
        "available": True,
        "required": required,
        "transcript_messages": transcript_messages,
        "db_messages": db_messages,
        "coverage": ratio,
        "threshold": settings.coverage_min,
        "passed": result.returncode == 0 and ratio >= settings.coverage_min,
        "db": str(db_path),
        "transcript": str(transcript),
        "script": str(script),
    }


async def coverage_gate(date_value: str, settings: Settings) -> dict[str, Any]:
    result = await material_integrity(date_value, settings)
    if result.get("required") and not result.get("available"):
        raise EditorError("coverage_unavailable", f"覆盖率闸门无法执行：{result.get('error', result)}")
    if result.get("available") and not result.get("passed"):
        ratio = float(result.get("coverage", 0.0))
        raise EditorError(
            "coverage_low",
            f"transcript 覆盖率 {ratio:.2%} 低于阈值 {settings.coverage_min:.2%}，拒绝蒸馏/出刊",
        )
    return result


async def run_ledger_core(
    date_value: str,
    settings: Settings,
    *,
    force_redistill: bool = False,
) -> dict[str, Any]:
    integrity = await coverage_gate(date_value, settings)
    cached = None if force_redistill else cached_result(
        settings, date_value, "ledger", settings.ledger_artifact(date_value)
    )
    if cached:
        cached["integrity"] = integrity
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
        summary["integrity"] = integrity
        warning = await refresh_health(settings, date_value)
        if warning:
            summary["health_warning"] = warning
        return summary


async def run_ledger_retry_core(date_value: str, settings: Settings) -> dict[str, Any]:
    """Retry Ledger distillation once, feeding the previous judge result back."""
    integrity = await coverage_gate(date_value, settings)
    artifact = settings.ledger_artifact(date_value)
    prior_judge = settings.judge_path(date_value, "ledger")
    if prior_judge.is_file() and artifact.is_file():
        prior = judge_summary(prior_judge, artifact)
        if prior["redistill_count"] >= 1:
            raise EditorError(
                "redistill_exhausted",
                f"{date_value} 日报已经按 judge 建议重蒸过 1 次，停止继续重试",
            )
    async with exclusive_editor_lock(settings):
        material = settings.materials_root / date_value
        transcript = material / "transcript.txt"
        if not transcript.is_file():
            raise EditorError("missing_material", f"缺少日报材料：{transcript}")
        settings.work_dir(date_value).mkdir(parents=True, exist_ok=True)
        feedback = prior_judge if prior_judge.is_file() else None
        argv = [str(settings.ledger_home / "run.sh"), date_value, "--output", str(artifact)]
        if feedback:
            argv.extend(["--judge-feedback", str(feedback)])
        await run_command(argv, cwd=settings.ledger_home, settings=settings)
        summary = await run_judge(settings, date_value, "ledger", artifact, redistill_count=1)
        summary["cached"] = False
        summary["redistilled"] = True
        summary["integrity"] = integrity
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


def _optional_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _recent_log_evidence(settings: Settings, date_value: str) -> dict[str, Any] | None:
    """Return a recent traceback/command failure without treating old logs as live."""
    candidates = [settings.logs_dir / f"daily-{date_value}.log", settings.logs_dir / f"self-heal-{date_value}.log"]
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    for path in candidates:
        try:
            stat = path.stat()
        except OSError:
            continue
        if settings.script_crash_window > 0 and now - stat.st_mtime > settings.script_crash_window:
            continue
        tail = safe_tail(path.read_text(encoding="utf-8", errors="replace"), 4_000)
        starts = list(re.finditer(r"=== .*daily start", tail))
        current = tail[starts[-1].start() :] if starts else tail
        if re.search(
            r"Traceback \(most recent call last\)|脚本.*崩溃|script\s+(?:crash|failed)|command failed rc=|\bfatal\b",
            current,
            re.I,
        ):
            return {"path": str(path), "tail": current}
    return None


async def _probe_public_page(settings: Settings, date_value: str) -> dict[str, Any]:
    url = f"{settings.public_base_url}/ledger/{date_value}/" if settings.public_base_url else ""
    if not url:
        return {"checked": False, "required": settings.require_page_check, "url": None, "reason": "public_base_url 未配置"}

    def request() -> dict[str, Any]:
        request_obj = Request(url, headers={"User-Agent": "ai325-hermes-selfcheck/1"})
        try:
            with urlopen(request_obj, timeout=settings.public_timeout) as response:
                return {"checked": True, "required": settings.require_page_check, "url": url, "status": response.status, "passed": response.status == 200}
        except HTTPError as exc:
            return {"checked": True, "required": settings.require_page_check, "url": url, "status": exc.code, "passed": False, "error": str(exc)}
        except (URLError, TimeoutError, OSError) as exc:
            return {"checked": True, "required": settings.require_page_check, "url": url, "status": None, "passed": False, "error": str(exc)}

    return await asyncio.to_thread(request)


async def diagnose_publish_core(date_value: str, settings: Settings) -> dict[str, Any]:
    """Inspect the user-visible delivery surface after a publish attempt."""
    ledger_artifact = settings.ledger_artifact(date_value)
    ledger_judge_path = settings.judge_path(date_value, "ledger")
    ledger_governed = settings.governed_ledger(date_value)
    arsenal_artifact = settings.arsenal_artifact(date_value)
    arsenal_judge_path = settings.judge_path(date_value, "arsenal")
    arsenal_governed = settings.governed_arsenal(date_value)
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def issue(kind: str, target: str, summary: str, evidence: Any, action: str) -> None:
        issues.append(
            {
                "kind": kind,
                "target": target,
                "summary": summary,
                "evidence": evidence,
                "action": action,
                "incident": f"{date_value}:{kind}:{target}",
            }
        )

    crash = _recent_log_evidence(settings, date_value)
    if crash:
        issue(
            "script_crash",
            "pipeline",
            "出刊脚本最近一次执行崩溃",
            crash,
            "收集 traceback 与最近日志并升级，不盲目重试",
        )

    ledger_judge: dict[str, Any] | None = None
    if ledger_judge_path.is_file() and ledger_artifact.is_file():
        try:
            ledger_judge = judge_summary(ledger_judge_path, ledger_artifact)
        except EditorError as exc:
            issue("artifact_missing", "ledger_judge", "日报 judge 文件损坏", str(exc), "只重跑日报评审")
    elif ledger_artifact.is_file() and not ledger_judge_path.is_file():
        issue("artifact_missing", "ledger_judge", "日报 judge 产物缺失", str(ledger_judge_path), "只重跑日报评审")
    elif not ledger_artifact.is_file():
        issue("artifact_missing", "ledger_staging", "日报 content.json 产物缺失", str(ledger_artifact), "只重蒸日报")
    elif ledger_judge and not ledger_judge.get("publishable"):
        issue(
            "judge_gate",
            "ledger",
            "日报 judge 门禁未通过",
            {"hard": ledger_judge.get("hard", []), "suggestions": ledger_judge.get("suggestions", []), "score": ledger_judge.get("score")},
            "按 judge hard_fail/suggestions 重蒸日报",
        )
    if ledger_judge is not None and not ledger_judge.get("publishable"):
        issue(
            "judge_gate",
            "ledger",
            "日报 judge 门禁未通过",
            {"hard": ledger_judge.get("hard", []), "suggestions": ledger_judge.get("suggestions", []), "score": ledger_judge.get("score")},
            "按 judge hard_fail/suggestions 重蒸日报",
        )

    arsenal_judge: dict[str, Any] | None = None
    if arsenal_judge_path.is_file() and arsenal_artifact.is_file():
        try:
            arsenal_judge = judge_summary(arsenal_judge_path, arsenal_artifact)
        except EditorError as exc:
            issue("artifact_missing", "arsenal_judge", "军火库 judge 文件损坏", str(exc), "只重跑军火库评审")
    elif arsenal_artifact.is_file() and not arsenal_judge_path.is_file():
        issue("artifact_missing", "arsenal_judge", "军火库 judge 产物缺失", str(arsenal_judge_path), "只重跑军火库评审")
    elif not arsenal_artifact.is_file():
        issue("artifact_missing", "arsenal_staging", "军火库 staging 产物缺失", str(arsenal_artifact), "只补军火库步骤")
    if arsenal_judge is not None and not arsenal_judge.get("publishable"):
        issue(
            "judge_gate",
            "arsenal",
            "军火库 judge 门禁未通过",
            {"hard": arsenal_judge.get("hard", []), "suggestions": arsenal_judge.get("suggestions", []), "score": arsenal_judge.get("score")},
            "按 judge hard_fail/suggestions 重蒸军火库",
        )

    if not ledger_governed.is_file():
        issue("artifact_missing", "ledger_governed", "治理 Ledger 未落盘", str(ledger_governed), "只补日报产物晋升")
    if not arsenal_governed.is_file():
        issue("artifact_missing", "arsenal_governed", "治理军火库未落盘", str(arsenal_governed), "只补军火库产物晋升")

    governed_payload = _optional_json(ledger_governed)
    quality_snapshot: dict[str, Any] | None = None
    if ledger_governed.is_file() and not isinstance(governed_payload, dict):
        issue(
            "artifact_missing",
            "ledger_governed",
            "治理 Ledger JSON 损坏或顶层格式错误",
            str(ledger_governed),
            "只补日报产物晋升",
        )
    elif isinstance(governed_payload, dict):
        if governed_payload.get("date") not in {None, date_value}:
            issue(
                "artifact_missing",
                "ledger_governed",
                "治理 Ledger 日期与本期不一致",
                {"path": str(ledger_governed), "date": governed_payload.get("date")},
                "只补日报产物晋升",
            )
        if governed_payload.get("complete") is not True:
            issue(
                "artifact_missing",
                "ledger_governed",
                "治理 Ledger 仍是 partial/complete=false",
                {"path": str(ledger_governed), "complete": governed_payload.get("complete")},
                "只补日报产物晋升",
            )
        quality = governed_payload.get("quality")
        quality = quality if isinstance(quality, dict) else {}
        grade = str(quality.get("grade") or "").strip()
        overall = quality.get("overall")
        quality_snapshot = {"grade": grade or None, "overall": overall, "passed": grade not in {"", "待评"} and isinstance(overall, (int, float)) and not isinstance(overall, bool)}
        if grade in {"", "待评"} or not isinstance(overall, (int, float)) or isinstance(overall, bool):
            issue(
                "quality_pending",
                "ledger_quality",
                "治理 Ledger 度数仍待评",
                {"grade": grade or None, "overall": overall},
                "重跑日报评审并补齐质量度数",
            )

    integrity = await material_integrity(date_value, settings)
    if integrity.get("available") and not integrity.get("passed"):
        issue(
            "data_insufficient",
            "transcript",
            "transcript 覆盖率低于发布阈值",
            integrity,
            "重新导出、重备料、重蒸日报",
        )
    elif not integrity.get("available"):
        warnings.append(
            {
                "kind": "evidence_missing",
                "target": "transcript",
                "level": "WARN",
                "summary": "覆盖率无法验证（证据缺失）",
                "evidence": integrity,
                "action": "不把证据缺失当作出刊失败，改用线上交付面三项兜底验证",
                "incident": f"{date_value}:evidence_missing:transcript",
            }
        )

    page = await _probe_public_page(settings, date_value)
    if page.get("required") and (not page.get("checked") or not page.get("passed")):
        issue("page_unhealthy", "ledger_page", "日报页面不是 HTTP 200", page, "重试静态发布后再次探测")

    delivery_fallback = {
        "checked": True,
        "ledger_present": ledger_governed.is_file(),
        "quality_non_pending": bool(quality_snapshot and quality_snapshot.get("passed")),
        "page_200": bool(page.get("checked") and page.get("passed")),
    }
    delivery_fallback["passed"] = all(
        bool(delivery_fallback[key])
        for key in ("ledger_present", "quality_non_pending", "page_200")
    )
    if warnings:
        for warning in warnings:
            warning["delivery_fallback"] = delivery_fallback
            warning["result"] = (
                "线上交付面三项通过，保留 WARN；不进入出刊失败/CRITICAL"
                if delivery_fallback["passed"]
                else "线上交付面兜底未完全通过，仍只记录 WARN；其他实际故障另行处理"
            )

    # ALERT is the self-heal delivery surface itself.  Reading it back here
    # makes a just-emitted collection warning look like a fresh collection
    # failure and can recursively trigger the bounded recovery playbook.
    collection_paths = [settings.logs_dir / f"daily-{date_value}.log", settings.export_log]
    for path in collection_paths:
        try:
            stat = path.stat()
            if settings.script_crash_window > 0 and dt.datetime.now(dt.timezone.utc).timestamp() - stat.st_mtime > settings.script_crash_window:
                continue
            tail = safe_tail(path.read_text(encoding="utf-8", errors="replace"), 2_000)
        except OSError:
            continue
        if re.search(r"(?:微信|wechat|wcdb|采集).*(?:失败|异常|断链|stale)|(?:失败|异常|断链|stale).*(?:微信|wechat|wcdb|采集)", tail, re.I):
            issue("collection_broken", "wechat_collection", "微信采集链疑似断链", {"path": str(path), "tail": tail}, "只尝试一次重新导出")
            break

    # A recent crash is authoritative: do not mask it behind missing artifacts.
    if crash:
        issues = [item for item in issues if item["kind"] == "script_crash"]
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in issues:
        if item["incident"] not in seen:
            seen.add(item["incident"])
            unique.append(item)
    priority = {
        "script_crash": 0,
        "data_insufficient": 1,
        "collection_broken": 2,
        "judge_gate": 3,
        "artifact_missing": 4,
        "quality_pending": 5,
        "page_unhealthy": 6,
    }
    unique.sort(key=lambda item: priority.get(str(item.get("kind")), 99))
    status = "ERROR" if unique else ("WARN" if warnings else "OK")
    return {
        "ok": not unique,
        "status": status,
        "date": date_value,
        "issues": unique,
        "warnings": warnings,
        "failure_type": unique[0]["kind"] if unique else None,
        "incident_key": unique[0]["incident"] if unique else None,
        "ledger": {
            "staging": str(ledger_artifact),
            "judge": str(ledger_judge_path),
            "governed": str(ledger_governed),
            "staging_exists": ledger_artifact.is_file(),
            "judge_exists": ledger_judge_path.is_file(),
            "governed_exists": ledger_governed.is_file(),
            "judge_summary": ledger_judge,
        },
        "arsenal": {
            "staging": str(arsenal_artifact),
            "judge": str(arsenal_judge_path),
            "governed": str(arsenal_governed),
            "staging_exists": arsenal_artifact.is_file(),
            "judge_exists": arsenal_judge_path.is_file(),
            "governed_exists": arsenal_governed.is_file(),
            "judge_summary": arsenal_judge,
        },
        "coverage": integrity,
        "quality": quality_snapshot,
        "page": page,
        "delivery_fallback": delivery_fallback,
    }


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


PRIVACY_HARD_MARK = "隐私形态"


def assert_publishable(settings: Settings, date_value: str) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger = judge_summary(
        settings.judge_path(date_value, "ledger"), settings.ledger_artifact(date_value)
    )
    arsenal = judge_summary(
        settings.judge_path(date_value, "arsenal"), settings.arsenal_artifact(date_value)
    )
    failures: list[str] = []
    # 日报是主刊：不过就整期停刊。
    if not ledger["publishable"]:
        failures.append(
            f"ledger 不可发布：score={ledger['score']} hard={' | '.join(ledger['hard']) or '(none)'}"
        )
    if not artifact_complete(settings.ledger_artifact(date_value)):
        failures.append("ledger content.complete 不是 true（partial 不可发布）")

    # 军火库是附栏（外部 RSS 采集）：质量不过时日报照发，该栏标缺口（Sun 2026-09-17 拍板）。
    # 唯一例外是隐私红线——命中就整期停刊，绝不降级。
    arsenal_payload = load_json(settings.arsenal_artifact(date_value))
    arsenal_reasons: list[str] = []
    if not arsenal["publishable"]:
        arsenal_reasons.append(
            f"score={arsenal['score']} hard={' | '.join(arsenal['hard']) or '(none)'}"
        )
    if not isinstance(arsenal_payload, list) or not arsenal_payload:
        arsenal_reasons.append("arsenal staging 不是非空数组")
    if arsenal_reasons:
        privacy_hits = [h for h in arsenal["hard"] if PRIVACY_HARD_MARK in h]
        if privacy_hits:
            failures.append("arsenal 命中隐私红线，不可降级发布：" + " | ".join(privacy_hits))
        else:
            arsenal["degraded"] = True
            arsenal["degraded_reason"] = "；".join(arsenal_reasons)

    if failures:
        raise EditorError("quality_gate_blocked", "；".join(failures))
    return ledger, arsenal


async def publish_core(
    date_value: str,
    settings: Settings,
    *,
    post_check: bool | None = None,
    force: bool = False,
) -> dict[str, Any]:
    post_check = settings.self_check_enabled if post_check is None else post_check
    payload: dict[str, Any]
    # A pre-existing passing judge is not enough to publish if today's
    # transcript later became sparse.  Reuse the same integrity script used by
    # server-daily before touching the static delivery surface.
    integrity = await coverage_gate(date_value, settings)
    async with exclusive_editor_lock(settings):
        ledger, arsenal = assert_publishable(settings, date_value)
        fingerprint = publish_fingerprint(settings, date_value)
        marker = settings.logs_dir / f"editor-publish-{date_value}.json"
        if marker.is_file() and not force:
            previous = load_json(marker)
            delivery_intact = settings.governed_root is None or (
                settings.governed_ledger(date_value).is_file()
                and settings.governed_arsenal(date_value).is_file()
            )
            if (
                isinstance(previous, dict)
                and previous.get("ok") is True
                and previous.get("fingerprint") == fingerprint
                and delivery_intact
            ):
                payload = {
                    "ok": True,
                    "published": True,
                    "idempotent": True,
                    "date": date_value,
                    "ledger_score": ledger["score"],
                    "arsenal_score": arsenal["score"],
                    "marker": str(marker),
                    "integrity": integrity,
                }
            else:
                payload = {}
        else:
            payload = {}
        if not payload:
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
                "integrity": integrity,
            }
            atomic_write_json(marker, payload)
            payload["marker"] = str(marker)
        if settings.public_base_url:
            payload["links"] = {
                "ledger": f"{settings.public_base_url}/ledger/{date_value}",
                "arsenal": f"{settings.public_base_url}/arsenal",
                "health": f"{settings.public_base_url}/health/daily.json",
            }
    if post_check:
        diagnosis = await diagnose_publish_core(date_value, settings)
        payload["post_publish_check"] = diagnosis
        if not diagnosis.get("ok"):
            payload["self_heal"] = await self_heal_core(
                date_value,
                settings,
                trigger="post-publish",
                initial_diagnosis=diagnosis,
            )
            payload["ok"] = bool(payload["self_heal"].get("ok"))
            atomic_write_json(settings.logs_dir / f"editor-publish-{date_value}.json", payload)
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


async def alert_core(
    text: str,
    settings: Settings,
    *,
    level: str = "ERROR",
    source: str = "一一总编",
    key: str = "hermes-editor",
    cooldown: int = 1800,
    details: str = "",
    escalate: bool = True,
) -> dict[str, Any]:
    level = level.upper()
    if level not in {"INFO", "WARN", "ERROR", "CRITICAL"}:
        raise EditorError("invalid_alert_level", f"不支持的告警级别：{level}")
    async with exclusive_editor_lock(settings):
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        payload = {"at": now, "source": source, "level": level, "message": text}
        if details:
            payload["details"] = safe_tail(details, 6_000)
        atomic_write_json(settings.logs_dir / "ALERT", payload)
        settings.export_log.parent.mkdir(parents=True, exist_ok=True)
        with settings.export_log.open("a", encoding="utf-8") as handle:
            handle.write(f"[{now}] [editor-alert] {text.replace(chr(10), ' ')}\n")
        details_path: Path | None = None
        if details:
            safe_key = re.sub(r"[^A-Za-z0-9_.-]+", "_", key)[:120]
            details_path = settings.logs_dir / f"{safe_key}.details.txt"
            details_path.write_text(safe_tail(details, 12_000), encoding="utf-8")
        argv = [
            str(settings.alert_command),
            level,
            "hermes-editor" if source == "一一总编" else source,
            text,
            "--key",
            key,
            "--cooldown",
            str(max(0, cooldown)),
            "--force",
        ]
        if not escalate:
            argv.append("--no-escalate")
        if details_path:
            argv.extend(["--details", str(details_path)])
        delivery = await run_command(
            argv,
            cwd=settings.repo,
            settings=settings,
        )
        return {
            "ok": True,
            "alert": str(settings.logs_dir / "ALERT"),
            "export_log": str(settings.export_log),
            "delivery": "queued_or_sent",
            "delivery_status": delivery.stdout.strip(),
            "level": level,
            "source": source,
            "key": key,
        }


async def report_incident_core(
    date_value: str,
    found: str,
    action: str,
    result: str,
    settings: Settings,
    *,
    level: str = "INFO",
    incident: str = "manual",
    attempt: int = 0,
    details: str = "",
    escalate: bool = True,
) -> dict[str, Any]:
    message = f"一一发现{found}→尝试{action}→结果{result}"
    key = f"hermes-selfheal:{date_value}:{incident}:{attempt}:{hashlib.sha1(message.encode('utf-8')).hexdigest()[:8]}"
    return await alert_core(
        message,
        settings,
        level=level,
        source="hermes-selfheal",
        key=key,
        cooldown=0,
        details=details,
        escalate=escalate,
    )


def _load_self_heal_state(settings: Settings, date_value: str) -> dict[str, Any]:
    payload = _optional_json(settings.self_heal_state_path(date_value))
    if not isinstance(payload, dict):
        payload = {"schema_version": 1, "date": date_value, "incidents": {}}
    incidents = payload.get("incidents")
    if not isinstance(incidents, dict):
        payload["incidents"] = {}
    return payload


def _save_self_heal_state(settings: Settings, date_value: str, state: dict[str, Any]) -> None:
    state["schema_version"] = 1
    state["date"] = date_value
    state["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    atomic_write_json(settings.self_heal_state_path(date_value), state)


@asynccontextmanager
async def exclusive_self_heal_lock(settings: Settings, date_value: str) -> AsyncIterator[None]:
    """Serialize dead-man, post-publish and manual self-heal triggers."""
    path = settings.self_heal_state_path(date_value).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise EditorError("self_heal_busy", f"同一日期已有自愈在运行；锁：{path}") from exc
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


def _date_command(command: tuple[str, ...], date_value: str) -> list[str]:
    return [part.replace("{date}", date_value) for part in command]


async def _run_recovery_command(
    command: tuple[str, ...],
    date_value: str,
    settings: Settings,
    *,
    label: str,
) -> CommandResult:
    if not command:
        raise EditorError("recovery_command_missing", f"未配置{label}命令，拒绝盲目重试")
    argv = _date_command(command, date_value)
    # morning-chain uses AI325_YDAY to select the target day.  Supplying the
    # same environment to custom commands is harmless and keeps fixtures
    # deterministic without mutating the parent process environment.
    argv = [
        "env",
        f"AI325_YDAY={date_value}",
        # The recovery command itself is held under the editor lock below;
        # child scripts may therefore reuse that lock without racing a publish.
        "AI325_EDITOR_LOCK_HELD=1",
        "AI325_SELF_HEAL_ACTIVE=1",
        *argv,
    ]
    async with exclusive_editor_lock(settings):
        return await run_command(argv, cwd=settings.repo, settings=settings)


async def _self_heal_action(issue: dict[str, Any], date_value: str, settings: Settings) -> dict[str, Any]:
    kind = str(issue.get("kind"))
    target = str(issue.get("target"))
    if kind == "script_crash":
        raise EditorError("script_crash_no_retry", "检测到脚本崩溃；按规则只收集 traceback，不盲目重试")
    if kind == "data_insufficient":
        await _run_recovery_command(
            settings.reexport_command,
            date_value,
            settings,
            label="微信重新导出/备料",
        )
        if settings.rematerialize_command:
            await _run_recovery_command(
                settings.rematerialize_command,
                date_value,
                settings,
                label="日报重备料",
            )
        ledger = await run_ledger_core(date_value, settings, force_redistill=True)
        published = await publish_core(date_value, settings, post_check=False)
        return {"recovery": "export_material_redistill", "ledger": ledger, "publish": published}
    if kind == "collection_broken":
        await _run_recovery_command(
            settings.reexport_command,
            date_value,
            settings,
            label="微信重新导出",
        )
        return {"recovery": "export_once"}
    if kind == "judge_gate":
        if target == "ledger":
            result = await run_ledger_retry_core(date_value, settings)
        elif target == "arsenal":
            result = await run_arsenal_core(date_value, settings)
        else:
            raise EditorError("unknown_incident", f"未知 judge 目标：{target}")
        if not result.get("publishable"):
            raise EditorError("quality_gate_blocked", f"{target} 按 judge 建议重蒸后仍未通过")
        published = await publish_core(date_value, settings, post_check=False)
        return {"recovery": "judge_feedback_redistill", "result": result, "publish": published}
    if kind == "quality_pending":
        result = await run_ledger_core(date_value, settings, force_redistill=True)
        if not result.get("publishable"):
            raise EditorError("quality_gate_blocked", "日报质量度数仍不可发布")
        published = await publish_core(date_value, settings, post_check=False)
        return {"recovery": "quality_rejudge", "result": result, "publish": published}
    if kind == "artifact_missing":
        if target in {"ledger_staging", "ledger_judge"}:
            result = await run_ledger_core(date_value, settings, force_redistill=target == "ledger_judge")
            if not result.get("publishable"):
                raise EditorError("quality_gate_blocked", "日报补产物后仍未通过门禁")
        elif target in {"arsenal_staging", "arsenal_judge"}:
            result = await run_arsenal_core(date_value, settings)
            if not result.get("publishable"):
                raise EditorError("quality_gate_blocked", "军火库补产物后仍未通过门禁")
        elif target in {"ledger_governed", "arsenal_governed"}:
            result = {"recovery": "promote_missing_governed_artifact"}
        else:
            raise EditorError("unknown_incident", f"未知产物目标：{target}")
        published = await publish_core(
            date_value,
            settings,
            post_check=False,
            force=target in {"ledger_governed", "arsenal_governed"},
        )
        return {"recovery": "repair_only_missing_step", "result": result, "publish": published}
    if kind == "page_unhealthy":
        published = await publish_core(date_value, settings, post_check=False, force=True)
        return {"recovery": "republish_static_page", "publish": published}
    raise EditorError("unknown_incident", f"未知自愈故障类型：{kind}")


async def _emit_incident(
    date_value: str,
    issue: dict[str, Any],
    settings: Settings,
    *,
    action: str,
    result: str,
    level: str,
    attempt: int,
    details: str = "",
) -> dict[str, Any]:
    try:
        return await report_incident_core(
            date_value,
            str(issue.get("summary", issue.get("kind", "未知故障"))),
            action,
            result,
            settings,
            level=level,
            incident=str(issue.get("incident", issue.get("kind", "unknown"))),
            attempt=attempt,
            details=details,
            escalate=not (
                level.upper() == "WARN"
                and str(issue.get("kind", "")) == "evidence_missing"
            ),
        )
    except (EditorError, OSError) as exc:
        # A broken alert command must not hide the original incident.  Keep
        # the error in the returned self-heal record; the caller still exits
        # non-zero/CRITICAL for the actual fault.
        return {"ok": False, "error": f"告警送达失败：{exc}"}


async def _self_heal_core(
    date_value: str,
    settings: Settings,
    *,
    trigger: str = "manual",
    initial_diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run bounded playbooks until the delivery surface is healthy or escalate."""
    state = _load_self_heal_state(settings, date_value)
    incidents = state.setdefault("incidents", {})
    events: list[dict[str, Any]] = []
    diagnosis = initial_diagnosis or await diagnose_publish_core(date_value, settings)
    warnings = diagnosis.get("warnings") or []
    for warning in warnings:
        warning_issue = {
            "kind": warning.get("kind", "evidence_missing"),
            "target": warning.get("target", "coverage"),
            "summary": warning.get("summary", "证据缺失"),
            "incident": warning.get("incident", f"{date_value}:evidence_missing:coverage"),
        }
        warning_result = warning.get("result") or "无法验证（证据缺失），保留 WARN"
        event = await _emit_incident(
            date_value,
            warning_issue,
            settings,
            action=warning.get("action", "降级为线上交付面验证"),
            result=warning_result,
            level="WARN",
            attempt=0,
            details=safe_tail(json.dumps(warning.get("evidence", {}), ensure_ascii=False), 4_000),
        )
        events.append(event)
    if diagnosis.get("ok"):
        return {
            "ok": True,
            "date": date_value,
            "trigger": trigger,
            "status": diagnosis.get("status", "OK"),
            "escalated": False,
            "critical": False,
            "warnings": warnings,
            "diagnosis": diagnosis,
            "events": events,
        }

    # A single invocation may repair more than one independent surface (for
    # example, a missing staging file followed by its governed copy).  Bound
    # the number of cycles so a malformed fixture cannot spin forever.
    for _cycle in range(8):
        if diagnosis.get("ok"):
            return {
                "ok": True,
                "date": date_value,
                "trigger": trigger,
                "status": diagnosis.get("status", "OK"),
                "escalated": False,
                "critical": False,
                "warnings": diagnosis.get("warnings") or [],
                "diagnosis": diagnosis,
                "events": events,
            }
        issues = diagnosis.get("issues") or []
        if not issues:
            break
        issue = issues[0]
        incident = str(issue.get("incident", f"{date_value}:unknown"))
        entry = incidents.get(incident)
        if not isinstance(entry, dict) or entry.get("status") == "resolved":
            entry = {"attempts": 0, "status": "open"}
            incidents[incident] = entry
        kind = str(issue.get("kind"))
        max_attempts = settings.collection_max_attempts if kind == "collection_broken" else settings.self_heal_max_attempts
        if kind == "script_crash":
            details = str((issue.get("evidence") or {}).get("tail", ""))
            event = await _emit_incident(
                date_value,
                issue,
                settings,
                action="收集 traceback 与最近日志（不重试）",
                result="脚本崩溃，升级 CRITICAL 并停止重试",
                level="CRITICAL",
                attempt=int(entry.get("attempts", 0)),
                details=details,
            )
            events.append(event)
            entry.update({"status": "critical", "last_failure": details})
            _save_self_heal_state(settings, date_value, state)
            final = await diagnose_publish_core(date_value, settings)
            return {
                "ok": False,
                "date": date_value,
                "trigger": trigger,
                "escalated": True,
                "critical": True,
                "failure_type": "script_crash",
                "diagnosis": final,
                "events": events,
            }
        attempts = int(entry.get("attempts", 0))
        if attempts >= max_attempts:
            event = await _emit_incident(
                date_value,
                issue,
                settings,
                action="停止继续重试",
                result=f"同一故障已自愈 {attempts} 次仍未恢复，升级 CRITICAL",
                level="CRITICAL",
                attempt=attempts,
                details=str(entry.get("last_failure", "")),
            )
            events.append(event)
            entry["status"] = "critical"
            _save_self_heal_state(settings, date_value, state)
            return {
                "ok": False,
                "date": date_value,
                "trigger": trigger,
                "escalated": True,
                "critical": True,
                "failure_type": kind,
                "diagnosis": diagnosis,
                "events": events,
            }

        attempt = attempts + 1
        entry.update({"attempts": attempt, "status": "running", "trigger": trigger})
        _save_self_heal_state(settings, date_value, state)
        start_event = await _emit_incident(
            date_value,
            issue,
            settings,
            action=f"{issue.get('action', '执行自愈')}（第{attempt}次）",
            result="执行中",
            level="INFO",
            attempt=attempt,
        )
        events.append(start_event)
        action_error = ""
        action_result: dict[str, Any] = {}
        try:
            action_result = await _self_heal_action(issue, date_value, settings)
        except Exception as exc:  # noqa: BLE001 - convert every action failure into an evidence record
            action_error = f"{type(exc).__name__}: {exc}"
            entry["last_failure"] = safe_tail(traceback.format_exc(), 6_000)
            failed_event = await _emit_incident(
                date_value,
                issue,
                settings,
                action=f"{issue.get('action', '执行自愈')}（第{attempt}次）",
                result=f"失败：{action_error}",
                level="ERROR",
                attempt=attempt,
                details=str(entry["last_failure"]),
            )
            events.append(failed_event)
        diagnosis = await diagnose_publish_core(date_value, settings)
        same_issue = any(str(item.get("incident")) == incident for item in (diagnosis.get("issues") or []))
        if not same_issue and not action_error:
            entry["status"] = "resolved"
            resolved_event = await _emit_incident(
                date_value,
                issue,
                settings,
                action=f"{issue.get('action', '执行自愈')}（第{attempt}次）",
                result="成功，交付面复检通过",
                level="INFO",
                attempt=attempt,
            )
            events.append(resolved_event)
            _save_self_heal_state(settings, date_value, state)
            continue
        if same_issue:
            entry["status"] = "open"
            remaining_event = await _emit_incident(
                date_value,
                issue,
                settings,
                action=f"{issue.get('action', '执行自愈')}（第{attempt}次）",
                result="动作完成但同一故障仍在，准备按上限处理",
                level="WARN",
                attempt=attempt,
                details=action_error or safe_tail(json.dumps(action_result, ensure_ascii=False), 4_000),
            )
            events.append(remaining_event)
            _save_self_heal_state(settings, date_value, state)
            if attempt >= max_attempts:
                critical_event = await _emit_incident(
                    date_value,
                    issue,
                    settings,
                    action="停止继续重试",
                    result=f"同一故障已自愈 {attempt} 次仍未恢复，升级 CRITICAL",
                    level="CRITICAL",
                    attempt=attempt,
                    details=str(entry.get("last_failure", "")),
                )
                events.append(critical_event)
                entry["status"] = "critical"
                _save_self_heal_state(settings, date_value, state)
                return {
                    "ok": False,
                    "date": date_value,
                    "trigger": trigger,
                    "escalated": True,
                    "critical": True,
                    "failure_type": kind,
                    "diagnosis": diagnosis,
                    "events": events,
                }
            if settings.self_heal_retry_delay > 0:
                await asyncio.sleep(settings.self_heal_retry_delay)
        elif action_error:
            # An action may fail while the original issue disappears due to a
            # concurrent process.  Re-run the diagnosis before escalating.
            entry["status"] = "open"
            _save_self_heal_state(settings, date_value, state)
            if attempt >= max_attempts:
                continue

    final = await diagnose_publish_core(date_value, settings)
    return {
        "ok": bool(final.get("ok")),
        "date": date_value,
        "trigger": trigger,
        "status": final.get("status", "ERROR"),
        "escalated": not bool(final.get("ok")),
        "critical": not bool(final.get("ok")),
        "warnings": final.get("warnings") or [],
        "diagnosis": final,
        "events": events,
    }


async def self_heal_core(
    date_value: str,
    settings: Settings,
    *,
    trigger: str = "manual",
    initial_diagnosis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async with exclusive_self_heal_lock(settings, date_value):
        return await _self_heal_core(
            date_value,
            settings,
            trigger=trigger,
            initial_diagnosis=initial_diagnosis,
        )


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
    name="diagnose_publish",
    annotations={
        "title": "Diagnose Published Delivery Surface",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def diagnose_publish(date: str) -> dict[str, Any]:
    """Check governed artifacts, quality degree, coverage and the public Ledger page."""
    params = DateInput(date=date)
    settings = Settings.from_env()
    return await tool_call("diagnose_publish", lambda: diagnose_publish_core(params.date, settings))


@mcp.tool(
    name="self_heal",
    annotations={
        "title": "Run Bounded Hermes Self-Heal",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    },
)
async def self_heal(date: str, trigger: str = "manual") -> dict[str, Any]:
    """Diagnose and run the bounded playbook; two failures escalate CRITICAL and stop."""
    params = SelfHealInput(date=date, trigger=trigger)
    settings = Settings.from_env()
    return await tool_call(
        "self_heal",
        lambda: self_heal_core(params.date, settings, trigger=params.trigger),
    )


@mcp.tool(
    name="report_incident",
    annotations={
        "title": "Report Hermes Self-Heal Incident",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def report_incident(
    date: str,
    found: str,
    action: str,
    result: str,
    level: str = "INFO",
    incident: str = "manual",
    attempt: int = 0,
) -> dict[str, Any]:
    """Write ``一一发现X→尝试Y→结果Z`` to the existing JSONL/admin alert channel."""
    params = IncidentInput(
        date=date,
        found=found,
        action=action,
        result=result,
        level=level,
        incident=incident,
        attempt=attempt,
    )
    settings = Settings.from_env()
    return await tool_call(
        "report_incident",
        lambda: report_incident_core(
            params.date,
            params.found,
            params.action,
            params.result,
            settings,
            level=params.level,
            incident=params.incident,
            attempt=params.attempt,
        ),
    )


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
        print(json.dumps({"server": SERVER_NAME, "tools": ["run_ledger", "run_arsenal", "redistill_theme", "publish", "diagnose_publish", "self_heal", "report_incident", "status", "alert"]}, ensure_ascii=False))
        return 0
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
