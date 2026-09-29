#!/usr/bin/env python3
"""Non-stdio entrypoint for dead-man and post-publish Hermes self-heal."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("date", help="Edition date in YYYY-MM-DD")
    parser.add_argument("--trigger", default="manual", help="deadman, post-publish or manual")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> dict[str, object]:
    params = server.SelfHealInput(date=args.date, trigger=args.trigger)
    return await server.self_heal_core(params.date, server.Settings.from_env(), trigger=params.trigger)


def main() -> int:
    args = parse_args()
    try:
        result = asyncio.run(run(args))
    except (ValueError, server.EditorError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
