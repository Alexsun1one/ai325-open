#!/usr/bin/env bash
# Deploy ai325_editor on the Hermes host. Defaults to a read-only plan.
set -euo pipefail

MODE="${1:---plan}"
if [[ "$MODE" != "--plan" && "$MODE" != "--apply" ]]; then
  echo "usage: $0 [--plan|--apply]" >&2
  exit 2
fi

REPO="${AI325_REPO:-/opt/xfsite/repo}"
SOURCE="$REPO/hermes/editor_mcp"
TARGET="${AI325_EDITOR_HOME:-/opt/ai325-editor}"
HERMES_HOME="${HERMES_HOME:-/data/second-brain/hermes}"
HERMES_BIN="${HERMES_BIN:-/usr/local/lib/hermes-agent/venv/bin/hermes}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
CONFIG="$HERMES_HOME/config.yaml"
JOBS="$HERMES_HOME/cron/jobs.json"
CRON_FILE="${AI325_FALLBACK_CRON_FILE:-/etc/cron.d/ai325-editor-fallback}"
STAMP="$(date +%Y%m%d-%H%M%S)"
CONFIG_BACKUP="$CONFIG.pre-ai325-$STAMP"
JOBS_BACKUP="$JOBS.pre-ai325-$STAMP"
CRON_BACKUP="$CRON_FILE.pre-ai325-$STAMP"
CODE_BACKUP="$TARGET.pre-ai325-$STAMP"

cat <<EOF
ai325_editor deploy plan
  repo:          $REPO
  source:        $SOURCE
  target:        $TARGET
  hermes home:   $HERMES_HOME
  config backup: $CONFIG_BACKUP
  jobs backup:   $JOBS_BACKUP
  fallback cron: $CRON_FILE
EOF

if [[ "$MODE" == "--plan" ]]; then
  echo "read-only plan; run with --apply on the Hermes host after checking the paths"
  exit 0
fi

[[ -f "$CONFIG" ]] || { echo "missing Hermes config: $CONFIG" >&2; exit 1; }
[[ -x "$HERMES_BIN" ]] || { echo "missing Hermes CLI: $HERMES_BIN" >&2; exit 1; }
[[ -f "$SOURCE/server.py" && -f "$SOURCE/requirements.txt" && -f "$SOURCE/date-context.sh" ]] || {
  echo "missing editor MCP source under $SOURCE" >&2
  exit 1
}
if [[ -f "$CRON_FILE" ]] && ! grep -Fq '# managed-by: ai325_editor' "$CRON_FILE"; then
  echo "refusing to overwrite unmanaged cron file: $CRON_FILE" >&2
  echo "move it aside or add this job manually after review" >&2
  exit 1
fi

cp -p "$CONFIG" "$CONFIG_BACKUP"
if [[ -f "$JOBS" ]]; then cp -p "$JOBS" "$JOBS_BACKUP"; fi
if [[ -f "$CRON_FILE" ]]; then cp -p "$CRON_FILE" "$CRON_BACKUP"; fi
if [[ -d "$TARGET" ]]; then cp -a "$TARGET" "$CODE_BACKUP"; fi

install -d -m 0755 "$TARGET" "$HERMES_HOME/scripts"
install -m 0644 "$SOURCE/server.py" "$SOURCE/__init__.py" "$SOURCE/requirements.txt" "$TARGET/"
if [[ ! -x "$TARGET/.venv/bin/python" ]]; then "$PYTHON_BIN" -m venv "$TARGET/.venv"; fi
"$TARGET/.venv/bin/pip" install -q -r "$TARGET/requirements.txt"

install -m 0755 "$SOURCE/date-context.sh" "$HERMES_HOME/scripts/ai325-editor-date.sh"

export HERMES_HOME
# 已存在时 mcp add 不会更新 env，先移除再加（配置已备份）
"$HERMES_BIN" mcp remove ai325_editor >/dev/null 2>&1 || true
printf 'y\n' | "$HERMES_BIN" mcp add ai325_editor \
  --command "$TARGET/.venv/bin/python" \
  --connect-timeout 60 \
  --env \
    AI325_REPO="$REPO" \
    AI325_LEDGER_HOME="$REPO/hermes/ledger" \
    AI325_ARSENAL_HOME=/opt/hermes-arsenal \
    AI325_HARNESS_HOME="$REPO/hermes/harness" \
    AI325_MATERIALS_ROOT=/opt/hermes-ledger/materials \
    AI325_LOGS_DIR=/opt/xfsite/logs \
    AI325_EXPORT_LOG=/opt/wechat-archive/export.log \
    AI325_HEALTH_DAILY="$REPO/site/public/health/daily.json" \
    AI325_EDITOR_LOCK_FILE=/opt/xfsite/logs/ai325-editor.lock \
    AI325_SERVER_DAILY="$REPO/scripts/server-daily.sh" \
    AI325_PUBLIC_BASE_URL="${AI325_PUBLIC_BASE_URL:-}" \
  --args "$TARGET/server.py"

PLATFORM_JSON="$($HERMES_BIN config get platform_toolsets.wecom --json 2>/dev/null || true)"
SERVERS_JSON="$($HERMES_BIN config get mcp_servers --json)"
PLATFORM_UPDATE="$($PYTHON_BIN - "$PLATFORM_JSON" "$SERVERS_JSON" <<'PY'
import json,sys
platform=json.loads(sys.argv[1]) if sys.argv[1] else None
servers=json.loads(sys.argv[2])
if not isinstance(platform,list):
    print("UNCHANGED")
    raise SystemExit(0)
if "no_mcp" in platform:
    print("BLOCKED")
    raise SystemExit(0)
server_names=set(servers) if isinstance(servers,dict) else set()
explicit=set(map(str,platform)) & server_names
if explicit and "ai325_editor" not in platform:
    print(json.dumps([*platform,"ai325_editor"],ensure_ascii=False,separators=(",",":")))
else:
    print("UNCHANGED")
PY
)"
if [[ "$PLATFORM_UPDATE" == "BLOCKED" ]]; then
  echo "WeCom platform explicitly contains no_mcp; refusing to override that security choice" >&2
  exit 1
elif [[ "$PLATFORM_UPDATE" != "UNCHANGED" ]]; then
  "$HERMES_BIN" config set --force platform_toolsets.wecom "$PLATFORM_UPDATE"
fi

# Hermes 还有一层并发批工具 420s 上限：timeouts.tools.concurrent_batch 提到 1800
grep -q "^timeouts:" "$CONFIG" || printf 'timeouts:\n  tools:\n    concurrent_batch: 1800\n' >> "$CONFIG"
# 军火库采集+蒸馏+评审常超 5 分钟：该 MCP 每次工具调用超时从默认 300s 提到 1800s（与 server.py 命令超时一致）
"$PYTHON_BIN" - "$CONFIG" <<'PYCFG'
import sys,re
p=sys.argv[1]; s=open(p,encoding="utf-8").read()
m=re.search(r"(?m)^  ai325_editor:\n(?:    .*\n)+", s)
if not m: raise SystemExit("ai325_editor block not found")
block=m.group(0)
if re.search(r"(?m)^    timeout:", block):
    block2=re.sub(r"(?m)^    timeout:.*$","    timeout: 1800",block)
elif "    connect_timeout:" in block:
    block2=block.replace("    connect_timeout:","    timeout: 1800\n    connect_timeout:",1)
else:
    block2=block.rstrip("\n")+"\n    timeout: 1800\n"
open(p,"w",encoding="utf-8").write(s.replace(block,block2,1))
print("mcp timeout: set" if block!=block2 else "mcp timeout: unchanged")
PYCFG
"$HERMES_BIN" mcp test ai325_editor
if ! "$HERMES_BIN" tools list --platform wecom | grep -Fq "ai325_editor"; then
  echo "ai325_editor is not visible on the existing WeCom tool view; refusing to rewrite platform toolsets automatically" >&2
  echo "inspect platform_toolsets/no_mcp in $CONFIG and enable only the MCP server after review" >&2
  exit 1
fi

EDITOR_PROMPT="$(cat "$REPO/hermes/prompts/editor-v1.md")"
EDITOR_JOB_ID=""
if [[ -f "$JOBS" ]]; then
  EDITOR_JOB_ID="$($PYTHON_BIN - "$JOBS" <<'PY'
import json,sys
with open(sys.argv[1],encoding="utf-8") as handle:
    payload=json.load(handle)
jobs=payload.get("jobs",[]) if isinstance(payload,dict) else payload
matches=[str(job.get("id","")) for job in jobs if isinstance(job,dict) and job.get("name")=="ai325-editor-daily"]
if len(matches)>1:
    print("duplicate ai325-editor-daily jobs; refusing ambiguous update",file=sys.stderr)
    raise SystemExit(3)
print(matches[0] if matches else "")
PY
)"
fi
if [[ -n "$EDITOR_JOB_ID" ]]; then
  "$HERMES_BIN" cron edit \
    --name ai325-editor-daily \
    --schedule "0 23 * * *" \
    --prompt "$EDITOR_PROMPT" \
    --deliver wecom \
    --script ai325-editor-date.sh \
    --workdir "$REPO" \
    --agent \
    --continuity \
    "$EDITOR_JOB_ID"
  "$HERMES_BIN" cron resume "$EDITOR_JOB_ID"
else
  "$HERMES_BIN" cron create \
    --name ai325-editor-daily \
    --deliver wecom \
    --script ai325-editor-date.sh \
    --workdir "$REPO" \
    --continuity \
    "0 23 * * *" \
    "$EDITOR_PROMPT"
fi
if [[ ! -f "$JOBS" ]] || ! "$PYTHON_BIN" - "$JOBS" <<'PY'
import json,sys
with open(sys.argv[1],encoding="utf-8") as handle:
    payload=json.load(handle)
jobs=payload.get("jobs",[]) if isinstance(payload,dict) else payload
raise SystemExit(0 if sum(1 for job in jobs if isinstance(job,dict) and job.get("name")=="ai325-editor-daily") == 1 else 1)
PY
then
  echo "Hermes CLI returned without one registered ai325-editor-daily job; aborting deployment" >&2
  exit 1
fi

CRON_TEMP="$(mktemp)"
cat > "$CRON_TEMP" <<EOF
# managed-by: ai325_editor
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
# cron.d 按 UTC 触发：北京 07:15 = UTC 23:15（TZ 只影响子进程）。一一总编 Hermes cron 为 UTC 23:00 = 北京 07:00
TZ=Asia/Shanghai
15 23 * * * root AI325_EDITOR_LOCK_WAIT_SECONDS=1800 $REPO/scripts/server-daily.sh --fallback
EOF
install -m 0644 "$CRON_TEMP" "$CRON_FILE"
rm -f "$CRON_TEMP"

if command -v systemctl >/dev/null 2>&1; then
  systemctl restart hermes-gateway.service
fi

cat <<EOF
deploy complete
verify:
  $HERMES_BIN mcp test ai325_editor
  $HERMES_BIN tools list --platform wecom
  $HERMES_BIN cron list --all
  $HERMES_BIN send --to wecom '[一一总编] 主动复命连通性测试'

rollback (inspect backup paths before running):
  cp -p '$CONFIG_BACKUP' '$CONFIG'
  test ! -f '$JOBS_BACKUP' || cp -p '$JOBS_BACKUP' '$JOBS'
  test ! -f '$CRON_BACKUP' || cp -p '$CRON_BACKUP' '$CRON_FILE'
  systemctl restart hermes-gateway.service
EOF
