#!/usr/bin/env python3
"""Stamp a converted site Ledger with quality and prompt provenance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
import os


def atomic_write(path: Path, payload: dict) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1)
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--judge-result", type=Path, required=True)
    parser.add_argument("--prompt-version", required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    judged = json.loads(args.judge_result.read_text(encoding="utf-8"))
    credits = ledger.setdefault("credits", {})
    credits["prompt_version"] = args.prompt_version
    credits["model"] = args.model
    credits["quality_grade"] = judged.get("grade", "F")
    credits["self_check_score"] = int(judged.get("score", 0) or 0)
    ledger["quality_gate"] = {
        "score": credits["self_check_score"],
        "grade": credits["quality_grade"],
        "judge_prompt_version": judged.get("prompt_version", "unknown"),
    }
    footer = ledger.setdefault("footer", [])
    marker = f"<b>Hermes 质量门禁</b>：本期自检 {credits['self_check_score']} 分 · {credits['quality_grade']}"
    footer[:] = [item for item in footer if not (isinstance(item, str) and "Hermes 质量门禁" in item)]
    footer.append(marker)
    atomic_write(args.ledger, ledger)
    print(json.dumps({"stamped": str(args.ledger), "score": credits["self_check_score"], "grade": credits["quality_grade"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
