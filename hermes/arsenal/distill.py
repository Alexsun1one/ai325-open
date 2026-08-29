#!/usr/bin/env python3
"""Filter candidates for the group and distill them into Arsenal schema entries."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests

from collect import canonical_url, clean_text


HERE = Path(__file__).resolve().parent
REPO_ROOT = Path(os.environ.get("XF_REPO", HERE.parents[1])).expanduser().resolve()
PROMPTS_DIR = Path(os.environ.get("HERMES_PROMPTS_DIR", HERE.parent / "prompts"))
PROMPT_VERSION = "arsenal-v3"
REAL_BY = "一一（Hermes × DeepSeek）"
DRY_BY = "一一(dry-run)"
LEGACY_REAL_BY = "Hermes"
LEGACY_DRY_BY = "Hermes(dry-run)"
AUTOMATED_BY_VALUES = {REAL_BY, DRY_BY, LEGACY_REAL_BY, LEGACY_DRY_BY}
DRY_BY_VALUES = {DRY_BY, LEGACY_DRY_BY}
DISTILL_TEMPERATURE = 0.2
SHANGHAI = ZoneInfo("Asia/Shanghai")
KINDS = {"提示词", "方法", "拆书", "工具", "论文", "文章", "案例"}
GROUP_KEYWORDS = ["换脑", "知识库", "Agent", "委托", "销售结构化", "小作文", "判断力"]
REQUIRED_FIELDS = {
    "id",
    "title",
    "kind",
    "source",
    "collected_at",
    "by",
    "one_line",
    "why",
    "for_whom",
    "takeaways",
    "quote",
    "tags",
    "threads",
    "body_md",
    "status",
}
SOURCE_FIELDS = {"name", "url", "author", "published_at"}
TOKEN_USAGE = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


class ValidationFailure(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def is_automated_by(value: str | None) -> bool:
    return value in AUTOMATED_BY_VALUES


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"读取版本化 prompt 失败 {path}: {exc}") from exc


def today_cst() -> str:
    return datetime.now(SHANGHAI).date().isoformat()


def read_candidates(path: Path, required: bool = True) -> list[dict[str, str]]:
    if not path.exists():
        if required:
            raise SystemExit(f"候选文件不存在：{path}")
        return []
    items: list[dict[str, str]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"候选第 {line_number} 行不是 JSON：{exc}") from exc
        if not isinstance(row, dict):
            raise SystemExit(f"候选第 {line_number} 行不是对象")
        missing = {"title", "url", "source", "published", "summary_raw", "lang"} - row.keys()
        if missing:
            raise SystemExit(f"候选第 {line_number} 行缺字段：{', '.join(sorted(missing))}")
        normalized_url = canonical_url(str(row["url"]))
        if not normalized_url:
            raise SystemExit(f"候选第 {line_number} 行 URL 无效")
        items.append(
            {
                "title": clean_text(row["title"], 300),
                "url": normalized_url,
                "source": clean_text(row["source"], 120),
                "published": clean_text(row["published"], 32),
                "summary_raw": clean_text(row["summary_raw"], 1600),
                "lang": clean_text(row["lang"], 16),
            }
        )
    if required and not items:
        raise SystemExit(f"候选文件为空：{path}")
    return items


def load_threads(ledger_dir: Path) -> list[dict[str, str]]:
    latest: dict[str, tuple[tuple[str, int], dict[str, str]]] = {}
    for path in sorted(ledger_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[warn] 跳过坏日报 {path.name}: {exc}", file=sys.stderr)
            continue
        if not isinstance(payload, dict):
            print(f"[warn] 跳过非对象日报 {path.name}", file=sys.stderr)
            continue
        date_value = payload.get("date") if isinstance(payload.get("date"), str) else ""
        issue_value = payload.get("issue") if isinstance(payload.get("issue"), int) else 0
        rank = (date_value, issue_value)
        threads = payload.get("threads", [])
        if not isinstance(threads, list):
            print(f"[warn] {path.name} 的 threads 不是数组", file=sys.stderr)
            continue
        for row in threads:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip():
                continue
            thread_id = row["id"].strip()
            normalized = {
                "id": thread_id,
                "title": clean_text(row.get("title", ""), 120),
                "theme": clean_text(row.get("theme", ""), 160),
                "status": clean_text(row.get("status", ""), 40),
            }
            if thread_id not in latest or rank >= latest[thread_id][0]:
                latest[thread_id] = (rank, normalized)
    return [latest[key][1] for key in sorted(latest)]


def sentence_count(text: str) -> int:
    chunks = [part.strip() for part in re.split(r"[。！？.!?]+", text) if part.strip()]
    return len(chunks)


def normalize_why(value: Any, title: str) -> str:
    raw = clean_text(value, 1200)
    chunks = [part.strip(" 。！？.!?") for part in re.split(r"[。！？.!?]+", raw) if part.strip(" 。！？.!?")]
    if not chunks:
        subject = clean_text(title, 40) or "这条内容"
        chunks = [f"{subject}值得纳入候选", "具体价值仍需结合群内真实任务验证"]
    elif len(chunks) == 1:
        chunks.append("具体价值仍需结合群内真实任务验证")
    return "".join(f"{part}。" for part in chunks[:3])


def is_date_or_empty(value: str) -> bool:
    if not value:
        return True
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def candidate_index(candidates: Iterable[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {canonical_url(row["url"]): row for row in candidates if canonical_url(row["url"])}


def stable_entry_id(entry: dict[str, Any], date_value: str) -> str:
    kind_slugs = {"提示词": "prompt", "方法": "method", "拆书": "book", "工具": "tool", "论文": "paper", "文章": "article", "案例": "case"}
    title = str(entry.get("title", ""))
    ascii_slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:42]
    source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
    url = canonical_url(str(source.get("url", "")))
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10] if url else "missing-url"
    stem = ascii_slug or "knowledge"
    return f"{kind_slugs.get(str(entry.get('kind')), 'knowledge')}-{stem}-{digest}-{date_value[:7].replace('-', '')}"


def normalize_system_fields(
    entries: Any,
    date_value: str,
    candidates: list[dict[str, str]],
    threads: list[dict[str, str]] | None = None,
    warnings: list[str] | None = None,
) -> Any:
    """Own deterministic/provenance fields and repair non-factual presentation rules."""
    if not isinstance(entries, list):
        return entries
    warnings = warnings if warnings is not None else []
    if len(entries) > 15:
        warnings.append(f"items: {len(entries)} 条超过建议上限 15，已截取前 15 条")
        del entries[15:]
    elif len(entries) < 8:
        warnings.append(f"items: 仅 {len(entries)} 条，低于建议 8 条；未编造条目补数")
    known = candidate_index(candidates)
    known_threads = {row["id"] for row in (threads or [])}
    seen_urls: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        prefix = f"items[{index}]"
        source = entry.get("source")
        original = None
        if isinstance(source, dict):
            url = canonical_url(str(source.get("url", "")))
            original = known.get(url)
            if original:
                if source.get("name") != original["source"]:
                    warnings.append(f"{prefix}.source.name 已回锁候选真值")
                if source.get("published_at") != original["published"]:
                    warnings.append(f"{prefix}.source.published_at 已回锁候选真值")
                if source.get("author"):
                    warnings.append(f"{prefix}.source.author 候选无证据，已清空")
                source["url"] = original["url"]
                source["name"] = original["source"]
                source["published_at"] = original["published"]
                source["author"] = ""
                if url in seen_urls:
                    warnings.append(f"{prefix}.source.url 与前项重复，保留并交给编辑复核")
                seen_urls.add(url)
        if original and (not isinstance(entry.get("title"), str) or not entry["title"].strip()):
            entry["title"] = original["title"]
            warnings.append(f"{prefix}.title 为空，已回填候选标题")
        if "one_line" in entry:
            raw_one_line = clean_text(entry.get("one_line"), 500)
            if not raw_one_line:
                raw_one_line = clean_text(entry.get("title", ""), 40) or "值得群友进一步判断的候选"
                warnings.append(f"{prefix}.one_line 为空，已回填安全摘要")
            if len(raw_one_line) > 40:
                raw_one_line = raw_one_line[:39].rstrip() + "…"
                warnings.append(f"{prefix}.one_line 超过 40 字，已自动截断")
            entry["one_line"] = raw_one_line
        if "why" in entry:
            old_count = sentence_count(str(entry.get("why", "")))
            normalized_why = normalize_why(entry.get("why"), str(entry.get("title", "")))
            if old_count not in {2, 3} or normalized_why != str(entry.get("why", "")).strip():
                warnings.append(f"{prefix}.why 已规范为 2–3 句且每句以句号结尾")
            entry["why"] = normalized_why
        if "quote" in entry and entry.get("quote") != "":
            entry["quote"] = ""
            warnings.append(f"{prefix}.quote 候选无逐字引文证据，已自动清空")
        if isinstance(entry.get("threads"), list):
            normalized_threads = [item for item in entry["threads"] if isinstance(item, str) and item in known_threads]
            if normalized_threads != entry["threads"]:
                warnings.append(f"{prefix}.threads 已移除未知或非法 thread id")
            entry["threads"] = list(dict.fromkeys(normalized_threads))
        if isinstance(entry.get("tags"), list):
            normalized_tags = list(dict.fromkeys(item.strip() for item in entry["tags"] if isinstance(item, str) and item.strip()))
            if normalized_tags != entry["tags"]:
                warnings.append(f"{prefix}.tags 已移除空值或重复值")
            entry["tags"] = normalized_tags
        entry["collected_at"] = date_value
        entry["by"] = REAL_BY
        entry["status"] = "shelved"
        entry["id"] = stable_entry_id(entry, date_value)
    return entries


def validate_entries(
    entries: Any,
    candidates: list[dict[str, str]],
    threads: list[dict[str, str]],
    expected_date: str,
    *,
    enforce_candidate_urls: bool = True,
    expected_by: str | None = None,
) -> list[dict[str, Any]]:
    errors: list[str] = []
    if not isinstance(entries, list):
        raise ValidationFailure(["顶层必须是数组"])
    candidates_by_url = candidate_index(candidates)
    for index, entry in enumerate(entries):
        prefix = f"items[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        missing = REQUIRED_FIELDS - entry.keys()
        extra = entry.keys() - REQUIRED_FIELDS
        if missing:
            errors.append(f"{prefix} 缺字段：{', '.join(sorted(missing))}")
        if extra:
            errors.append(f"{prefix} 多字段：{', '.join(sorted(extra))}")
        if missing:
            continue
        if not isinstance(entry.get("id"), str):
            errors.append(f"{prefix}.id 必须是字符串")
        for field in ("title", "by", "one_line", "why", "for_whom", "quote", "body_md"):
            if not isinstance(entry.get(field), str):
                errors.append(f"{prefix}.{field} 必须是字符串")
        if expected_by is not None and entry.get("by") != expected_by:
            errors.append(f"{prefix}.by 必须为 {expected_by}")
        if entry.get("kind") not in KINDS:
            errors.append(f"{prefix}.kind 不在枚举中")
        takeaways = entry.get("takeaways")
        if not isinstance(takeaways, list) or not 3 <= len(takeaways) <= 5:
            errors.append(f"{prefix}.takeaways 必须有 3–5 项")
        elif not all(isinstance(item, str) and item.strip() for item in takeaways):
            errors.append(f"{prefix}.takeaways 只能包含非空字符串")
        tags = entry.get("tags")
        if not isinstance(tags, list) or not all(isinstance(item, str) for item in tags):
            errors.append(f"{prefix}.tags 必须是字符串数组")
        output_threads = entry.get("threads")
        if not isinstance(output_threads, list) or not all(isinstance(item, str) and item for item in output_threads):
            errors.append(f"{prefix}.threads 必须是字符串数组")
        source = entry.get("source")
        if not isinstance(source, dict):
            errors.append(f"{prefix}.source 必须是对象")
            continue
        source_missing = SOURCE_FIELDS - source.keys()
        source_extra = source.keys() - SOURCE_FIELDS
        if source_missing:
            errors.append(f"{prefix}.source 缺字段：{', '.join(sorted(source_missing))}")
            continue
        if source_extra:
            errors.append(f"{prefix}.source 多字段：{', '.join(sorted(source_extra))}")
        if not all(isinstance(source.get(field), str) for field in SOURCE_FIELDS):
            errors.append(f"{prefix}.source 所有字段必须是字符串")
            continue
        url = canonical_url(source["url"])
        is_sun_source = source["name"] == "Sun 的沉淀"
        if is_sun_source:
            if is_automated_by(expected_by):
                errors.append(f"{prefix}.source.name 不能由一一/Hermes 伪装成 Sun 的沉淀")
            if source["url"]:
                errors.append(f"{prefix}.source.url 对 Sun 的沉淀必须为空")
            if source["author"] != "Sun":
                errors.append(f"{prefix}.source.author 对 Sun 的沉淀必须是 Sun")
            if not isinstance(entry.get("body_md"), str) or not entry["body_md"].strip():
                errors.append(f"{prefix}.body_md 对 Sun 的沉淀必须给全文")
        elif not url:
            errors.append(f"{prefix}.source.url 不能为空或无效")
        if not is_date_or_empty(source["published_at"]):
            errors.append(f"{prefix}.source.published_at 必须是 YYYY-MM-DD 或空")
        if is_automated_by(expected_by) and source["author"]:
            errors.append(f"{prefix}.source.author 必须留空：候选集没有作者证据")
        if enforce_candidate_urls:
            original = candidates_by_url.get(url) if not is_sun_source else None
            if is_sun_source and not is_automated_by(expected_by):
                continue
            if not original:
                errors.append(f"{prefix}.source.url 不在候选集：{source['url']}")
            else:
                if source["published_at"] != original["published"]:
                    errors.append(f"{prefix}.source.published_at 与候选不一致")
    if errors:
        raise ValidationFailure(errors)
    return entries


def extract_json(content: str) -> Any:
    stripped = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        stripped = fenced.group(1).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start_object = stripped.find("{")
        start_array = stripped.find("[")
        starts = [position for position in (start_object, start_array) if position >= 0]
        if not starts:
            raise
        start = min(starts)
        end = max(stripped.rfind("}"), stripped.rfind("]"))
        if end <= start:
            raise
        payload = json.loads(stripped[start : end + 1])
    if isinstance(payload, dict) and set(payload) == {"items"}:
        return payload["items"]
    return payload


def schema_prompt(date_value: str, threads: list[dict[str, str]]) -> str:
    thread_ids = [row["id"] for row in threads]
    return load_prompt("arsenal-distill-v3.md") + f"""

群当前主题关键词：{' / '.join(GROUP_KEYWORDS)}。
日报线索（threads）如下：{json.dumps(threads, ensure_ascii=False)}

从用户给出的候选集中，只保留对这个群今天真正有用的 8–15 条。判断标准：能提升 Agent 委托、知识库建设、销售结构化、行动判断或群体实践；纯发布通稿、重复资讯、只有热度没有方法的内容淘汰。

只输出一个 JSON 对象：{{"items": [...]}}，不要 Markdown，不要解释。每个条目字段必须恰好为：
id,title,kind,source,collected_at,by,one_line,why,for_whom,takeaways,quote,tags,threads,body_md,status

硬约束：
- kind 只能是：提示词、方法、拆书、工具、论文、文章、案例。
- source 必须恰好含 name,url,author,published_at；name/url/published_at 必须逐字复制某个候选，author 必须是空字符串，因为候选没有作者证据。
- collected_at 固定为 {date_value}；by 固定为 {REAL_BY}；status 先写 shelved。
- id 用英文小写稳定 slug，以 {date_value[:7].replace('-', '')} 结尾，例如 article-context-engineering-{date_value[:7].replace('-', '')}。
- one_line 写 1–40 个汉字，直接说它解决什么；不要写前缀“这篇文章介绍了”。
- why 必须写两到三句，每一句都必须以中文句号“。”结尾；给判断，不要复述标题。
- for_whom 写一句。takeaways 必须写 3–5 条可执行动作，不摘抄。
- quote 必须直接写空字符串 ""：候选没有逐字原文证据，禁止从摘要猜引语。
- tags 1–8 个；threads 只能从 {json.dumps(thread_ids, ensure_ascii=False)} 中选，可空。
- body_md 可为空；严禁补写候选里没有的事实、作者、数字、日期或引语。
- URL 必须来自候选，不能改写、不能另找链接、不能编造。
"""


def candidate_payload(candidates: list[dict[str, str]]) -> str:
    compact = []
    for index, row in enumerate(candidates):
        compact.append(
            {
                "candidate_id": index,
                "title": row["title"],
                "url": row["url"],
                "source": row["source"],
                "published": row["published"],
                "summary_raw": row["summary_raw"][:600],
                "lang": row["lang"],
            }
        )
    return "候选集（只能从这里选择）：\n" + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))


def call_deepseek(
    candidates: list[dict[str, str]],
    threads: list[dict[str, str]],
    date_value: str,
    api_key: str,
    retries: int,
    timeout: float,
    judge_feedback: str = "",
) -> tuple[list[dict[str, Any]], list[str]]:
    api_url = os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    system = schema_prompt(date_value, threads)
    user = candidate_payload(candidates)
    if judge_feedback:
        user += "\n\n上一次质量 judge 的具体反馈（本次必须修正）：\n" + judge_feedback
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    seed = os.environ.get("DEEPSEEK_SEED", "").strip()
    request_seed: dict[str, int] = {}
    if seed:
        try:
            request_seed["seed"] = int(seed)
        except ValueError as exc:
            raise SystemExit("DEEPSEEK_SEED 必须是整数") from exc
    last_error = "未调用"
    for attempt in range(1, retries + 1):
        content = ""
        try:
            response = requests.post(
                api_url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": DISTILL_TEMPERATURE,
                    "max_tokens": 8192,
                    "response_format": {"type": "json_object"},
                    **request_seed,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
            for key in TOKEN_USAGE:
                TOKEN_USAGE[key] += int(usage.get(key, 0) or 0)
            content = payload["choices"][0]["message"]["content"]
            normalization_warnings: list[str] = []
            entries = normalize_system_fields(
                extract_json(content),
                date_value,
                candidates,
                threads,
                normalization_warnings,
            )
            validated = validate_entries(
                entries,
                candidates,
                threads,
                date_value,
                enforce_candidate_urls=True,
                expected_by=REAL_BY,
            )
            for warning in normalization_warnings:
                print(f"[warn] {warning}", file=sys.stderr)
            return validated, normalization_warnings
        except ValidationFailure as exc:
            last_error = "；".join(exc.errors[:12])
        except (requests.RequestException, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            last_error = str(exc)
        print(f"[retry {attempt}/{retries}] DeepSeek 输出失败：{last_error}", file=sys.stderr)
        if content:
            messages.append({"role": "assistant", "content": content})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "请在你上一版 JSON 的基础上只修复下列硬错误，保留已经正确的选择与判断；"
                        f"然后重新输出完整 JSON 对象。具体错误：{last_error}"
                    ),
                }
            )
    raise SystemExit(f"DeepSeek 连续 {retries} 次失败；保留已有产物不覆盖。最后错误：{last_error}")


DRY_RUN_BLUEPRINTS = [
    {
        "id": "article-effective-agents",
        "title": "Building effective agents",
        "kind": "文章",
        "source": ("Anthropic Newsroom", "https://www.anthropic.com/research/building-effective-agents"),
        "one_line": "把智能体复杂度控制在任务真正需要的范围内",
        "why": "它把工作流与自主智能体分开讨论，判断标准清楚。对本群最有价值的不是框架名字，而是先用最简单结构验证任务。",
        "for_whom": "适合正在拆 Agent 任务或评估是否需要多 Agent 的群友。",
        "takeaways": ["先写清任务是否能由固定步骤完成", "只有路径不可预知时才提高自主性", "为每次工具调用保留可检查结果"],
        "tags": ["Agent", "委托", "工作流"],
        "threads": ["brain-swap"],
    },
    {
        "id": "paper-react-agents",
        "title": "ReAct: Synergizing Reasoning and Acting in Language Models",
        "kind": "论文",
        "source": ("arXiv cs.AI", "https://arxiv.org/abs/2210.03629"),
        "one_line": "让推理与行动交替发生并留下可检查轨迹",
        "why": "它说明只会想或只会调用工具都不够。对委托者的启发是把观察结果重新送回下一步判断。",
        "for_whom": "适合设计工具调用循环和 Agent 调试流程的人。",
        "takeaways": ["每次行动后读取真实观察", "把失败结果纳入下一步判断", "评测时同时检查答案与行动轨迹"],
        "tags": ["Agent", "论文", "工具调用"],
        "threads": ["brain-swap"],
    },
    {
        "id": "article-contextual-retrieval",
        "title": "Contextual Retrieval",
        "kind": "方法",
        "source": ("Simon Willison", "https://simonwillison.net/2024/Sep/19/contextual-retrieval/"),
        "one_line": "在切片入库前补足语境以改善检索命中",
        "why": "它直面知识库切片失去上下文的常见故障。这个方法值得看，但必须用自己的真实查询集验证，而不是迷信单次指标。",
        "for_whom": "适合正在处理长文切片与 RAG 召回偏差的人。",
        "takeaways": ["先收集当前检索失败样本", "给切片补充文档级语境", "用固定问题集比较改造前后结果"],
        "tags": ["知识库", "RAG", "检索"],
        "threads": ["knowledge-base"],
    },
    {
        "id": "tool-mcp-servers",
        "title": "Model Context Protocol servers",
        "kind": "工具",
        "source": ("GitHub Trending AI & Agents", "https://github.com/modelcontextprotocol/servers"),
        "one_line": "一组可参考的 MCP 服务端实现与集成样例",
        "why": "它适合拿来理解工具边界和接口形态，不适合整包照搬。群友真正需要先确定的是授权范围、失败处理和审计证据。",
        "for_whom": "适合准备给 Agent 接入外部工具与数据的人。",
        "takeaways": ["先选一个低风险只读工具试接", "为输入输出定义明确 schema", "把权限与错误日志纳入验收"],
        "tags": ["MCP", "Agent", "工具"],
        "threads": ["knowledge-base"],
    },
    {
        "id": "tool-huggingface-agents-course",
        "title": "Hugging Face Agents Course",
        "kind": "方法",
        "source": ("Hugging Face Daily Papers", "https://huggingface.co/learn/agents-course/unit0/introduction"),
        "one_line": "用循序练习理解 Agent 的组成与运行循环",
        "why": "课程适合补齐共同语言，但学习本身不会自动产生交付。最好把每一单元绑定到一个群内真实任务。",
        "for_whom": "适合刚开始系统理解 Agent 工作机制的群友。",
        "takeaways": ["选一个真实委托作为贯穿练习", "每学一节就记录可验证产物", "结课时复盘哪些环节仍需人工判断"],
        "tags": ["Agent", "课程", "实践"],
        "threads": ["brain-swap"],
    },
    {
        "id": "tool-langgraph",
        "title": "LangGraph",
        "kind": "工具",
        "source": ("GitHub Trending AI & Agents", "https://github.com/langchain-ai/langgraph"),
        "one_line": "用图结构表达有状态的智能体工作流",
        "why": "它对长流程、分支和人工闸门很有帮助。若任务只有三四个固定步骤，引入它反而可能增加维护成本。",
        "for_whom": "适合已经确认需要状态、循环或人工审批的 Agent 项目。",
        "takeaways": ["先画状态和转移再选框架", "给循环设置退出条件", "在高风险节点保留人工确认"],
        "tags": ["Agent", "工作流", "状态机"],
        "threads": ["brain-swap"],
    },
    {
        "id": "article-structured-outputs",
        "title": "Structured Outputs",
        "kind": "方法",
        "source": ("OpenAI News", "https://openai.com/index/introducing-structured-outputs-in-the-api"),
        "one_line": "让模型输出受 schema 约束并在失败时显式处理",
        "why": "结构化输出能减少解析事故，但不能保证内容事实正确。它应该和来源锁定、字段校验、重试及人工抽查一起使用。",
        "for_whom": "适合把模型结果接入发布或业务流程的人。",
        "takeaways": ["先定义最小且严格的输出 schema", "对 URL 与日期做外部真值校验", "重试耗尽时保留旧产物并报警"],
        "tags": ["结构化输出", "校验", "工程"],
        "threads": ["knowledge-base"],
    },
    {
        "id": "article-practical-agent-guide",
        "title": "A practical guide to building agents",
        "kind": "文章",
        "source": ("OpenAI News", "https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents"),
        "one_line": "从任务、工具与护栏三层检查 Agent 是否可落地",
        "why": "它能帮助团队把模糊的 Agent 想法拆成工程对象。真正的门槛仍是任务成功标准和异常时由谁负责。",
        "for_whom": "适合准备把 Agent 从演示推进到真实业务的人。",
        "takeaways": ["先定义一个可量化任务结果", "只提供完成任务必需的工具", "为越权和低置信度结果设计护栏"],
        "tags": ["Agent", "落地", "护栏"],
        "threads": ["ai-economics"],
    },
]


def dry_run_entries(date_value: str, threads: list[dict[str, str]]) -> list[dict[str, Any]]:
    known_threads = {row["id"] for row in threads}
    suffix = date_value[:7].replace("-", "")
    entries = []
    for blueprint in DRY_RUN_BLUEPRINTS:
        source_name, source_url = blueprint["source"]
        entries.append(
            {
                "id": f"{blueprint['id']}-{suffix}",
                "title": blueprint["title"],
                "kind": blueprint["kind"],
                "source": {"name": source_name, "url": source_url, "author": "", "published_at": ""},
                "collected_at": date_value,
                "by": DRY_BY,
                "one_line": blueprint["one_line"],
                "why": blueprint["why"],
                "for_whom": blueprint["for_whom"],
                "takeaways": blueprint["takeaways"],
                "quote": "",
                "tags": blueprint["tags"],
                "threads": [item for item in blueprint["threads"] if item in known_threads],
                "body_md": "",
                "status": "shelved",
            }
        )
    return validate_entries(
        entries,
        [],
        threads,
        date_value,
        enforce_candidate_urls=False,
        expected_by=DRY_BY,
    )


def atomic_write_json(path: Path, entries: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=today_cst(), help="蒸馏日期，YYYY-MM-DD（默认上海当天）")
    parser.add_argument("--candidates", type=Path, help="候选 JSONL；默认 candidates/YYYY-MM-DD.jsonl")
    parser.add_argument("--ledger-dir", type=Path, default=REPO_ROOT / "site" / "content" / "ledgers")
    parser.add_argument("--output", type=Path, help="覆盖输出路径；默认 site/content/arsenal/YYYY-MM-DD.json")
    parser.add_argument("--dry-run", action="store_true", help="不用 API，输出固定 8 条 schema 样例")
    parser.add_argument("--retries", type=int, default=3, help="DeepSeek 校验失败重试次数")
    parser.add_argument("--timeout", type=float, default=120.0, help="DeepSeek 请求超时秒数")
    parser.add_argument("--validate-only", type=Path, help="只校验一个已有 JSON 文件")
    parser.add_argument("--reject-dry-run", action="store_true", help="校验时拒绝一一/Hermes dry-run 产物（发布闸门用）")
    parser.add_argument("--judge-feedback", type=Path, help="上一轮 judge JSON，重蒸时带 suggestions")
    parser.add_argument("--usage-output", type=Path, help="写入本次 DeepSeek token 用量")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print("--date 必须是 YYYY-MM-DD", file=sys.stderr)
        return 2
    candidate_path = args.candidates or HERE / "candidates" / f"{args.date}.jsonl"
    output = args.output or REPO_ROOT / "site" / "content" / "arsenal" / f"{args.date}.json"
    threads = load_threads(args.ledger_dir)
    if not threads:
        print("[warn] 未读到日报 threads；输出 threads 只能为空", file=sys.stderr)
    if args.validate_only:
        candidates = read_candidates(candidate_path, required=False)
        payload = json.loads(args.validate_only.read_text(encoding="utf-8"))
        if args.reject_dry_run and any(isinstance(row, dict) and row.get("by") in DRY_BY_VALUES for row in payload):
            print("发布闸门拒绝一一/Hermes dry-run 样例", file=sys.stderr)
            return 2
        by_values = {row.get("by") for row in payload if isinstance(row, dict)} if isinstance(payload, list) else set()
        expected_by = next(iter(by_values)) if len(by_values) == 1 and next(iter(by_values), None) in AUTOMATED_BY_VALUES else None
        validate_entries(
            payload,
            candidates,
            threads,
            args.date,
            enforce_candidate_urls=expected_by not in DRY_BY_VALUES,
            expected_by=expected_by,
        )
        print(json.dumps({"valid": True, "items": len(payload), "path": str(args.validate_only)}, ensure_ascii=False))
        return 0
    candidates = read_candidates(candidate_path, required=not args.dry_run)
    if args.dry_run:
        entries = dry_run_entries(args.date, threads)
        mode = "dry-run"
        normalization_warnings: list[str] = []
    else:
        if len(candidates) < 8:
            print(f"真实蒸馏至少需要 8 条候选，当前 {len(candidates)}", file=sys.stderr)
            return 2
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            print("缺 DEEPSEEK_API_KEY；请设置环境变量或使用 --dry-run", file=sys.stderr)
            return 2
        judge_feedback = ""
        if args.judge_feedback:
            feedback_payload = json.loads(args.judge_feedback.read_text(encoding="utf-8"))
            if isinstance(feedback_payload, dict):
                feedback_items = feedback_payload.get("hard_fail", []) + feedback_payload.get("suggestions", [])
                judge_feedback = "\n".join(f"- {item}" for item in feedback_items if isinstance(item, str))
        entries, normalization_warnings = call_deepseek(
            candidates,
            threads,
            args.date,
            api_key,
            max(1, args.retries),
            args.timeout,
            judge_feedback,
        )
        mode = "deepseek"
    atomic_write_json(output, entries)
    if args.usage_output:
        atomic_write_json(args.usage_output, {"prompt_version": PROMPT_VERSION, "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"), "token_usage": TOKEN_USAGE})
    print(
        json.dumps(
            {
                "date": args.date,
                "mode": mode,
                "candidates": len(candidates),
                "threads": len(threads),
                "distilled": len(entries),
                "warnings": normalization_warnings,
                "prompt_version": PROMPT_VERSION,
                "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat") if mode == "deepseek" else None,
                "token_usage": TOKEN_USAGE,
                "output": str(output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
