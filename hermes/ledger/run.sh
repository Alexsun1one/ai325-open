#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export TZ=Asia/Shanghai
DAY="${1:-$(date +%F)}"
shift "$(( $# > 0 ? 1 : 0 ))"

ENV_FILE="${HERMES_ENV_FILE:-/data/second-brain/hermes/.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

XF_REPO="${XF_REPO:-$(cd "$ROOT/../.." && pwd)}"
MATERIALS_ROOT="${HERMES_MATERIALS_ROOT:-$ROOT/materials}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

exec "$PYTHON_BIN" "$ROOT/distill_ledger.py" \
  "$MATERIALS_ROOT/$DAY" \
  --date "$DAY" \
  --ledger-dir "$XF_REPO/site/content/ledgers" \
  --usage-output "$MATERIALS_ROOT/$DAY/distill-usage.json" \
  "$@"
