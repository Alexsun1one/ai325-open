#!/usr/bin/env bash
# 从主仓按白名单同步公开快照 → squash 提交 → 推 ai325-open。
# 用法：bash scripts/ops/sync-public.sh
# 说明：
#   - 白名单只覆盖可复用源码（app/agent/hermes/scripts 子集 + site 代码与静态资源）。
#   - 公开仓的 README.md、assets/、site/content/ 为独立维护的门面与构建占位，不被同步覆盖。
#   - PUBLIC-SOURCE.json 的 source_commit 更新为本次主仓 HEAD。
set -euo pipefail

MAIN_REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PUBLIC_REMOTE="${PUBLIC_REMOTE:-git@github.com:Alexsun1one/ai325-open.git}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "→ clone 公开仓"
git clone --depth 1 "$PUBLIC_REMOTE" "$WORK/public" >/dev/null 2>&1

sync_dir() {
  local rel="$1"
  local src="$MAIN_REPO/$rel" dst="$WORK/public/$rel"
  if [ ! -d "$src" ]; then echo "⚠ 缺失目录 $rel，跳过"; return; fi
  mkdir -p "$dst"
  rsync -a --delete \
    --exclude '__pycache__' --exclude '.venv' --exclude '*.pyc' \
    "$src/" "$dst/"
  echo "→ 同步 $rel/"
}

# 代码目录（整目录）
sync_dir app
sync_dir agent
sync_dir hermes

# scripts 白名单（只同步可复用构建脚本，不含部署/发信/服务器脚本）
SCRIPTS_KEEP=(
  build_context_units.py build_people.py extract_flagship.py
  generate_badges.py hermes_to_ledger.py markup.py rebuild_essays.py
)
mkdir -p "$WORK/public/scripts"
for f in "${SCRIPTS_KEEP[@]}"; do
  if [ -f "$MAIN_REPO/scripts/$f" ]; then cp "$MAIN_REPO/scripts/$f" "$WORK/public/scripts/"; fi
done
# 同步脚本自身（ops/）
mkdir -p "$WORK/public/scripts/ops"
cp "$MAIN_REPO/scripts/ops/sync-public.sh" "$WORK/public/scripts/ops/sync-public.sh"
echo "→ 同步 scripts（白名单 ${#SCRIPTS_KEEP[@]} 个 + ops/sync-public.sh）"

# site：代码与静态资源（content 是生产数据，不同步；README/assets 不动）
sync_dir site/src
sync_dir site/public
for f in site/package.json site/package-lock.json site/next.config.ts site/tsconfig.json site/eslint.config.mjs site/postcss.config.mjs site/.gitignore; do
  if [ -f "$MAIN_REPO/$f" ]; then cp "$MAIN_REPO/$f" "$WORK/public/$f"; fi
done
echo "→ 同步 site 配置"

# 根配置与文档（README.md 不在白名单：公开仓独立维护门面）
for f in .gitignore Dockerfile CODEX-VISUAL-SPEC.md DESIGN.md; do
  if [ -f "$MAIN_REPO/$f" ]; then cp "$MAIN_REPO/$f" "$WORK/public/$f"; fi
done

# 源提交标记
SRC_COMMIT="$(git -C "$MAIN_REPO" rev-parse HEAD)"
python3 - "$WORK/public/PUBLIC-SOURCE.json" "$SRC_COMMIT" <<'PY'
import json, sys
path, commit = sys.argv[1], sys.argv[2]
data = json.load(open(path, encoding="utf-8"))
data["source_commit"] = commit
data["synced_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"source_commit → {commit[:12]}")
PY

cd "$WORK/public"
if git diff --cached --quiet && git diff --quiet; then
  echo "→ 无变化，跳过"
  exit 0
fi
git add -A
git commit -q -m "同步公开快照 @ ${SRC_COMMIT:0:12}（白名单：app/agent/hermes/scripts/site 代码）"
git push origin main >/dev/null 2>&1
echo "→ 已推送 ai325-open @ $(git rev-parse --short HEAD)"
