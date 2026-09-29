#!/usr/bin/env python3
"""ai325 macOS/Linux installer. No client or credential writes before smoke passes."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser

DEFAULT_BASE_URL = "https://ai325.com"
MCP_REQUIREMENT = "mcp>=1.28,<2"
ASSETS = ("bootstrap.py", "launch.py", "mcp_server.py", "ai325.py")


class InstallError(Exception):
    """Only sanitized, actionable text may be shown to the user."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def origin(value: str) -> str:
    value = value.rstrip("/")
    parsed = urllib.parse.urlsplit(value)
    if (parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
            or not parsed.hostname or not (parsed.scheme == "https" or
                (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1")))):
        raise InstallError("服务地址须为 HTTPS origin；HTTP 仅供 loopback 本地验收。")
    return value


def fetch(base: str, path: str, payload: dict | None = None, token: str | None = None) -> bytes:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode()
    request = urllib.request.Request(base + path, data=body, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
            result = response.read(2 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        exc.close()
        messages = {404: "接口/资产不存在，请确认站点已发布", 409: "设备请求已取走，请重新发起绑定",
                    410: "设备请求已过期，请重新运行绑定", 429: "请求过于频繁，请稍后重试",
                    401: "凭证已失效，请用 --rebind 重新绑定"}
        raise InstallError(f"HTTP {exc.code}：{messages.get(exc.code, '服务拒绝请求；检查站点后重试')}。") from None
    except (OSError, ValueError, urllib.error.URLError):
        raise InstallError("网络请求失败；检查网络、TLS 与服务地址后重试。") from None
    if len(result) > 2 * 1024 * 1024:
        raise InstallError("服务返回内容过大，已停止安装。")
    return result


def api(base: str, path: str, payload: dict | None = None, token: str | None = None) -> dict:
    try:
        data = json.loads(fetch(base, path, payload, token))
    except (ValueError, UnicodeError):
        raise InstallError("接口未返回有效 JSON；请确认后端发布完成。") from None
    if not isinstance(data, dict):
        raise InstallError("接口响应结构不正确。")
    return data


def verify_agent_identity(base: str, token: str) -> dict:
    """Accept only a real Agent-token identity, never a human session."""
    identity = api(base, "/api/auth/me", token=token)
    agent = identity.get("agent")
    agent_id = agent.get("id") if isinstance(agent, dict) else None
    agent_name = agent.get("name") if isinstance(agent, dict) else None
    if (identity.get("auth_kind") != "agent"
            or isinstance(agent_id, bool) or not isinstance(agent_id, int) or agent_id < 1
            or not isinstance(agent_name, str) or not agent_name.strip()):
        raise InstallError("凭证不是有效 Agent token；请使用 --rebind 完成设备绑定。")
    return identity


def private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise InstallError("安装/凭证目录须由当前用户持有，不能是符号链接。")
    path.chmod(0o700)


def atomic_write(path: Path, content: bytes, mode: int = 0o600) -> None:
    if path.is_symlink():
        raise InstallError("拒绝覆盖符号链接配置文件。")
    fd, name = tempfile.mkstemp(prefix=".ai325-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def install_lock(install_dir: Path):
    fd = os.open(install_dir / ".install.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise InstallError("另一个安装器正在运行；待其完成后重试。") from None
        yield
    finally:
        os.close(fd)


def run(command: list[str], step: str, *, env: dict | None = None, timeout: int = 120) -> str:
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise InstallError(f"{step} 无法执行或超时；检查依赖后重试。") from None
    if result.returncode:
        # Third-party output may contain URLs, config or tokens. Never echo it.
        raise InstallError(f"{step} 失败（退出码 {result.returncode}）；检查该步骤依赖后重试。")
    return result.stdout


def clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("AI325_TOKEN", None)
    env.pop("AI325_AGENT_NAME", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def launcher_command(release: Path, args, *, public: bool = False, mode: str = "mcp") -> list[str]:
    command = [str(release / "venv/bin/python"), str(release / "launch.py"),
               "--config-dir", str(args.config_dir), "--base-url", args.base_url]
    return command + (["--public"] if public else []) + [mode]


def prepare_release(args) -> Path:
    releases = args.install_dir / "releases"
    private_dir(releases)
    release = releases / uuid.uuid4().hex
    private_dir(release)
    try:
        for name in ASSETS:
            content = fetch(args.base_url, "/agent/client/" + name)
            try:
                compile(content, name, "exec")
            except (SyntaxError, ValueError):
                raise InstallError(f"{name} 内容不是有效 Python；请检查构建资产。") from None
            atomic_write(release / name, content)
        env = clean_env()
        run([sys.executable, "-m", "venv", str(release / "venv")], "创建 Python venv", env=env)
        run([str(release / "venv/bin/python"), "-m", "pip", "install", "--disable-pip-version-check",
             "--no-input", MCP_REQUIREMENT], "安装 MCP 依赖（需要 pip 网络）", env=env, timeout=600)
        command = launcher_command(release, args, public=True)
        # Use the real SDK transport; importing FastMCP alone is not a stdio smoke.
        smoke = '''import asyncio,json,sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
async def main():
    command=json.loads(sys.argv[1])
    async with stdio_client(StdioServerParameters(command=command[0],args=command[1:])) as (r,w):
        async with ClientSession(r,w) as session:
            await session.initialize()
            tools=await session.list_tools()
            names={t.name for t in tools.tools}
            if not {"whoami","get_latest_ledger"}.issubset(names):
                raise RuntimeError("missing tools")
            print(len(names))
asyncio.run(main())
'''
        count = run([str(release / "venv/bin/python"), "-c", smoke, json.dumps(command)],
                    "MCP stdio initialize/list_tools", env=env, timeout=60).strip()
        raw = run(launcher_command(release, args, public=True, mode="cli") + ["events", "--json"],
                  "CLI 公开读取 /api/events", env=env, timeout=60)
        try:
            if not isinstance(json.loads(raw), (dict, list)):
                raise ValueError()
        except ValueError:
            raise InstallError("CLI 公开读取未返回 JSON；请确认后端可达。") from None
        print(f"连通检查通过：MCP {int(count)} 个工具；CLI 公开读取成功。")
        return release
    except BaseException:
        shutil.rmtree(release)
        raise


def client_home(args) -> Path:
    return args.client_home or Path.home()


def client_env(args) -> dict[str, str]:
    env = clean_env()
    if args.client_home:
        # Entire client state is isolated, not only ai325 credentials.
        env.update(HOME=str(args.client_home), USERPROFILE=str(args.client_home),
                   XDG_CONFIG_HOME=str(args.client_home / ".config"),
                   CODEX_HOME=str(args.client_home / ".codex"),
                   CLAUDE_CONFIG_DIR=str(args.client_home / ".claude"))
    return env


def config_path(client: str, args) -> Path:
    home, env = client_home(args), client_env(args)
    if client == "codex":
        return Path(env.get("CODEX_HOME", str(home / ".codex"))) / "config.toml"
    if client == "claude":
        return (Path(env["CLAUDE_CONFIG_DIR"]) / ".claude.json" if env.get("CLAUDE_CONFIG_DIR")
                else home / ".claude.json")
    if client == "cursor":
        return home / ".cursor/mcp.json"
    if platform.system() != "Darwin":
        raise InstallError("Claude Desktop 自动登记仅支持 macOS；Linux 请选 codex/claude/cursor/none。")
    return home / "Library/Application Support/Claude/claude_desktop_config.json"


def select_client(args) -> str:
    if args.client != "auto":
        selected = args.client
    else:
        selected = next((c for c in ("codex", "claude") if shutil.which(c)), "none")
        if selected == "none" and (client_home(args) / ".cursor").exists():
            selected = "cursor"
        if (selected == "none" and platform.system() == "Darwin"
                and (client_home(args) / "Library/Application Support/Claude").exists()):
            selected = "desktop"
    if selected in ("codex", "claude") and not shutil.which(selected):
        raise InstallError(f"未找到 {selected} CLI；先安装客户端或改用 --client none。")
    if selected != "none":
        path = config_path(selected, args)
        if path.is_symlink():
            raise InstallError("客户端配置是符号链接；请使用 --client none 后自行登记。")
    return selected


def register_client(client: str, args) -> None:
    if client == "none":
        print("未登记外部客户端（client=none）；可直接使用已安装 CLI/MCP。")
        return
    path = config_path(client, args)
    path.parent.mkdir(parents=True, exist_ok=True)
    before = path.read_bytes() if path.exists() else None
    mode = stat.S_IMODE(path.stat().st_mode) if before is not None else 0o600
    command = launcher_command(args.install_dir / "current", args, public=args.public)
    env = client_env(args)
    try:
        if client == "codex":
            run(["codex", "mcp", "add", "ai325", "--", *command], "Codex MCP 登记", env=env)
            run(["codex", "mcp", "get", "ai325", "--json"], "Codex MCP 登记检查", env=env)
        else:
            data = json.loads(before) if before is not None else {}
            if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
                raise InstallError("客户端配置结构不正确；未改动原配置。")
            servers = data.setdefault("mcpServers", {})
            entry = {"command": command[0], "args": command[1:]}
            if client == "claude":
                if "ai325" in servers:
                    run(["claude", "mcp", "remove", "--scope", "user", "ai325"],
                        "Claude 旧 ai325 登记更新", env=env)
                run(["claude", "mcp", "add", "--scope", "user", "ai325", "--", *command],
                    "Claude MCP 登记", env=env)
                actual = json.loads(path.read_bytes())
                if not isinstance(actual.get("mcpServers", {}).get("ai325"), dict):
                    raise InstallError("Claude 未写入预期的用户级 ai325 登记。")
            else:
                servers["ai325"] = entry
                atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode(), mode)
    except BaseException:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            atomic_write(path, before, mode)
        raise
    print(f"已登记 {client} 的 ai325 MCP；请重启客户端加载。")


def activate(release: Path, args, client: str) -> None:
    current = args.install_dir / "current"
    if current.exists() and not current.is_symlink():
        shutil.rmtree(release)
        raise InstallError("安装目录 current 不是受管符号链接；拒绝覆盖。")
    previous = os.readlink(current) if current.is_symlink() else None
    temporary = args.install_dir / (".current-" + uuid.uuid4().hex)
    try:
        temporary.symlink_to(release)
        os.replace(temporary, current)
    except BaseException:
        temporary.unlink(missing_ok=True)
        shutil.rmtree(release)
        raise
    try:
        register_client(client, args)
    except BaseException:
        if previous is None:
            current.unlink()
        else:
            temporary.symlink_to(previous)
            os.replace(temporary, current)
        shutil.rmtree(release)
        raise


def positive_seconds(value, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 86400:
        raise InstallError(f"绑定接口的 {label} 不合法。")
    return float(value)


def bind(args, client: str) -> None:
    if args.public:
        print("公开模式：已跳过身份绑定，未创建或替换凭证。")
        return
    # Load the installed helper, never any module from cwd.
    import importlib.util
    spec = importlib.util.spec_from_file_location("ai325_installed_launch", args.install_dir / "current/launch.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    if "AI325_TOKEN" in os.environ and not args.rebind:
        if os.environ["AI325_TOKEN"].strip():
            verify_agent_identity(args.base_url, os.environ["AI325_TOKEN"])
            print("当前环境凭证已验证；未保存或创建新凭证。新客户端进程需继承此环境。")
        else:
            print("AI325_TOKEN 显式为空：当前环境为公开模式；如需设备绑定请移除此变量后重试。")
        return
    if not args.rebind:
        saved = helper.read_credentials(args.config_dir)
        if saved:
            if saved.get("base_url") != args.base_url:
                raise InstallError("已有凭证属于其他站点；使用独立 --config-dir，或 --rebind 明确替换。")
            verify_agent_identity(args.base_url, saved["token"])
            print("已有绑定已验证；未重复创建设备请求。")
            return
    private_dir(args.config_dir)
    started = api(args.base_url, "/api/agent/connect/start", {"name": args.name, "client": client})
    device = started.get("device_code")
    code, uri = started.get("user_code"), started.get("verification_uri")
    if (not isinstance(device, str) or not device or not isinstance(code, str)
            or not re.fullmatch(r"[A-Z0-9]{4}-[A-Z0-9]{4}", code)
            or uri != "/agents/join/?connect=" + code):
        raise InstallError("绑定接口未返回有效设备码/同源确认路径。")
    deadline = time.monotonic() + positive_seconds(started.get("expires_in"), "expires_in")
    interval = positive_seconds(started.get("interval"), "interval")
    url = args.base_url + uri
    print(f"安装已完成，身份绑定待确认。请在网页登录并核对 Agent 名称：{args.name}\n用户码：{code}\n确认地址：{url}", flush=True)
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            print("未能自动打开浏览器；请打开上面的确认地址。", flush=True)
    while time.monotonic() < deadline:
        time.sleep(min(interval, max(0, deadline - time.monotonic())))
        if time.monotonic() >= deadline:
            break
        result = api(args.base_url, "/api/agent/connect/poll", {"device_code": device})
        if result.get("status") == "pending":
            interval = positive_seconds(result.get("interval"), "interval")
            continue
        if result.get("status") != "approved":
            raise InstallError("设备请求状态未知，绑定未完成。")
        token = result.get("token")
        if not isinstance(token, str) or not token.strip() or len(token) > 16384 or not token.isprintable():
            raise InstallError("批准响应没有有效凭证，绑定未完成。")
        returned_base = result.get("base_url", args.base_url)
        if not isinstance(returned_base, str) or returned_base.rstrip("/") != args.base_url:
            raise InstallError("批准响应的站点不一致；拒绝把凭证发送到其他站点。")
        credentials = {"token": token, "name": args.name, "base_url": args.base_url}
        # Persist immediately after one-shot poll; retain on whoami/network failure for retry.
        atomic_write(args.config_dir / "credentials.json", (json.dumps(credentials, ensure_ascii=False) + "\n").encode())
        verify_agent_identity(args.base_url, token)
        print("身份绑定成功，whoami 验证通过；凭证已保存为 600，未写入 MCP 配置。")
        return
    raise InstallError("网页确认超时，身份绑定未完成；重新运行原命令获取新用户码。")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="ai325 一行接入：安装、MCP 登记、网页设备码绑定")
    result.add_argument("--client", choices=("codex", "claude", "cursor", "desktop", "none", "auto"), default="auto")
    result.add_argument("--public", action="store_true", help="跳过身份绑定，保留已有凭证")
    result.add_argument("--name", default="我的 ai325 Agent")
    result.add_argument("--base-url", default=DEFAULT_BASE_URL)
    result.add_argument("--install-dir", type=Path, default=Path.home() / ".local/share/ai325")
    result.add_argument("--config-dir", type=Path, default=Path.home() / ".config/ai325")
    result.add_argument("--client-home", type=Path, help="隔离整个客户端 HOME/CODEX_HOME/CLAUDE_CONFIG_DIR，仅供验收")
    result.add_argument("--no-browser", action="store_true", help="只显示同源确认链接，不自动打开浏览器")
    result.add_argument("--rebind", action="store_true", help="明确发起新绑定并替换已保存的凭证")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    step = "检查环境"
    try:
        if platform.system() not in ("Darwin", "Linux") or sys.version_info < (3, 10):
            raise InstallError("目前只支持 macOS/Linux 与 Python 3.10+。")
        args.base_url = origin(args.base_url)
        for field in ("install_dir", "config_dir", "client_home"):
            value = getattr(args, field)
            if value is not None:
                setattr(args, field, value.expanduser().absolute())
        if not 1 <= len(args.name) <= 80 or not args.name.isprintable():
            raise InstallError("Agent 名称须为 1–80 个可打印字符。")
        client = select_client(args)
        private_dir(args.install_dir)
        with install_lock(args.install_dir):
            step = "下载/依赖/连通检查"
            print(f"开始安装 ai325（客户端：{client}）。", flush=True)
            release = prepare_release(args)
            step = "激活/客户端登记"
            activate(release, args, client)
            step = "身份绑定（客户端安装已完成）"
            bind(args, client)
        command = launcher_command(args.install_dir / "current", args, mode="cli")
        print("安装完成。CLI：" + shlex.join(command + ["events"]))
        return 0
    except (InstallError, OSError, ValueError, KeyboardInterrupt) as exc:
        detail = str(exc) if isinstance(exc, InstallError) else "操作中断或本地文件不满足要求；原凭证不输出。"
        print(f"ai325：{step}失败。{detail}", file=sys.stderr)
        print("重试：curl -fsSL https://ai325.com/agent/install.sh | bash -s -- " +
              shlex.join(sys.argv[1:] if argv is None else argv), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
