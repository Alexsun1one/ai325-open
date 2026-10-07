#!/usr/bin/env bash
# Run inside the publisher's existing editor lock, before the static build.
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [ "${AI325_SKIP_EXTERNAL_SOURCES:-0}" = "1" ]; then
  echo "[sources] refresh skipped explicitly; publishing the existing snapshot"
  exit 0
fi
python3 "$REPO/scripts/ops/collect_external_sources.py" \
  --config "$REPO/config/external-sources.json" \
  --output "$REPO/site/public/data/external-knowledge.json"
rc=$?
if [ "$rc" -ne 0 ]; then
  echo "[sources] refresh incomplete (exit=$rc); source status and last successful items are retained" >&2
fi
exit "$rc"
