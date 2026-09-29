#!/bin/bash
# Canonical source; copied by site/scripts/copy-agent-client.mjs during build.
set -euo pipefail

ai325_install() {
  case "$(uname -s)" in
    Darwin|Linux) ;;
    *) echo 'ai325：目前仅支持 macOS/Linux 与 Python 3.10+。' >&2; return 1 ;;
  esac
  local python_bin='' candidate stage_dir
  for candidate in python3 python3.14 python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3,10))' 2>/dev/null; then
      python_bin="$candidate"; break
    fi
  done
  if [[ -z "$python_bin" ]]; then
    echo 'ai325：需要 Python 3.10+（含 venv）；安装 Python 后重试本命令。' >&2
    return 1
  fi
  stage_dir=$(mktemp -d "${TMPDIR:-/tmp}/ai325-bootstrap.XXXXXXXX")
  trap '[[ -z "${stage_dir:-}" ]] || rm -f "$stage_dir/bootstrap.py"; [[ -z "${stage_dir:-}" ]] || rmdir "$stage_dir" 2>/dev/null || true' EXIT
  "$python_bin" - "$stage_dir/bootstrap.py" "$@" <<'PY'
import argparse, pathlib, sys, urllib.parse, urllib.request
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--base-url', default='https://ai325.com')
args, _ = parser.parse_known_args(sys.argv[2:])
base = args.base_url.rstrip('/')
url = urllib.parse.urlsplit(base)
if (url.username or url.password or url.query or url.fragment or url.path
    or not url.hostname or not (url.scheme == 'https' or
        (url.scheme == 'http' and url.hostname in ('127.0.0.1', 'localhost', '::1')))):
    sys.exit('ai325：服务地址必须是 HTTPS origin；本地测试仅允许 loopback HTTP。')
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None
try:
    with urllib.request.build_opener(NoRedirect).open(base + '/agent/client/bootstrap.py', timeout=45) as response:
        data = response.read(1048577)
    if not data or len(data) > 1048576:
        raise ValueError()
    compile(data, 'bootstrap.py', 'exec')
    pathlib.Path(sys.argv[1]).write_bytes(data)
except Exception:
    sys.exit('ai325：下载/校验安装器失败；检查站点、网络或构建资产后重试原命令。')
PY
  "$python_bin" "$stage_dir/bootstrap.py" "$@" < /dev/null
  rm -f "$stage_dir/bootstrap.py"
  rmdir "$stage_dir"
  stage_dir=''
  trap - EXIT
}
ai325_install "$@"
