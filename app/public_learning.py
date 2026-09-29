"""Anonymous, read-only discovery API backed only by the static public directory."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import threading
from email.utils import format_datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, urlparse
from xml.etree import ElementTree as ET

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

router = APIRouter()

_DIRECTORY_RELATIVE_PATH = Path("discover") / "directory.json"
_PUBLIC_BASE_URL = "https://ai325.com"
_KIND_VALUES = {"knowledge", "skill", "resource", "ledger"}
_ITEM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_MAX_ITEMS = 10_000
_MAX_TITLE = 240
_MAX_SUMMARY = 2_000
_MAX_TAGS = 24
_MAX_TAG = 80
_MAX_TOPIC_ID = 160
_MAX_SOURCE_URL = 2_000
_cache_lock = threading.Lock()
_cache_signature: tuple[int, int, int] | None = None
_cache_payload: dict[str, Any] | None = None


def _directory_path() -> Path:
    return Path(os.environ.get("XF_STATIC_DIR", "/app/static")) / _DIRECTORY_RELATIVE_PATH


def _bad_directory() -> HTTPException:
    # Do not expose a host path or malformed source content to anonymous clients.
    return HTTPException(status_code=503, detail="公开学习目录暂不可用")


def _string(value: Any, *, field: str, maximum: int, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    result = value.strip()
    if not result or len(result) > maximum or any(ord(char) < 32 for char in result):
        raise ValueError(f"{field} is invalid")
    return result


def _date(value: Any, *, field: str) -> dt.date:
    text = _string(value, field=field, maximum=10)
    try:
        return dt.date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{field} must be an ISO date") from error


def _updated_at(value: Any) -> dt.datetime:
    text = _string(value, field="updatedAt", maximum=64)
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("updatedAt must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError("updatedAt must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def _relative_url(value: Any) -> str:
    url = _string(value, field="url", maximum=2_000)
    parsed = urlparse(url)
    if not url.startswith("/") or url.startswith("//") or "\\" in url or parsed.scheme or parsed.netloc:
        raise ValueError("url must be a site-relative path")
    return url


def _source_url(value: Any) -> str | None:
    if value is None:
        return None
    url = _string(value, field="sourceUrl", maximum=_MAX_SOURCE_URL)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("sourceUrl must be an https URL")
    return url


def _normalize_item(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("item must be an object")
    item_id = _string(raw.get("id"), field="id", maximum=160)
    if not _ITEM_ID.fullmatch(item_id):
        raise ValueError("id is invalid")
    kind = raw.get("kind")
    if kind not in _KIND_VALUES:
        raise ValueError("kind is invalid")
    raw_tags = raw.get("tags")
    if not isinstance(raw_tags, list) or len(raw_tags) > _MAX_TAGS:
        raise ValueError("tags is invalid")
    tags = [_string(tag, field="tag", maximum=_MAX_TAG) for tag in raw_tags]
    if len(set(tags)) != len(tags):
        raise ValueError("tags must be unique")
    topic_id = _string(raw.get("topicId"), field="topicId", maximum=_MAX_TOPIC_ID, required=False)
    return {
        "id": item_id,
        "kind": kind,
        "title": _string(raw.get("title"), field="title", maximum=_MAX_TITLE),
        "summary": _string(raw.get("summary"), field="summary", maximum=_MAX_SUMMARY),
        "url": _relative_url(raw.get("url")),
        "date": _date(raw.get("date"), field="date").isoformat(),
        "tags": tags,
        "sourceUrl": _source_url(raw.get("sourceUrl")),
        "topicId": topic_id,
    }


def _normalize_directory(raw: Any, raw_bytes: bytes) -> dict[str, Any]:
    if not isinstance(raw, dict) or raw.get("schemaVersion") != 1:
        raise ValueError("invalid directory schema")
    updated_at = _updated_at(raw.get("updatedAt"))
    raw_items = raw.get("items")
    if not isinstance(raw_items, list) or len(raw_items) > _MAX_ITEMS:
        raise ValueError("items is invalid")
    items = [_normalize_item(item) for item in raw_items]
    if len({item["id"] for item in items}) != len(items):
        raise ValueError("ids must be unique")
    items.sort(key=lambda item: (item["date"], item["id"]), reverse=True)
    return {
        "schemaVersion": 1,
        "updatedAt": raw["updatedAt"],
        "updatedAtParsed": updated_at,
        "items": items,
        "etag": '"' + hashlib.sha256(raw_bytes).hexdigest() + '"',
    }


def _load_directory() -> dict[str, Any]:
    global _cache_payload, _cache_signature
    path = _directory_path()
    try:
        stat_before = path.stat()
        signature = (stat_before.st_ino, stat_before.st_mtime_ns, stat_before.st_size)
    except OSError as error:
        raise _bad_directory() from error
    with _cache_lock:
        if _cache_signature == signature and _cache_payload is not None:
            return _cache_payload
        try:
            raw_bytes = path.read_bytes()
            stat_after = path.stat()
            stable_signature = (stat_after.st_ino, stat_after.st_mtime_ns, stat_after.st_size)
            if stable_signature != signature:
                retry_signature = stable_signature
                raw_bytes = path.read_bytes()
                stat_after = path.stat()
                stable_signature = (stat_after.st_ino, stat_after.st_mtime_ns, stat_after.st_size)
                if stable_signature != retry_signature:
                    raise OSError("directory changed while being read")
            payload = _normalize_directory(json.loads(raw_bytes), raw_bytes)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            raise _bad_directory() from error
        _cache_signature = stable_signature
        _cache_payload = payload
        return payload


def _cache_headers(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "Cache-Control": "public, max-age=60, must-revalidate",
        "ETag": payload["etag"],
        "Last-Modified": format_datetime(payload["updatedAtParsed"], usegmt=True),
    }


def _not_modified(request: Request, payload: dict[str, Any], headers: dict[str, str]) -> Response | None:
    requested = request.headers.get("if-none-match", "")
    if requested and (requested.strip() == "*" or payload["etag"] in {tag.strip() for tag in requested.split(",")}):
        return Response(status_code=304, headers=headers)
    return None


def _json_response(request: Request, payload: dict[str, Any], body: dict[str, Any]) -> Response:
    headers = _cache_headers(payload)
    if response := _not_modified(request, payload, headers):
        return response
    return Response(
        content=json.dumps(body, ensure_ascii=False, separators=(",", ":")),
        media_type="application/json",
        headers=headers,
    )


def _matches(item: dict[str, Any], q: str | None, kind: str | None, topic: str | None, since: dt.date | None) -> bool:
    if kind and item["kind"] != kind:
        return False
    if topic and item["topicId"] != topic:
        return False
    if since and item["date"] < since.isoformat():
        return False
    if q:
        needle = q.casefold()
        haystack = " ".join([item["title"], item["summary"], *item["tags"]]).casefold()
        return needle in haystack
    return True


@router.get("/api/public/learning")
def public_learning(
    request: Request,
    q: str | None = Query(None, max_length=200),
    kind: Literal["knowledge", "skill", "resource", "ledger"] | None = None,
    topic: str | None = Query(None, max_length=_MAX_TOPIC_ID),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    since: dt.date | None = None,
) -> Response:
    payload = _load_directory()
    query = q.strip() if q else None
    topic_value = topic.strip() if topic else None
    matches = [item for item in payload["items"] if _matches(item, query, kind, topic_value, since)]
    page = matches[offset:offset + limit]
    next_offset = offset + len(page)
    return _json_response(request, payload, {
        "schemaVersion": 1,
        "updatedAt": payload["updatedAt"],
        "items": page,
        "total": len(matches),
        "has_more": next_offset < len(matches),
        "next_offset": next_offset if next_offset < len(matches) else None,
    })


@router.get("/api/public/learning/{item_id}")
def public_learning_detail(item_id: str, request: Request) -> Response:
    payload = _load_directory()
    item = next((entry for entry in payload["items"] if entry["id"] == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="公开学习条目不存在")
    return _json_response(request, payload, {"schemaVersion": 1, "updatedAt": payload["updatedAt"], "item": item})


@router.get("/feed/learning.xml")
def learning_feed(request: Request) -> Response:
    payload = _load_directory()
    knowledge = [item for item in payload["items"] if item["kind"] == "knowledge"][:50]
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "ai325 公开学习目录"
    ET.SubElement(channel, "link").text = _PUBLIC_BASE_URL + "/learn/"
    ET.SubElement(channel, "description").text = "仅知识条目；按日期最新 50 条，来源只提供链接与摘要，不提供全文。"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(payload["updatedAtParsed"], usegmt=True)
    for item in knowledge:
        entry = ET.SubElement(channel, "item")
        ET.SubElement(entry, "title").text = item["title"]
        ET.SubElement(entry, "link").text = _PUBLIC_BASE_URL + item["url"]
        ET.SubElement(entry, "guid", isPermaLink="false").text = f"learning:{item['id']}"
        ET.SubElement(entry, "description").text = item["summary"]
        ET.SubElement(entry, "pubDate").text = format_datetime(
            dt.datetime.combine(dt.date.fromisoformat(item["date"]), dt.time.min, tzinfo=dt.timezone.utc), usegmt=True
        )
        if item["sourceUrl"]:
            ET.SubElement(entry, "source", url=item["sourceUrl"]).text = "来源链接"
    headers = _cache_headers(payload)
    # feed 专属 Content-Type 提前挂 headers：304 命中也带 charset，旧客户端不沿用乱码类型
    headers["Content-Type"] = "application/rss+xml; charset=utf-8"
    # UTF-8 BOM：客户端把 feed 当 text/plain 探测时中文不乱码；XML 解析器容忍 BOM
    body = b"\xef\xbb\xbf" + ET.tostring(rss, encoding="utf-8", xml_declaration=True)
    # feed 独立 ETag=最终 body 哈希：与 JSON 目录 ETag 解耦，旧无-BOM缓存的目录 ETag 不再 304
    headers["ETag"] = f'"{hashlib.sha256(body).hexdigest()}"'
    requested = request.headers.get("if-none-match", "")
    if requested and (requested.strip() == "*" or headers["ETag"] in {tag.strip() for tag in requested.split(",")}):
        return Response(status_code=304, headers=headers)
    return Response(content=body, headers=headers)
