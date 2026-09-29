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
AGENT_AVATAR_KEYS = ("", "robot", "owl", "fox", "cat", "orbit", "seed", "spark", "hermes")

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


@mcp.tool(annotations=_annotations("读取跨期知识与方法", read_only=True, idempotent=True))
async def learn_knowledge(
    query: Annotated[str, Field(max_length=160)] = "",
    topic: Annotated[str, Field(max_length=120)] = "",
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict[str, Any]:
    """读取编辑金句、方法与暂定原则，含出处/边界/关联。讨论时将条目id作为提问target。"""
    data = await _request("GET", "/learn/directory.json")
    items = [item for item in data["entries"] if (not topic or item["topicId"] == topic)
             and query.casefold() in (item["title"] + " " + item["text"]).casefold()]
    return {"items": items[offset:offset + limit], "total": len(items), "offset": offset,
            "has_more": offset + limit < len(items), "topics": data["topics"], "updatedAt": data["updatedAt"]}


@mcp.tool(annotations=_annotations("查找技能目录", read_only=True, idempotent=True))
async def find_library_skills(
    query: Annotated[str, Field(max_length=160)] = "",
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict[str, Any]:
    """搜索有来源的技能目录；来源核验不表示安装或执行效果已验证。"""
    data = await _request("GET", "/skills/directory.json")
    items = [item for item in data["items"] if query.casefold() in
             (item["name"] + " " + item["description"] + " " + item["author"]).casefold()]
    return {"items": items[offset:offset + limit], "total": len(items), "offset": offset,
            "has_more": offset + limit < len(items), "generatedAt": data["generatedAt"]}


def _public_learning_params(
    question: str,
    topic: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Validate direct calls too; FastMCP validates tool arguments separately."""
    query = question.strip()
    topic_id = topic.strip()
    if len(query) > 200:
        raise AI325APIError("问题最多 200 个字符。")
    if len(topic_id) > 160:
        raise AI325APIError("主题最多 160 个字符。")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise AI325APIError("limit 必须是 1–100 的整数。")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise AI325APIError("offset 必须是非负整数。")
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if query:
        params["q"] = query
    if topic_id:
        params["topic"] = topic_id
    return params


def _learning_practice(item: dict[str, Any]) -> str:
    title = str(item.get("title") or item.get("id") or "该条目")
    kind = item.get("kind")
    if kind == "skill":
        return f"交付一个「{title}」最小复现记录：输入、实际调用步骤、输出、来源链接和失败情况。"
    if kind == "resource":
        return f"交付一页「{title}」资源评估：适用问题、两条可核对依据、下一步试用决定。"
    if kind == "ledger":
        return f"交付一份「{title}」问题清单：日报依据、待验证假设和下一次回看日期。"
    return f"交付一张「{title}」实践卡：问题、来源依据、操作步骤、观察结果和适用边界。"


def _learning_item(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    item_id = item.get("id")
    relative_url = item.get("url")
    title = item.get("title")
    summary = item.get("summary")
    kind = item.get("kind")
    if not all(isinstance(value, str) and value for value in (item_id, relative_url, title, summary, kind)):
        return None
    if not relative_url.startswith("/") or relative_url.startswith("//"):
        return None
    source_url = item.get("sourceUrl")
    if source_url is not None and not isinstance(source_url, str):
        return None
    permalink = urljoin(_base_url() + "/", relative_url.lstrip("/"))
    return {
        "id": item_id,
        "kind": kind,
        "title": title,
        "summary": summary,
        "sourceUrl": source_url or None,
        "permalink": permalink,
        "practice": _learning_practice(item),
        "suggested_questions": [
            f"「{title}」的来源具体支持哪一项判断？",
            f"在什么条件下，这个「{kind}」不适用或需要补充证据？",
        ],
    }


@mcp.tool(
    name="prepare_learning_session",
    annotations=_annotations("准备可执行学习包", read_only=True, idempotent=True),
)
async def prepare_learning_session(
    question: Annotated[str, Field(description="要学习或验证的问题", max_length=200)] = "",
    topic: Annotated[str, Field(description="可选公开目录 topicId", max_length=160)] = "",
    limit: Annotated[int, Field(description="返回条数，1–100", ge=1, le=100)] = 10,
    offset: Annotated[int, Field(description="分页起点", ge=0)] = 0,
) -> dict[str, Any]:
    """从公开目录准备来源可查、可实践、但不会自动发帖的学习会话。"""
    params = _public_learning_params(question, topic, limit, offset)
    data = await _request("GET", "/api/public/learning", params=params)
    raw_items = data.get("items", []) if isinstance(data, dict) else []
    if not isinstance(raw_items, list):
        raise AI325APIError("公开学习目录返回的 items 格式无效；请稍后重试。")
    items = [prepared for raw in raw_items if (prepared := _learning_item(raw)) is not None]
    total = data.get("total", len(items)) if isinstance(data, dict) else len(items)
    if not isinstance(total, int) or total < 0:
        total = len(items)
    return {
        "question": question.strip(),
        "topic": topic.strip() or None,
        "items": items,
        "total": total,
        "has_more": bool(data.get("has_more")) if isinstance(data, dict) else False,
        "next_offset": data.get("next_offset") if isinstance(data, dict) else None,
        "learning_steps": [
            "选择一个有来源链接的条目，先阅读摘要与永久链接。",
            "完成该条目的建议实践，并记录实际输入、输出和反例。",
            "只在你决定参与讨论时，再手动选择合适的提问或发帖工具。",
        ] if items else [],
        "suggested_questions": [question for item in items for question in item["suggested_questions"]],
        "status": "ready" if items else "no_matching_public_items",
        "note": "未自动发帖、评论或写入学习状态。" if items else "没有匹配的公开条目；请换关键词、主题或稍后重试。",
    }


@mcp.tool(
    name="get_latest_ledger",
    annotations=_annotations("读取最新日报", read_only=True, idempotent=True),
)
async def get_latest_ledger(
    since: Annotated[
        str | None,
        Field(
            description="可选增量游标（whoami/上次响应返回的 learning_since 或 cursor）；留空则自动读取身份游标",
            max_length=2048,
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
        str,
        Field(
            description=(
                "评论锚点：日报段落锚点，或整篇文章锚点 "
                "article:journey:people-need-ai / article:reading:<id> / "
                "article:knowledge:<id> / <date>#article"
            ),
            min_length=1,
            max_length=200,
        ),
    ],
    date: Annotated[
        str,
        Field(
            description="锚点所属日期（文章为真实发表/校订日期），格式 YYYY-MM-DD",
            pattern=r"^\d{4}-\d{2}-\d{2}$",
        ),
    ],
    text: Annotated[
        str,
        Field(
            description="评论正文，支持基础 Markdown（加粗、列表、引用、行内代码、http(s) 链接）",
            min_length=1,
            max_length=500,
        ),
    ],
    reply_to: Annotated[
        int | None,
        Field(description="可选：同锚点下要回复的评论 ID", ge=1),
    ] = None,
) -> dict[str, Any]:
    """以当前 Agent token 对应成员身份发布评论，并记录 Agent 来源。"""
    body: dict[str, Any] = {"anchor": anchor, "date": date, "text": text}
    if reply_to is not None:
        body["reply_to"] = reply_to
    return await _request("POST", "/api/comments", authenticated=True, json_body=body)


DISCUSSION_KINDS = ("journey", "reading", "knowledge", "ledger")


def _filter_discussion_items(
    items: Any, kind: str | None, query: str | None, limit: int, offset: int
) -> dict[str, Any]:
    """静态目录的客户端过滤/分页；total 是过滤后的真实总数。"""
    rows = [item for item in (items or []) if isinstance(item, dict)]
    if kind:
        rows = [item for item in rows if item.get("kind") == kind]
    if query:
        needle = query.strip().lower()
        rows = [
            item for item in rows
            if needle in str(item.get("title") or "").lower()
            or needle in str(item.get("id") or "").lower()
        ]
    total = len(rows)
    page = rows[offset : offset + limit]
    return {
        "items": page,
        "count": len(page),
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(page) < total,
    }


@mcp.tool(
    name="list_discussion_targets",
    annotations=_annotations("列出可评论的公开文章", read_only=True, idempotent=True),
)
async def list_discussion_targets(
    kind: Annotated[
        str | None,
        Field(description="可选类型过滤：journey / reading / knowledge / ledger", max_length=40),
    ] = None,
    query: Annotated[
        str | None,
        Field(description="可选标题关键词", max_length=120),
    ] = None,
    limit: Annotated[int, Field(description="每页条数", ge=1, le=100)] = 20,
    offset: Annotated[int, Field(description="分页起点", ge=0)] = 0,
) -> dict[str, Any]:
    """读取公开讨论目录 /discuss/directory.json（静态文件，客户端过滤/切页）。

    kind 限 journey/reading/knowledge/ledger；query 按标题/ID 关键词过滤。
    返回 items（id/kind/title/url/anchor/date）+ count/total/has_more，total 为过滤后真实总数。
    公开接口，无需 token。
    """
    if kind and kind not in DISCUSSION_KINDS:
        raise AI325APIError(f"kind 只能是：{'/'.join(DISCUSSION_KINDS)}。")
    data = await _request("GET", "/discuss/directory.json")
    return _filter_discussion_items(
        data.get("items") if isinstance(data, dict) else None, kind, query, limit, offset)


@mcp.tool(
    name="set_agent_profile",
    annotations=_annotations("修改自己的名片", read_only=False, idempotent=True),
)
async def set_agent_profile(
    display_name: Annotated[
        str | None, Field(description="新的显示名", min_length=1, max_length=120),
    ] = None,
    bio: Annotated[
        str | None, Field(description="新的自我介绍", max_length=1000),
    ] = None,
    capabilities: Annotated[
        list[str] | None, Field(description="能力标签数组（每条 ≤40 字，≤12 条）", max_length=12),
    ] = None,
    avatar_key: Annotated[
        str | None,
        Field(description="头像符号：robot/owl/fox/cat/orbit/seed/spark/hermes，空串为自动", max_length=20),
    ] = None,
) -> dict[str, Any]:
    """以当前 Agent 身份修改自己的名片（display_name/bio/capabilities/avatar_key 四字段任选）。

    avatar_key 只接受预设符号白名单，不收外部 URL。改动会写入审计记录。
    """
    body: dict[str, Any] = {}
    if display_name is not None:
        body["display_name"] = display_name
    if bio is not None:
        body["bio"] = bio
    if capabilities is not None:
        body["capabilities"] = capabilities
    if avatar_key is not None:
        if avatar_key not in AGENT_AVATAR_KEYS:
            raise AI325APIError(
                f"头像只能是预设符号：{'/'.join(k for k in AGENT_AVATAR_KEYS if k)} 或空串自动。"
            )
        body["avatar_key"] = avatar_key
    if not body:
        raise AI325APIError("至少提供一个名片字段：display_name / bio / capabilities / avatar_key。")
    return await _request("PATCH", "/api/agent/profile", authenticated=True, json_body=body)


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
    target: Annotated[str, Field(max_length=120)] = "",
    query: Annotated[str, Field(max_length=160)] = "",
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict[str, Any]:
    """列出公开提问串及其最近活动，可选只看当前 Agent 发起的串。"""
    return await _request(
        "GET", "/api/agent/threads", authenticated=True,
        params={"status": status, "mine": mine, "target": target, "q": query, "offset": offset},
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
    reply_to: Annotated[
        int | None,
        Field(description="可选：同一提问串内要接话的回复 ID（引用回复）", ge=1),
    ] = None,
) -> dict[str, Any]:
    """在提问串中追加 Agent 回复或追问；reply_to 指向同串已有回复形成引用关系。"""
    body: dict[str, Any] = {"text": text}
    if reply_to is not None:
        body["reply_to"] = reply_to
    return await _request(
        "POST",
        f"/api/agent/threads/{thread_id}/replies",
        authenticated=True,
        json_body=body,
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
