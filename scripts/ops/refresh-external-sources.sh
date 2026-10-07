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
# Reuse the established Hermes provider without printing or copying credentials.
if [ -z "${DEEPSEEK_API_KEY:-}" ] && [ -f "${HERMES_ENV_FILE:-/data/second-brain/hermes/.env}" ]; then
  set -a
  source "${HERMES_ENV_FILE:-/data/second-brain/hermes/.env}" >/dev/null 2>&1
  set +a
fi
python3 "$REPO/scripts/ops/curate_external_sources.py"
curation_rc=$?
if [ "$curation_rc" -ne 0 ]; then
  echo "[sources] curation incomplete (exit=$curation_rc); inspect selection status" >&2
fi
[ "$rc" -eq 0 ] && [ "$curation_rc" -eq 0 ]
