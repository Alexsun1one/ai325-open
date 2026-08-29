#!/usr/bin/env python3
"""Collect public knowledge sources into a normalized, deduplicated JSONL file."""

from __future__ import annotations

import argparse
import difflib
import email.utils
import html
import json
import os
import re
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests
import yaml
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


HERE = Path(__file__).resolve().parent
SHANGHAI = ZoneInfo("Asia/Shanghai")
REQUIRED_SOURCE_KEYS = {"name", "url", "kind", "lang", "parser"}
TRACKING_PARAMS = {"ref", "ref_src", "source", "spm", "via"}


class CollectionError(RuntimeError):
    """A source failed in a way that should be reported but not hide other sources."""


def today_cst() -> str:
    return datetime.now(SHANGHAI).date().isoformat()


def clean_text(value: Any, limit: int = 1600) -> str:
    if value is None:
        return ""
    raw = html.unescape(str(value))
    text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True) if "<" in raw else raw
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def canonical_url(value: str, base: str = "") -> str:
    absolute = urljoin(base, value.strip())
    parts = urlsplit(absolute)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    scheme = parts.scheme.lower()
    host = parts.hostname.lower() if parts.hostname else ""
    port = parts.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")
    query = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_PARAMS:
            continue
        query.append((key, val))
    return urlunsplit((scheme, netloc, path, urlencode(sorted(query)), ""))


def normalize_published(value: Any) -> str:
    raw = clean_text(value, 120)
    if not raw:
        return ""
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
        return parsed.date().isoformat()
    except (TypeError, ValueError, OverflowError):
        pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.date().isoformat()
    except ValueError:
        pass
    match = re.search(r"(?<!\d)(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", raw)
    if match:
        try:
            return datetime(*map(int, match.groups())).date().isoformat()
        except ValueError:
            return ""
    return ""


def build_session() -> requests.Session:
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Hermes-Arsenal/1.0 (+https://ai325.com; public-feed collector)",
            "Accept": "application/json, application/atom+xml, application/rss+xml, application/xml, text/xml, text/html;q=0.9, */*;q=0.5",
        }
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def fetch(session: requests.Session, url: str, timeout: float) -> requests.Response:
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CollectionError(str(exc)) from exc
    content_type = response.headers.get("content-type", "").lower()
    if "charset=" not in content_type and response.encoding and response.encoding.lower() in {"iso-8859-1", "latin-1"}:
        response.encoding = response.apparent_encoding
    return response


def candidate(source: dict[str, Any], title: Any, url: Any, published: Any = "", summary: Any = "") -> dict[str, str] | None:
    cleaned_title = clean_text(title, 300)
    cleaned_url = canonical_url(str(url or ""), str(source["url"]))
    if len(cleaned_title) < 4 or not cleaned_url:
        return None
    return {
        "title": cleaned_title,
        "url": cleaned_url,
        "source": str(source["name"]),
        "published": normalize_published(published),
        "summary_raw": clean_text(summary),
        "lang": str(source["lang"]),
    }


def parse_hn(response: requests.Response, source: dict[str, Any]) -> list[dict[str, str]]:
    payload = response.json()
    items = []
    for hit in payload.get("hits", []):
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID', '')}"
        summary = hit.get("story_text") or f"HN {hit.get('points', 0)} points · {hit.get('num_comments', 0)} comments"
        item = candidate(source, hit.get("title"), url, hit.get("created_at"), summary)
        if item:
            items.append(item)
    return items


def parse_github(response: requests.Response, source: dict[str, Any]) -> list[dict[str, str]]:
    soup = BeautifulSoup(response.text, "html.parser")
    items = []
    for row in soup.select("article.Box-row"):
        link = row.select_one("h2 a[href]")
        if not link:
            continue
        repo = re.sub(r"\s+", "", link.get_text(" ", strip=True))
        desc = row.select_one("p")
        item = candidate(source, repo, link.get("href"), "", desc.get_text(" ", strip=True) if desc else "")
        if item:
            items.append(item)
    return items


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def child_text(node: ET.Element, names: Iterable[str]) -> str:
    wanted = {name.lower() for name in names}
    for child in list(node):
        if local_name(child.tag) in wanted:
            if child.text and child.text.strip():
                return child.text.strip()
            if list(child):
                return " ".join(part.strip() for part in child.itertext() if part.strip())
    return ""


def feed_link(node: ET.Element) -> str:
    for child in list(node):
        if local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href", "").strip()
        rel = child.attrib.get("rel", "alternate")
        if href and rel in {"alternate", ""}:
            return href
        if child.text and child.text.strip():
            return child.text.strip()
    return child_text(node, ("id",))


def parse_feed(response: requests.Response, source: dict[str, Any]) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as exc:
        raise CollectionError(f"invalid XML: {exc}") from exc
    items = []
    for node in root.iter():
        if local_name(node.tag) not in {"item", "entry"}:
            continue
        item = candidate(
            source,
            child_text(node, ("title",)),
            feed_link(node),
            child_text(node, ("published", "updated", "pubdate", "date")),
            child_text(node, ("summary", "description", "content", "encoded")),
        )
        if item:
            items.append(item)
    return items


def parse_hf(response: requests.Response, source: dict[str, Any]) -> list[dict[str, str]]:
    payload = response.json()
    items = []
    if not isinstance(payload, list):
        raise CollectionError("Hugging Face response is not a list")
    for row in payload:
        paper = row.get("paper", row) if isinstance(row, dict) else {}
        paper_id = paper.get("id", "")
        url = f"https://huggingface.co/papers/{paper_id}" if paper_id else ""
        item = candidate(source, paper.get("title"), url, paper.get("publishedAt"), paper.get("summary"))
        if item:
            items.append(item)
    return items


def parse_html_links(response: requests.Response, source: dict[str, Any]) -> list[dict[str, str]]:
    soup = BeautifulSoup(response.text, "html.parser")
    include_pattern = str(source.get("include_url_regex", ""))
    matcher = re.compile(include_pattern) if include_pattern else None
    items = []
    seen = set()
    for link in soup.find_all("a", href=True):
        url = canonical_url(str(link.get("href", "")), str(source["url"]))
        title = clean_text(link.get_text(" ", strip=True), 300)
        if not url or url in seen or len(title) < 6:
            continue
        if matcher and not matcher.search(url):
            continue
        parent_text = clean_text(link.parent.get_text(" ", strip=True) if link.parent else "", 900)
        summary = parent_text if parent_text != title else ""
        item = candidate(source, title, url, parent_text, summary)
        if item:
            seen.add(url)
            items.append(item)
    return items


PARSERS: dict[str, Callable[[requests.Response, dict[str, Any]], list[dict[str, str]]]] = {
    "hn_algolia": parse_hn,
    "github_trending": parse_github,
    "feed": parse_feed,
    "hf_papers": parse_hf,
    "html_links": parse_html_links,
}


def load_sources(path: Path) -> list[dict[str, Any]]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SystemExit(f"无法读取 sources.yaml：{exc}") from exc
    sources = payload.get("sources") if isinstance(payload, dict) else None
    if not isinstance(sources, list) or not sources:
        raise SystemExit("sources.yaml 必须包含非空 sources 数组")
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise SystemExit(f"sources[{index}] 不是对象")
        missing = REQUIRED_SOURCE_KEYS - source.keys()
        if missing:
            raise SystemExit(f"sources[{index}] 缺字段：{', '.join(sorted(missing))}")
        if source["parser"] not in PARSERS:
            raise SystemExit(f"sources[{index}] parser 不支持：{source['parser']}")
    return sources


def keyword_match(item: dict[str, str], keywords: list[Any]) -> bool:
    if not keywords:
        return True
    haystack = f"{item['title']} {item['summary_raw']}".casefold()
    return any(str(keyword).casefold() in haystack for keyword in keywords)


def title_key(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title).casefold()
    return "".join(char for char in normalized if char.isalnum())


def titles_near(left: str, right: str) -> bool:
    if left == right:
        return True
    if min(len(left), len(right)) < 12:
        return False
    ratio = difflib.SequenceMatcher(None, left, right, autojunk=False).ratio()
    return ratio >= 0.9


def deduplicate(items: Iterable[dict[str, str]], limit: int) -> list[dict[str, str]]:
    # Round-robin sources before applying the global cap. Otherwise early, high-volume
    # feeds can crowd every Chinese or independent source out of the daily file.
    groups: dict[str, list[dict[str, str]]] = {}
    for item in items:
        groups.setdefault(item["source"], []).append(item)
    positions = {source: 0 for source in groups}
    output: list[dict[str, str]] = []
    urls: set[str] = set()
    title_keys: list[str] = []
    while len(output) < limit:
        added_this_round = False
        remaining = False
        for source, source_items in groups.items():
            position = positions[source]
            while position < len(source_items):
                remaining = True
                item = source_items[position]
                position += 1
                positions[source] = position
                url = item["url"]
                key = title_key(item["title"])
                if url in urls or any(titles_near(key, old) for old in title_keys):
                    continue
                urls.add(url)
                title_keys.append(key)
                output.append(item)
                added_this_round = True
                break
            if len(output) >= limit:
                break
        if not added_this_round or not remaining:
            break
    return output


def atomic_write_jsonl(path: Path, items: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for item in items:
                handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def source_attempts(source: dict[str, Any]) -> list[dict[str, Any]]:
    attempts = [source]
    fallbacks = source.get("fallbacks", [])
    if not isinstance(fallbacks, list):
        raise CollectionError("fallbacks 必须是数组")
    for fallback in fallbacks:
        if isinstance(fallback, str):
            fallback = {"url": fallback, "parser": "feed"}
        if not isinstance(fallback, dict) or not isinstance(fallback.get("url"), str):
            raise CollectionError("fallback 必须含 url")
        merged = {**source, **fallback}
        if merged.get("parser") not in PARSERS:
            raise CollectionError(f"fallback parser 不支持：{merged.get('parser')}")
        attempts.append(merged)
    return attempts


def collect(
    sources: list[dict[str, Any]], timeout: float, limit: int
) -> tuple[list[dict[str, str]], list[str], list[str]]:
    session = build_session()
    collected: list[dict[str, str]] = []
    failures: list[str] = []
    fallbacks_used: list[str] = []
    for source in sources:
        name = str(source["name"])
        attempt_errors: list[str] = []
        selected: list[dict[str, str]] = []
        try:
            attempts = source_attempts(source)
        except CollectionError as exc:
            attempts = []
            attempt_errors.append(str(exc))
        for attempt_index, attempt in enumerate(attempts):
            attempt_url = str(attempt["url"])
            try:
                response = fetch(session, attempt_url, float(attempt.get("timeout", timeout)))
                parser = PARSERS[str(attempt["parser"])]
                parsed = parser(response, attempt)
                filtered = [item for item in parsed if keyword_match(item, attempt.get("keywords", []))]
                source_limit = max(1, min(int(attempt.get("max_items", 20)), 50))
                selected = filtered[:source_limit]
                if not selected:
                    raise CollectionError(f"解析 {len(parsed)} 条，但关键词过滤后为 0")
                collected.extend(selected)
                route = "primary" if attempt_index == 0 else f"fallback#{attempt_index}"
                print(f"[ok] {name} via {route}: {len(selected)} / {len(parsed)}", file=sys.stderr)
                if attempt_index > 0:
                    fallbacks_used.append(f"{name}: {attempt_url}")
                break
            except (CollectionError, requests.RequestException, ValueError, KeyError, json.JSONDecodeError) as exc:
                attempt_errors.append(f"{attempt_url} -> {exc}")
                if attempt_index + 1 < len(attempts):
                    print(f"[warn] {name} 尝试失败，切备用：{attempt_errors[-1]}", file=sys.stderr)
        if not selected:
            reason = f"{name}: " + " | ".join(attempt_errors)
            failures.append(reason)
            print(f"[fail] {reason}", file=sys.stderr)
    return deduplicate(collected, limit), failures, fallbacks_used


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=today_cst(), help="输出日期，YYYY-MM-DD（默认上海当天）")
    parser.add_argument("--sources", type=Path, default=HERE / "sources.yaml")
    parser.add_argument("--output", type=Path, help="覆盖输出文件；默认 candidates/YYYY-MM-DD.jsonl")
    parser.add_argument("--limit", type=int, default=120, help="全局条数上限，最大 120")
    parser.add_argument("--timeout", type=float, default=18.0, help="单请求超时秒数")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        datetime.strptime(args.date, "%Y-%m-%d")
    except ValueError:
        print("--date 必须是 YYYY-MM-DD", file=sys.stderr)
        return 2
    limit = max(1, min(args.limit, 120))
    output = args.output or HERE / "candidates" / f"{args.date}.jsonl"
    sources = load_sources(args.sources)
    items, failures, fallbacks_used = collect(sources, args.timeout, limit)
    if not items:
        print("所有信源均未产出候选；保留已有文件，不覆盖", file=sys.stderr)
        return 1
    atomic_write_jsonl(output, items)
    print(
        json.dumps(
            {
                "date": args.date,
                "collected": len(items),
                "failed_sources": failures,
                "fallbacks_used": fallbacks_used,
                "output": str(output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
