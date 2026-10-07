#!/usr/bin/env python3
"""Collect configured RSS/Atom sources into site/public/data/external-knowledge.json.

Exit codes: 0 all sources ok; 1 some source failed (file still written atomically,
failed sources keep their previous items); 2 fatal config/output error (nothing written).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app import external_sources as ext  # noqa: E402

DEFAULT_CONFIG = "config/external-sources.json"
DEFAULT_OUTPUT = "site/public/data/external-knowledge.json"


def resolve(path: str) -> Path:
    p = Path(path).expanduser()
    return p if p.is_absolute() else ROOT / p


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None, fetcher=ext.fetch_feed, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--max-bytes", type=int)
    args = parser.parse_args(argv)
    config_path, output_path = resolve(args.config), resolve(args.output)
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        ext.validate_config(config)
        if args.timeout is not None:
            config.setdefault("limits", {})["timeoutSeconds"] = args.timeout
        if args.max_bytes is not None:
            config.setdefault("limits", {})["maxBytes"] = args.max_bytes
        ext.validate_limits(config.get("limits", {}))
        previous = None
        if output_path.exists():
            previous = json.loads(output_path.read_text(encoding="utf-8"))
            ext.validate_document(previous)
        document, failures = ext.collect(config, previous, now or datetime.now(timezone.utc), fetcher)
        ext.validate_document(document)
        if not args.dry_run:
            atomic_write(output_path, json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    except (OSError, ValueError, TypeError) as exc:
        print(f"fatal: {exc}", file=sys.stderr)
        return 2
    ok = sum(1 for s in document["sources"] if s["status"] == "ok")
    print(json.dumps({"ok": ok, "failed": failures, "items": len(document["items"]), "output": str(output_path), "dryRun": args.dry_run}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
