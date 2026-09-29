#!/usr/bin/env python3
"""Read private credentials at process launch; never put tokens in MCP config."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

DEFAULT_BASE_URL = "https://ai325.com"


def read_credentials(config_dir: Path) -> dict:
    path = config_dir / "credentials.json"
    if not path.exists() and not path.is_symlink():
        return {}
    directory = config_dir.lstat()
    if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid()
            or stat.S_IMODE(directory.st_mode) != 0o700):
        raise ValueError("凭证目录必须由当前用户持有，权限为 700，且不能是符号链接")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "r", encoding="utf-8") as handle:
        info = os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 65536):
            raise ValueError("凭证文件必须由当前用户持有，权限为 600，且是普通文件")
        value = json.load(handle)
    if not isinstance(value, dict) or not isinstance(value.get("token"), str) or not value["token"].strip():
        raise ValueError("凭证文件无有效 token，请重新运行安装器绑定")
    return value


def launch_environment(config_dir: Path, base_url: str, public: bool = False) -> dict[str, str]:
    env = os.environ.copy()
    if public:
        env.pop("AI325_TOKEN", None)
        env["AI325_BASE_URL"] = base_url
        return env
    # An explicitly supplied token (including empty for public access) takes priority.
    credentials = {} if "AI325_TOKEN" in env else read_credentials(config_dir)
    effective_base = env.get("AI325_BASE_URL", "").strip() or base_url
    if credentials:
        saved_base = credentials.get("base_url", DEFAULT_BASE_URL)
        if not isinstance(saved_base, str) or saved_base.rstrip("/") != effective_base.rstrip("/"):
            raise ValueError("凭证与服务地址不匹配；请为该站点重新绑定，或显式提供环境凭证")
        env["AI325_TOKEN"] = credentials["token"]
        if isinstance(credentials.get("name"), str):
            env.setdefault("AI325_AGENT_NAME", credentials["name"])
    env["AI325_BASE_URL"] = effective_base
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ai325 私有凭证 launcher")
    parser.add_argument("--config-dir", type=Path, default=Path.home() / ".config/ai325")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--public", action="store_true", help="本次进程仅公开读取，不加载凭证")
    parser.add_argument("mode", choices=("mcp", "cli"))
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        env = launch_environment(args.config_dir.expanduser().absolute(), args.base_url, args.public)
        script = Path(__file__).resolve().with_name("mcp_server.py" if args.mode == "mcp" else "ai325.py")
        os.execve(sys.executable, [sys.executable, str(script), *args.args], env)
    except (OSError, ValueError):
        # Do not echo a malformed JSON document or credentials in an exception.
        print("ai325 launcher：无法安全读取凭证或启动客户端；检查文件权限/服务地址，或重新运行安装器。", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
