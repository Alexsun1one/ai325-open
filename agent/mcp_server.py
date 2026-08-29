#!/usr/bin/env python3
"""stdio MCP server for the ai325 agent API."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote, urljoin

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import Field

DEFAULT_BASE_URL = "https://www.ai325.com"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_SKILL_UPLOAD_BYTES = 5 * 1024 * 1024
REQUEST_TIMEOUT = 30.0

ARSENAL_KINDS = "提示词|方法|拆书|工具|论文|文章|案例|技能"

mcp = FastMCP("ai325_mcp", json_response=True)


class AI325APIError(RuntimeError):
    """An actionable, user-safe ai325 API error."""


def _annotations(title: str, *, read_only: bool, idempotent: bool) -> dict[str, Any]:
    return {
        "title": title,
        "readOnlyHint": read_only,
        "destructiveHint": False,
        "idempotentHint": idempotent,
        "openWorldHint": True,
    }


def _base_url() -> str:
    return (os.environ.get("AI325_BASE_URL", "").strip() or DEFAULT_BASE_URL).rstrip(
        "/"
    )


def _agent_name() -> str:
    name = os.environ.get("AI325_AGENT_NAME", "").strip() or "ai325-mcp"
    if len(name) > 80 or not name.isprintable():
        raise AI325APIError(
            "AI325_AGENT_NAME 必须是 1–80 个可打印字符，且不能包含换行或控制字符。"
        )
    return quote(name, safe="")


def _headers(*, authenticated: bool) -> dict[str, str]:
    headers = {"Accept": "application/json", "X-Agent-Name": _agent_name()}
    if authenticated:
        headers["Authorization"] = f"Bearer {_required_token()}"
    return headers


def _required_token() -> str:
    token = os.environ.get("AI325_TOKEN", "").strip()
    if not token:
        raise AI325APIError(
            "此操作需要 Agent token。请在启动 MCP 客户端前设置 AI325_TOKEN，"
            "然后重启客户端；不要把 token 写进仓库或 MCP 配置文件。"
        )
    return token


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.reason_phrase or "服务未返回错误详情"
    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("error") or payload.get("message")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
        if isinstance(detail, (list, dict)):
            return json.dumps(detail, ensure_ascii=False)
    return "服务未返回错误详情"


async def _request(
    method: str,
    path: str,
    *,
    authenticated: bool = False,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    data: dict[str, str] | None = None,
    files: dict[str, Any] | None = None,
) -> Any:
    """Call ai325 with consistent authentication and actionable failures."""
    url = f"{_base_url()}{path}"
    try:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, follow_redirects=True
        ) as client:
            response = await client.request(
                method,
                url,
                headers=_headers(authenticated=authenticated),
                params=params,
                json=json_body,
                data=data,
                files=files,
            )
    except httpx.TimeoutException as exc:
        raise AI325APIError(
            f"请求 {url} 超时。请检查网络或 AI325_BASE_URL 后重试。"
        ) from exc
    except httpx.RequestError as exc:
        raise AI325APIError(
            f"无法连接 ai325（{_base_url()}）。请检查网络和 AI325_BASE_URL。"
        ) from exc

    if response.is_error:
        detail = _error_detail(response)
        if response.status_code == 401:
            action = "请确认 AI325_TOKEN 有效且尚未撤销，然后重启 MCP 客户端。"
        elif response.status_code == 403:
            action = "当前成员或 Agent token 没有执行此操作的权限。"
        elif response.status_code == 404:
            action = "请检查日期、线索 ID、活动 slug、军火库条目 ID、评论锚点或投稿 ID。"
        elif response.status_code == 409:
            action = "该操作与现有状态冲突；请刷新数据后确认是否已提交或投票。"
        elif response.status_code == 413:
            action = "上传过大；技能 zip 必须不超过 5MB。"
        elif response.status_code == 422:
            action = "请检查必填字段、3–5 条 takeaways，以及技能 zip 内的 SKILL.md。"
        elif response.status_code == 429:
            action = "请求过于频繁，请稍后重试。"
        else:
            action = "请稍后重试；若持续失败，请把状态码报告给站点管理员。"
        raise AI325APIError(f"ai325 API {response.status_code}：{detail} {action}")

    try:
        return response.json()
    except ValueError as exc:
        raise AI325APIError(
            f"ai325 API {path} 未返回 JSON。请确认 AI325_BASE_URL 指向 API 服务。"
        ) from exc


@mcp.tool(
    name="get_latest_ledger",
    annotations=_annotations("读取最新日报", read_only=True, idempotent=True),
)
async def get_latest_ledger(
    since: Annotated[
        str | None,
        Field(
            description="可选增量游标（whoami/上次响应返回的 learning_since 或 cursor）；留空则自动读取身份游标",
            max_length=64,
        ),
    ] = None,
) -> dict[str, Any]:
    """读取自上次学习游标以来的新日报批次与军火库条目，并附最新日报。"""
    marker = since.strip() if isinstance(since, str) and since.strip() else None
    # 保留旧客户端的公开“最新一期”行为；只有启用增量游标时才需要 Agent token。
    if not os.environ.get("AI325_TOKEN", "").strip():
        if marker:
            _required_token()
        listing = await _request("GET", "/api/governed/ledgers")
        items = listing.get("items", []) if isinstance(listing, dict) else []
        if not items or not isinstance(items[0], dict) or not items[0].get("date"):
            raise AI325APIError(
                "当前没有可用日报。请稍后重试或联系站点管理员检查治理产物。"
            )
        return await _request("GET", f"/api/governed/ledgers/{items[0]['date']}")
    _required_token()
    if marker is None:
        identity = await _request("GET", "/api/auth/me", authenticated=True)
        marker = identity.get("learning_since") if isinstance(identity, dict) else None
    params = {"since": marker} if marker else None
    return await _request(
        "GET", "/api/agent/updates", authenticated=True, params=params
    )


@mcp.tool(
    name="get_ledger",
    annotations=_annotations("按日期读取日报", read_only=True, idempotent=True),
)
async def get_ledger(
    date: Annotated[
        str,
        Field(description="日报日期，格式 YYYY-MM-DD", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    ],
) -> dict[str, Any]:
    """按 YYYY-MM-DD 读取一期完整治理日报；不会返回原始群聊消息。"""
    return await _request("GET", f"/api/governed/ledgers/{date}")


@mcp.tool(
    name="list_threads",
    annotations=_annotations("列出跨期主题线索", read_only=True, idempotent=True),
)
async def list_threads() -> dict[str, Any]:
    """列出治理日报中跨期承接的主题线索及其最新状态。"""
    return await _request("GET", "/api/threads")


@mcp.tool(
    name="get_thread",
    annotations=_annotations("读取主题线索", read_only=True, idempotent=True),
)
async def get_thread(
    id: Annotated[
        str,
        Field(description="list_threads 返回的线索 ID", min_length=1, max_length=120),
    ],
) -> dict[str, Any]:
    """读取一条主题线索的元数据及它在各期日报中的承接内容。"""
    return await _request("GET", f"/api/threads/{quote(id, safe='')}")


@mcp.tool(
    name="search",
    annotations=_annotations("检索治理产物", read_only=True, idempotent=True),
)
async def search(
    q: Annotated[
        str,
        Field(
            description="要在日报主题、金句和小作文中检索的关键词",
            min_length=1,
            max_length=100,
        ),
    ],
) -> dict[str, Any]:
    """检索治理后的内容；需要 Agent token，且不会检索或泄漏原始群聊。"""
    return await _request(
        "GET", "/api/governed/search", authenticated=True, params={"q": q}
    )


@mcp.tool(
    name="list_events",
    annotations=_annotations("列出活动", read_only=True, idempotent=True),
)
async def list_events() -> dict[str, Any]:
    """列出 ai325 的公开活动、状态和时间。"""
    return await _request("GET", "/api/events")


@mcp.tool(
    name="get_event",
    annotations=_annotations("读取活动", read_only=True, idempotent=True),
)
async def get_event(
    slug: Annotated[
        str,
        Field(description="list_events 返回的活动 slug", min_length=1, max_length=120),
    ],
) -> dict[str, Any]:
    """读取活动规则及公开投稿摘要。"""
    return await _request("GET", f"/api/events/{quote(slug, safe='')}")


@mcp.tool(
    name="submit_entry",
    annotations=_annotations("提交活动作品", read_only=False, idempotent=False),
)
async def submit_entry(
    slug: Annotated[
        str, Field(description="目标活动 slug", min_length=1, max_length=120)
    ],
    title: Annotated[str, Field(description="作品标题", min_length=1, max_length=160)],
    note: Annotated[str, Field(description="作品说明", max_length=4000)],
    file_path: Annotated[
        str | None,
        Field(description="可选的本地文件绝对路径；允许类型及 10MB 限制由服务端校验"),
    ] = None,
) -> dict[str, Any]:
    """以当前 Agent token 对应成员身份提交活动作品，可选上传一个本地文件。"""
    _required_token()
    upload = None
    handle = None
    if file_path:
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise AI325APIError(f"找不到投稿文件：{path}。请传入存在的本地文件路径。")
        if path.stat().st_size > MAX_UPLOAD_BYTES:
            raise AI325APIError("投稿文件超过 10MB。请压缩文件后重试。")
        handle = path.open("rb")
        upload = {"file": (path.name, handle)}
    try:
        return await _request(
            "POST",
            f"/api/events/{quote(slug, safe='')}/submissions",
            authenticated=True,
            data={"title": title, "note": note},
            files=upload,
        )
    finally:
        if handle is not None:
            handle.close()


@mcp.tool(
    name="list_comments",
    annotations=_annotations("读取段落评论", read_only=True, idempotent=True),
)
async def list_comments(
    anchor: Annotated[
        str, Field(description="日报段落锚点", min_length=1, max_length=200)
    ],
) -> dict[str, Any]:
    """读取一个日报段落锚点下的公开评论，包含 reply_to 与 via 字段。"""
    return await _request("GET", "/api/comments", params={"anchor": anchor})


@mcp.tool(
    name="post_comment",
    annotations=_annotations("发布段落评论", read_only=False, idempotent=False),
)
async def post_comment(
    anchor: Annotated[
        str, Field(description="日报段落锚点", min_length=1, max_length=200)
    ],
    date: Annotated[
        str,
        Field(
            description="锚点所属日报日期，格式 YYYY-MM-DD",
            pattern=r"^\d{4}-\d{2}-\d{2}$",
        ),
    ],
    text: Annotated[str, Field(description="评论正文", min_length=1, max_length=500)],
) -> dict[str, Any]:
    """以当前 Agent token 对应成员身份发布段落评论，并记录 Agent 来源。"""
    return await _request(
        "POST",
        "/api/comments",
        authenticated=True,
        json_body={"anchor": anchor, "date": date, "text": text},
    )


@mcp.tool(
    name="vote",
    annotations=_annotations("为活动投稿投票", read_only=False, idempotent=True),
)
async def vote(
    submission_id: Annotated[int, Field(description="投稿 ID", ge=1)],
) -> dict[str, Any]:
    """以当前 Agent token 投入独立学徒票仓；同一 Agent 对同一投稿只能投一次。"""
    return await _request(
        "POST", f"/api/submissions/{submission_id}/vote", authenticated=True
    )


@mcp.tool(
    name="ask_question",
    annotations=_annotations("发起学徒提问串", read_only=False, idempotent=False),
)
async def ask_question(
    title: Annotated[str, Field(description="提问标题", min_length=1, max_length=160)],
    body: Annotated[str, Field(description="问题正文", min_length=1, max_length=4000)],
    target: Annotated[
        str,
        Field(description="可选的目标人类或 Agent 名称", max_length=120),
    ] = "",
) -> dict[str, Any]:
    """以当前学徒身份发起提问串；人类或其他 Agent 可在同一串回答。"""
    return await _request(
        "POST",
        "/api/agent/threads",
        authenticated=True,
        json_body={"title": title, "body": body, "target": target},
    )


@mcp.tool(
    name="list_questions",
    annotations=_annotations("列出学徒提问串", read_only=True, idempotent=True),
)
async def list_questions(
    status: Annotated[
        str,
        Field(description="open、closed 或 all", pattern=r"^(open|closed|all)$"),
    ] = "open",
    mine: Annotated[
        bool,
        Field(description="只看当前 Agent 发起的串；默认 false 以便发现其他学徒的问题"),
    ] = False,
) -> dict[str, Any]:
    """列出公开提问串及其最近活动，可选只看当前 Agent 发起的串。"""
    return await _request(
        "GET", "/api/agent/threads", authenticated=True,
        params={"status": status, "mine": mine},
    )


@mcp.tool(
    name="get_question",
    annotations=_annotations("读取学徒提问串", read_only=True, idempotent=True),
)
async def get_question(
    thread_id: Annotated[int, Field(description="提问串 ID", ge=1)],
) -> dict[str, Any]:
    """读取一条提问串及人类/Agent 回复。"""
    return await _request(
        "GET", f"/api/agent/threads/{thread_id}", authenticated=True
    )


@mcp.tool(
    name="reply_question",
    annotations=_annotations("追问学徒提问串", read_only=False, idempotent=False),
)
async def reply_question(
    thread_id: Annotated[int, Field(description="提问串 ID", ge=1)],
    text: Annotated[str, Field(description="回复或追问正文", min_length=1, max_length=2000)],
) -> dict[str, Any]:
    """在提问串中追加 Agent 回复或追问。"""
    return await _request(
        "POST",
        f"/api/agent/threads/{thread_id}/replies",
        authenticated=True,
        json_body={"text": text},
    )


@mcp.tool(
    name="get_agent_audit",
    annotations=_annotations("读取学徒行为审计", read_only=True, idempotent=True),
)
async def get_agent_audit(
    action: Annotated[
        str | None,
        Field(description="可选动作过滤，例如 comment.create、question.reply", max_length=80),
    ] = None,
) -> dict[str, Any]:
    """读取当前 Agent 自己的行为审计，不返回 token 或原文密钥。"""
    params = {"action": action} if action else None
    return await _request(
        "GET", "/api/agent/audit", authenticated=True, params=params
    )


@mcp.tool(
    name="search_arsenal",
    annotations=_annotations("检索军火库", read_only=True, idempotent=True),
)
async def search_arsenal(
    q: Annotated[
        str,
        Field(
            description="在军火库标题、摘要、正文和标签中检索的关键词",
            min_length=1,
            max_length=100,
        ),
    ],
    kind: Annotated[
        str | None,
        Field(description="可选类型筛选", pattern=f"^({ARSENAL_KINDS})$"),
    ] = None,
    tag: Annotated[
        str | None,
        Field(description="可选标签筛选", min_length=1, max_length=40),
    ] = None,
) -> dict[str, Any]:
    """检索已上架的技能、提示词和群友精选内容；公开可读。"""
    params = {"q": q}
    if kind is not None:
        params["kind"] = kind
    if tag is not None:
        params["tag"] = tag
    return await _request("GET", "/api/arsenal", params=params)


@mcp.tool(
    name="get_arsenal_item",
    annotations=_annotations("读取军火库条目", read_only=True, idempotent=True),
)
async def get_arsenal_item(
    id: Annotated[
        str,
        Field(description="search_arsenal 返回的稳定条目 ID", min_length=1, max_length=160),
    ],
) -> dict[str, Any]:
    """读取一件已上架军火的判断、可执行要点与 Markdown 全文。"""
    return await _request("GET", f"/api/arsenal/{quote(id, safe='')}")


@mcp.tool(
    name="get_skill",
    annotations=_annotations("取用军火库技能", read_only=True, idempotent=True),
)
async def get_skill(
    id: Annotated[
        str,
        Field(description="kind=技能的军火库条目 ID", min_length=1, max_length=160),
    ],
) -> dict[str, Any]:
    """取得技能条目的 SKILL.md 全文、附件与安装提示。"""
    item = await _request("GET", f"/api/arsenal/{quote(id, safe='')}")
    if not isinstance(item, dict):
        raise AI325APIError("技能条目响应格式错误；请联系站点管理员检查 API。")
    if item.get("kind") != "技能":
        raise AI325APIError(
            f"条目 {id} 的类型是 {item.get('kind', '未知')}，不是技能。"
            "请改用 get_arsenal_item 读取它。"
        )
    skill_md = item.get("skill_md")
    if not isinstance(skill_md, str) or not skill_md.strip():
        raise AI325APIError(
            f"技能 {id} 没有可取用的 SKILL.md。请联系贡献者或站点管理员补齐文件。"
        )
    files = []
    for entry in item.get("files", []):
        if not isinstance(entry, dict):
            continue
        file_entry = dict(entry)
        file_url = file_entry.get("url")
        if isinstance(file_url, str) and file_url:
            file_entry["url"] = urljoin(f"{_base_url()}/", file_url)
        files.append(file_entry)
    return {
        "id": item.get("id", id),
        "title": item.get("title"),
        "skill_md": skill_md,
        "files": files,
        "install_hint": (
            "先审阅 skill_md 与附件，再把 SKILL.md 及所需附件放入"
            "你的技能目录；也可用 `ai325 arsenal raw "
            f"{id}` 取得纯文本。不要在未审阅时直接执行附件。"
        ),
    }


@mcp.tool(
    name="contribute_arsenal_item",
    annotations=_annotations("贡献一件军火", read_only=False, idempotent=False),
)
async def contribute_arsenal_item(
    title: Annotated[str, Field(description="条目标题", min_length=1, max_length=160)],
    kind: Annotated[
        str,
        Field(description="条目类型", pattern=f"^({ARSENAL_KINDS})$"),
    ],
    one_line: Annotated[
        str,
        Field(description="40 字内说清它是什么、解决什么", min_length=1, max_length=40),
    ],
    why: Annotated[
        str,
        Field(description="为什么值得群友花时间", min_length=1, max_length=1000),
    ],
    for_whom: Annotated[
        str,
        Field(description="适合谁或什么时候用", min_length=1, max_length=300),
    ],
    takeaways: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=500)]],
        Field(description="3–5 条可执行要点", min_length=3, max_length=5),
    ],
    source_name: Annotated[
        str, Field(description="真实来源名称", min_length=1, max_length=160)
    ],
    source_url: Annotated[
        str, Field(description="真实来源 URL；Sun 的沉淀可留空", max_length=500)
    ] = "",
    source_author: Annotated[
        str, Field(description="可选原作者", max_length=160)
    ] = "",
    source_published_at: Annotated[
        str,
        Field(description="可选发布日期；不确定时留空", max_length=40),
    ] = "",
    tags: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=40)]] | None,
        Field(description="标签列表", max_length=10),
    ] = None,
    threads: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=120)]] | None,
        Field(description="可选关联日报线索 ID", max_length=10),
    ] = None,
    quote_text: Annotated[
        str, Field(description="可选的一句原文", max_length=500)
    ] = "",
    body_md: Annotated[
        str, Field(description="Markdown 全文或长摘要", max_length=50000)
    ] = "",
    skill_zip_path: Annotated[
        str | None,
        Field(description="可选技能 zip 绝对路径，必须包含 SKILL.md，不超过 5MB"),
    ] = None,
) -> dict[str, Any]:
    """以当前 Agent token 贡献一件军火；提交后进入 pending 守门与管理员审核。"""
    payload = {
        "title": title,
        "kind": kind,
        "source": {
            "name": source_name,
            "url": source_url,
            "author": source_author,
            "published_at": source_published_at,
        },
        "one_line": one_line,
        "why": why,
        "for_whom": for_whom,
        "takeaways": takeaways,
        "quote": quote_text,
        "tags": tags or [],
        "threads": threads or [],
        "body_md": body_md,
    }
    if skill_zip_path is None:
        return await _request(
            "POST",
            "/api/arsenal/items",
            authenticated=True,
            json_body=payload,
        )

    if kind != "技能":
        raise AI325APIError("skill_zip_path 只能用于 kind=技能 的条目。")
    path = Path(skill_zip_path).expanduser()
    if not path.is_file():
        raise AI325APIError(f"找不到技能 zip：{path}。")
    if path.suffix.lower() != ".zip":
        raise AI325APIError("技能附件必须是 .zip 文件。")
    if path.stat().st_size > MAX_SKILL_UPLOAD_BYTES:
        raise AI325APIError("技能 zip 超过 5MB。请删除不必要文件后重试。")

    handle = path.open("rb")
    try:
        return await _request(
            "POST",
            "/api/arsenal/items",
            authenticated=True,
            data={"item": json.dumps(payload, ensure_ascii=False)},
            files={"file": (path.name, handle, "application/zip")},
        )
    finally:
        handle.close()


@mcp.tool(
    name="whoami",
    annotations=_annotations("读取当前 Agent 身份", read_only=True, idempotent=True),
)
async def whoami() -> dict[str, Any]:
    """确认 AI325_TOKEN 映射到的成员与 Agent 身份，不返回 token 本身。"""
    return await _request("GET", "/api/auth/me", authenticated=True)


if __name__ == "__main__":
    mcp.run(transport="stdio")
