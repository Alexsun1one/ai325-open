#!/usr/bin/env python3
"""Combine per-artifact judge results and publish a 14-day health summary."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any


QUALITY_NAME = re.compile(r"^quality-(\d{4}-\d{2}-\d{2})\.json$")


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write(path: Path, payload: Any) -> None:
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


def combine(args: argparse.Namespace) -> int:
    artifacts: dict[str, dict[str, Any]] = {}
    for kind, path in (("ledger", args.ledger_result), ("arsenal", args.arsenal_result)):
        if path and path.exists():
            payload = load(path)
            artifacts[kind] = payload if isinstance(payload, dict) else {"passed": False, "hard_fail": ["判定结果不是对象"]}
        else:
            artifacts[kind] = {
                "kind": kind,
                "passed": False,
                "score": 0,
                "grade": "F",
                "hard_fail": [f"{kind} 质量判定结果缺失"],
                "soft": [],
                "suggestions": [],
                "redistill_count": 0,
                "elapsed_ms": 0,
                "token_usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
    passed = all(bool(result.get("passed")) for result in artifacts.values())
    scores = [int(result.get("score", 0) or 0) for result in artifacts.values()]
    score = min(scores) if scores else 0
    grade = "A" if passed and score >= 85 else "B" if passed else "F"
    hard = [f"{kind}: {message}" for kind, result in artifacts.items() for message in result.get("hard_fail", [])]
    soft = [f"{kind}: {message}" for kind, result in artifacts.items() for message in result.get("soft", [])]
    suggestions = list(
        dict.fromkeys(
            f"{kind}: {message}"
            for kind, result in artifacts.items()
            for message in result.get("suggestions", [])
        )
    )
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for result in artifacts.values():
        raw = result.get("token_usage", {})
        for key in usage:
            usage[key] += int(raw.get(key, 0) or 0) if isinstance(raw, dict) else 0
    payload = {
        "date": args.date,
        "passed": passed,
        "score": score,
        "grade": grade,
        "hard_fail": hard,
        "soft": soft,
        "suggestions": suggestions,
        "redistill_count": sum(int(result.get("redistill_count", 0) or 0) for result in artifacts.values()),
        "elapsed_ms": (
            int(args.pipeline_elapsed_ms)
            if getattr(args, "pipeline_elapsed_ms", None) is not None
            else sum(int(result.get("elapsed_ms", 0) or 0) for result in artifacts.values())
        ),
        "token_usage": usage,
        "prompt_versions": {
            kind: {
                "artifact": result.get("artifact_prompt_version"),
                "judge": result.get("prompt_version"),
            }
            for kind, result in artifacts.items()
        },
        "artifacts": artifacts,
    }
    atomic_write(args.output, payload)
    if not passed:
        if args.alert_file:
            args.alert_file.parent.mkdir(parents=True, exist_ok=True)
            args.alert_file.write_text(
                json.dumps({"date": args.date, "score": score, "hard_fail": hard}, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        if args.export_log:
            args.export_log.parent.mkdir(parents=True, exist_ok=True)
            with args.export_log.open("a", encoding="utf-8") as handle:
                handle.write(
                    f"[{dt.datetime.now().isoformat(timespec='seconds')}] [quality-fail] {args.date} score={score} "
                    + " | ".join(hard[:5])
                    + "\n"
                )
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if passed else 2


def aggregate(args: argparse.Namespace) -> int:
    today = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    floor = today - dt.timedelta(days=max(1, args.days) - 1)
    rows: list[dict[str, Any]] = []
    if args.logs_dir.exists():
        for path in sorted(args.logs_dir.glob("quality-*.json")):
            match = QUALITY_NAME.fullmatch(path.name)
            if not match:
                continue
            date_value = dt.date.fromisoformat(match.group(1))
            if floor <= date_value <= today:
                payload = load(path)
                if isinstance(payload, dict):
                    rows.append(
                        {
                            "date": payload.get("date", match.group(1)),
                            "passed": bool(payload.get("passed")),
                            "score": int(payload.get("score", 0) or 0),
                            "grade": payload.get("grade", "F"),
                            "redistill_count": int(payload.get("redistill_count", 0) or 0),
                            "elapsed_ms": int(payload.get("elapsed_ms", 0) or 0),
                            "token_usage": payload.get("token_usage", {}),
                            "hard_fail": payload.get("hard_fail", []),
                            "prompt_versions": payload.get("prompt_versions", {}),
                        }
                    )
    output = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "window_days": args.days,
        "summary": {
            "days": len(rows),
            "passed": sum(1 for row in rows if row["passed"]),
            "failed": sum(1 for row in rows if not row["passed"]),
            "average_score": round(sum(row["score"] for row in rows) / len(rows), 1) if rows else None,
        },
        "days": rows,
    }
    atomic_write(args.output, output)
    print(json.dumps(output, ensure_ascii=False))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    merge = sub.add_parser("combine")
    merge.add_argument("--date", required=True)
    merge.add_argument("--ledger-result", type=Path)
    merge.add_argument("--arsenal-result", type=Path)
    merge.add_argument("--output", type=Path, required=True)
    merge.add_argument("--alert-file", type=Path)
    merge.add_argument("--export-log", type=Path)
    merge.add_argument("--pipeline-elapsed-ms", type=int)
    view = sub.add_parser("aggregate")
    view.add_argument("--logs-dir", type=Path, required=True)
    view.add_argument("--output", type=Path, required=True)
    view.add_argument("--days", type=int, default=14)
    view.add_argument("--date")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(combine(args) if args.command == "combine" else aggregate(args))
