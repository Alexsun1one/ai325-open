#!/usr/bin/env python3
"""Hermes quality judge: deterministic gates first, optional DeepSeek review second."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any
from urllib import error as urlerror
from urllib import request


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
PROMPT_PATH = Path(os.environ.get("HERMES_PROMPTS_DIR", REPO_ROOT / "hermes/prompts")) / "judge-v1.md"
PROMPT_VERSION = "judge-v1"
TONE_CLASSES = {"s", "j", "h"}
ARSENAL_KINDS = {"提示词", "方法", "拆书", "工具", "论文", "文章", "案例"}
ENGINEERING_SLOP = ("口径", "治理产物", "端点", "静态", "渲染", "数据层", "接线", "缺口", "闭环", "赋能")
ACTION_PREFIXES = (
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
    "盘点",
    "体检",
    "给",
    "把",
    "用",
)
TRANSCRIPT_LINE = re.compile(r"^\[(?P<time>\d{2}-\d{2} \d{2}:\d{2})\]\s*(?P<author>[^:]+):\s*(?P<text>.*)$")
PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
SECRET_RE = re.compile(
    r"(?i)(?:password|passwd|secret|token|密码|口令|密钥)\s*[:=：]\s*[^\s,;，；]{4,}"
)
LONG_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9+/=_]{32,}(?![A-Za-z0-9])")


class JudgeError(Exception):
    pass


def load_json(path: Path | None, default: Any = None) -> Any:
    if not path:
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JudgeError(f"JSON 读取失败 {path}: {exc}") from exc


def atomic_write(path: Path, payload: Any) -> None:
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


def plain(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(value or ""))).strip()


def sentence_count(value: Any) -> int:
    return len([part for part in re.split(r"[。！？.!?]+", plain(value)) if part.strip()])


def all_text(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(all_text(item) for item in value.values())
    if isinstance(value, list):
        return "\n".join(all_text(item) for item in value)
    return str(value) if isinstance(value, (str, int, float)) else ""


def transcript_data(path: Path | None) -> tuple[str, dict[str, list[str]], list[str]]:
    if not path:
        return "", {}, []
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise JudgeError(f"transcript 读取失败 {path}: {exc}") from exc
    utterances: dict[str, list[str]] = {}
    lines = raw.splitlines()
    for line in lines:
        match = TRANSCRIPT_LINE.match(line)
        if match:
            utterances.setdefault(match.group("author").strip(), []).append(match.group("text").strip())
    return raw, utterances, lines


def privacy_hits(text: str) -> list[str]:
    scrubbed = re.sub(r"https?://\S+", "", text)
    hits: list[str] = []
    if PHONE_RE.search(scrubbed):
        hits.append("手机号形态")
    if ID_RE.search(scrubbed):
        hits.append("身份证形态")
    if SECRET_RE.search(scrubbed):
        hits.append("密码/密钥形态")
    if LONG_TOKEN_RE.search(scrubbed):
        hits.append("长令牌形态")
    return hits


def latest_previous(directory: Path | None, date_value: str) -> dict[str, Any]:
    if not directory or not directory.exists():
        return {}
    paths = sorted(path for path in directory.glob("*.json") if path.stem < date_value)
    payload = load_json(paths[-1], {}) if paths else {}
    return payload if isinstance(payload, dict) else {}


def source_newcomer_names(value: Any) -> set[str]:
    if isinstance(value, dict):
        rows = value.get("newcomers") or value.get("items") or [value]
    else:
        rows = value if isinstance(value, list) else []
    return {
        str(row.get("name") or row.get("nickname") or row.get("display_name")).strip()
        for row in rows
        if isinstance(row, dict) and (row.get("name") or row.get("nickname") or row.get("display_name"))
    }


def ledger_mechanical(
    artifact: dict[str, Any], transcript_path: Path | None, previous: dict[str, Any], newcomers_source: Any
) -> tuple[int, list[str], list[str], list[str], dict[str, Any], dict[str, Any]]:
    hard: list[str] = []
    soft: list[str] = []
    suggestions: list[str] = []
    raw_transcript, utterances, transcript_lines = transcript_data(transcript_path)

    sections = {
        "hero": isinstance(artifact.get("stats_override") or artifact.get("stats"), dict),
        "pulse": isinstance(artifact.get("hours"), dict) and bool(artifact.get("pulse")),
        "events": isinstance(artifact.get("events"), list) and bool(artifact.get("events")),
        "members": isinstance(artifact.get("members_focus"), list) and bool(artifact.get("members_focus")),
        "themes": isinstance(artifact.get("themes"), list) and bool(artifact.get("themes")),
        "tone": isinstance(artifact.get("tone_notes"), list) and bool(artifact.get("tone_notes")),
        "quotes": isinstance(artifact.get("quotes"), list) and bool(artifact.get("quotes")),
        "growth": isinstance(artifact.get("growth"), dict) and bool(artifact.get("growth")),
    }
    missing_sections = [name for name, present in sections.items() if not present]
    if missing_sections:
        hard.append(f"八段缺失：{', '.join(missing_sections)}")

    quotes = artifact.get("quotes", []) if isinstance(artifact.get("quotes"), list) else []
    if len(quotes) < 5:
        hard.append(f"金句少于 5 条：{len(quotes)}")
    quote_verified = 0
    quote_failures: list[int] = []
    for index, quote in enumerate(quotes):
        if not isinstance(quote, dict) or quote.get("g") not in TONE_CLASSES:
            hard.append(f"quotes[{index}] 缺 s/j/h 语气标记")
            continue
        text, author = str(quote.get("t", "")).strip(), str(quote.get("a", "")).strip()
        if transcript_path and (not text or text not in raw_transcript):
            quote_failures.append(index)
            continue
        if transcript_path and author in utterances and not any(text in message for message in utterances[author]):
            soft.append(f"quotes[{index}] 原文可找到，但署名需复核")
        quote_verified += 1
    if quote_failures:
        hard.append(f"金句未在 transcript 逐字定位：{quote_failures}")

    themes = artifact.get("themes", []) if isinstance(artifact.get("themes"), list) else []
    if len(themes) < 3:
        hard.append(f"themes 少于 3 幕：{len(themes)}")
    deep_pass = 0
    voices_total = 0
    voices_verified = 0
    for theme_index, theme in enumerate(themes):
        if not isinstance(theme, dict):
            hard.append(f"themes[{theme_index}] 不是对象")
            continue
        deep = str(theme.get("deep", ""))
        if "没说破" not in deep or sentence_count(deep) < 3:
            hard.append(f"themes[{theme_index}].deep 需含“没说破”且至少 3 句")
        else:
            deep_pass += 1
        voices = theme.get("voices", [])
        if isinstance(voices, list):
            for voice in voices:
                if not isinstance(voice, dict):
                    continue
                voices_total += 1
                value = str(voice.get("v", ""))
                if not transcript_path or (value and value in raw_transcript):
                    voices_verified += 1
                else:
                    hard.append(f"themes[{theme_index}] voice 未在 transcript 逐字定位")
                if not any(key in voice for key in ("g", "cls", "tone")):
                    soft.append(f"themes[{theme_index}] voice 无独立语气字段，仅能依赖 tone_notes 复核")

    tones = {
        note.get("cls")
        for note in artifact.get("tone_notes", [])
        if isinstance(note, dict) and note.get("cls") in TONE_CLASSES
    }
    if tones != TONE_CLASSES:
        hard.append("tone_notes 未覆盖 s/j/h 三档")

    growth = artifact.get("growth", {}) if isinstance(artifact.get("growth"), dict) else {}
    todo = growth.get("todo", []) if isinstance(growth.get("todo"), list) else []
    action_total = 0
    bad_actions: list[str] = []
    bad_phases: list[str] = []
    for block in todo:
        if not isinstance(block, dict):
            continue
        phase = str(block.get("phase", ""))
        if not any(expected in phase for expected in ("今天", "本周", "本月")):
            bad_phases.append(phase or "(空)")
        for action in block.get("items", []) if isinstance(block.get("items"), list) else []:
            action_total += 1
            text = plain(action)
            if len(text) > 40 or not text.startswith(ACTION_PREFIXES):
                bad_actions.append(text[:60])
    if not 3 <= action_total <= 12:
        hard.append(f"行动清单数量异常：{action_total}")
    if bad_phases:
        hard.append(f"行动阶段未标今天/本周/本月：{bad_phases}")
    if bad_actions:
        soft.append(f"{len(bad_actions)} 条 todo 未以动词开头或超过 40 字")
        suggestions.append("把 todo 改成动词开头、一天内可打勾、不超过 40 字的任务")

    full_text = all_text(artifact)
    slop_counts = {word: full_text.count(word) for word in ENGINEERING_SLOP if word in full_text}
    if slop_counts:
        soft.append("工程腔词命中：" + "、".join(f"{word}×{count}" for word, count in slop_counts.items()))
        suggestions.append("删掉“口径/治理产物/接线/闭环/赋能”等报表腔，换成具体的人、问题和动作")
    privacy = privacy_hits(full_text)
    if privacy:
        hard.append("成品命中隐私形态：" + "、".join(privacy))

    current_threads = {
        str(item.get("id") or item.get("thread_id"))
        for item in artifact.get("threads", []) + themes
        if isinstance(item, dict) and (item.get("id") or item.get("thread_id"))
    }
    previous_threads = {
        str(item.get("id"))
        for item in previous.get("threads", [])
        if isinstance(item, dict) and item.get("id")
    }
    overlap = current_threads & previous_threads
    if previous_threads and not overlap:
        hard.append("线索 id 承接率为 0，未接上一期 threads")

    expected_newcomers = source_newcomer_names(newcomers_source)
    actual_newcomers = source_newcomer_names(artifact.get("newcomers", []))
    missing_newcomers = expected_newcomers - actual_newcomers
    if missing_newcomers:
        hard.append("newcomers 缺卡：" + "、".join(sorted(missing_newcomers)))

    if quote_failures:
        suggestions.append("金句只从 transcript 逐字复制，不要润色标点或改写署名")
    if any("deep" in item for item in hard):
        suggestions.append("每幕 deep 用至少 3 条碎片推出“没说破的：”，然后落到一个动作")

    hard_penalty = min(60, 12 * len(hard))
    soft_penalty = min(25, 3 * len(soft) + min(10, sum(slop_counts.values())))
    score = max(0, 100 - hard_penalty - soft_penalty)
    metrics = {
        "sections": sum(sections.values()),
        "quotes": len(quotes),
        "quotes_verified": quote_verified,
        "themes": len(themes),
        "deep_pass": deep_pass,
        "tone_classes": sorted(tones),
        "voices": voices_total,
        "voices_verified": voices_verified,
        "actions": action_total,
        "threads": len(current_threads),
        "thread_overlap": len(overlap),
        "newcomers_expected": len(expected_newcomers),
        "newcomers_present": len(actual_newcomers),
    }
    llm_context = {
        "title": artifact.get("title"),
        "lead": artifact.get("lead"),
        "themes": themes,
        "tone_notes": artifact.get("tone_notes", []),
        "quotes": quotes[:10],
        "previous_threads": list(previous_threads),
        "current_threads": list(current_threads),
        "transcript_context": tone_contexts(artifact, transcript_lines),
    }
    return score, hard, soft, suggestions, metrics, llm_context


def tone_contexts(artifact: dict[str, Any], lines: list[str]) -> list[str]:
    needles: list[str] = []
    for note in artifact.get("tone_notes", []) if isinstance(artifact.get("tone_notes"), list) else []:
        if isinstance(note, dict):
            match = re.search(r"[「“\"]([^」”\"]{2,120})[」”\"]", plain(note.get("body")))
            if match:
                needles.append(match.group(1))
    for quote in artifact.get("quotes", []) if isinstance(artifact.get("quotes"), list) else []:
        if len(needles) >= 5:
            break
        if isinstance(quote, dict) and isinstance(quote.get("t"), str) and quote["t"] not in needles:
            needles.append(quote["t"])
    contexts: list[str] = []
    for needle in needles[:5]:
        for index, line in enumerate(lines):
            if needle in line:
                contexts.append("\n".join(lines[max(0, index - 2) : index + 3]))
                break
    return contexts


def candidate_urls(path: Path | None) -> set[str]:
    if not path or not path.exists():
        return set()
    urls: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JudgeError(f"候选集 JSONL 无效：{exc}") from exc
        if isinstance(row, dict) and isinstance(row.get("url"), str):
            urls.add(row["url"].rstrip("/"))
    return urls


def arsenal_mechanical(
    artifact: Any, candidates_path: Path | None, previous: dict[str, Any]
) -> tuple[int, list[str], list[str], list[str], dict[str, Any], dict[str, Any]]:
    hard: list[str] = []
    soft: list[str] = []
    suggestions: list[str] = []
    if not isinstance(artifact, list):
        return 0, ["arsenal 顶层必须是数组"], [], [], {"items": 0}, {"items": []}
    if not 8 <= len(artifact) <= 15:
        hard.append(f"arsenal 必须 8–15 条，当前 {len(artifact)}")
    urls = candidate_urls(candidates_path)
    previous_threads = {
        str(item.get("id"))
        for item in previous.get("threads", [])
        if isinstance(item, dict) and item.get("id")
    }
    source_hits = 0
    thread_items = 0
    thread_hits = 0
    for index, item in enumerate(artifact):
        if not isinstance(item, dict):
            hard.append(f"items[{index}] 必须是对象")
            continue
        if item.get("kind") not in ARSENAL_KINDS:
            hard.append(f"items[{index}].kind 不在枚举中")
        source = item.get("source")
        if not isinstance(source, dict):
            hard.append(f"items[{index}].source 必须是对象")
        else:
            url = str(source.get("url", "")).rstrip("/")
            sun = source.get("name") == "Sun 的沉淀" and not url
            if urls and not sun and url not in urls:
                hard.append(f"items[{index}].source.url 不在候选集")
            elif sun or not urls or url in urls:
                source_hits += 1
            if source.get("author") and item.get("by") == "Hermes":
                hard.append(f"items[{index}] 编造了候选未提供的作者")
        takeaways = item.get("takeaways")
        if not isinstance(takeaways, list) or not 3 <= len(takeaways) <= 5:
            hard.append(f"items[{index}].takeaways 必须 3–5 条")
        one_line = str(item.get("one_line", ""))
        if not one_line or len(one_line) > 40:
            soft.append(f"items[{index}].one_line 不在 1–40 字")
        why_sentences = sentence_count(item.get("why", ""))
        if why_sentences not in (2, 3):
            soft.append(f"items[{index}].why 不是 2–3 句")
        item_threads = item.get("threads", []) if isinstance(item.get("threads"), list) else []
        if item_threads:
            thread_items += 1
            if not previous_threads or set(item_threads) & previous_threads:
                thread_hits += 1
    full_text = all_text(artifact)
    slop = {word: full_text.count(word) for word in ENGINEERING_SLOP if word in full_text}
    if slop:
        soft.append("工程腔词命中：" + "、".join(f"{word}×{count}" for word, count in slop.items()))
    privacy = privacy_hits(full_text)
    if privacy:
        hard.append("arsenal 命中隐私形态：" + "、".join(privacy))
    hit_rate = (thread_hits / thread_items) if thread_items else 1.0
    if previous_threads and hit_rate < 0.5:
        soft.append(f"threads 命中率仅 {hit_rate:.0%}")
        suggestions.append("只在内容真正接上日报线索时填 threads，但既有线索 id 必须精确复用")
    if slop:
        suggestions.append("把军火库条目从工程报告腔改成“这能帮谁、今天怎么用”")
    score = max(0, 100 - min(60, 12 * len(hard)) - min(25, 3 * len(soft) + sum(slop.values())))
    metrics = {
        "items": len(artifact),
        "candidate_urls": len(urls),
        "source_hits": source_hits,
        "thread_items": thread_items,
        "thread_hits": thread_hits,
        "thread_hit_rate": round(hit_rate, 4),
    }
    context = {
        "items": [
            {
                "title": item.get("title"),
                "kind": item.get("kind"),
                "one_line": item.get("one_line"),
                "why": item.get("why"),
                "takeaways": item.get("takeaways"),
                "threads": item.get("threads"),
            }
            for item in artifact[:15]
            if isinstance(item, dict)
        ],
        "previous_threads": sorted(previous_threads),
    }
    return score, hard, soft, suggestions, metrics, context


def extract_json(content: str) -> dict[str, Any]:
    stripped = content.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        stripped = fence.group(1).strip()
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise JudgeError("judge 输出顶层必须是对象")
    return payload


def llm_judge(context: dict[str, Any], api_key: str, model: str, timeout: float) -> tuple[dict[str, Any], dict[str, int]]:
    try:
        system = PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise JudgeError(f"读取 judge prompt 失败：{exc}") from exc
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False, separators=(",", ":"))},
        ],
        "temperature": 0,
        "max_tokens": 2048,
        "response_format": {"type": "json_object"},
    }
    seed = os.environ.get("DEEPSEEK_SEED", "").strip()
    if seed:
        try:
            body["seed"] = int(seed)
        except ValueError as exc:
            raise JudgeError("DEEPSEEK_SEED 必须是整数") from exc
    req = request.Request(
        os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions"),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        raw = response_payload["choices"][0]["message"]["content"]
        judged = extract_json(raw)
    except (urlerror.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise JudgeError(f"DeepSeek judge 失败：{exc}") from exc
    expected = {"deep_score", "tone_score", "style_score", "continuity_score", "soft", "suggestions"}
    if set(judged) != expected:
        raise JudgeError("DeepSeek judge 字段不齐或有多余字段")
    for field in ("deep_score", "tone_score", "style_score", "continuity_score"):
        if not isinstance(judged[field], int) or not 0 <= judged[field] <= 100:
            raise JudgeError(f"DeepSeek judge.{field} 必须是 0–100 整数")
    if not isinstance(judged["soft"], list) or not isinstance(judged["suggestions"], list):
        raise JudgeError("DeepSeek judge.soft/suggestions 必须是数组")
    usage_raw = response_payload.get("usage", {}) if isinstance(response_payload, dict) else {}
    usage = {
        "prompt_tokens": int(usage_raw.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(usage_raw.get("completion_tokens", 0) or 0),
        "total_tokens": int(usage_raw.get("total_tokens", 0) or 0),
    }
    return judged, usage


def load_usage(paths: list[Path]) -> dict[str, int]:
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for path in paths:
        payload = load_json(path, {})
        if isinstance(payload, dict) and isinstance(payload.get("token_usage"), dict):
            payload = payload["token_usage"]
        if not isinstance(payload, dict):
            continue
        for key in total:
            total[key] += int(payload.get(key, 0) or 0)
    return total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--kind", choices=("ledger", "arsenal"), required=True)
    parser.add_argument("--transcript", type=Path)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--previous-dir", type=Path)
    parser.add_argument("--newcomers", type=Path)
    parser.add_argument("--date")
    parser.add_argument("--mechanical-only", action="store_true")
    parser.add_argument("--require-llm", action="store_true")
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_JUDGE_MODEL", os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")))
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--redistill-count", type=int, default=0)
    parser.add_argument("--artifact-prompt-version", default="unknown")
    parser.add_argument("--upstream-usage", type=Path, action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    artifact = load_json(args.artifact)
    date_value = args.date or (artifact.get("date") if isinstance(artifact, dict) else None) or dt.date.today().isoformat()
    previous = load_json(args.previous, {}) if args.previous else latest_previous(args.previous_dir, date_value)
    if not isinstance(previous, dict):
        previous = {}
    newcomers = load_json(args.newcomers, []) if args.newcomers and args.newcomers.exists() else []
    if args.kind == "ledger":
        if not isinstance(artifact, dict):
            raise JudgeError("ledger artifact 顶层必须是对象")
        mechanical, hard, soft, suggestions, metrics, llm_context = ledger_mechanical(
            artifact, args.transcript, previous, newcomers
        )
        artifact_prompt_version = str(
            artifact.get("prompt_version")
            or (artifact.get("credits", {}).get("prompt_version") if isinstance(artifact.get("credits"), dict) else "")
            or args.artifact_prompt_version
        )
    else:
        mechanical, hard, soft, suggestions, metrics, llm_context = arsenal_mechanical(
            artifact, args.candidates, previous
        )
        artifact_prompt_version = args.artifact_prompt_version

    llm_result: dict[str, Any] | None = None
    judge_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    judge_mode = "mechanical-only"
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not args.mechanical_only and api_key:
        try:
            llm_result, judge_usage = llm_judge(llm_context, api_key, args.model, args.timeout)
            judge_mode = "deepseek"
            soft.extend(str(item) for item in llm_result["soft"] if str(item).strip())
            suggestions.extend(str(item) for item in llm_result["suggestions"] if str(item).strip())
        except JudgeError as exc:
            if args.require_llm:
                hard.append(str(exc))
            else:
                soft.append(str(exc))
    elif args.require_llm:
        hard.append("DeepSeek judge 必需，但 DEEPSEEK_API_KEY 缺失")

    if llm_result:
        llm_score = round(
            sum(llm_result[field] for field in ("deep_score", "tone_score", "style_score", "continuity_score")) / 4
        )
        score = round(mechanical * 0.6 + llm_score * 0.4)
    else:
        llm_score = None
        score = mechanical
    hard = list(dict.fromkeys(hard))
    soft = list(dict.fromkeys(soft))
    suggestions = list(dict.fromkeys(suggestions))
    passed = not hard and score >= 70
    grade = "A" if passed and score >= 85 else "B" if passed else "F"
    upstream_usage = load_usage(args.upstream_usage)
    token_usage = {
        "judge": judge_usage,
        "upstream": upstream_usage,
        "prompt_tokens": judge_usage["prompt_tokens"] + upstream_usage["prompt_tokens"],
        "completion_tokens": judge_usage["completion_tokens"] + upstream_usage["completion_tokens"],
        "total_tokens": judge_usage["total_tokens"] + upstream_usage["total_tokens"],
    }
    result = {
        "date": date_value,
        "kind": args.kind,
        "artifact": str(args.artifact),
        "passed": passed,
        "score": score,
        "grade": grade,
        "hard_fail": hard,
        "soft": soft,
        "suggestions": suggestions,
        "mechanical_score": mechanical,
        "llm_score": llm_score,
        "judge_mode": judge_mode,
        "model": args.model if judge_mode == "deepseek" else None,
        "prompt_version": PROMPT_VERSION,
        "artifact_prompt_version": artifact_prompt_version,
        "redistill_count": args.redistill_count,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "token_usage": token_usage,
        "metrics": metrics,
        "llm_detail": llm_result,
    }
    if args.output:
        atomic_write(args.output, result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if passed else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (JudgeError, OSError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(1)
