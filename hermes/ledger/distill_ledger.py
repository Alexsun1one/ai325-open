#!/usr/bin/env python3
"""Distill a daily Hermes transcript into _hermes_spec.md content.json.

The real path is deliberately multi-stage: every transcript line is included in
exactly one extraction chunk, then the chunk evidence is assembled into the
eight-section ledger.  Verbatim material is checked locally before an atomic
write.  ``--dry-run`` never calls DeepSeek and emits a deterministic sample.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import unicodedata
from typing import Any, Callable
from urllib import error as urlerror
from urllib import request


HERE = Path(__file__).resolve().parent
PROMPTS_DIR = Path(os.environ.get("HERMES_PROMPTS_DIR", HERE.parent / "prompts"))
PROMPT_VERSION = "ledger-v3"
REAL_DISTILLED_BY = "一一（Hermes × DeepSeek）"
DRY_DISTILLED_BY = "一一(dry-run)"
TONE_CLASSES = {"s", "j", "h"}
THREAD_STATUSES = {"ongoing", "closed"}
TODO_PHASES = {"今天", "本周", "本月"}
ALLOWED_TAGS = {"b", "i", "br", "u"}
DEFAULT_CHUNK_SIZE = 5_500
CHUNK_EVIDENCE_LIMIT = 25
CHUNK_OUTPUT_CHAR_LIMIT = 6_000
SKELETON_OUTPUT_CHAR_LIMIT = 6_000
FINAL_OUTPUT_CHAR_LIMIT = 10_000
MIN_QUOTES = 5
CACHE_VERSION = 1
DEFAULT_MAX_RUNTIME_SECONDS = 25 * 60
MAX_THEME_REPAIR_ATTEMPTS = 2
EVIDENCE_TYPES = {
    "event",
    "fragment",
    "tone",
    "quote",
    "member",
    "newcomer",
    "arsenal",
    "docket",
    "clash",
}
TOKEN_USAGE = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
ACTION_VERBS = {
    "写",
    "重写",
    "列",
    "整理",
    "检查",
    "验证",
    "记录",
    "创建",
    "建立",
    "选",
    "拆",
    "跑",
    "做",
    "复盘",
    "对比",
    "访谈",
    "尝试",
    "标注",
    "更新",
    "删除",
}
ENGINEERING_REPLACEMENTS = {
    "口径": "说法",
    "治理产物": "整理结果",
    "端点": "接口",
    "静态": "固定",
    "渲染": "呈现",
    "数据层": "数据",
    "接线": "连起来",
    "缺口": "问题",
    "闭环": "做完并检查",
    "赋能": "帮助",
}
DEFAULT_DEEP_JUDGE_FEEDBACK = (
    "themes[*].deep 尽量含“没说破”且至少 3 句；能定位时逐字引用，找不到就写不带引号的判断；"
    "最后一句尽量落到一个动作。这些是质量目标，不是整份拒绝条件。"
)
TOP_FIELDS = {
    "date",
    "stats_override",
    "hours",
    "events",
    "themes",
    "tone_notes",
    "quotes",
    "growth",
    "members_focus",
    "title",
    "lead",
    "coverage",
    "complete",
    "pulse",
    "insights",
    "glossary",
    "arsenal",
    "docket",
    "clashes",
    "newcomers",
    "members_total",
    "essays_total",
    "essays_open",
    "distilled_by",
    "reviewed_by",
    "prompt_version",
}
LIST_LIMITS = {
    "events": 12,
    "themes": 6,
    "tone_notes": 6,
    "quotes": 10,
    "members_focus": 12,
    "insights": 6,
    "glossary": 12,
    "arsenal": 8,
    "docket": 10,
    "clashes": 5,
    "newcomers": 12,
}
TRANSCRIPT_LINE = re.compile(r"^\[(?P<time>\d{2}-\d{2} \d{2}:\d{2})\]\s*(?P<author>[^:]+):\s*(?P<text>.*)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LINE_ID_RE = re.compile(r"^L\d{4,}$")
PUNCTUATION_MAP = str.maketrans(
    {
        "，": ",",
        "、": ",",
        "。": ".",
        "．": ".",
        "：": ":",
        "；": ";",
        "！": "!",
        "？": "?",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "｛": "{",
        "｝": "}",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "「": '"',
        "」": '"',
        "『": '"',
        "』": '"',
    }
)


class LedgerError(Exception):
    """Operational failure that must preserve an existing content.json."""


class ValidationFailure(LedgerError):
    def __init__(self, errors: list[str]):
        super().__init__("；".join(errors))
        self.errors = errors


class TimeBudgetExceeded(LedgerError):
    """The process-wide runtime budget expired between recoverable stages."""


class RunBudget:
    def __init__(self, limit_seconds: float = DEFAULT_MAX_RUNTIME_SECONDS) -> None:
        if limit_seconds <= 0:
            raise LedgerError("--max-runtime 必须 > 0")
        self.limit_seconds = limit_seconds
        self.started_at = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def remaining(self) -> float:
        return max(0.0, self.limit_seconds - self.elapsed())

    def check(self, stage: str) -> None:
        if self.remaining() <= 0:
            raise TimeBudgetExceeded(
                f"总时长超过 {self.limit_seconds / 60:g} 分钟，停止于 {stage}"
            )

    def request_timeout(self, configured: float, stage: str) -> float:
        self.check(stage)
        return max(0.1, min(configured, self.remaining()))


def stage_start(name: str, budget: RunBudget) -> float:
    budget.check(name)
    print(
        f"[stage] {name} start total={budget.elapsed():.1f}s remaining={budget.remaining():.1f}s",
        file=sys.stderr,
    )
    return time.monotonic()


def stage_done(name: str, started_at: float, budget: RunBudget, status: str = "ok") -> None:
    print(
        f"[stage] {name} {status} elapsed={time.monotonic() - started_at:.1f}s total={budget.elapsed():.1f}s",
        file=sys.stderr,
    )


def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LedgerError(f"读取版本化 prompt 失败 {path}: {exc}") from exc


def load_json(path: Path, *, required: bool = True) -> Any:
    if not path.exists():
        if required:
            raise LedgerError(f"缺少文件：{path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LedgerError(f"JSON 读取失败 {path}: {exc}") from exc


def load_materials(materials: Path) -> dict[str, Any]:
    transcript_path = materials / "transcript.txt"
    try:
        transcript = transcript_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise LedgerError(f"读取失败 {transcript_path}: {exc}") from exc
    if not transcript.strip():
        raise LedgerError("transcript.txt 为空")
    stats = load_json(materials / "stats.json")
    if not isinstance(stats, dict):
        raise LedgerError("stats.json 顶层必须是对象")
    avatars = load_json(materials / "avatars.json", required=False)
    newcomers = load_json(materials / "newcomers.json", required=False)
    context_path = materials / "context-prev.md"
    context = context_path.read_text(encoding="utf-8") if context_path.exists() else ""
    return {
        "transcript": transcript,
        "stats": stats,
        "avatars": avatars or {},
        "newcomers": newcomers or [],
        "context": context,
    }


def infer_date(materials: Path, transcript: str, explicit: str | None) -> str:
    value = explicit
    if not value and DATE_RE.fullmatch(materials.name):
        value = materials.name
    if not value:
        match = TRANSCRIPT_LINE.search(transcript)
        if match:
            value = f"{dt.date.today().year}-{match.group('time')[:5]}"
    if not value or not DATE_RE.fullmatch(value):
        raise LedgerError("无法推断日期，请传 --date YYYY-MM-DD")
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise LedgerError(f"日期无效：{value}") from exc
    return value


def load_previous(ledger_dir: Path | None, date_value: str, explicit: Path | None) -> tuple[dict[str, Any], str]:
    if explicit:
        payload = load_json(explicit)
        if not isinstance(payload, dict):
            raise LedgerError("上一期 Ledger 必须是对象")
        return payload, str(explicit)
    if not ledger_dir or not ledger_dir.exists():
        return {}, ""
    choices = sorted(path for path in ledger_dir.glob("*.json") if path.stem < date_value)
    if not choices:
        return {}, ""
    payload = load_json(choices[-1])
    if not isinstance(payload, dict):
        raise LedgerError(f"上一期 Ledger 必须是对象：{choices[-1]}")
    return payload, str(choices[-1])


def previous_context(previous: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue": previous.get("issue"),
        "threads": previous.get("threads", []),
        "docket": previous.get("docket", []),
        "glossary": previous.get("glossary", []),
        "growth_todo": previous.get("growth", {}).get("todo", []) if isinstance(previous.get("growth"), dict) else [],
        "members": previous.get("stats", {}).get("members", 0) if isinstance(previous.get("stats"), dict) else 0,
        "essays": previous.get("stats", {}).get("essays", 0) if isinstance(previous.get("stats"), dict) else 0,
        "essays_open": previous.get("stats", {}).get("essays_open", 0) if isinstance(previous.get("stats"), dict) else 0,
    }


def parse_utterances(transcript: str) -> dict[str, list[str]]:
    utterances: dict[str, list[str]] = {}
    for line in transcript.splitlines():
        match = TRANSCRIPT_LINE.match(line)
        if not match:
            continue
        author = match.group("author").strip()
        text = match.group("text").strip()
        utterances.setdefault(author, []).append(text)
    return utterances


def numbered_transcript(transcript: str) -> str:
    """Prefix every physical transcript line with a stable L0001-style id."""
    return "\n".join(f"L{index:04d} {line}" for index, line in enumerate(transcript.splitlines(), 1))


def transcript_line_index(transcript: str) -> dict[str, dict[str, str]]:
    """Map stable line ids to the original, unmodified speaker text."""
    index: dict[str, dict[str, str]] = {}
    for number, line in enumerate(transcript.splitlines(), 1):
        match = TRANSCRIPT_LINE.match(line)
        if not match:
            continue
        line_id = f"L{number:04d}"
        index[line_id] = {
            "line": line_id,
            "time": match.group("time"),
            "a": match.group("author").strip(),
            "text": match.group("text").strip(),
        }
    return index


def normalized_with_positions(value: str) -> tuple[str, list[tuple[int, int]]]:
    """Normalize whitespace/full-width punctuation while retaining source offsets."""
    tokens: list[tuple[str, int, int]] = []
    for source_index, source_char in enumerate(value):
        for char in unicodedata.normalize("NFKC", source_char):
            if char.isspace():
                continue
            tokens.append((char.translate(PUNCTUATION_MAP), source_index, source_index + 1))
    normalized: list[str] = []
    positions: list[tuple[int, int]] = []
    cursor = 0
    while cursor < len(tokens):
        char, start, end = tokens[cursor]
        if char in {".", "…"}:
            run = cursor + 1
            while run < len(tokens) and tokens[run][0] in {".", "…"}:
                end = tokens[run][2]
                run += 1
            if run - cursor > 1 or char == "…":
                normalized.append("…")
                positions.append((start, end))
                cursor = run
                continue
        normalized.append(char)
        positions.append((start, end))
        cursor += 1
    return "".join(normalized), positions


def normalize_verbatim(value: Any) -> str:
    return normalized_with_positions(str(value or ""))[0]


def unwrap_reference_fragment(value: str) -> str:
    stripped = value.strip()
    pairs = (("“", "”"), ("「", "」"), ("『", "』"), ('"', '"'), ("'", "'"))
    for left, right in pairs:
        if len(stripped) >= 2 and stripped.startswith(left) and stripped.endswith(right):
            return stripped[len(left) : -len(right)].strip()
    return stripped


def locate_normalized_substring(message: str, fragment: str) -> str | None:
    """Return the exact original slice when a normalized fragment occurs in a line."""
    fragment = unwrap_reference_fragment(fragment)
    normalized_message, positions = normalized_with_positions(message)
    normalized_fragment = normalize_verbatim(fragment)
    if not normalized_fragment:
        return None
    offset = normalized_message.find(normalized_fragment)
    if offset < 0:
        return None
    start = positions[offset][0]
    end = positions[offset + len(normalized_fragment) - 1][1]
    return message[start:end]


def canonical_verbatim(text: str, author: str, utterances: dict[str, list[str]]) -> str | None:
    if not normalize_verbatim(text) or not author.strip():
        return None
    for message in utterances.get(author.strip(), []):
        match = locate_normalized_substring(message, text)
        if match is not None:
            return match
    return None


def model_display_name(model: str) -> str:
    return "DeepSeek" if "deepseek" in model.casefold() else model


def distilled_by(model: str, *, dry_run: bool = False) -> str:
    if dry_run:
        return DRY_DISTILLED_BY
    display = model_display_name(model)
    return REAL_DISTILLED_BY if display == "DeepSeek" else f"一一（Hermes × {display}）"


def is_sensitive(text: str) -> bool:
    if re.search(r"(?i)(?:password|passwd|secret|token|密码|口令|密钥)", text):
        return True
    if re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", text):
        return True
    without_public_urls = re.sub(r"https?://\S+", "", text)
    if re.search(r"(?<![A-Za-z0-9])[A-Za-z0-9_+/=-]{18,}(?![A-Za-z0-9])", without_public_urls):
        return True
    return False


def redact_for_model(transcript: str) -> str:
    redacted: list[str] = []
    for line in transcript.splitlines():
        match = TRANSCRIPT_LINE.match(line)
        if not match:
            redacted.append(line)
            continue
        text = match.group("text")
        if is_sensitive(text):
            text = "[敏感内容已移除]"
        else:
            text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[手机号已打码]", text)
        redacted.append(f"[{match.group('time')}] {match.group('author')}: {text}")
    return "\n".join(redacted)


def reference_fragment(data: dict[str, Any]) -> str:
    for field in ("fragment", "quote", "v", "text"):
        value = data.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def resolve_line_reference(
    data: dict[str, Any],
    line_index: dict[str, dict[str, str]],
    allowed_line_ids: set[str] | None = None,
) -> tuple[dict[str, str], str] | None:
    raw_line = str(data.get("line", "")).strip().upper()
    if raw_line.isdigit():
        raw_line = f"L{int(raw_line):04d}"
    if (
        not LINE_ID_RE.fullmatch(raw_line)
        or raw_line not in line_index
        or (allowed_line_ids is not None and raw_line not in allowed_line_ids)
    ):
        return None
    source = line_index[raw_line]
    supplied_author = str(data.get("a", "")).strip()
    if supplied_author and normalize_verbatim(supplied_author) != normalize_verbatim(source["a"]):
        return None
    message = source["text"]
    fragment = reference_fragment(data)
    exact: str | None = None
    start, end = data.get("start"), data.get("end")
    if isinstance(start, int) and not isinstance(start, bool) and isinstance(end, int) and not isinstance(end, bool):
        if 0 <= start < end <= len(message):
            candidate = message[start:end]
            if not fragment or normalize_verbatim(candidate) == normalize_verbatim(unwrap_reference_fragment(fragment)):
                exact = candidate
        if exact is None and 0 <= start <= end < len(message):
            candidate = message[start : end + 1]
            if not fragment or normalize_verbatim(candidate) == normalize_verbatim(unwrap_reference_fragment(fragment)):
                exact = candidate
    if exact is None and fragment:
        exact = locate_normalized_substring(message, fragment)
    if exact is None or not exact.strip() or is_sensitive(exact):
        return None
    return source, exact


def canonicalize_evidence_references(
    payload: dict[str, Any],
    line_index: dict[str, dict[str, str]],
    warnings: list[str],
    allowed_line_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Resolve model line references to exact original substrings before assembly."""
    canonical: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("evidence", [])):
        if not isinstance(item, dict) or not isinstance(item.get("data"), dict):
            continue
        kind = item.get("type")
        data = copy.deepcopy(item["data"])
        if kind in {"quote", "tone"}:
            resolved = resolve_line_reference(data, line_index, allowed_line_ids)
            if resolved is None:
                warnings.append(f"evidence[{index}] {kind} 行号/片段无法定位，已丢弃")
                continue
            source, exact = resolved
            data.update({"line": source["line"], "a": source["a"], "t": source["time"], "v": exact})
            for field in ("fragment", "start", "end", "quote", "text"):
                data.pop(field, None)
            tone = data.get("g" if kind == "quote" else "cls")
            if tone not in TONE_CLASSES:
                warnings.append(f"evidence[{index}] {kind} 语气标非法，已丢弃")
                continue
        elif kind == "fragment" and isinstance(data.get("evidence"), list):
            fragments: list[dict[str, str]] = []
            for fragment_index, fragment in enumerate(data["evidence"]):
                if not isinstance(fragment, dict):
                    continue
                resolved = resolve_line_reference(fragment, line_index, allowed_line_ids)
                if resolved is None:
                    warnings.append(
                        f"evidence[{index}].data.evidence[{fragment_index}] 行号/片段无法定位，已丢弃"
                    )
                    continue
                source, exact = resolved
                fragments.append(
                    {"line": source["line"], "a": source["a"], "v": exact, "t": source["time"]}
                )
            data["evidence"] = fragments
        canonical.append({"type": kind, "data": data})
    return {"evidence": canonical}


def find_reference_line(
    text: str, author: str, line_index: dict[str, dict[str, str]]
) -> tuple[dict[str, str], str] | None:
    for source in line_index.values():
        if normalize_verbatim(source["a"]) != normalize_verbatim(author):
            continue
        exact = locate_normalized_substring(source["text"], text)
        if exact is not None and not is_sensitive(exact):
            return source, exact
    return None


def resolve_content_references(
    content: Any, transcript: str, warnings: list[str]
) -> dict[str, Any]:
    """Turn final-stage quote/voice references into canonical output fields."""
    if not isinstance(content, dict):
        raise ValidationFailure(["顶层必须是 JSON 对象"])
    resolved_content = copy.deepcopy(content)
    line_index = transcript_line_index(transcript)
    resolved_quotes: list[dict[str, str]] = []
    for index, quote in enumerate(resolved_content.get("quotes", [])):
        if not isinstance(quote, dict):
            warnings.append(f"quotes[{index}] 不是引用对象，已丢弃")
            continue
        resolved = resolve_line_reference(quote, line_index) if quote.get("line") else None
        if resolved is None and isinstance(quote.get("t"), str) and isinstance(quote.get("a"), str):
            resolved = find_reference_line(quote["t"], quote["a"], line_index)
        if resolved is None:
            warnings.append(f"quotes[{index}] 行号/片段无法定位，已丢弃")
            continue
        source, exact = resolved
        resolved_quotes.append({"t": exact, "a": source["a"], "g": str(quote.get("g", ""))})
    resolved_content["quotes"] = resolved_quotes

    themes = resolved_content.get("themes", [])
    if isinstance(themes, list):
        for theme_index, theme in enumerate(themes):
            if not isinstance(theme, dict):
                continue
            resolved_voices: list[dict[str, str]] = []
            for voice_index, voice in enumerate(theme.get("voices", [])):
                if not isinstance(voice, dict):
                    warnings.append(f"themes[{theme_index}].voices[{voice_index}] 不是引用对象，已丢弃")
                    continue
                resolved = resolve_line_reference(voice, line_index) if voice.get("line") else None
                if resolved is None and isinstance(voice.get("v"), str) and isinstance(voice.get("a"), str):
                    resolved = find_reference_line(voice["v"], voice["a"], line_index)
                if resolved is None:
                    warnings.append(
                        f"themes[{theme_index}].voices[{voice_index}] 行号/片段无法定位，已丢弃"
                    )
                    continue
                source, exact = resolved
                resolved_voices.append({"a": source["a"], "v": exact, "g": str(voice.get("g", ""))})
            theme["voices"] = resolved_voices
    return resolved_content


def quote_exists(text: str, author: str, utterances: dict[str, list[str]]) -> bool:
    return canonical_verbatim(text, author, utterances) is not None


def chunk_transcript(transcript: str, size: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_size = 0
    for line in transcript.splitlines(keepends=True):
        if current and current_size + len(line) > size:
            chunks.append("".join(current))
            current = []
            current_size = 0
        current.append(line)
        current_size += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


def strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline >= 0:
            stripped = stripped[first_newline + 1 :]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


def json_stack(source: str) -> tuple[list[tuple[str, int]], bool]:
    """Return unmatched containers and whether the source ends inside a string."""
    stack: list[tuple[str, int]] = []
    in_string = False
    escaped = False
    for index, char in enumerate(source):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append((char, index))
        elif char in "}]":
            expected = "{" if char == "}" else "["
            if not stack or stack[-1][0] != expected:
                return [], in_string
            stack.pop()
    return stack, in_string


def close_json_prefix(prefix: str) -> str | None:
    prefix = re.sub(r",\s*$", "", prefix.rstrip())
    stack, in_string = json_stack(prefix)
    if not prefix or in_string:
        return None
    return prefix + "".join("}" if opener == "{" else "]" for opener, _ in reversed(stack))


def repair_truncated_json(source: str) -> str | None:
    """Drop the last incomplete array object and close remaining containers."""
    start = min((i for i in (source.find("{"), source.find("[")) if i >= 0), default=-1)
    if start < 0:
        return None
    candidate = source[start:].strip()
    stack, _ = json_stack(candidate)

    # Typical cutoff: {"evidence":[{complete},{incomplete...  Drop only
    # the innermost unfinished object whose parent is an array.
    drop_at: int | None = None
    for position in range(len(stack) - 1, 0, -1):
        if stack[position][0] == "{" and stack[position - 1][0] == "[":
            drop_at = stack[position][1]
            break
    if drop_at is not None:
        closed = close_json_prefix(candidate[:drop_at])
        if closed:
            try:
                json.loads(closed)
                return closed
            except json.JSONDecodeError:
                pass

    # The cutoff may happen just after a complete element or before only the
    # final closing brackets.  Closing those containers is safe.
    closed = close_json_prefix(candidate)
    if closed:
        try:
            json.loads(closed)
            return closed
        except json.JSONDecodeError:
            return None
    return None


def extract_json(content: str) -> Any:
    stripped = strip_json_fence(content)
    payload: Any
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as original_error:
        start = min((i for i in (stripped.find("{"), stripped.find("[")) if i >= 0), default=-1)
        end = max(stripped.rfind("}"), stripped.rfind("]"))
        if start >= 0 and end > start:
            try:
                payload = json.loads(stripped[start : end + 1])
            except json.JSONDecodeError:
                payload = None
            else:
                if isinstance(payload, dict) and set(payload) == {"content"} and isinstance(payload["content"], dict):
                    return payload["content"]
                return payload
        repaired = repair_truncated_json(stripped)
        if not repaired:
            raise original_error
        payload = json.loads(repaired)
        print("[warn] DeepSeek JSON 被截断：已丢弃最后一个不完整对象并闭合结构", file=sys.stderr)
    if isinstance(payload, dict) and set(payload) == {"content"} and isinstance(payload["content"], dict):
        return payload["content"]
    return payload


def deepseek_request(
    messages: list[dict[str, str]],
    api_key: str,
    model: str,
    api_url: str,
    timeout: float,
    budget: RunBudget | None = None,
    stage: str = "DeepSeek 请求",
) -> str:
    payload_body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.15,
        "max_tokens": 8192,
        "response_format": {"type": "json_object"},
    }
    seed = os.environ.get("DEEPSEEK_SEED", "").strip()
    if seed:
        try:
            payload_body["seed"] = int(seed)
        except ValueError as exc:
            raise LedgerError("DEEPSEEK_SEED 必须是整数") from exc
    body = json.dumps(payload_body, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        api_url,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        effective_timeout = budget.request_timeout(timeout, stage) if budget else timeout
        with request.urlopen(req, timeout=effective_timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LedgerError(f"DeepSeek 请求失败：{exc}") from exc
    try:
        usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
        for key in TOKEN_USAGE:
            TOKEN_USAGE[key] += int(usage.get(key, 0) or 0)
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LedgerError("DeepSeek 响应缺 choices[0].message.content") from exc


def call_with_repair(
    messages: list[dict[str, str]],
    parse: Callable[[str], Any],
    api_key: str,
    model: str,
    api_url: str,
    timeout: float,
    retries: int,
    stage: str,
    budget: RunBudget | None = None,
) -> Any:
    history = list(messages)
    errors: list[str] = []
    for attempt in range(1, retries + 1):
        attempt_name = f"{stage} attempt {attempt}/{retries}"
        attempt_started = stage_start(attempt_name, budget) if budget else time.monotonic()
        raw = ""
        try:
            raw = deepseek_request(history, api_key, model, api_url, timeout, budget, attempt_name)
            parsed = parse(raw)
            if budget:
                stage_done(attempt_name, attempt_started, budget)
            return parsed
        except TimeBudgetExceeded:
            if budget:
                stage_done(attempt_name, attempt_started, budget, "timeout")
            raise
        except ValidationFailure as exc:
            detail = "；".join(exc.errors[:16])
        except (LedgerError, json.JSONDecodeError, TypeError, ValueError) as exc:
            detail = str(exc)
        if budget and budget.remaining() <= 0:
            stage_done(attempt_name, attempt_started, budget, "timeout")
            budget.check(attempt_name)
        if budget:
            stage_done(attempt_name, attempt_started, budget, "retry")
        errors.append(detail)
        print(f"[retry {attempt}/{retries}] {stage}：{detail}", file=sys.stderr)
        if raw:
            history.append({"role": "assistant", "content": raw})
        history.append(
            {
                "role": "user",
                "content": (
                    "请在上一版 JSON 基础上只修复下列具体错误，保留已正确的证据与判断，"
                    "只输出 JSON，不要 Markdown、解释或多余字段，必须控制长度；"
                    f"然后重新输出完整 JSON 对象。具体错误：{detail}"
                ),
            }
        )
    raise LedgerError(f"{stage} 连续 {retries} 次失败：{errors[-1] if errors else '未知错误'}")


def extraction_cache_path(
    cache_dir: Path, index: int, chunk: str, date_value: str, model: str
) -> tuple[Path, str]:
    digest = hashlib.sha256(
        f"{CACHE_VERSION}\0{PROMPT_VERSION}\0{date_value}\0{model}\0{chunk}".encode("utf-8")
    ).hexdigest()
    return cache_dir / f"chunk-{index:03d}-{digest[:16]}.json", digest


def read_extraction_cache(path: Path, digest: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("cache_version") != CACHE_VERSION or payload.get("digest") != digest:
        return None
    result = payload.get("result")
    return result if isinstance(result, dict) else None


def write_extraction_cache(path: Path, digest: str, result: dict[str, Any]) -> None:
    atomic_write_json(
        path,
        {"cache_version": CACHE_VERSION, "digest": digest, "prompt_version": PROMPT_VERSION, "result": result},
    )


def extract_chunks(
    transcript: str,
    date_value: str,
    api_key: str,
    model: str,
    api_url: str,
    timeout: float,
    retries: int,
    chunk_size: int,
    cache_dir: Path | None = None,
    budget: RunBudget | None = None,
) -> list[dict[str, Any]]:
    chunks = chunk_transcript(numbered_transcript(redact_for_model(transcript)), chunk_size)
    line_index = transcript_line_index(transcript)
    results: list[dict[str, Any]] = []
    system = load_prompt("ledger-extract-v3.md")
    for index, chunk in enumerate(chunks, start=1):
        chunk_name = f"切片抽取 {index}/{len(chunks)}"
        chunk_started = stage_start(chunk_name, budget) if budget else time.monotonic()
        reference_warnings: list[str] = []
        allowed_line_ids = set(re.findall(r"(?m)^(L\d{4,})\b", chunk))
        prompt = f"""
日期：{date_value}
这是全文第 {index}/{len(chunks)} 切片。
顶层必须且只能是：
{{"evidence":[{{"type":"event|fragment|tone|quote|member|newcomer|arsenal|docket|clash","data":{{...}}}}]}}

规则：
- evidence 总数不得超过 {CHUNK_EVIDENCE_LIMIT} 条，各类合计，不是每类 {CHUNK_EVIDENCE_LIMIT} 条。
- 整个 JSON 控制在 {CHUNK_OUTPUT_CHAR_LIMIT} 字符内；每条只保留必要字段，不复制整篇小作文。
- 每一行开头的 L0001 是稳定行号。所有引用只能返回行号，不得自由复述原话。
- fragment.data={{topic,time,evidence:[{{line,a,fragment,start,end}}],meaning}}，evidence 最多 3 条。
- tone.data={{line,a,fragment,start,end,cls,reason}}，cls 只能 s/j/h。
- quote.data={{line,a,fragment,start,end,g}}，g 只能 s/j/h。
- fragment 可给该行连续片段；也可给 start/end（相对消息正文、0 起、左闭右开）。至少给 fragment 或 start/end。
- 其他 type 的 data 使用任务 schema 中同名字段。
- 优先保留能支撑主题幕、语气、金句、新人、悬案的不重复证据。
切片：
{chunk}
""".strip()

        def parse_chunk(raw: str) -> dict[str, Any]:
            payload = extract_json(raw)
            if not isinstance(payload, dict):
                raise ValidationFailure(["切片输出顶层必须是对象"])
            if set(payload) != {"evidence"}:
                raise ValidationFailure(["切片输出只能有 evidence 字段，不要多余字段"])
            evidence = payload["evidence"]
            if not isinstance(evidence, list):
                raise ValidationFailure(["切片输出 evidence 必须是数组"])
            errors: list[str] = []
            for evidence_index, item in enumerate(evidence):
                path = f"evidence[{evidence_index}]"
                if not isinstance(item, dict) or set(item) != {"type", "data"}:
                    errors.append(f"{path} 必须且只能有 type/data")
                    continue
                if item.get("type") not in EVIDENCE_TYPES:
                    errors.append(f"{path}.type 不在枚举中")
                if not isinstance(item.get("data"), dict):
                    errors.append(f"{path}.data 必须是对象")
            if errors:
                raise ValidationFailure(errors)
            payload = canonicalize_evidence_references(
                payload, line_index, reference_warnings, allowed_line_ids
            )
            evidence = payload["evidence"]
            if len(evidence) > CHUNK_EVIDENCE_LIMIT:
                print(
                    f"[warn] chunk {index}/{len(chunks)} 证据超过 {CHUNK_EVIDENCE_LIMIT} 条，已截断",
                    file=sys.stderr,
                )
                evidence = evidence[:CHUNK_EVIDENCE_LIMIT]
            while evidence and len(json.dumps({"evidence": evidence}, ensure_ascii=False, separators=(",", ":"))) > CHUNK_OUTPUT_CHAR_LIMIT:
                evidence.pop()
            if not evidence:
                raise ValidationFailure([f"切片证据为空或单条过长，整体必须小于 {CHUNK_OUTPUT_CHAR_LIMIT} 字符"])
            payload["evidence"] = evidence
            return payload

        cache_path: Path | None = None
        digest = ""
        cached: dict[str, Any] | None = None
        if cache_dir is not None:
            cache_path, digest = extraction_cache_path(cache_dir, index, chunk, date_value, model)
            cached = read_extraction_cache(cache_path, digest)
        if cached is not None:
            try:
                result = parse_chunk(json.dumps(cached, ensure_ascii=False))
            except (LedgerError, json.JSONDecodeError, TypeError, ValueError):
                print(f"[warn] chunk {index}/{len(chunks)} 缓存无效，重新抽取", file=sys.stderr)
                cached = None
            else:
                print(f"[cache] extracted chunk {index}/{len(chunks)}", file=sys.stderr)
        if cached is None:
            result = call_with_repair(
                [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                parse_chunk,
                api_key,
                model,
                api_url,
                timeout,
                retries,
                f"切片 {index}/{len(chunks)} 抽取失败",
                budget,
            )
            if cache_path is not None:
                write_extraction_cache(cache_path, digest, result)
        for evidence_index, item in enumerate(result["evidence"], start=1):
            item["id"] = f"c{index:02d}-e{evidence_index:02d}"
        results.append(result)
        for warning in reference_warnings:
            print(f"[warn] chunk {index}/{len(chunks)} {warning}", file=sys.stderr)
        compact_size = len(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
        print(
            f"[ok] extracted chunk {index}/{len(chunks)}: {len(result['evidence'])} evidence / {compact_size} chars",
            file=sys.stderr,
        )
        if budget:
            stage_done(chunk_name, chunk_started, budget)
    return results


def quote_evidence_items(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for chunk in chunks:
        for item in chunk.get("evidence", []):
            if not (
                isinstance(item, dict)
                and item.get("type") == "quote"
                and isinstance(item.get("data"), dict)
                and item["data"].get("line")
                and item["data"].get("v")
            ):
                continue
            key = (str(item["data"].get("a", "")), normalize_verbatim(item["data"]["v"]))
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
    return result


def high_frequency_quote_lines(transcript: str, stats: dict[str, Any], max_chars: int = 7_000) -> str:
    line_index = transcript_line_index(transcript)
    raw_speakers = stats.get("speakers", [])
    speakers = [
        str(item[0]).strip()
        for item in raw_speakers
        if isinstance(item, list) and len(item) >= 2 and str(item[0]).strip()
    ][:12]
    if not speakers:
        speakers = list(dict.fromkeys(source["a"] for source in line_index.values()))[:12]
    by_author = {
        author: [
            source
            for source in line_index.values()
            if source["a"] == author
            and 6 <= len(source["text"]) <= 360
            and not is_sensitive(source["text"])
            and source["text"] != "[敏感内容已移除]"
        ]
        for author in speakers
    }
    selected: list[str] = []
    used = 0
    position = 0
    while used < max_chars:
        added = False
        for author in speakers:
            rows = by_author.get(author, [])
            if position >= len(rows):
                continue
            source = rows[position]
            rendered = f"{source['line']} [{source['time']}] {source['a']}: {source['text']}"
            if selected and used + len(rendered) + 1 > max_chars:
                continue
            selected.append(rendered)
            used += len(rendered) + 1
            added = True
        if not added:
            break
        position += 1
    return "\n".join(selected)


def supplement_quote_evidence(
    chunks: list[dict[str, Any]],
    transcript: str,
    stats: dict[str, Any],
    judge_feedback: str,
    api_key: str,
    model: str,
    api_url: str,
    timeout: float,
    retries: int,
    cache_dir: Path | None,
    budget: RunBudget | None = None,
) -> list[dict[str, Any]]:
    current = quote_evidence_items(chunks)
    if len(current) >= MIN_QUOTES:
        return chunks
    candidates = high_frequency_quote_lines(transcript, stats)
    if not candidates:
        raise ValidationFailure([f"逐字金句证据仅 {len(current)} 条，且没有可补抽的高频发言行"])
    system = load_prompt("ledger-extract-v3.md")
    prompt = f"""
这是金句不足时唯一一次补抽。当前只有 {len(current)} 条，至少需要 {MIN_QUOTES} 条。
候选只来自 stats.json 的高频发言者，并已带稳定行号。
只输出：{{"quotes":[{{"line":"L0123","a":"署名","g":"s|j|h","fragment":"该行连续片段","start":0,"end":12}}]}}
规则：
- 返回 5–10 个不重复候选；只能引用下列行，禁止复述或改标点。
- fragment 与 start/end 二选一即可；start/end 相对消息正文、0 起、左闭右开。
- 优先选择能独立成立、有判断或有代表性语气的句子，避开纯链接、寒暄和隐私。
- judge 建议：{judge_feedback or '金句必须按行号逐字定位；优先补足至少 5 条可核验引用。'}
候选行：
{candidates}
    """.strip()
    line_index = transcript_line_index(transcript)
    allowed_line_ids = set(re.findall(r"(?m)^(L\d{4,})\b", candidates))
    reference_warnings: list[str] = []

    def parse_supplement(raw: str) -> dict[str, Any]:
        payload = extract_json(raw)
        if not isinstance(payload, dict) or set(payload) != {"quotes"} or not isinstance(payload["quotes"], list):
            raise ValidationFailure(["金句补抽必须且只能输出 quotes 数组"])
        raw_evidence = {
            "evidence": [
                {"type": "quote", "data": item}
                for item in payload["quotes"][:10]
                if isinstance(item, dict)
            ]
        }
        canonical = canonicalize_evidence_references(
            raw_evidence, line_index, reference_warnings, allowed_line_ids
        )
        if not canonical["evidence"]:
            raise ValidationFailure(["金句补抽没有任何可按行号回填的引用"])
        return canonical

    digest = hashlib.sha256(
        f"quotes\0{CACHE_VERSION}\0{PROMPT_VERSION}\0{model}\0{candidates}\0{judge_feedback}".encode("utf-8")
    ).hexdigest()
    cache_path = cache_dir / f"quotes-supplement-{digest[:16]}.json" if cache_dir is not None else None
    supplemental = read_extraction_cache(cache_path, digest) if cache_path is not None else None
    if supplemental is not None:
        try:
            supplemental = parse_supplement(
                json.dumps({"quotes": [item["data"] for item in supplemental.get("evidence", [])]}, ensure_ascii=False)
            )
        except (LedgerError, json.JSONDecodeError, TypeError, ValueError):
            supplemental = None
        else:
            print("[cache] quote supplement", file=sys.stderr)
    if supplemental is None:
        supplemental = call_with_repair(
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            parse_supplement,
            api_key,
            model,
            api_url,
            timeout,
            retries,
            "金句不足补抽失败",
            budget,
        )
        if cache_path is not None:
            write_extraction_cache(cache_path, digest, supplemental)

    seen = {(item["data"]["a"], normalize_verbatim(item["data"]["v"])) for item in current}
    additions: list[dict[str, Any]] = []
    for item in supplemental["evidence"]:
        key = (item["data"]["a"], normalize_verbatim(item["data"]["v"]))
        if key in seen:
            continue
        seen.add(key)
        additions.append(item)
    for index, item in enumerate(additions, 1):
        item["id"] = f"quote-extra-e{index:02d}"
    if additions:
        chunks.append({"evidence": additions})
    for warning in reference_warnings:
        print(f"[warn] quote supplement {warning}", file=sys.stderr)
    total = len(quote_evidence_items(chunks))
    print(f"[ok] quote evidence: {len(current)} + {len(additions)} = {total}", file=sys.stderr)
    if total < MIN_QUOTES:
        raise ValidationFailure([f"逐字金句证据补抽后仍只有 {total} 条，至少需要 {MIN_QUOTES} 条"])
    return chunks


def evidence_by_id(chunks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(item["id"]): item
        for chunk in chunks
        for item in chunk.get("evidence", [])
        if isinstance(item, dict) and item.get("id")
    }


def planned_quotes(skeleton: dict[str, Any], chunks: list[dict[str, Any]]) -> list[dict[str, str]]:
    indexed = evidence_by_id(chunks)
    quotes: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for evidence_id in skeleton.get("quote_plan", []):
        item = indexed.get(str(evidence_id), {})
        data = item.get("data", {}) if item.get("type") == "quote" else {}
        if not isinstance(data, dict):
            continue
        text, author, tone = str(data.get("v", "")), str(data.get("a", "")), str(data.get("g", ""))
        key = (author, normalize_verbatim(text))
        if not key[0] or not key[1] or key in seen or tone not in TONE_CLASSES:
            continue
        seen.add(key)
        quotes.append({"t": text, "a": author, "g": tone})
    return quotes[: LIST_LIMITS["quotes"]]


def numbered_reference_catalog(chunks: list[dict[str, Any]]) -> str:
    rows: dict[str, str] = {}
    for item in evidence_by_id(chunks).values():
        data = item.get("data", {})
        references = data.get("evidence", []) if item.get("type") == "fragment" else [data]
        for reference in references if isinstance(references, list) else []:
            if not isinstance(reference, dict) or not reference.get("line") or not reference.get("v"):
                continue
            rows[str(reference["line"])] = (
                f"{reference['line']} [{reference.get('t', '')}] {reference.get('a', '')}: {reference['v']}"
            )
    return "\n".join(rows[key] for key in sorted(rows))


def schema_prompt() -> str:
    return """
顶层必须且只能有这些字段：
date,stats_override,hours,events,themes,tone_notes,quotes,growth,members_focus,title,lead,coverage,complete,pulse,insights,glossary,arsenal,docket,clashes,newcomers,members_total,essays_total,essays_open,distilled_by,reviewed_by,prompt_version
嵌套 schema：
stats_override={msgs:int,active:int}; hours={"00":int,...};
events=[{t,h,d}];
themes=[{h,when,body,deep,voices:[{line,a,g:"j|s|h",fragment,start,end}],thread_id,thread_title,thread_status:"ongoing|closed"}];
tone_notes=[{h,body,cls:"j|s|h"}]; quotes=[{line,a,g:"j|s|h",fragment,start,end}];
growth={takeaways:[str],todo:[{phase:"今天|本周|本月",items:[str]}]};
members_focus=[{name,role,msgs:int,tone:"j|s|h",quote,tags:[str]}];
coverage={from,to,cutoff,note}; pulse={caption,note};
insights=[{h,en,body}]; glossary=[{term,def}]; arsenal=[{h,body}];
docket=[{kind,h,d,status:"open|closed"}]; clashes=[{h,en,sides,verdict}];
newcomers=[{name,note,t,by,first_words}].
""".strip()


def evidence_ids(chunks: list[dict[str, Any]]) -> set[str]:
    return {
        str(item["id"])
        for chunk in chunks
        for item in chunk.get("evidence", [])
        if isinstance(item, dict) and item.get("id")
    }


def validate_skeleton(payload: Any, chunks: list[dict[str, Any]]) -> dict[str, Any]:
    fields = {
        "title",
        "lead_angle",
        "event_plan",
        "theme_plan",
        "tone_plan",
        "quote_plan",
        "member_plan",
        "growth_plan",
        "extension_plan",
    }
    errors: list[str] = []
    if not isinstance(payload, dict):
        raise ValidationFailure(["八段骨架顶层必须是对象"])
    missing, extra = fields - payload.keys(), payload.keys() - fields
    if missing:
        errors.append(f"八段骨架缺字段：{', '.join(sorted(missing))}")
    if extra:
        errors.append(f"八段骨架多字段：{', '.join(sorted(extra))}")
    if errors:
        raise ValidationFailure(errors)
    for field in ("title", "lead_angle"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            errors.append(f"八段骨架.{field} 必须是非空字符串")
    for field in ("event_plan", "theme_plan", "tone_plan", "quote_plan", "member_plan"):
        if not isinstance(payload[field], list):
            errors.append(f"八段骨架.{field} 必须是数组")
    if errors:
        raise ValidationFailure(errors)

    valid_ids = evidence_ids(chunks)
    quote_ids = {
        str(item["id"])
        for chunk in chunks
        for item in chunk.get("evidence", [])
        if isinstance(item, dict) and item.get("id") and item.get("type") == "quote"
    }

    def check_ids(values: Any, path: str, minimum: int = 1) -> None:
        if not isinstance(values, list) or len(values) < minimum or not all(isinstance(value, str) for value in values):
            errors.append(f"{path} 必须是至少 {minimum} 个 evidence id 的数组")
            return
        if len(set(values)) < minimum:
            errors.append(f"{path} 必须包含至少 {minimum} 个不同的 evidence id")
        unknown = sorted(set(values) - valid_ids)
        if unknown:
            errors.append(f"{path} 含未知 evidence id：{', '.join(unknown[:5])}")

    if not 1 <= len(payload["event_plan"]) <= 12:
        errors.append("event_plan 必须 1–12 条")
    for index, item in enumerate(payload["event_plan"]):
        if not isinstance(item, dict) or set(item) != {"evidence_ids", "angle"} or not isinstance(item.get("angle"), str):
            errors.append(f"event_plan[{index}] 必须且只能有 evidence_ids/angle")
            continue
        check_ids(item["evidence_ids"], f"event_plan[{index}].evidence_ids")

    if not 3 <= len(payload["theme_plan"]) <= 6:
        errors.append("theme_plan 必须 3–6 幕")
    theme_fields = {"h", "thread_id", "thread_title", "thread_status", "evidence_ids", "deep_question"}
    for index, item in enumerate(payload["theme_plan"]):
        if not isinstance(item, dict) or set(item) != theme_fields:
            errors.append(f"theme_plan[{index}] 字段不齐")
            continue
        for field in theme_fields - {"evidence_ids"}:
            if not isinstance(item[field], str) or not item[field].strip():
                errors.append(f"theme_plan[{index}].{field} 必须是非空字符串")
        if item.get("thread_status") not in THREAD_STATUSES:
            errors.append(f"theme_plan[{index}].thread_status 不在枚举中")
        check_ids(item.get("evidence_ids"), f"theme_plan[{index}].evidence_ids", minimum=3)

    if len(payload["tone_plan"]) != 3:
        errors.append("tone_plan 必须恰好 3 条")
    tones: set[str] = set()
    for index, item in enumerate(payload["tone_plan"]):
        if not isinstance(item, dict) or set(item) != {"cls", "evidence_id", "reason"}:
            errors.append(f"tone_plan[{index}] 必须且只能有 cls/evidence_id/reason")
            continue
        if item.get("cls") not in TONE_CLASSES:
            errors.append(f"tone_plan[{index}].cls 不在 s/j/h 中")
        else:
            tones.add(item["cls"])
        if item.get("evidence_id") not in valid_ids:
            errors.append(f"tone_plan[{index}].evidence_id 未知")
        if not isinstance(item.get("reason"), str):
            errors.append(f"tone_plan[{index}].reason 必须是字符串")
    if tones != TONE_CLASSES:
        errors.append("tone_plan 必须同时覆盖 s/j/h")

    if not 5 <= len(payload["quote_plan"]) <= 10:
        errors.append("quote_plan 必须 5–10 条")
    check_ids(payload["quote_plan"], "quote_plan", minimum=5)
    non_quote_ids = sorted(set(payload["quote_plan"]) - quote_ids)
    if non_quote_ids:
        errors.append(f"quote_plan 只能引用 quote evidence id：{', '.join(non_quote_ids[:5])}")
    if len(planned_quotes(payload, chunks)) < MIN_QUOTES:
        errors.append(f"quote_plan 必须选出至少 {MIN_QUOTES} 条不同的逐字金句")

    if not 1 <= len(payload["member_plan"]) <= 12:
        errors.append("member_plan 必须 1–12 条")
    for index, item in enumerate(payload["member_plan"]):
        if not isinstance(item, dict) or set(item) != {"name", "evidence_ids"} or not isinstance(item.get("name"), str):
            errors.append(f"member_plan[{index}] 必须且只能有 name/evidence_ids")
            continue
        check_ids(item["evidence_ids"], f"member_plan[{index}].evidence_ids")

    growth = payload["growth_plan"]
    if not isinstance(growth, dict) or set(growth) != {"takeaways", "actions"}:
        errors.append("growth_plan 必须且只能有 takeaways/actions")
    elif not all(isinstance(growth[field], list) for field in ("takeaways", "actions")):
        errors.append("growth_plan.takeaways/actions 必须是数组")
    extension = payload["extension_plan"]
    extension_fields = {"insights", "glossary", "arsenal", "docket", "clashes", "newcomers"}
    if not isinstance(extension, dict) or set(extension) != extension_fields:
        errors.append("八段骨架.extension_plan 字段不齐")
    elif not all(isinstance(extension[field], list) for field in extension_fields):
        errors.append("八段骨架.extension_plan 各字段必须是数组")

    compact_length = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    if compact_length > SKELETON_OUTPUT_CHAR_LIMIT:
        errors.append(f"八段骨架超过 {SKELETON_OUTPUT_CHAR_LIMIT} 字符，请只保留证据 id 和简短写作角度")
    if errors:
        raise ValidationFailure(errors)
    return payload


def build_skeleton_messages(
    date_value: str,
    stats: dict[str, Any],
    context: str,
    previous: dict[str, Any],
    newcomers: Any,
    chunks: list[dict[str, Any]],
    model: str,
    judge_feedback: str = "",
) -> list[dict[str, str]]:
    system = load_prompt("ledger-skeleton-v3.md")
    prompt = f"""
日期：{date_value}
模型：{model}
只输出以下骨架，字段不得增减，整体小于 {SKELETON_OUTPUT_CHAR_LIMIT} 字符：
{{
  "title":"短标题", "lead_angle":"导语角度",
  "event_plan":[{{"evidence_ids":["c01-e01"],"angle":"短角度"}}],
  "theme_plan":[{{"h":"幕名","thread_id":"旧id或新slug","thread_title":"线索名","thread_status":"ongoing|closed","evidence_ids":["至少3个id"],"deep_question":"没说破的结构"}}],
  "tone_plan":[{{"cls":"s|j|h","evidence_id":"id","reason":"短理由"}}],
  "quote_plan":["5–10个quote evidence id"],
  "member_plan":[{{"name":"人名","evidence_ids":["id"]}}],
  "growth_plan":{{"takeaways":["3–5个角度"],"actions":["3–5个一日动作"]}},
  "extension_plan":{{"insights":[],"glossary":[],"arsenal":[],"docket":[],"clashes":[],"newcomers":[]}}
}}
必须有 3–6 个主题幕，每幕引用至少 3 个证据 id；语气恰好覆盖 s/j/h。
线索优先沿用上期 thread_id；新线索才起稳定英文 slug。

stats.json（数字真值，程序还会回锁）：
{json.dumps(stats, ensure_ascii=False)}

context-prev.md：
{context or '(无)'}

上一期承接数据：
{json.dumps(previous_context(previous), ensure_ascii=False)}

newcomers.json（如有）：
{json.dumps(newcomers, ensure_ascii=False)}

切片证据包：
{json.dumps(chunks, ensure_ascii=False)}

证据引用行原文索引（总装只能按这些 L 行号引用）：
{numbered_reference_catalog(chunks)}
{f'上一轮质量 judge 反馈（必须修正）：{judge_feedback}' if judge_feedback else ''}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": prompt}]


def build_fill_messages(
    date_value: str,
    stats: dict[str, Any],
    context: str,
    previous: dict[str, Any],
    newcomers: Any,
    chunks: list[dict[str, Any]],
    skeleton: dict[str, Any],
    model: str,
    judge_feedback: str = "",
) -> list[dict[str, str]]:
    system = load_prompt("ledger-fill-v3.md")
    prompt = f"""
日期：{date_value}
模型署名：{distilled_by(model)}

{schema_prompt()}

只按下列骨架填充，最终紧凑 JSON 必须小于 {FINAL_OUTPUT_CHAR_LIMIT} 字符：
{json.dumps(skeleton, ensure_ascii=False)}

填充规则：
1. 八段都有：HERO 数字、24h 心电图解读、时间线、成员/新人、主题幕、语气分层、金句、成长+行动。
2. tone_notes 必须同时有 s 认真、j 玩笑、h 半真；每条 body 用「」包逐字证据并解释判定。j 不得当观点。
3. 每一幕 theme.deep 的质量目标是至少 3 句：能定位时，每个判断句各用「」引用一条 transcript 原话；其中一句以“没说破的：”开头；最后一句以可执行动词落到一天内动作。找不到逐字证据时直接写不带引号的判断，绝不编造引文；程序会记 warning 并交给 judge 评分。
4. quotes 5–10 条；quotes 只返回 {{line,a,g,fragment,start,end}}，themes[].voices 只返回 {{line,a,g,fragment,start,end}}，g 只能 s/j/h。程序会按 L 行号从原 transcript 回填 t/v，禁止自己复述。
5. 文字必须紧凑：lead 不超过 180 字，每个 event.d 不超过 100 字，每幕 body/deep 各不超过 260 字，每条 insight.body 不超过 220 字。
6. 富文本只允许 <b> <i> <br> <u>；insights 中延伸用 <u>没说破的：…</u>。不得编造质量分。
7. 全文禁用这些工程腔：口径、治理产物、端点、静态、渲染、数据层、接线、缺口、闭环、赋能。改写成具体的人、问题和动作。

stats.json：{json.dumps(stats, ensure_ascii=False)}
context-prev.md：{context or '(无)'}
上一期承接：{json.dumps(previous_context(previous), ensure_ascii=False)}
newcomers.json：{json.dumps(newcomers, ensure_ascii=False)}
证据包：{json.dumps(chunks, ensure_ascii=False)}
证据引用行原文索引：
{numbered_reference_catalog(chunks)}
{f'上一轮质量 judge 反馈（必须修正）：{judge_feedback}' if judge_feedback else ''}
""".strip()
    return [{"role": "system", "content": system}, {"role": "user", "content": prompt}]


def strip_disallowed_html(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        closing, tag = match.group(1), match.group(2).lower()
        if tag not in ALLOWED_TAGS:
            return ""
        if tag == "br":
            return "<br>"
        return f"<{closing}{tag}>"

    return re.sub(r"<\s*(/?)\s*([A-Za-z0-9]+)(?:\s+[^>]*)?>", replace, value)


def plain(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(value or ""))).strip()


def replace_engineering_jargon(value: str) -> tuple[str, list[str]]:
    """Replace banned report jargon outside verbatim quotation spans."""
    parts = re.split(r"(「[^」]*」|“[^”]*”|\"[^\"]*\")", value)
    hits: list[str] = []
    for index in range(0, len(parts), 2):
        for word, replacement in ENGINEERING_REPLACEMENTS.items():
            if word in parts[index]:
                hits.extend([word] * parts[index].count(word))
                parts[index] = parts[index].replace(word, replacement)
    return "".join(parts), hits


def clean_engineering_jargon(content: dict[str, Any], warnings: list[str]) -> None:
    targets: list[tuple[dict[str, Any], str, str]] = [
        (content, "title", "title"),
        (content, "lead", "lead"),
    ]
    for group, fields in (
        ("events", ("h", "d")),
        ("themes", ("h", "body", "deep", "thread_title")),
        ("tone_notes", ("h", "body")),
        ("members_focus", ("role",)),
        ("insights", ("h", "body")),
        ("glossary", ("term", "def")),
        ("arsenal", ("h", "body")),
        ("docket", ("kind", "h", "d")),
        ("clashes", ("h", "sides", "verdict")),
        ("newcomers", ("note",)),
    ):
        for row_index, item in enumerate(content.get(group, [])):
            if not isinstance(item, dict):
                continue
            for field in fields:
                targets.append((item, field, f"{group}[{row_index}].{field}"))
    for group in ("coverage", "pulse"):
        item = content.get(group)
        if isinstance(item, dict):
            for field in item:
                if field not in {"from", "to", "cutoff"}:
                    targets.append((item, field, f"{group}.{field}"))
    growth = content.get("growth")
    if isinstance(growth, dict):
        for index, value in enumerate(growth.get("takeaways", [])):
            if isinstance(value, str):
                cleaned, hits = replace_engineering_jargon(value)
                growth["takeaways"][index] = cleaned
                if hits:
                    warnings.append(f"growth.takeaways[{index}] 已替换工程腔：{'、'.join(dict.fromkeys(hits))}")
        for block_index, block in enumerate(growth.get("todo", [])):
            if not isinstance(block, dict):
                continue
            for action_index, value in enumerate(block.get("items", [])):
                if isinstance(value, str):
                    cleaned, hits = replace_engineering_jargon(value)
                    block["items"][action_index] = cleaned
                    if hits:
                        warnings.append(
                            f"growth.todo[{block_index}].items[{action_index}] 已替换工程腔："
                            + "、".join(dict.fromkeys(hits))
                        )
    for member_index, member in enumerate(content.get("members_focus", [])):
        if not isinstance(member, dict) or not isinstance(member.get("tags"), list):
            continue
        for tag_index, value in enumerate(member["tags"]):
            if isinstance(value, str):
                cleaned, hits = replace_engineering_jargon(value)
                member["tags"][tag_index] = cleaned
                if hits:
                    warnings.append(
                        f"members_focus[{member_index}].tags[{tag_index}] 已替换工程腔："
                        + "、".join(dict.fromkeys(hits))
                    )
    for item, field, label in targets:
        value = item.get(field)
        if not isinstance(value, str):
            continue
        cleaned, hits = replace_engineering_jargon(value)
        if hits:
            item[field] = cleaned
            warnings.append(f"{label} 已替换工程腔：{'、'.join(dict.fromkeys(hits))}")


def title_grams(value: str) -> set[str]:
    clean = re.sub(r"[^\w\u4e00-\u9fff]", "", value.lower())
    return {clean[index : index + 2] for index in range(max(0, len(clean) - 1))}


def normalize_threads(content: dict[str, Any], previous: dict[str, Any], warnings: list[str]) -> None:
    old_threads = [item for item in previous.get("threads", []) if isinstance(item, dict) and item.get("id")]
    by_id = {str(item["id"]): item for item in old_threads}
    for index, theme in enumerate(content.get("themes", [])):
        if not isinstance(theme, dict):
            continue
        supplied = str(theme.get("thread_id", ""))
        title = str(theme.get("thread_title") or theme.get("h") or "")
        if supplied in by_id:
            continue
        grams = title_grams(title)
        scores = [
            (
                len(grams & (title_grams(str(item.get("title", ""))) | title_grams(str(item.get("theme", ""))))),
                item,
            )
            for item in old_threads
        ]
        score, match = max(scores, key=lambda pair: pair[0], default=(0, None))
        if match and score >= 2:
            theme["thread_id"] = str(match["id"])
            theme["thread_title"] = str(match.get("title") or title)
            warnings.append(f"themes[{index}].thread_id 已沿用上期 {match['id']}")


def normalize_content(
    content: Any,
    transcript: str,
    stats: dict[str, Any],
    previous: dict[str, Any],
    date_value: str,
    model: str,
    warnings: list[str],
) -> dict[str, Any]:
    if not isinstance(content, dict):
        raise ValidationFailure(["顶层必须是 JSON 对象"])
    normalized = copy.deepcopy(content)
    for extra in sorted(normalized.keys() - TOP_FIELDS):
        normalized.pop(extra, None)
        warnings.append(f"content.{extra} 为多余字段，已移除")

    normalized["date"] = date_value
    speakers = stats.get("speakers", [])
    active = len(speakers) if isinstance(speakers, list) else 0
    truth_stats = {"msgs": int(stats.get("msgs", 0) or 0), "active": active}
    if normalized.get("stats_override") != truth_stats:
        warnings.append("stats_override 已回锁 stats.json 真值")
    normalized["stats_override"] = truth_stats
    truth_hours = copy.deepcopy(stats.get("hours")) if isinstance(stats.get("hours"), dict) else {}
    if normalized.get("hours") != truth_hours:
        warnings.append("hours 已回锁 stats.json 真值")
    normalized["hours"] = truth_hours
    normalized["distilled_by"] = distilled_by(model)
    normalized["reviewed_by"] = "待 Sun 复核"
    normalized["prompt_version"] = PROMPT_VERSION

    list_defaults = (
        "events",
        "themes",
        "tone_notes",
        "quotes",
        "members_focus",
        "insights",
        "glossary",
        "arsenal",
        "docket",
        "clashes",
        "newcomers",
    )
    for key in list_defaults:
        if not isinstance(normalized.get(key), list):
            normalized[key] = []
            warnings.append(f"{key} 缺失或类型错误，已补空数组")

    row_defaults: dict[str, dict[str, Any]] = {
        "events": {"t": "", "h": "", "d": ""},
        "tone_notes": {"h": "", "body": "", "cls": ""},
        "quotes": {"t": "", "a": "", "g": ""},
        "members_focus": {"name": "", "role": "", "msgs": 0, "tone": "", "quote": "", "tags": []},
        "insights": {"h": "", "en": "", "body": ""},
        "glossary": {"term": "", "def": ""},
        "arsenal": {"h": "", "body": ""},
        "docket": {"kind": "", "h": "", "d": "", "status": "open"},
        "clashes": {"h": "", "en": "", "sides": "", "verdict": ""},
        "newcomers": {"name": "", "note": "", "t": "", "by": "", "first_words": ""},
    }
    for key, defaults in row_defaults.items():
        rows: list[dict[str, Any]] = []
        for index, item in enumerate(normalized[key]):
            if not isinstance(item, dict):
                warnings.append(f"{key}[{index}] 不是对象，已丢弃")
                continue
            row: dict[str, Any] = {}
            for field, default in defaults.items():
                value = item.get(field, copy.deepcopy(default))
                if isinstance(default, str) and not isinstance(value, str):
                    value = str(value) if value is not None else ""
                    warnings.append(f"{key}[{index}].{field} 已转为字符串")
                elif isinstance(default, int) and not isinstance(value, int):
                    value = 0
                    warnings.append(f"{key}[{index}].{field} 已回填 0")
                elif isinstance(default, list) and not isinstance(value, list):
                    value = []
                    warnings.append(f"{key}[{index}].{field} 已回填空数组")
                row[field] = value
            rows.append(row)
        normalized[key] = rows

    normalized_themes: list[dict[str, Any]] = []
    theme_defaults: dict[str, Any] = {
        "h": "",
        "when": "",
        "body": "",
        "deep": "",
        "voices": [],
        "thread_id": "",
        "thread_title": "",
        "thread_status": "ongoing",
    }
    for index, item in enumerate(normalized["themes"]):
        if not isinstance(item, dict):
            warnings.append(f"themes[{index}] 不是对象，已丢弃")
            continue
        theme = {field: copy.deepcopy(item.get(field, default)) for field, default in theme_defaults.items()}
        for field in ("h", "when", "body", "deep", "thread_id", "thread_title", "thread_status"):
            if not isinstance(theme[field], str):
                theme[field] = str(theme[field]) if theme[field] is not None else ""
        if theme["thread_status"] not in THREAD_STATUSES:
            theme["thread_status"] = "ongoing"
            warnings.append(f"themes[{index}].thread_status 已回填 ongoing")
        if not isinstance(theme["voices"], list):
            theme["voices"] = []
            warnings.append(f"themes[{index}].voices 已回填空数组")
        normalized_themes.append(theme)
    normalized["themes"] = normalized_themes

    first_theme = plain(normalized["themes"][0].get("h")) if normalized["themes"] else "今日群聊"
    issue = int(previous.get("issue", 0) or 0) + 1
    if not isinstance(normalized.get("title"), str) or not normalized["title"].strip():
        normalized["title"] = f"第 {issue:03d} 批 · {first_theme}"
        warnings.append("title 缺失，已根据批次与首幕名自动补齐")
    if len(normalized["title"]) > 120:
        normalized["title"] = normalized["title"][:119].rstrip() + "…"
        warnings.append("title 超长，已自动截断")
    if not isinstance(normalized.get("lead"), str) or not normalized["lead"].strip():
        body = plain(normalized["themes"][0].get("body")) if normalized["themes"] else ""
        normalized["lead"] = body[:60] or f"今日共 {truth_stats['msgs']} 条消息、{truth_stats['active']} 位发言者。"
        warnings.append("lead 缺失，已根据首幕或 stats.json 自动补齐")
    if len(normalized["lead"]) > 180:
        normalized["lead"] = normalized["lead"][:179].rstrip() + "…"
        warnings.append("lead 超过 180 字，已自动截断")
    if not isinstance(normalized.get("complete"), bool):
        normalized["complete"] = True
        warnings.append("complete 缺失或类型错误，已回填 true")

    last_time = "23:59"
    transcript_times = [match.group("time")[-5:] for line in transcript.splitlines() if (match := TRANSCRIPT_LINE.match(line))]
    if transcript_times:
        last_time = transcript_times[-1]
    coverage = normalized.get("coverage") if isinstance(normalized.get("coverage"), dict) else {}
    from_value = coverage.get("from") if isinstance(coverage.get("from"), str) else ""
    to_value = coverage.get("to") if isinstance(coverage.get("to"), str) else ""
    if not DATE_RE.fullmatch(from_value):
        from_value = date_value
        warnings.append("coverage.from 无效，已回填任务日期")
    if not DATE_RE.fullmatch(to_value):
        to_value = date_value
        warnings.append("coverage.to 无效，已回填任务日期")
    cutoff = coverage.get("cutoff") if isinstance(coverage.get("cutoff"), str) else ""
    if not cutoff.strip():
        cutoff = f"{date_value} {last_time}"
        warnings.append("coverage.cutoff 缺失，已根据 transcript 末条时间补齐")
    note = coverage.get("note") if isinstance(coverage.get("note"), str) else ""
    if not note.strip():
        note = f"数字以 stats.json 为准：{truth_stats['msgs']} 条消息、{truth_stats['active']} 位发言者。"
    normalized["coverage"] = {"from": from_value, "to": to_value, "cutoff": cutoff, "note": note}

    pulse = normalized.get("pulse") if isinstance(normalized.get("pulse"), dict) else {}
    normalized["pulse"] = {
        "caption": str(pulse.get("caption", "")),
        "note": str(pulse.get("note", "")),
    }
    growth = normalized.get("growth") if isinstance(normalized.get("growth"), dict) else {}
    takeaways = [str(item).strip() for item in growth.get("takeaways", []) if isinstance(item, str) and item.strip()] if isinstance(growth.get("takeaways"), list) else []
    todo_rows: list[dict[str, Any]] = []
    for block_index, block in enumerate(growth.get("todo", []) if isinstance(growth.get("todo"), list) else []):
        if not isinstance(block, dict):
            warnings.append(f"growth.todo[{block_index}] 不是对象，已丢弃")
            continue
        phase = str(block.get("phase", ""))
        if phase not in TODO_PHASES:
            phase = "今天"
            warnings.append(f"growth.todo[{block_index}].phase 无效，已回填今天")
        actions: list[str] = []
        for action_index, raw_action in enumerate(block.get("items", []) if isinstance(block.get("items"), list) else []):
            action = plain(raw_action)
            if not action:
                continue
            if not any(verb in action for verb in ACTION_VERBS):
                warnings.append(f"growth.todo[{block_index}].items[{action_index}] 缺可执行动词，已丢弃")
                continue
            if len(action) > 40:
                action = action[:39].rstrip() + "…"
                warnings.append(f"growth.todo[{block_index}].items[{action_index}] 超过 40 字，已截断")
            actions.append(action)
        if actions:
            todo_rows.append({"phase": phase, "items": actions})
    normalized["growth"] = {"takeaways": takeaways[:5], "todo": todo_rows}

    for field in ("members_total", "essays_total", "essays_open"):
        if not isinstance(normalized.get(field), int) or normalized[field] < 0:
            previous_stats = previous.get("stats", {}) if isinstance(previous.get("stats"), dict) else {}
            normalized[field] = int(previous_stats.get(field.removesuffix("_total"), 0) or 0)
            warnings.append(f"{field} 缺失或无效，已回填上期真值或 0")

    for key, limit in LIST_LIMITS.items():
        value = normalized.get(key)
        if isinstance(value, list) and len(value) > limit:
            warnings.append(f"{key} 超过 {limit} 条，已自动截断")
            normalized[key] = value[:limit]

    rich_paths: list[tuple[dict[str, Any], str, str]] = []
    for group, fields in (
        ("events", ("d",)),
        ("themes", ("body", "deep")),
        ("tone_notes", ("body",)),
        ("insights", ("body",)),
        ("arsenal", ("body",)),
        ("clashes", ("sides", "verdict")),
    ):
        for index, item in enumerate(normalized[group]):
            for field in fields:
                rich_paths.append((item, field, f"{group}[{index}].{field}"))
    for item, field, label in rich_paths:
        if isinstance(item.get(field), str):
            cleaned = strip_disallowed_html(item[field])
            if cleaned != item[field]:
                item[field] = cleaned
                warnings.append(f"{label} 已移除不允许的 HTML 标签/属性")

    clean_engineering_jargon(normalized, warnings)

    utterances = parse_utterances(transcript)
    valid_quotes: list[dict[str, Any]] = []
    for index, item in enumerate(normalized["quotes"]):
        text, author = str(item.get("t", "")), str(item.get("a", ""))
        exact = canonical_verbatim(text, author, utterances)
        if is_sensitive(text):
            warnings.append(f"quotes[{index}] 涉敏已丢弃")
        elif exact is None:
            warnings.append(f"quotes[{index}] 无法按署名在 transcript 逐字找到，已丢弃")
        else:
            if exact != text:
                item["t"] = exact
                warnings.append(f"quotes[{index}] 已按归一化定位回填 transcript 原文")
            valid_quotes.append(item)
    normalized["quotes"] = valid_quotes

    for theme_index, theme in enumerate(normalized.get("themes", [])):
        voices: list[dict[str, Any]] = []
        for voice_index, voice in enumerate(theme["voices"]):
            if not isinstance(voice, dict):
                warnings.append(f"themes[{theme_index}].voices[{voice_index}] 不是对象，已丢弃")
                continue
            text, author = str(voice.get("v", "")), str(voice.get("a", ""))
            exact = canonical_verbatim(text, author, utterances)
            if is_sensitive(text) or exact is None:
                warnings.append(
                    f"themes[{theme_index}].voices[{voice_index}] 无法逐字核验或涉敏，已丢弃"
                )
            else:
                if exact != text:
                    warnings.append(
                        f"themes[{theme_index}].voices[{voice_index}] 已按归一化定位回填 transcript 原文"
                    )
                voices.append({"a": author, "v": exact, "g": str(voice.get("g", ""))})
        theme["voices"] = voices

    for index, member in enumerate(normalized.get("members_focus", [])):
        if member["quote"] and (
            is_sensitive(member["quote"])
            or not quote_exists(member["quote"], str(member.get("name", "")), utterances)
        ):
            member["quote"] = ""
            warnings.append(f"members_focus[{index}].quote 无法逐字核验，已清空")

    for index, newcomer in enumerate(normalized.get("newcomers", [])):
        first_words = newcomer["first_words"]
        if first_words and (
            is_sensitive(first_words)
            or not quote_exists(first_words, str(newcomer.get("name", "")), utterances)
        ):
            newcomer["first_words"] = ""
            warnings.append(f"newcomers[{index}].first_words 无法逐字核验，已清空")

    normalize_threads(normalized, previous, warnings)
    if isinstance(normalized.get("quotes"), list) and len(normalized["quotes"]) < MIN_QUOTES:
        warnings.append(f"quotes 逐字清洗后仅 {len(normalized['quotes'])} 条")
    return normalized


def privacy_shapes(content: dict[str, Any]) -> list[str]:
    text = json.dumps(content, ensure_ascii=False)
    text = re.sub(r"https?://[^\s\"']+", "", text)
    hits: list[str] = []
    if re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", text):
        hits.append("手机号")
    if re.search(r"(?<!\d)\d{17}[\dXx](?!\d)", text):
        hits.append("身份证")
    if re.search(r"(?i)(?:password|passwd|secret|token|密码|口令|密钥)\s*[:=：]\s*[^\s,;，；]{4,}", text):
        hits.append("密码/密钥")
    if re.search(r"(?<![A-Za-z0-9])[A-Za-z0-9+/=_]{24,}(?![A-Za-z0-9])", text):
        hits.append("长令牌")
    return hits


def validate_content(
    content: Any, expected_date: str, *, allow_repairable_theme_issues: bool = False
) -> dict[str, Any]:
    """Reject only structural, verbatim/tone and privacy failures.

    Presentation, lengths, sentence counts, dates and optional schema fields are
    normalized before this hard gate.
    """
    if not isinstance(content, dict):
        raise ValidationFailure(["顶层必须是 JSON 对象"])
    errors: list[str] = []
    section_checks = {
        "HERO": isinstance(content.get("stats_override"), dict),
        "群体心电图": isinstance(content.get("hours"), dict) and isinstance(content.get("pulse"), dict),
        "时间线": isinstance(content.get("events"), list) and bool(content.get("events")),
        "成员/新面孔": (
            isinstance(content.get("members_focus"), list)
            and isinstance(content.get("newcomers"), list)
            and bool(content.get("members_focus") or content.get("newcomers"))
        ),
        "主题幕": isinstance(content.get("themes"), list) and bool(content.get("themes")),
        "语气分层": isinstance(content.get("tone_notes"), list) and bool(content.get("tone_notes")),
        "金句墙": isinstance(content.get("quotes"), list) and len(content.get("quotes", [])) >= MIN_QUOTES,
        "成长/行动": (
            isinstance(content.get("growth"), dict)
            and bool(content.get("growth", {}).get("takeaways") or content.get("growth", {}).get("todo"))
        ),
    }
    missing = [name for name, present in section_checks.items() if not present]
    if missing:
        errors.append("八段结构缺失：" + "、".join(missing))

    for index, note in enumerate(content.get("tone_notes", [])):
        if not isinstance(note, dict) or note.get("cls") not in TONE_CLASSES:
            errors.append(f"tone_notes[{index}].cls 不在 s/j/h 中")
    for index, quote in enumerate(content.get("quotes", [])):
        if not isinstance(quote, dict) or quote.get("g") not in TONE_CLASSES:
            errors.append(f"quotes[{index}].g 不在 s/j/h 中")
    if not allow_repairable_theme_issues:
        for theme_index, theme in enumerate(content.get("themes", [])):
            if not isinstance(theme, dict):
                continue
            for voice_index, voice in enumerate(theme.get("voices", [])):
                if not isinstance(voice, dict) or voice.get("g") not in TONE_CLASSES:
                    errors.append(f"themes[{theme_index}].voices[{voice_index}].g 不在 s/j/h 中")
    for index, member in enumerate(content.get("members_focus", [])):
        if isinstance(member, dict) and member.get("tone") not in TONE_CLASSES:
            errors.append(f"members_focus[{index}].tone 不在 s/j/h 中")

    privacy = privacy_shapes(content)
    if privacy:
        errors.append("成品含隐私形态：" + "、".join(privacy))
    if errors:
        raise ValidationFailure(errors)
    return content


def validate_expected_newcomers(
    content: dict[str, Any], source: Any, warnings: list[str] | None = None
) -> None:
    """Soft-fill named newcomers so one missing card cannot reject a whole issue."""
    warnings = warnings if warnings is not None else []
    if isinstance(source, dict):
        if isinstance(source.get("newcomers"), list):
            entries = source["newcomers"]
        elif isinstance(source.get("items"), list):
            entries = source["items"]
        else:
            entries = [source]
    elif isinstance(source, list):
        entries = source
    else:
        entries = []
    expected = {
        str(item.get("name") or item.get("nickname") or item.get("display_name")).strip()
        for item in entries
        if isinstance(item, dict) and (item.get("name") or item.get("nickname") or item.get("display_name"))
    }
    actual = {
        str(item.get("name", "")).strip()
        for item in content.get("newcomers", [])
        if isinstance(item, dict) and item.get("name")
    }
    missing = sorted(expected - actual)
    for name in missing:
        content.setdefault("newcomers", []).append(
            {"name": name, "note": "来自 newcomers.json，细节待补。", "t": "", "by": "", "first_words": ""}
        )
        warnings.append(f"newcomers 缺少 {name}，已自动补最小卡片")


def quoted_fragments(value: str) -> list[str]:
    """Return evidence fragments inside Chinese or ASCII quotation marks."""
    plain = re.sub(r"<[^>]+>", "", value)
    fragments: list[str] = []
    for match in re.finditer(r"「([^」]{2,120})」|“([^”]{2,120})”|\"([^\"]{2,120})\"", plain):
        fragment = next((group for group in match.groups() if group is not None), "").strip()
        if fragment:
            fragments.append(fragment)
    return fragments


def prose_sentences(value: str) -> list[str]:
    """Split prose into sentences without splitting punctuation inside quotes."""
    text = plain(value)
    sentences: list[str] = []
    current: list[str] = []
    closing_quote = ""
    quote_pairs = {"「": "」", "“": "”", "『": "』", '"': '"'}
    for char in text:
        current.append(char)
        if closing_quote:
            if char == closing_quote:
                closing_quote = ""
            continue
        if char in quote_pairs:
            closing_quote = quote_pairs[char]
            continue
        if char in "。！？!?":
            sentence = "".join(current).strip()
            if sentence:
                sentences.append(sentence)
            current = []
    tail = "".join(current).strip()
    if tail:
        sentences.append(tail)
    return sentences


def theme_repair_issues(theme: Any, transcript: str, index: int) -> list[str]:
    if not isinstance(theme, dict):
        return [f"themes[{index}] 不是对象"]
    issues: list[str] = []
    sentences = prose_sentences(str(theme.get("deep", "")))
    if len(sentences) < 3:
        issues.append(f"themes[{index}].deep 需含“没说破”且至少 3 句")
    if not any(sentence.lstrip().startswith("没说破的：") for sentence in sentences):
        issues.append(f"themes[{index}].deep 必须有一句以“没说破的：”开头")
    normalized_transcript = normalize_verbatim(transcript)
    for sentence_index, sentence in enumerate(sentences[:-1]):
        fragments = quoted_fragments(sentence)
        if not fragments:
            issues.append(f"themes[{index}].deep 第 {sentence_index + 1} 个判断缺逐字原话")
        elif not any(normalize_verbatim(fragment) in normalized_transcript for fragment in fragments):
            issues.append(f"themes[{index}].deep 第 {sentence_index + 1} 个判断引文无法定位")
    if sentences and not any(verb in sentences[-1] for verb in ACTION_VERBS):
        issues.append(f"themes[{index}].deep 最后一句必须以可执行动作收尾")
    voices = theme.get("voices", [])
    if isinstance(voices, list):
        for voice_index, voice in enumerate(voices):
            if not isinstance(voice, dict) or voice.get("g") not in TONE_CLASSES:
                issues.append(f"themes[{index}].voices[{voice_index}].g 必须是 s/j/h")
    return issues


def collect_theme_repair_issues(content: dict[str, Any], transcript: str) -> dict[int, list[str]]:
    return {
        index: issues
        for index, theme in enumerate(content.get("themes", []))
        if (issues := theme_repair_issues(theme, transcript, index))
    }


def strip_unverified_deep_quotes(
    content: dict[str, Any], transcript: str, warnings: list[str]
) -> None:
    """Keep an unsupported judgment but remove punctuation that claims verbatim evidence."""
    normalized_transcript = normalize_verbatim(transcript)
    quote_pattern = re.compile(r"「([^」]{2,120})」|“([^”]{2,120})”|\"([^\"]{2,120})\"")
    for theme_index, theme in enumerate(content.get("themes", [])):
        if not isinstance(theme, dict) or not isinstance(theme.get("deep"), str):
            continue

        def replace(match: re.Match[str]) -> str:
            fragment = next((group for group in match.groups() if group is not None), "").strip()
            if normalize_verbatim(fragment) in normalized_transcript:
                return match.group(0)
            warnings.append(
                f"themes[{theme_index}].deep 引文无法定位，已去掉引用标记并按普通判断保留：{fragment[:36]}"
            )
            return fragment

        theme["deep"] = quote_pattern.sub(replace, theme["deep"])


def validate_theme_depth(
    content: dict[str, Any], transcript: str, warnings: list[str] | None = None
) -> dict[int, list[str]]:
    """Report deep-writing quality issues as soft warnings; never reject content."""
    warnings = warnings if warnings is not None else []
    issues = collect_theme_repair_issues(content, transcript)
    for messages in issues.values():
        for message in messages:
            warning = f"{message}，已按软规则接受，交由 judge 评分"
            if warning not in warnings:
                warnings.append(warning)
    return issues


def repair_themes_once(
    content: dict[str, Any],
    transcript: str,
    skeleton: dict[str, Any],
    chunks: list[dict[str, Any]],
    judge_feedback: str,
    api_key: str,
    model: str,
    api_url: str,
    timeout: float,
    budget: RunBudget | None = None,
) -> dict[str, Any]:
    """Repair only currently failing theme blocks with one additional model call."""
    issues = collect_theme_repair_issues(content, transcript)
    if not issues:
        return content
    indexed = evidence_by_id(chunks)
    selected_ids: set[str] = set(skeleton.get("quote_plan", []))
    for tone in skeleton.get("tone_plan", []):
        if isinstance(tone, dict) and isinstance(tone.get("evidence_id"), str):
            selected_ids.add(tone["evidence_id"])
    theme_plan = skeleton.get("theme_plan", [])
    for theme_index in issues:
        if theme_index < len(theme_plan) and isinstance(theme_plan[theme_index], dict):
            selected_ids.update(
                value
                for value in theme_plan[theme_index].get("evidence_ids", [])
                if isinstance(value, str)
            )
    selected_items = [
        copy.deepcopy(indexed[evidence_id])
        for evidence_id in sorted(selected_ids)
        if evidence_id in indexed
    ]
    selected_chunks = [{"evidence": selected_items}]
    feedback = judge_feedback.strip() or "\n".join(
        message for messages in issues.values() for message in messages
    )
    prompt = f"""
只局部重填下列失败主题幕，不得重写整份日报，也不得修改标题、时间线、金句墙或其他主题。
Judge 原话（逐字遵守）：
{feedback or DEFAULT_DEEP_JUDGE_FEEDBACK}

必须且只能输出：
{{"themes":[{{"index":1,"deep":"至少三句","voices":[{{"line":"L0123","a":"署名","g":"s|j|h","fragment":"连续原话","start":0,"end":12}}]}}]}}

局部补写规则（deep 质量项为软规则；quotes/voices 的逐字与语气仍是硬规则）：
- 只返回索引 {sorted(issues)}，每个索引恰好一次。
- deep 目标至少 3 句。除最后动作句外，能定位时每个判断句各用「」引一条下方原话；找不到时写不带引号的判断，不得伪造引文。
- 其中一句必须以“没说破的：”开头；最后一句必须以写、整理、验证、记录、检查等动作收尾。
- 每幕至少返回 1 条 voice 且每条必须带 g；j 是玩笑/自嘲，s 是认真判断，h 仅用于确有“玩笑壳、认真芯”两层的原话。
- 禁用：{'、'.join(ENGINEERING_REPLACEMENTS)}。不得写无引文支撑的武断结论。

当前失败与当前主题：
{json.dumps([{"index": index, "issues": messages, "theme": content["themes"][index]} for index, messages in issues.items()], ensure_ascii=False)}

相关证据：
{json.dumps(selected_chunks, ensure_ascii=False)}

可引用编号原文：
{numbered_reference_catalog(selected_chunks)}
""".strip()
    raw = deepseek_request(
        [
            {"role": "system", "content": load_prompt("ledger-fill-v3.md")},
            {"role": "user", "content": prompt},
        ],
        api_key,
        model,
        api_url,
        timeout,
        budget,
        "主题幕局部补写",
    )
    payload = extract_json(raw)
    if not isinstance(payload, dict) or set(payload) != {"themes"} or not isinstance(payload["themes"], list):
        raise ValidationFailure(["主题局部补写必须且只能输出 themes 数组"])
    returned = {
        item.get("index"): item
        for item in payload["themes"]
        if isinstance(item, dict) and isinstance(item.get("index"), int)
    }
    if len(returned) != len(payload["themes"]) or set(returned) != set(issues):
        raise ValidationFailure(
            [f"主题局部补写索引不匹配：需要 {sorted(issues)}，实际 {sorted(returned)}"]
        )
    line_index = transcript_line_index(transcript)
    allowed_line_ids = set(re.findall(r"(?m)^(L\d{4,})\b", numbered_reference_catalog(selected_chunks)))
    repaired = copy.deepcopy(content)
    for theme_index, item in returned.items():
        if set(item) != {"index", "deep", "voices"} or not isinstance(item.get("deep"), str):
            raise ValidationFailure([f"themes[{theme_index}] 局部补写必须且只能有 index/deep/voices"])
        if not isinstance(item.get("voices"), list) or not item["voices"]:
            raise ValidationFailure([f"themes[{theme_index}].voices 必须是非空数组"])
        voices: list[dict[str, str]] = []
        for voice_index, voice in enumerate(item["voices"]):
            if not isinstance(voice, dict) or voice.get("g") not in TONE_CLASSES:
                raise ValidationFailure([f"themes[{theme_index}].voices[{voice_index}].g 必须是 s/j/h"])
            resolved = resolve_line_reference(voice, line_index, allowed_line_ids)
            if resolved is None:
                raise ValidationFailure([f"themes[{theme_index}].voices[{voice_index}] 行号/片段无法定位"])
            source, exact = resolved
            voices.append({"a": source["a"], "v": exact, "g": str(voice["g"])})
        repaired["themes"][theme_index]["deep"] = item["deep"]
        repaired["themes"][theme_index]["voices"] = voices
    print(f"[repair] themes only: {','.join(str(index) for index in sorted(issues))}", file=sys.stderr)
    return repaired


def repair_themes_best_effort(
    content: dict[str, Any],
    transcript: str,
    skeleton: dict[str, Any],
    chunks: list[dict[str, Any]],
    judge_feedback: str,
    api_key: str,
    model: str,
    api_url: str,
    timeout: float,
    warnings: list[str],
    budget: RunBudget | None = None,
) -> dict[str, Any]:
    """Try each still-failing theme at most twice, then preserve it with warnings."""
    current = copy.deepcopy(content)
    retry_feedback = judge_feedback.strip() or DEFAULT_DEEP_JUDGE_FEEDBACK
    for attempt in range(1, MAX_THEME_REPAIR_ATTEMPTS + 1):
        issues = collect_theme_repair_issues(current, transcript)
        if not issues:
            break
        name = f"主题幕局部补写 {attempt}/{MAX_THEME_REPAIR_ATTEMPTS} themes={','.join(map(str, sorted(issues)))}"
        started = stage_start(name, budget) if budget else time.monotonic()
        try:
            current = repair_themes_once(
                current,
                transcript,
                skeleton,
                chunks,
                retry_feedback,
                api_key,
                model,
                api_url,
                timeout,
                budget,
            )
        except TimeBudgetExceeded:
            if budget:
                stage_done(name, started, budget, "timeout")
            raise
        except (LedgerError, json.JSONDecodeError, TypeError, ValueError) as exc:
            warnings.append(f"主题幕局部补写第 {attempt} 次失败：{exc}")
            retry_feedback = (
                f"{judge_feedback.strip() or DEFAULT_DEEP_JUDGE_FEEDBACK}\n"
                f"上一次局部补写具体错误：{exc}。只修这些主题，不要重写整份。"
            )
            if budget:
                stage_done(name, started, budget, "warning")
            continue
        if budget:
            stage_done(name, started, budget)
        remaining = collect_theme_repair_issues(current, transcript)
        retry_feedback = "\n".join(
            message for messages in remaining.values() for message in messages
        ) or retry_feedback

    strip_unverified_deep_quotes(current, transcript, warnings)
    validate_theme_depth(current, transcript, warnings)
    return current


def mark_partial(content: dict[str, Any], reason: str, warnings: list[str]) -> dict[str, Any]:
    partial = copy.deepcopy(content)
    partial["complete"] = False
    coverage = partial.get("coverage")
    if not isinstance(coverage, dict):
        coverage = {}
        partial["coverage"] = coverage
    note = str(coverage.get("note", "")).strip()
    marker = f"[partial] {reason}"
    coverage["note"] = f"{note} {marker}".strip()
    warnings.append(f"{reason}；已落地当前最佳产物并标记 partial/complete=false")
    return partial


def emergency_partial_content(
    date_value: str,
    material: dict[str, Any],
    previous: dict[str, Any],
    model: str,
    reason: str,
    warnings: list[str],
) -> dict[str, Any]:
    """Build a truthful eight-section fallback from local facts when no model candidate exists."""
    line_index = transcript_line_index(material["transcript"])
    safe_lines = [
        row
        for row in line_index.values()
        if 6 <= len(row["text"]) <= 180 and not is_sensitive(row["text"])
    ]
    quotes = [
        {"t": row["text"], "a": row["a"], "g": "s"}
        for row in safe_lines[: max(MIN_QUOTES, 6)]
    ]
    if len(quotes) < MIN_QUOTES:
        raise TimeBudgetExceeded(f"{reason}；transcript 中不足 {MIN_QUOTES} 条安全原文，无法构造 partial")
    first = safe_lines[0]
    raw_speakers = material["stats"].get("speakers", [])
    speakers = [
        (str(item[0]), int(item[1]))
        for item in raw_speakers
        if isinstance(item, list) and len(item) >= 2 and str(item[0]).strip()
    ]
    prev = previous_context(previous)
    partial = {
        "date": date_value,
        "stats_override": {
            "msgs": int(material["stats"].get("msgs", 0) or 0),
            "active": len(speakers),
        },
        "hours": copy.deepcopy(material["stats"].get("hours", {})),
        "events": [
            {
                "t": first["time"][-5:],
                "h": "当日材料已进入蒸馏",
                "d": "进程达到时长预算，先保存可逐字核验的部分产物，主题组织待重蒸。",
            }
        ],
        "themes": [
            {
                "h": "部分蒸馏 · 主题待重整",
                "when": f"{first['time'][-5:]}–截止",
                "body": "本期只完成了材料读取与安全原文保全，尚未完成完整主题判断。",
                "deep": "没说破的：当前不能把未完成的组织冒充结论。今天检查 partial 标记并重新运行蒸馏。",
                "voices": [{"a": first["a"], "v": first["text"], "g": "s"}],
                "thread_id": "partial-redistill",
                "thread_title": "等待重新蒸馏",
                "thread_status": "ongoing",
            }
        ],
        "tone_notes": [
            {"h": "认真 s", "body": "partial：认真语气尚未完成抽查。", "cls": "s"},
            {"h": "玩笑 j", "body": "partial：玩笑语气尚未完成抽查。", "cls": "j"},
            {"h": "半真 h", "body": "partial：半真语气尚未完成抽查。", "cls": "h"},
        ],
        "quotes": quotes,
        "growth": {
            "takeaways": ["本期产物未完成，只可使用已经逐字回查的原文。"],
            "todo": [{"phase": "今天", "items": ["检查 partial 标记并重新运行蒸馏"]}],
        },
        "members_focus": [
            {
                "name": name,
                "role": "当日发言者",
                "msgs": count,
                "tone": "s",
                "quote": "",
                "tags": ["待重蒸"],
            }
            for name, count in speakers[:8]
        ] or [{"name": first["a"], "role": "当日发言者", "msgs": 0, "tone": "s", "quote": first["text"], "tags": ["待重蒸"]}],
        "title": "部分蒸馏 · 等待重跑",
        "lead": "达到进程时长预算，先保留可逐字核验的原文与事实字段；本期不可视为完整日报。",
        "coverage": {"from": date_value, "to": date_value, "cutoff": "", "note": ""},
        "complete": False,
        "pulse": {"caption": "partial", "note": "24 小时心电图尚未完成解读。"},
        "insights": [],
        "glossary": [],
        "arsenal": [],
        "docket": [],
        "clashes": [],
        "newcomers": [],
        "members_total": int(prev.get("members") or 0),
        "essays_total": int(prev.get("essays") or 0),
        "essays_open": int(prev.get("essays_open") or 0),
        "distilled_by": distilled_by(model),
        "reviewed_by": "待 Sun 复核",
        "prompt_version": PROMPT_VERSION,
    }
    normalized = normalize_content(
        partial,
        material["transcript"],
        material["stats"],
        previous,
        date_value,
        model,
        warnings,
    )
    return mark_partial(normalized, reason, warnings)


def self_check(
    content: dict[str, Any], transcript: str, warnings: list[str] | None = None
) -> dict[str, Any]:
    warnings = warnings if warnings is not None else []
    errors: list[str] = []
    utterances = parse_utterances(transcript)
    quote_count = 0
    for index, quote in enumerate(content["quotes"]):
        if not quote_exists(quote["t"], quote["a"], utterances):
            errors.append(f"quotes[{index}] 未在 transcript 按署名逐字找到")
        elif is_sensitive(quote["t"]):
            errors.append(f"quotes[{index}] 含敏感内容")
        else:
            quote_count += 1

    voices_verified = 0
    for theme_index, theme in enumerate(content["themes"]):
        for voice_index, voice in enumerate(theme.get("voices", [])):
            if not quote_exists(str(voice.get("v", "")), str(voice.get("a", "")), utterances):
                errors.append(f"themes[{theme_index}].voices[{voice_index}] 未在 transcript 按署名逐字找到")
            elif is_sensitive(str(voice.get("v", ""))):
                errors.append(f"themes[{theme_index}].voices[{voice_index}] 含敏感内容")
            else:
                voices_verified += 1

    tone_checked = 0
    tone_words = {
        "j": ("玩笑", "自嘲", "段子", "复读", "哈哈"),
        "s": ("认真", "观点", "方法", "判断", "建议"),
        "h": ("半真", "玩笑壳", "认真芯", "字面", "两层"),
    }
    for index, note in enumerate(content["tone_notes"][:3]):
        fragments = quoted_fragments(note["body"])
        normalized_transcript = normalize_verbatim(transcript)
        if not fragments or not any(normalize_verbatim(fragment) in normalized_transcript for fragment in fragments):
            warnings.append(f"tone_notes[{index}] 缺 transcript 中可逐字回查的「证据」")
            continue
        if not any(word in note["body"] for word in tone_words[note["cls"]]):
            warnings.append(f"tone_notes[{index}] 未解释 {note['cls']} 语气判定")
            continue
        tone_checked += 1
    if tone_checked < 3:
        warnings.append("玩笑/语气标注逐字抽查少于 3 条")

    deep_count = sum(1 for theme in content["themes"] if "没说破的：" in theme["deep"])
    if deep_count < 3:
        warnings.append("少于 3 个 themes.deep 包含“没说破的：”")

    actions = [action for block in content["growth"]["todo"] for action in block["items"]]
    if not 3 <= len(actions) <= 5:
        warnings.append(f"行动清单清洗后为 {len(actions)} 条，建议 3–5 条")
    for index, action in enumerate(actions):
        if len(action) > 50:
            warnings.append(f"行动[{index}] 超过 50 字")
        if not any(verb in action for verb in ACTION_VERBS):
            warnings.append(f"行动[{index}] 缺可执行动词")
    if errors:
        raise ValidationFailure(errors)
    return {
        "quotes_verified": quote_count,
        "voices_verified": voices_verified,
        "tone_notes_spot_checked": tone_checked,
        "deep_unspoken_count": deep_count,
        "one_day_actions": len(actions),
    }


def dry_run_content(
    date_value: str, stats: dict[str, Any], previous: dict[str, Any], model: str
) -> dict[str, Any]:
    speakers = stats.get("speakers", []) if isinstance(stats.get("speakers"), list) else []
    speaker_counts = {str(item[0]): int(item[1]) for item in speakers if isinstance(item, list) and len(item) >= 2}
    hours = stats.get("hours", {}) if isinstance(stats.get("hours"), dict) else {}
    peak_hour, peak_count = max(hours.items(), key=lambda pair: pair[1], default=("00", 0))
    prev = previous_context(previous)
    members_total = int(prev.get("members") or 0)
    essays_total = int(prev.get("essays") or 0)
    essays_open = int(prev.get("essays_open") or 0)
    return {
        "date": date_value,
        "stats_override": {"msgs": int(stats.get("msgs", 0)), "active": len(speakers)},
        "hours": hours,
        "events": [
            {"t": "00:53", "h": "新工具之后的新问题", "d": "高博文把话题从“AI 替代什么”推向“问题是否还存在”。"},
            {"t": "01:47", "h": "大一新人登船", "d": "阿豪入群后先自嘲“小卡拉米”，随后交了长篇小作文。"},
            {"t": "11:28", "h": "知识库问题成为公共课题", "d": "Mr_Ghost 抛出企业知识库自循环难题，群内开始按不同实践视角拆解。"},
            {"t": "13:50", "h": "复读机警告升格为上下文纪律", "d": "从玩笑式执法落到群聊信息质量，筛选意识开始成形。"},
        ],
        "themes": [
            {
                "h": "第一幕 · 小作文与人机共著",
                "when": "00:04–04:52",
                "body": "多位新成员交出自述，同时直面 AI 代笔带来的罪过感与表达肌肉焦虑。",
                "deep": "原话「虽然是AI写的，也是你的积累啊」把讨论从工具拉回经历与责任。没说破的：另一句「科学的尽头是打牌，是玄学」提醒我们，群里的轻松外壳也在降低新人开口的门槛。今天重写一段 AI 文本，标出原始素材、模型补写和本人取舍。",
                "voices": [{"a": "孙务远", "v": "虽然是AI写的，也是你的积累啊", "g": "s"}],
                "thread_id": "essays",
                "thread_title": "小作文",
                "thread_status": "ongoing",
            },
            {
                "h": "第二幕 · 知识库远征",
                "when": "10:39–12:23",
                "body": "从 Tim 的长期协作难题、Mr_Ghost 的自循环诉求，到张对内容准确度的担心，知识库讨论从容量转向治理。",
                "deep": "原话「交流的过程突然自己因为别人说的本来不相干的一句话，来灵感了」说明不同实践者能彼此触发。没说破的：追问「当所有人都开始使用新工具之后，还有什么问题没有被重新提出」把知识库从容量问题推向判断问题。今天整理一个真实失败样本，写清它如何被发现和修正。",
                "voices": [
                    {
                        "a": "孙务远",
                        "v": "你看上面，很多人在研究知识库。然后你会发现 A 的问题，在 B 那里不是问题，B 的问题，在 A 那里不是问题",
                        "g": "s"
                    }
                ],
                "thread_id": "knowledge-base",
                "thread_title": "知识库远征",
                "thread_status": "ongoing",
            },
            {
                "h": "第三幕 · 上下文的公共卫生",
                "when": "13:29–14:05",
                "body": "“复读机警告”先以段子出现，随后被明确为上下文约束；群聊开始把信息密度当成共同责任。",
                "deep": "原话「群里少复读，会影响上下文」把群聊信息密度变成共同责任。没说破的：「要吹就吹大点」用自我拆穿的玩笑，让成员敢于暴露尚未成熟的目标。今天验证一段群聊，给消息标注新信息、复读或玩笑。",
                "voices": [{"a": "钟天炜", "v": "群里少复读，会影响上下文", "g": "s"}],
                "thread_id": "context-discipline",
                "thread_title": "上下文纪律",
                "thread_status": "ongoing",
            },
        ],
        "tone_notes": [
            {
                "h": "玩笑 · 打牌玄学",
                "body": "原话「科学的尽头是打牌，是玄学」接在深夜打牌话题后，是明显的玩笑和自嘲，不当作科学观点。",
                "cls": "j",
            },
            {
                "h": "认真 · 积累仍归于当事人",
                "body": "原话「虽然是AI写的，也是你的积累啊」直接回应代笔罪过感，是认真的作者权判断。",
                "cls": "s",
            },
            {
                "h": "半真 · 把牛吹大",
                "body": "原话「要吹就吹大点」是玩笑壳、认真芯：字面上自我拆穿，另一层在鼓励放大目标。",
                "cls": "h",
            },
        ],
        "quotes": [
            {"t": "科学的尽头是打牌，是玄学", "a": "wenxin5007", "g": "j"},
            {"t": "当所有人都开始使用新工具之后，还有什么问题没有被重新提出", "a": "高博文", "g": "s"},
            {"t": "虽然是AI写的，也是你的积累啊", "a": "孙务远", "g": "s"},
            {"t": "交流的过程突然自己因为别人说的本来不相干的一句话，来灵感了", "a": "孙务远", "g": "s"},
            {"t": "群里少复读，会影响上下文", "a": "钟天炜", "g": "s"},
            {"t": "要吹就吹大点", "a": "孙务远", "g": "h"},
        ],
        "growth": {
            "takeaways": [
                "AI 参与写作时，原始经历、取舍和责任仍需由当事人署名。",
                "知识库的核心不是容量，而是错误可被发现、修正并回流。",
                "群体上下文是共同资产，克制复读也是知识治理。",
            ],
            "todo": [
                {
                    "phase": "今天",
                    "items": [
                        "重写一段 AI 代笔文本，标出原始素材、模型补写和本人取舍",
                        "整理一个知识库失败样本，写清发现和修正路径",
                        "验证一段群聊，给消息标注新信息、复读或玩笑",
                        "记录今天一次被他人跨领域观点触发的灵感",
                    ],
                }
            ],
        },
        "members_focus": [
            {
                "name": "孙务远",
                "role": "群主 · 讨论编织者",
                "msgs": speaker_counts.get("孙务远", 0),
                "tone": "h",
                "quote": "要吹就吹大点",
                "tags": ["组织讨论", "知识库", "半真语气"],
            },
            {
                "name": "庄康发",
                "role": "活跃讨论者",
                "msgs": speaker_counts.get("庄康发", 0),
                "tone": "h",
                "quote": "",
                "tags": ["深夜在场", "接话发动机"],
            },
            {
                "name": "高博文",
                "role": "问题重构者",
                "msgs": speaker_counts.get("高博文", 0),
                "tone": "s",
                "quote": "当所有人都开始使用新工具之后，还有什么问题没有被重新提出",
                "tags": ["问题意识", "原理导向"],
            },
        ],
        "title": "第 002 批 · 从小作文到上下文纪律",
        "lead": "这一天，新人用小作文交出经历，老成员则把知识库、AI 代笔和群聊上下文变成了可共同检验的问题。真正的主线不是又出现了多少工具，而是人如何对判断和责任继续署名。",
        "coverage": {
            "from": date_value,
            "to": date_value,
            "cutoff": f"{date_value} 16:00",
            "note": "样例 transcript 共 514 行；数字以 stats.json 为准。",
        },
        "complete": True,
        "pulse": {
            "caption": f"{peak_hour} 时达到 {peak_count} 条的当日高峰；高峰与集中小作文和主题辩论重叠。",
            "note": "曲线只描述 stats.json 记录到的时段，空白小时不自动推断。",
        },
        "insights": [
            {
                "h": "一 · 署名权比代笔权更重要",
                "en": "AUTHORSHIP",
                "body": "AI 可以重组表达，但经历、取舍和责任仍来自当事人。<u>没说破的：这种罪过感其实是一个好的质量传感器，它在问“这句话还有没有人负责”。</u>",
            },
            {
                "h": "二 · 知识库是编辑制度",
                "en": "EDITORIAL MEMORY",
                "body": "多个实践者的问题互为答案。<u>没说破的：所谓进化循环，首先是一套决定什么进库、谁能更正、错误如何回流的权利结构。</u>",
            },
            {
                "h": "三 · 群聊也需要信息卫生",
                "en": "CONTEXT HYGIENE",
                "body": "复读机警告从段子变成了上下文规则。<u>没说破的：每一条无信息量回复都在消耗后来者的注意力，克制本身就是对共同记忆的维护。</u>",
            },
        ],
        "glossary": [
            {"term": "小作文 💡", "def": "新成员用经历、判断和未来方向完成的入群仪式。"},
            {"term": "复读机 😄", "def": "无新信息的跟贴；当日进一步被视为上下文污染。"},
            {"term": "金丹期 🔥", "def": "对知识库从搭建进入治理阶段的修真式自嘲。"},
        ],
        "arsenal": [
            {"h": "开源图表工具", "body": "lieflat-charts：https://github.com/larashero3-dotcom/lieflat-charts"},
            {"h": "知识库实践课题", "body": "企业知识库进化反馈自循环、经营数据决策和权限分级推送。"},
        ],
        "docket": [
            {
                "kind": "技术悬案",
                "h": "企业知识库进化反馈自循环",
                "d": "Mr_Ghost 提出后，当日形成了共同研究意向，但尚无验收过的实现。",
                "status": "open",
            }
        ],
        "clashes": [
            {
                "h": "对撞一 · AI 代笔与作者罪过感",
                "en": "GHOSTWRITING",
                "sides": "<b>庄康发</b>：感觉使用 AI 写有点罪过。<br><b>孙务远</b>：素材和积累仍属于当事人。",
                "verdict": "<u>裁决：能否署名不取决于是否用模型，而取决于经历、取舍和最终责任是否真的由本人承担。</u>",
            }
        ],
        "newcomers": [
            {"name": "阿豪", "note": "大一学生，入群后交出 AI 实践自述。", "t": "08-23 01:47", "by": "孙务远", "first_words": "我是个小卡拉米"},
            {"name": "Sean.Wang", "note": "澳门旅行与新媒体实践者。", "t": "08-23 02:44", "by": "孙务远", "first_words": "大家好，要向大家多多学习[胜利][胜利]"},
        ],
        "members_total": members_total,
        "essays_total": essays_total,
        "essays_open": essays_open,
        "distilled_by": distilled_by(model, dry_run=True),
        "reviewed_by": "待 Sun 复核",
        "prompt_version": PROMPT_VERSION,
    }


def assemble_real(
    date_value: str,
    material: dict[str, Any],
    previous: dict[str, Any],
    api_key: str,
    model: str,
    api_url: str,
    timeout: float,
    retries: int,
    chunk_size: int,
    judge_feedback: str = "",
    cache_dir: Path | None = None,
    budget: RunBudget | None = None,
) -> tuple[dict[str, Any], list[str], dict[str, Any], int]:
    budget = budget or RunBudget()
    extraction_started = stage_start("全文切片抽取", budget)
    chunks = extract_chunks(
        material["transcript"],
        date_value,
        api_key,
        model,
        api_url,
        timeout,
        retries,
        chunk_size,
        cache_dir,
        budget,
    )
    extraction_chunk_count = len(chunks)
    stage_done("全文切片抽取", extraction_started, budget)
    supplement_started = stage_start("金句数量检查与补抽", budget)
    chunks = supplement_quote_evidence(
        chunks,
        material["transcript"],
        material["stats"],
        judge_feedback,
        api_key,
        model,
        api_url,
        timeout,
        retries,
        cache_dir,
        budget,
    )
    stage_done("金句数量检查与补抽", supplement_started, budget)
    skeleton_messages = build_skeleton_messages(
        date_value,
        material["stats"],
        material["context"],
        previous,
        material["newcomers"],
        chunks,
        model,
        judge_feedback,
    )

    def parse_skeleton(raw: str) -> dict[str, Any]:
        return validate_skeleton(extract_json(raw), chunks)

    skeleton = call_with_repair(
        skeleton_messages,
        api_key=api_key,
        model=model,
        api_url=api_url,
        timeout=timeout,
        retries=retries,
        stage="八段骨架生成失败",
        parse=parse_skeleton,
        budget=budget,
    )
    print(
        f"[ok] assembly skeleton: {len(skeleton['theme_plan'])} themes / {len(skeleton['quote_plan'])} quotes",
        file=sys.stderr,
    )
    fill_messages = build_fill_messages(
        date_value,
        material["stats"],
        material["context"],
        previous,
        material["newcomers"],
        chunks,
        skeleton,
        model,
        judge_feedback,
    )
    success_warnings: list[str] = []
    success_checks: dict[str, Any] = {}

    def parse_final(raw: str) -> dict[str, Any]:
        nonlocal success_warnings, success_checks
        warnings: list[str] = []
        payload = resolve_content_references(extract_json(raw), material["transcript"], warnings)
        structural_quotes = planned_quotes(skeleton, chunks)
        if len(structural_quotes) < MIN_QUOTES:
            raise ValidationFailure(
                [f"quote_plan 按行号回填后仅 {len(structural_quotes)} 条，至少需要 {MIN_QUOTES} 条"]
            )
        payload["quotes"] = structural_quotes
        compact_length = len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        if compact_length > FINAL_OUTPUT_CHAR_LIMIT:
            warnings.append(
                f"最终 content.json 为 {compact_length} 字符，超过建议值 {FINAL_OUTPUT_CHAR_LIMIT}，已按软规则接受"
            )
        normalized = normalize_content(
            payload,
            material["transcript"],
            material["stats"],
            previous,
            date_value,
            model,
            warnings,
        )
        validate_content(normalized, date_value, allow_repairable_theme_issues=True)
        validate_expected_newcomers(normalized, material["newcomers"], warnings)
        self_check(normalized, material["transcript"], [])
        success_warnings = warnings
        return normalized

    result = call_with_repair(
        fill_messages,
        api_key=api_key,
        model=model,
        api_url=api_url,
        timeout=timeout,
        retries=retries,
        stage="八段成品填充失败",
        parse=parse_final,
        budget=budget,
    )
    repair_warnings: list[str] = []
    final_status = "ok"
    try:
        if collect_theme_repair_issues(result, material["transcript"]):
            result = repair_themes_best_effort(
                result,
                material["transcript"],
                skeleton,
                chunks,
                judge_feedback or DEFAULT_DEEP_JUDGE_FEEDBACK,
                api_key,
                model,
                api_url,
                timeout,
                repair_warnings,
                budget,
            )
        result = normalize_content(
            result,
            material["transcript"],
            material["stats"],
            previous,
            date_value,
            model,
            repair_warnings,
        )
        final_started = stage_start("最终硬规则校验", budget)
    except TimeBudgetExceeded as exc:
        result = mark_partial(result, str(exc), repair_warnings)
        final_started = time.monotonic()
        final_status = "partial"
    validate_content(result, date_value)
    validate_theme_depth(result, material["transcript"], repair_warnings)
    validate_expected_newcomers(result, material["newcomers"], repair_warnings)
    success_checks = self_check(result, material["transcript"], repair_warnings)
    stage_done("最终硬规则校验", final_started, budget, final_status)
    success_warnings.extend(repair_warnings)
    return result, success_warnings, success_checks, extraction_chunk_count


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("materials", type=Path, help="materials/YYYY-MM-DD 目录")
    parser.add_argument("--date", help="任务日期 YYYY-MM-DD")
    parser.add_argument("--output", type=Path, help="输出 content.json；默认写入材料目录")
    parser.add_argument("--ledger-dir", type=Path, help="站点 Ledger JSON 目录，用于跨日承接")
    parser.add_argument("--previous", type=Path, help="显式指定上一期 Ledger JSON")
    parser.add_argument("--dry-run", action="store_true", help="使用固定样例，不调用 DeepSeek")
    parser.add_argument("--validate-only", type=Path, help="只校验指定 content.json，不写文件")
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"))
    parser.add_argument("--api-url", default=os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions"))
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--chunk-cache", type=Path, help="成功切片持久缓存目录；默认 materials/.distill-cache")
    parser.add_argument("--judge-feedback", type=Path, help="上一轮 judge JSON，重蒸时带 suggestions")
    parser.add_argument("--usage-output", type=Path, help="写入本次 DeepSeek token 用量")
    parser.add_argument(
        "--max-runtime",
        type=float,
        default=DEFAULT_MAX_RUNTIME_SECONDS,
        help="进程总时长预算（秒），默认 1500；超时落地已有最佳产物并标 partial",
    )
    return parser.parse_args()


def default_ledger_dir() -> Path:
    repo = os.environ.get("XF_REPO")
    if repo:
        return Path(repo) / "site/content/ledgers"
    return Path(__file__).resolve().parents[2] / "site/content/ledgers"


def main() -> int:
    args = parse_args()
    if args.retries < 1 or args.chunk_size < 2_000:
        raise LedgerError("--retries 必须 >=1，--chunk-size 必须 >=2000")
    budget = RunBudget(args.max_runtime)
    material = load_materials(args.materials)
    date_value = infer_date(args.materials, material["transcript"], args.date)
    ledger_dir = args.ledger_dir or default_ledger_dir()
    previous, previous_path = load_previous(ledger_dir, date_value, args.previous)
    judge_feedback = ""
    if args.judge_feedback:
        feedback_payload = load_json(args.judge_feedback)
        if isinstance(feedback_payload, dict):
            feedback_items = feedback_payload.get("hard_fail", []) + feedback_payload.get("suggestions", [])
            judge_feedback = "\n".join(f"- {item}" for item in feedback_items if isinstance(item, str))
    output = args.output or args.materials / "content.json"

    if args.validate_only:
        started = stage_start("validate-only", budget)
        raw = load_json(args.validate_only)
        warnings: list[str] = []
        normalized = normalize_content(
            raw,
            material["transcript"],
            material["stats"],
            previous,
            date_value,
            args.model,
            warnings,
        )
        validate_content(normalized, date_value)
        strip_unverified_deep_quotes(normalized, material["transcript"], warnings)
        validate_theme_depth(normalized, material["transcript"], warnings)
        validate_expected_newcomers(normalized, material["newcomers"], warnings)
        checks = self_check(normalized, material["transcript"], warnings)
        stage_done("validate-only", started, budget)
        print(json.dumps({"valid": True, "warnings": warnings, "self_check": checks}, ensure_ascii=False))
        return 0

    if args.dry_run:
        started = stage_start("dry-run 生成与校验", budget)
        raw = dry_run_content(date_value, material["stats"], previous, args.model)
        warnings = []
        content = normalize_content(
            raw,
            material["transcript"],
            material["stats"],
            previous,
            date_value,
            args.model,
            warnings,
        )
        # Preserve an unmistakable dry-run marker after system-field locking.
        content["distilled_by"] = distilled_by(args.model, dry_run=True)
        validate_content(content, date_value)
        strip_unverified_deep_quotes(content, material["transcript"], warnings)
        validate_theme_depth(content, material["transcript"], warnings)
        validate_expected_newcomers(content, material["newcomers"], warnings)
        checks = self_check(content, material["transcript"], warnings)
        chunks = len(chunk_transcript(numbered_transcript(redact_for_model(material["transcript"])), args.chunk_size))
        mode = "dry-run"
        stage_done("dry-run 生成与校验", started, budget)
    else:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise LedgerError("缺少 DEEPSEEK_API_KEY；本地验证请用 --dry-run")
        try:
            content, warnings, checks, chunks = assemble_real(
                date_value,
                material,
                previous,
                api_key,
                args.model,
                args.api_url,
                args.timeout,
                args.retries,
                args.chunk_size,
                judge_feedback,
                args.chunk_cache or args.materials / ".distill-cache",
                budget,
            )
            mode = "deepseek-partial" if content.get("complete") is False else "deepseek"
        except TimeBudgetExceeded as exc:
            warnings = []
            if output.is_file():
                try:
                    content = normalize_content(
                        load_json(output),
                        material["transcript"],
                        material["stats"],
                        previous,
                        date_value,
                        args.model,
                        warnings,
                    )
                    content = mark_partial(content, str(exc), warnings)
                except (LedgerError, OSError, TypeError, ValueError) as fallback_error:
                    warnings.append(f"已有候选不可复用：{fallback_error}")
                    content = emergency_partial_content(
                        date_value, material, previous, args.model, str(exc), warnings
                    )
            else:
                content = emergency_partial_content(
                    date_value, material, previous, args.model, str(exc), warnings
                )
            strip_unverified_deep_quotes(content, material["transcript"], warnings)
            validate_content(content, date_value)
            validate_theme_depth(content, material["transcript"], warnings)
            validate_expected_newcomers(content, material["newcomers"], warnings)
            checks = self_check(content, material["transcript"], warnings)
            chunks = len(chunk_transcript(numbered_transcript(redact_for_model(material["transcript"])), args.chunk_size))
            mode = "deepseek-partial"

    atomic_write_json(output, content)
    if args.usage_output:
        atomic_write_json(
            args.usage_output,
            {"prompt_version": PROMPT_VERSION, "model": args.model, "token_usage": TOKEN_USAGE},
        )
    for warning in warnings:
        print(f"[warn] {warning}", file=sys.stderr)
    print(
        json.dumps(
            {
                "date": date_value,
                "mode": mode,
                "partial": content.get("complete") is False,
                "transcript_chars": len(material["transcript"]),
                "chunks": chunks,
                "previous": previous_path or None,
                "warnings": warnings,
                "prompt_version": PROMPT_VERSION,
                "model": args.model if mode.startswith("deepseek") else None,
                "token_usage": TOKEN_USAGE,
                "self_check": checks,
                "output": str(output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LedgerError, OSError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(1)
