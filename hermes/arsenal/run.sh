#!/usr/bin/env bash
# Hermes Arsenal daily collector + distiller.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DAY="$(TZ=Asia/Shanghai date +%F)"
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    20??-??-??) DAY="$arg" ;;
    *) echo "未知参数：$arg（用法：run.sh [YYYY-MM-DD] [--dry-run]）" >&2; exit 2 ;;
  esac
done

CANDIDATES="$HERE/candidates/$DAY.jsonl"
echo "[Hermes Arsenal] $DAY 开始采集"
if ! python3 "$HERE/collect.py" --date "$DAY" --output "$CANDIDATES"; then
  echo "[Hermes Arsenal] 采集失败；上方 [fail] 行是各信源原因，未启动蒸馏" >&2
  exit 1
fi

COLLECTED="$(wc -l < "$CANDIDATES" | tr -d ' ')"
DISTILL_ARGS=(--date "$DAY" --candidates "$CANDIDATES")
if [ "$DRY_RUN" -eq 1 ]; then
  DISTILL_ARGS+=(--dry-run)
fi

echo "[Hermes Arsenal] 候选 $COLLECTED 条，开始蒸馏"
if ! python3 "$HERE/distill.py" "${DISTILL_ARGS[@]}"; then
  echo "[Hermes Arsenal] 蒸馏失败；已有有效产物未被覆盖" >&2
  exit 1
fi

REPO="${XF_REPO:-$(cd "$HERE/../.." && pwd)}"
OUTPUT="$REPO/site/content/arsenal/$DAY.json"
if [ -f "$OUTPUT" ]; then
  DISTILLED="$(python3 -c 'import json,sys; print(len(json.load(open(sys.argv[1], encoding="utf-8"))))' "$OUTPUT")"
  echo "[Hermes Arsenal] 完成：候选 $COLLECTED 条 → 军火库 $DISTILLED 条 → $OUTPUT"
else
  echo "[Hermes Arsenal] 蒸馏命令成功但未找到 $OUTPUT" >&2
  exit 1
fi
