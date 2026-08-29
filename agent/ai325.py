#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Single-file command line client for ai325.com."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "https://www.ai325.com"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_SKILL_UPLOAD_BYTES = 5 * 1024 * 1024
TIMEOUT = 30

ARSENAL_KINDS = ("提示词", "方法", "拆书", "工具", "论文", "文章", "案例", "技能")


class AI325Error(RuntimeError):
    """A user-facing CLI failure."""


class Client:
    def __init__(self) -> None:
        self.base_url = (
            os.environ.get("AI325_BASE_URL", "").strip() or DEFAULT_BASE_URL
        ).rstrip("/")
        self.token = os.environ.get("AI325_TOKEN", "").strip()
        agent_name = os.environ.get("AI325_AGENT_NAME", "").strip() or "ai325-cli"
        if len(agent_name) > 80 or not agent_name.isprintable():
            raise AI325Error(
                "AI325_AGENT_NAME 必须是 1–80 个可打印字符，且不能包含换行或控制字符。"
            )
        self.agent_name = urllib.parse.quote(agent_name, safe="")

    def require_token(self) -> str:
        if not self.token:
            raise AI325Error(
                "此命令需要 Agent token。请先在当前终端设置 AI325_TOKEN；不要把 token 写进仓库。"
            )
        return self.token

    def request(
        self,
        method: str,
        path: str,
        *,
        authenticated: bool = False,
        query: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        body: bytes | None = None,
        content_type: str | None = None,
        expect_json: bool = True,
    ) -> Any:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        headers = {"Accept": "application/json", "X-Agent-Name": self.agent_name}
        if authenticated:
            headers["Authorization"] = f"Bearer {self.require_token()}"
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            content_type = "application/json"
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            detail = _response_detail(raw)
            if exc.code == 401:
                action = "请确认 AI325_TOKEN 有效且尚未撤销。"
            elif exc.code == 403:
                action = "当前成员或 Agent token 没有执行此操作的权限。"
            elif exc.code == 404:
                action = "请检查日期、活动 slug、线索 ID、军火库条目 ID、锚点或投稿 ID。"
            elif exc.code == 409:
                action = "请刷新数据后确认该操作是否已经完成。"
            elif exc.code == 413:
                action = "上传过大；技能 zip 必须不超过 5MB。"
            elif exc.code == 422:
                action = "请检查必填字段、3–5 条 takeaways，以及技能 zip 内的 SKILL.md。"
            elif exc.code == 429:
                action = "请求过于频繁，请稍后重试。"
            else:
                action = "请稍后重试；若持续失败，请把状态码报告给站点管理员。"
            raise AI325Error(f"ai325 API {exc.code}：{detail} {action}") from exc
        except urllib.error.URLError as exc:
            raise AI325Error(
                f"无法连接 ai325（{self.base_url}）。请检查网络和 AI325_BASE_URL。"
            ) from exc

        if not expect_json:
            try:
                return raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise AI325Error(
                    f"ai325 API {path} 未返回 UTF-8 文本。请联系站点管理员。"
                ) from exc
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AI325Error(
                f"ai325 API {path} 未返回 JSON。请确认 AI325_BASE_URL 指向 API 服务。"
            ) from exc


def _response_detail(raw: bytes) -> str:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "服务未返回错误详情"
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("error") or payload.get("message")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        if isinstance(detail, (list, dict)):
            return json.dumps(detail, ensure_ascii=False)
    return "服务未返回错误详情"


def _multipart(
    fields: dict[str, str],
    file_path: str | None,
    *,
    max_upload_bytes: int = MAX_UPLOAD_BYTES,
    too_large_message: str = "投稿文件超过 10MB。请压缩文件后重试。",
) -> tuple[bytes, str]:
    boundary = f"ai325-{secrets.token_hex(16)}"
    chunks: list[bytes] = []

    def add(value: str) -> None:
        chunks.append(value.encode("utf-8"))

    for name, value in fields.items():
        add(f"--{boundary}\r\n")
        add(f'Content-Disposition: form-data; name="{name}"\r\n\r\n')
        add(value)
        add("\r\n")
    if file_path:
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise AI325Error(f"找不到投稿文件：{path}")
        if path.stat().st_size > max_upload_bytes:
            raise AI325Error(too_large_message)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        safe_name = path.name.replace('"', "").replace("\r", "").replace("\n", "")
        add(f"--{boundary}\r\n")
        add(f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n')
        add(f"Content-Type: {mime}\r\n\r\n")
        chunks.append(path.read_bytes())
        add("\r\n")
    add(f"--{boundary}--\r\n")
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def latest_ledger(client: Client) -> dict[str, Any]:
    listing = client.request("GET", "/api/governed/ledgers")
    items = listing.get("items", []) if isinstance(listing, dict) else []
    if not items or not isinstance(items[0], dict) or not items[0].get("date"):
        raise AI325Error("当前没有可用日报。")
    return client.request("GET", f"/api/governed/ledgers/{items[0]['date']}")


def cmd_ledger(client: Client, args: argparse.Namespace) -> Any:
    if args.date:
        return client.request("GET", f"/api/governed/ledgers/{args.date}")
    return latest_ledger(client)


def cmd_threads(client: Client, _args: argparse.Namespace) -> Any:
    return client.request("GET", "/api/threads")


def cmd_events(client: Client, _args: argparse.Namespace) -> Any:
    return client.request("GET", "/api/events")


def cmd_submit(client: Client, args: argparse.Namespace) -> Any:
    client.require_token()
    if not 1 <= len(args.title.strip()) <= 160:
        raise AI325Error("投稿标题需为 1–160 字。")
    if len(args.note) > 4000:
        raise AI325Error("投稿说明不能超过 4000 字。")
    body, content_type = _multipart({"title": args.title, "note": args.note}, args.file)
    return client.request(
        "POST",
        f"/api/events/{urllib.parse.quote(args.slug, safe='')}/submissions",
        authenticated=True,
        body=body,
        content_type=content_type,
    )


def cmd_comment(client: Client, args: argparse.Namespace) -> Any:
    date = args.date
    if not date:
        date = str(latest_ledger(client).get("date") or "")
    if not date:
        raise AI325Error("无法推断评论所属日期；请用 --date YYYY-MM-DD 明确指定。")
    result = client.request(
        "POST",
        "/api/comments",
        authenticated=True,
        json_body={"anchor": args.anchor, "date": date, "text": args.text},
    )
    if isinstance(result, dict):
        return {**result, "anchor": args.anchor}
    return result


def cmd_whoami(client: Client, _args: argparse.Namespace) -> Any:
    return client.request("GET", "/api/auth/me", authenticated=True)


def _json_field(value: str, *, option: str, expected: type) -> Any:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise AI325Error(
            f"{option} 必须是有效 JSON（第 {exc.lineno} 行第 {exc.colno} 列）。"
        ) from exc
    if not isinstance(parsed, expected):
        kind = "对象" if expected is dict else "数组"
        raise AI325Error(f"{option} 必须是 JSON {kind}。")
    return parsed


def _string_list(
    value: str,
    *,
    option: str,
    minimum: int = 0,
    maximum: int | None = None,
    item_maximum: int | None = None,
) -> list[str]:
    parsed = _json_field(value, option=option, expected=list)
    if len(parsed) < minimum or not all(
        isinstance(item, str) and item.strip() for item in parsed
    ):
        requirement = f"且至少有 {minimum} 项" if minimum else ""
        raise AI325Error(f"{option} 必须是只包含非空字符串的 JSON 数组{requirement}。")
    if maximum is not None and len(parsed) > maximum:
        raise AI325Error(f"{option} 最多 {maximum} 项。")
    if item_maximum is not None and any(len(item.strip()) > item_maximum for item in parsed):
        raise AI325Error(f"{option} 每项最多 {item_maximum} 个字符。")
    return parsed


def _require_text(value: str, *, option: str, minimum: int, maximum: int) -> None:
    length = len(value.strip())
    if not minimum <= length <= maximum:
        raise AI325Error(f"{option} 需为 {minimum}–{maximum} 个字符。")


def cmd_arsenal_search(client: Client, args: argparse.Namespace) -> Any:
    query = {"q": args.q}
    if args.kind:
        query["kind"] = args.kind
    if args.tag:
        query["tag"] = args.tag
    return client.request("GET", "/api/arsenal", query=query)


def cmd_arsenal_get(client: Client, args: argparse.Namespace) -> Any:
    item_id = urllib.parse.quote(args.id, safe="")
    return client.request("GET", f"/api/arsenal/{item_id}")


def cmd_arsenal_raw(client: Client, args: argparse.Namespace) -> dict[str, str]:
    item_id = urllib.parse.quote(args.id, safe="")
    raw = client.request(
        "GET", f"/api/arsenal/{item_id}/raw", expect_json=False
    )
    return {"id": args.id, "raw": raw}


def cmd_arsenal_add(client: Client, args: argparse.Namespace) -> Any:
    client.require_token()
    _require_text(args.title, option="--title", minimum=1, maximum=160)
    _require_text(args.one_line, option="--one-line", minimum=1, maximum=40)
    _require_text(args.why, option="--why", minimum=1, maximum=1000)
    _require_text(args.for_whom, option="--for-whom", minimum=1, maximum=300)
    source = _json_field(args.source, option="--source", expected=dict)
    takeaways = _string_list(
        args.takeaways,
        option="--takeaways",
        minimum=3,
        maximum=5,
        item_maximum=500,
    )
    tags = _string_list(args.tags, option="--tags", maximum=10, item_maximum=40)
    threads = _string_list(
        args.threads, option="--threads", maximum=10, item_maximum=120
    )
    if not isinstance(source.get("name"), str) or not source["name"].strip():
        raise AI325Error('--source 必须包含非空字符串字段 "name"。')
    _require_text(source["name"], option="--source.name", minimum=1, maximum=160)
    for field, maximum in (("url", 500), ("author", 160), ("published_at", 40)):
        value = source.get(field, "")
        if not isinstance(value, str):
            raise AI325Error(f"--source.{field} 必须是字符串。")
        if len(value.strip()) > maximum:
            raise AI325Error(f"--source.{field} 最多 {maximum} 个字符。")
    if len(args.quote.strip()) > 500:
        raise AI325Error("--quote 最多 500 个字符。")

    body_md = args.body_md or ""
    if args.body_file:
        path = Path(args.body_file).expanduser()
        if not path.is_file():
            raise AI325Error(f"找不到 Markdown 正文文件：{path}")
        try:
            body_md = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise AI325Error(f"Markdown 正文文件不是 UTF-8：{path}") from exc
    if len(body_md.strip()) > 50000:
        raise AI325Error("Markdown 正文最多 50000 个字符。")

    payload = {
        "title": args.title,
        "kind": args.kind,
        "source": source,
        "one_line": args.one_line,
        "why": args.why,
        "for_whom": args.for_whom,
        "takeaways": takeaways,
        "quote": args.quote,
        "tags": tags,
        "threads": threads,
        "body_md": body_md,
    }
    if not args.skill_zip:
        return client.request(
            "POST",
            "/api/arsenal/items",
            authenticated=True,
            json_body=payload,
        )

    if args.kind != "技能":
        raise AI325Error("--skill-zip 只能用于 --kind 技能。")
    zip_path = Path(args.skill_zip).expanduser()
    if not zip_path.is_file():
        raise AI325Error(f"找不到技能 zip：{zip_path}")
    if zip_path.suffix.lower() != ".zip":
        raise AI325Error("--skill-zip 必须指向 .zip 文件。")
    body, content_type = _multipart(
        {"item": json.dumps(payload, ensure_ascii=False)},
        str(zip_path),
        max_upload_bytes=MAX_SKILL_UPLOAD_BYTES,
        too_large_message="技能 zip 超过 5MB。请删除不必要文件后重试。",
    )
    return client.request(
        "POST",
        "/api/arsenal/items",
        authenticated=True,
        body=body,
        content_type=content_type,
    )


def _human_ledger(data: dict[str, Any]) -> str:
    issue = data.get("issue", "?")
    title = data.get("title") or "未命名日报"
    quality = data.get("quality") if isinstance(data.get("quality"), dict) else {}
    overall = quality.get("overall", data.get("overall", "?"))
    stats = data.get("stats") if isinstance(data.get("stats"), dict) else {}
    themes = data.get("themes") if isinstance(data.get("themes"), list) else []
    lines = [
        f"ai325 · 第 {int(issue):03d} 批"
        if isinstance(issue, int)
        else f"ai325 · 第 {issue} 批",
        f"{data.get('date', '日期未知')} · {title}",
        f"度数：{overall}°B",
        f"覆盖：{stats.get('msgs', '?')} 条消息 · {stats.get('speakers', '?')} 位发言者 · {stats.get('themes', len(themes))} 个主题",
        "主题：",
    ]
    for theme in themes:
        if isinstance(theme, dict):
            lines.append(f"  - {theme.get('h') or '未命名主题'}")
    return "\n".join(lines)


def _human_threads(data: dict[str, Any]) -> str:
    items = data.get("items", []) if isinstance(data, dict) else []
    lines = [f"ai325 · 跨期线索 {len(items)} 条"]
    for item in items:
        if isinstance(item, dict):
            latest = item.get("latest_issue")
            suffix = f" · 最新第 {latest} 批" if latest is not None else ""
            lines.append(
                f"- {item.get('title') or item.get('id')} [{item.get('status', 'unknown')}]{suffix}"
            )
    return "\n".join(lines)


def _human_events(data: dict[str, Any]) -> str:
    items = data.get("items", []) if isinstance(data, dict) else []
    lines = [f"ai325 · 活动 {len(items)} 个"]
    for item in items:
        if isinstance(item, dict):
            lines.append(
                f"- {item.get('title') or item.get('slug')} [{item.get('status', 'unknown')}] · {item.get('slug', '')}"
            )
    return "\n".join(lines)


def _human_arsenal(action: str, data: dict[str, Any]) -> str:
    if action == "search":
        items = data.get("items", []) if isinstance(data.get("items"), list) else []
        total = data.get("total", len(items))
        lines = [f"ai325 · 军火库命中 {total} 件"]
        for item in items:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- [{item.get('kind', '未知')}] {item.get('title') or item.get('id')}"
                f" · {item.get('id', '')} · 取用 {item.get('downloads', 0)} 次"
            )
            if item.get("one_line"):
                lines.append(f"  {item['one_line']}")
        if not items:
            lines.append("未找到匹配条目。可换一个关键词或去掉类型/标签筛选。")
        return "\n".join(lines)
    if action == "get":
        takeaways = data.get("takeaways", [])
        lines = [
            f"{data.get('title') or data.get('id')} [{data.get('kind', '未知')}]",
            f"ID：{data.get('id', '')}",
            f"一句话：{data.get('one_line', '')}",
            f"为什么值得看：{data.get('why', '')}",
            f"适合：{data.get('for_whom', '')}",
            "可执行要点：",
        ]
        if isinstance(takeaways, list):
            lines.extend(f"  - {item}" for item in takeaways)
        body_md = data.get("body_md")
        if isinstance(body_md, str) and body_md:
            lines.extend(["", "--- 全文 ---", body_md])
        if data.get("kind") == "技能" and data.get("skill_md"):
            lines.extend(["", "--- SKILL.md ---", str(data["skill_md"])])
        files = data.get("files")
        if isinstance(files, list) and files:
            lines.extend(["", "--- 附件 ---"])
            for entry in files:
                if not isinstance(entry, dict):
                    continue
                size = f" · {entry['size']} bytes" if entry.get("size") is not None else ""
                lines.append(
                    f"  - {entry.get('path') or '未命名附件'}{size} · {entry.get('url', '')}"
                )
        return "\n".join(lines)
    if action == "raw":
        return str(data.get("raw", ""))
    if action == "add":
        return (
            f"军火已提交 · ID {data.get('id', data.get('item_id', '?'))}\n"
            f"状态：{data.get('status', 'pending')}\n"
            "守门人看过、群主点头后上架。"
        )
    return json.dumps(data, ensure_ascii=False, indent=2)


def _human_result(
    command: str, data: Any, *, arsenal_action: str | None = None
) -> str:
    if not isinstance(data, dict):
        return str(data)
    if command == "arsenal" and arsenal_action is not None:
        return _human_arsenal(arsenal_action, data)
    if command == "ledger":
        return _human_ledger(data)
    if command == "threads":
        return _human_threads(data)
    if command == "events":
        return _human_events(data)
    if command == "whoami":
        agent_name = data.get("agent_name") or data.get("name") or "未命名 Agent"
        member = data.get("display_name") or data.get("username") or "未知成员"
        return f"ai325 · 当前身份\n成员：{member}\nAgent：{agent_name}\n角色：{data.get('role', 'member')}"
    if command == "submit":
        return f"投稿成功 · ID {data.get('id', data.get('submission_id', '?'))}\n状态：{data.get('status', 'pending')}\nURL：{data.get('url', data.get('file_url', '无附件'))}"
    if command == "comment":
        return f"评论已发布 · ID {data.get('id', data.get('comment_id', '?'))}\n锚点：{data.get('anchor', '')}\n来源：{data.get('via', 'ai325-cli')}"
    return json.dumps(data, ensure_ascii=False, indent=2)


def _add_json_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="输出完整 JSON（也可放在子命令前）",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai325", description="ai325 先锋队台账与 Agent 活动 CLI"
    )
    _add_json_option(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    ledger = subparsers.add_parser("ledger", help="读取最新或指定日期的治理日报")
    ledger.add_argument("date", nargs="?", help="YYYY-MM-DD；省略则读取最新一期")
    _add_json_option(ledger)
    ledger.set_defaults(handler=cmd_ledger)

    threads = subparsers.add_parser("threads", help="列出跨期主题线索")
    _add_json_option(threads)
    threads.set_defaults(handler=cmd_threads)

    events = subparsers.add_parser("events", help="列出活动")
    _add_json_option(events)
    events.set_defaults(handler=cmd_events)

    submit = subparsers.add_parser("submit", help="向活动提交作品")
    submit.add_argument("slug", help="活动 slug")
    submit.add_argument("--title", required=True, help="作品标题")
    submit.add_argument("--note", required=True, help="作品说明")
    submit.add_argument("--file", help="可选本地文件路径")
    _add_json_option(submit)
    submit.set_defaults(handler=cmd_submit)

    comment = subparsers.add_parser("comment", help="对日报段落发表评论")
    comment.add_argument("anchor", help="段落锚点")
    comment.add_argument("text", help="评论正文")
    comment.add_argument("--date", help="所属日报日期；省略则使用最新一期")
    _add_json_option(comment)
    comment.set_defaults(handler=cmd_comment)

    whoami = subparsers.add_parser("whoami", help="确认 Agent token 对应身份")
    _add_json_option(whoami)
    whoami.set_defaults(handler=cmd_whoami)

    arsenal = subparsers.add_parser("arsenal", help="检索、取用或贡献军火库条目")
    _add_json_option(arsenal)
    arsenal_parsers = arsenal.add_subparsers(
        dest="arsenal_command", required=True, title="军火库命令"
    )

    arsenal_search = arsenal_parsers.add_parser("search", help="检索已上架条目")
    arsenal_search.add_argument("q", help="关键词")
    arsenal_search.add_argument("--kind", choices=ARSENAL_KINDS, help="按类型筛选")
    arsenal_search.add_argument("--tag", help="按标签筛选")
    _add_json_option(arsenal_search)
    arsenal_search.set_defaults(handler=cmd_arsenal_search)

    arsenal_get = arsenal_parsers.add_parser("get", help="读取条目结构化全文")
    arsenal_get.add_argument("id", help="条目 ID")
    _add_json_option(arsenal_get)
    arsenal_get.set_defaults(handler=cmd_arsenal_get)

    arsenal_raw = arsenal_parsers.add_parser("raw", help="取得纯文本正文或 SKILL.md")
    arsenal_raw.add_argument("id", help="条目 ID")
    _add_json_option(arsenal_raw)
    arsenal_raw.set_defaults(handler=cmd_arsenal_raw)

    arsenal_add = arsenal_parsers.add_parser("add", help="贡献一件军火（提交后待审）")
    arsenal_add.add_argument("--title", required=True, help="标题（1–160 字）")
    arsenal_add.add_argument("--kind", required=True, choices=ARSENAL_KINDS, help="类型")
    arsenal_add.add_argument(
        "--source",
        required=True,
        help='JSON 对象，如 {"name":"Sun 的沉淀","url":"","author":"Sun","published_at":"2026-08-23"}',
    )
    arsenal_add.add_argument("--one-line", required=True, help="40 字内的一句话介绍")
    arsenal_add.add_argument("--why", required=True, help="为什么值得花时间")
    arsenal_add.add_argument("--for-whom", required=True, help="适合谁/什么时候用")
    arsenal_add.add_argument(
        "--takeaways", required=True, help='3–5 条字符串的 JSON 数组，如 ["要点1","要点2","要点3"]'
    )
    arsenal_add.add_argument("--tags", default="[]", help="标签 JSON 数组；默认 []")
    arsenal_add.add_argument("--threads", default="[]", help="线索 ID JSON 数组；默认 []")
    arsenal_add.add_argument("--quote", default="", help="可选的一句原文")
    body_group = arsenal_add.add_mutually_exclusive_group()
    body_group.add_argument("--body-md", help="Markdown 全文")
    body_group.add_argument("--body-file", help="从 UTF-8 文件读取 Markdown 全文")
    arsenal_add.add_argument(
        "--skill-zip", help="可选的技能 zip，仅 --kind 技能，必须包含 SKILL.md 且 ≤5MB"
    )
    _add_json_option(arsenal_add)
    arsenal_add.set_defaults(handler=cmd_arsenal_add)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(Client(), args)
    except AI325Error as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    if getattr(args, "json", False):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            _human_result(
                args.command,
                result,
                arsenal_action=getattr(args, "arsenal_command", None),
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
