"""Collect public RSS/Atom feeds into an independent external-knowledge document.

Feed content is untrusted data: it is parsed, cleaned to plain text and never
executed or rendered as HTML.  Idea of a curated feed list follows KKKKhazix/AIHOT (MIT).
"""
from __future__ import annotations

import gzip
import hashlib
import html
import io
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from xml.parsers import expat
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

SCHEMA_VERSION = 1
USER_AGENT = "ai325-external-sources/1.0 (+https://ai325.com)"
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_BYTES = 3_000_000
DEFAULT_MAX_ITEMS = 30
MAX_TITLE = 240
MAX_SUMMARY = 300
MAX_TAGS = 8
MAX_URL = 2_000
MAX_ERROR = 200
_TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|mc_cid|mc_eid|ref|ref_src)$", re.I)
_BLOCKS = re.compile(r"<(script|style)\b.*?</\1\s*>", re.I | re.S)
_TAGS = re.compile(r"<[^>]*>")
_CTRL = re.compile(r"[\x00-\x1f\x7f​-‏‪-‮⁠﻿]")
_SPACE = re.compile(r"\s+")
_ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SOURCE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
MIN_TIMEOUT, MAX_TIMEOUT = 1.0, 120.0
MIN_MAX_BYTES, MAX_MAX_BYTES = 1_000, 10_000_000
MIN_MAX_ITEMS, MAX_MAX_ITEMS = 1, 100
MAX_NAME = 120
MAX_TAG = 40


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean_text(value: Any, limit: int) -> str:
    """Unescape entities, drop markup/control characters, collapse whitespace."""
    text = value if isinstance(value, str) else ""
    for _ in range(2):  # second pass handles double-escaped markup (&lt;p&gt;)
        text = _TAGS.sub(" ", _BLOCKS.sub(" ", html.unescape(text)))
    text = _SPACE.sub(" ", _CTRL.sub(" ", text)).strip()
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _clean_tags(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return list(dict.fromkeys(t for t in (clean_text(v, MAX_TAG) for v in values) if t))[:MAX_TAGS]


def _is_iso_z(value: Any) -> bool:
    if not isinstance(value, str) or not _ISO_Z.fullmatch(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _plain(value: Any, limit: int, *, allow_empty: bool = False) -> bool:
    if not isinstance(value, str) or len(value) > limit:
        return False
    if not value:
        return allow_empty
    return _TAGS.search(value) is None and _CTRL.search(value) is None


def safe_http_url(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    url = value.strip()
    if not url or len(url) > MAX_URL or _CTRL.search(url) or "\\" in url or " " in url:
        return None
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        return None
    return url


def canonicalize_url(url: str) -> str:
    p = urlparse(url)
    query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _TRACKING.match(k)])
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", query, ""))


def parse_date(value: Any, now: datetime) -> str | None:
    """Return UTC ISO string, or None when missing, timezone-less, invalid or in the future."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    parsed: datetime | None = None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00").replace("z", "+00:00"))
        except ValueError:
            return None
    if parsed is None or parsed.tzinfo is None:
        return None
    if parsed > now + timedelta(days=1) or parsed.year < 1990:
        return None
    return _iso(parsed)


def _local(tag: Any) -> str:
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _child_text(node: ET.Element, *names: str) -> str:
    for child in node:
        if _local(child.tag) in names and (child.text or "").strip():
            return child.text or ""
    return ""


def _entry_link(node: ET.Element) -> str:
    for child in node:
        if _local(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        if href is not None:
            if child.attrib.get("rel", "alternate") == "alternate":
                return href
        elif (child.text or "").strip():
            return child.text or ""
    return ""


def _refuse_declarations(xml: bytes) -> None:
    """Reject DOCTYPE/ENTITY (entity-expansion attacks) before the tree parser sees the bytes."""
    def refuse(*_args: Any) -> None:
        raise ValueError("feed declares DOCTYPE/ENTITY")

    probe = expat.ParserCreate()
    probe.StartDoctypeDeclHandler = refuse
    probe.EntityDeclHandler = refuse
    try:
        probe.Parse(xml, True)
    except expat.ExpatError as exc:
        raise ValueError(f"invalid XML: {exc}") from None


def parse_feed(xml: bytes, source: dict[str, Any], fetched_at: datetime) -> list[dict[str, Any]]:
    """Parse RSS 2.0 / Atom bytes into item dicts. Raises ValueError on unsafe or invalid XML."""
    _refuse_declarations(xml)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError(f"invalid XML: {exc}") from None
    nodes = [n for n in root.iter() if _local(n.tag) in ("item", "entry")]
    if _local(root.tag) not in ("rss", "feed", "rdf"):
        raise ValueError("not an RSS/Atom feed")
    source_id = source["id"]
    items: list[dict[str, Any]] = []
    for node in nodes:
        url = safe_http_url(_entry_link(node).strip())
        title = clean_text(_child_text(node, "title"), MAX_TITLE)
        if not url or not title:
            continue
        summary = clean_text(_child_text(node, "description", "summary", "content", "encoded"), MAX_SUMMARY)
        categories = [clean_text(c.attrib.get("term") or c.text or "", 40) for c in node if _local(c.tag) in ("category", "subject")]
        tags = list(dict.fromkeys(t for t in [*(_clean_tags(source.get("tags", []))), *categories] if t))[:MAX_TAGS]
        canonical = canonicalize_url(url)
        items.append({
            "id": f"ext-{source_id}-{hashlib.sha256(canonical.encode()).hexdigest()[:12]}",
            "sourceId": source_id,
            "sourceName": source["name"],
            "url": url,
            "canonicalUrl": canonical,
            "title": title,
            "summary": summary,
            "tags": tags,
            "publishedAt": parse_date(_child_text(node, "pubdate", "published", "updated", "date"), fetched_at),
            "fetchedAt": _iso(fetched_at),
        })
    return items


class _HttpsRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        if urlparse(newurl).scheme != "https":
            raise urllib.error.URLError("redirect to non-https URL refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read_limited(stream: Any, max_bytes: int) -> bytes:
    data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError(f"response exceeds {max_bytes} bytes")
    return data


def fetch_feed(url: str, *, timeout: float = DEFAULT_TIMEOUT, max_bytes: int = DEFAULT_MAX_BYTES) -> bytes:
    if not safe_http_url(url):
        raise ValueError("unsafe feed URL")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, identity", "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9"})
    with urllib.request.build_opener(_HttpsRedirect).open(request, timeout=timeout) as response:
        body = _read_limited(response, max_bytes)
    if body[:2] == b"\x1f\x8b":
        with gzip.GzipFile(fileobj=io.BytesIO(body)) as unzipped:
            body = _read_limited(unzipped, max_bytes)
    return body


def _short_error(exc: BaseException) -> str:
    detail = getattr(exc, "reason", None) or exc
    return clean_text(f"{type(exc).__name__}: {detail}", MAX_ERROR)


def _sort_key(item: dict[str, Any]) -> tuple[int, str]:
    return (1 if item["publishedAt"] else 0, item["publishedAt"] or "")


def collect(config: dict[str, Any], previous: dict[str, Any] | None, now: datetime,
            fetcher: Callable[..., bytes] = fetch_feed) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fetch every configured source. A failing source keeps its previous items and is reported."""
    limits = validate_limits(config.get("limits", {}))
    timeout = float(limits["timeoutSeconds"])
    max_bytes = int(limits["maxBytes"])
    max_items = int(limits["maxItemsPerSource"])
    prev_sources = {s["id"]: s for s in (previous or {}).get("sources", [])}
    prev_items: dict[str, list[dict[str, Any]]] = {}
    for item in (previous or {}).get("items", []):
        prev_items.setdefault(item["sourceId"], []).append(item)
    sources: list[dict[str, Any]] = []
    per_source: list[list[dict[str, Any]]] = []
    failures: list[dict[str, Any]] = []
    fetched_now = _iso(now)
    prev_updated = (previous or {}).get("updatedAt")
    updated_at = prev_updated if _is_iso_z(prev_updated) else None
    for cfg in config["sources"]:
        old = prev_sources.get(cfg["id"], {})
        old_items = prev_items.get(cfg["id"], [])
        homepage = cfg.get("homepage")
        if not safe_http_url(homepage):
            raise ValueError(f"source {cfg['id']}: https homepage required")
        meta = {"id": cfg["id"], "name": cfg["name"], "feedUrl": cfg["feedUrl"], "homepage": homepage,
                "tags": _clean_tags(cfg.get("tags", [])), "lastAttemptAt": fetched_now}
        try:
            fresh = parse_feed(fetcher(cfg["feedUrl"], timeout=timeout, max_bytes=max_bytes), cfg, now)
            old_fetched = {i["id"]: i["fetchedAt"] for i in old_items}
            for item in fresh:
                item["fetchedAt"] = old_fetched.get(item["id"], item["fetchedAt"])
            fresh.sort(key=_sort_key, reverse=True)
            kept = fresh[:max_items]
            meta.update(status="ok", lastSuccessAt=fetched_now, lastError=None)
            updated_at = fetched_now
        except Exception as exc:  # noqa: BLE001 - any single-source failure must not lose other sources
            kept = old_items
            error = _short_error(exc)
            meta.update(status="failed", lastSuccessAt=old.get("lastSuccessAt"), lastError=error)
            failures.append({"sourceId": cfg["id"], "error": error})
        if cfg.get("articleHosts"):
            meta["articleHosts"] = cfg["articleHosts"]
        meta["itemCount"] = len(kept)
        sources.append(meta)
        per_source.append(kept)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in per_source:
        for item in group:
            if item["canonicalUrl"] not in seen:
                seen.add(item["canonicalUrl"])
                items.append(item)
    items.sort(key=lambda i: i["id"])
    items.sort(key=_sort_key, reverse=True)
    for meta in sources:
        meta["itemCount"] = sum(1 for i in items if i["sourceId"] == meta["id"])
    document = {"schemaVersion": SCHEMA_VERSION, "updatedAt": updated_at,
                "sources": sources, "items": items}
    return document, failures


def validate_limits(limits: Any) -> dict[str, Any]:
    if limits is None:
        limits = {}
    if not isinstance(limits, dict):
        raise ValueError("limits must be an object")
    timeout = limits.get("timeoutSeconds", DEFAULT_TIMEOUT)
    max_bytes = limits.get("maxBytes", DEFAULT_MAX_BYTES)
    max_items = limits.get("maxItemsPerSource", DEFAULT_MAX_ITEMS)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not (MIN_TIMEOUT <= float(timeout) <= MAX_TIMEOUT):
        raise ValueError(f"timeoutSeconds must be {MIN_TIMEOUT:g}-{MAX_TIMEOUT:g}")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not (MIN_MAX_BYTES <= max_bytes <= MAX_MAX_BYTES):
        raise ValueError(f"maxBytes must be {MIN_MAX_BYTES}-{MAX_MAX_BYTES}")
    if isinstance(max_items, bool) or not isinstance(max_items, int) or not (MIN_MAX_ITEMS <= max_items <= MAX_MAX_ITEMS):
        raise ValueError(f"maxItemsPerSource must be {MIN_MAX_ITEMS}-{MAX_MAX_ITEMS}")
    return {"timeoutSeconds": float(timeout), "maxBytes": max_bytes, "maxItemsPerSource": max_items}


def validate_article_hosts(hosts: Any) -> None:
    if not isinstance(hosts, list) or len(hosts) > 10 or any(not isinstance(h, str) or not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*\.[a-z]{2,}", h) for h in hosts):
        raise ValueError("articleHosts must be a bounded list of hostnames")


def validate_config(config: Any) -> None:
    if not isinstance(config, dict) or config.get("schemaVersion") != 1 or not isinstance(config.get("sources"), list) or not config["sources"]:
        raise ValueError("config must be {schemaVersion:1, sources:[...]}")
    if "limits" in config:
        validate_limits(config["limits"])
    ids: set[str] = set()
    for s in config["sources"]:
        if not isinstance(s, dict) or not _SOURCE_ID.fullmatch(str(s.get("id", ""))) or s["id"] in ids:
            raise ValueError("source id invalid or duplicated")
        ids.add(s["id"])
        if not _plain(s.get("name"), MAX_NAME) or not safe_http_url(s.get("feedUrl")) or not str(s["feedUrl"]).startswith("https://"):
            raise ValueError(f"source {s['id']}: name/https feedUrl required")
        if not safe_http_url(s.get("homepage")) or not str(s["homepage"]).startswith("https://"):
            raise ValueError(f"source {s['id']}: https homepage required")
        validate_article_hosts(s.get("articleHosts", []))
        if "tags" in s and not isinstance(s.get("tags"), list):
            raise ValueError(f"source {s['id']}: tags must be a list")


def validate_document(doc: Any) -> None:
    if not isinstance(doc, dict) or doc.get("schemaVersion") != 1 or not isinstance(doc.get("sources"), list) or not isinstance(doc.get("items"), list):
        raise ValueError("invalid external knowledge document")
    if doc.get("updatedAt") is not None and not _is_iso_z(doc.get("updatedAt")):
        raise ValueError("updatedAt must be ISO8601Z or null")
    source_ids: set[str] = set()
    for source in doc["sources"]:
        if not isinstance(source, dict):
            raise ValueError("invalid source")
        sid = source.get("id")
        if not isinstance(sid, str) or not _SOURCE_ID.fullmatch(sid) or sid in source_ids:
            raise ValueError(f"source id invalid or duplicated: {sid}")
        validate_article_hosts(source.get("articleHosts", []))
        source_ids.add(sid)
        if not _plain(source.get("name"), MAX_NAME):
            raise ValueError(f"source {sid}: invalid name")
        if not safe_http_url(source.get("feedUrl")) or not safe_http_url(source.get("homepage")):
            raise ValueError(f"source {sid}: unsafe feedUrl/homepage")
        if source.get("status") not in ("ok", "failed") or not _is_iso_z(source.get("lastAttemptAt")):
            raise ValueError(f"source {sid}: invalid status/lastAttemptAt")
        last_ok = source.get("lastSuccessAt")
        if last_ok is not None and not _is_iso_z(last_ok):
            raise ValueError(f"source {sid}: lastSuccessAt must be ISO8601Z or null")
        if source["status"] == "ok" and not _is_iso_z(last_ok):
            raise ValueError(f"source {sid}: ok source needs lastSuccessAt")
        err = source.get("lastError")
        if source["status"] == "failed":
            if not _plain(err, MAX_ERROR):
                raise ValueError(f"source {sid}: failed source needs plain lastError")
        elif err is not None:
            raise ValueError(f"source {sid}: ok source lastError must be null")
        if not isinstance(source.get("tags"), list) or len(source["tags"]) > MAX_TAGS or not all(_plain(t, MAX_TAG) for t in source["tags"]):
            raise ValueError(f"source {sid}: invalid tags")
        if not isinstance(source.get("itemCount"), int) or isinstance(source["itemCount"], bool) or source["itemCount"] < 0:
            raise ValueError(f"source {sid}: invalid itemCount")
    ids: set[str] = set()
    counts: dict[str, int] = {sid: 0 for sid in source_ids}
    for item in doc["items"]:
        if not isinstance(item, dict):
            raise ValueError("invalid item")
        for field in ("id", "sourceId", "sourceName", "url", "canonicalUrl", "title", "fetchedAt"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise ValueError(f"item missing {field}")
        sid = item["sourceId"]
        if sid not in source_ids:
            raise ValueError(f"item {item['id']}: unknown sourceId")
        if not _plain(item["title"], MAX_TITLE) or not _plain(item.get("summary"), MAX_SUMMARY, allow_empty=True) or not _plain(item["sourceName"], MAX_NAME):
            raise ValueError(f"item {item['id']}: unsafe title/summary/sourceName")
        if not safe_http_url(item["url"]) or not safe_http_url(item["canonicalUrl"]) or item["id"] in ids:
            raise ValueError(f"invalid item {item['id']}")
        if item["canonicalUrl"] != canonicalize_url(item["canonicalUrl"]):
            raise ValueError(f"item {item['id']}: canonicalUrl is not canonical")
        expected = f"ext-{sid}-{hashlib.sha256(item['canonicalUrl'].encode()).hexdigest()[:12]}"
        if item["id"] != expected:
            raise ValueError(f"item {item['id']}: id does not match canonicalUrl")
        if not isinstance(item.get("tags"), list) or len(item["tags"]) > MAX_TAGS or not all(_plain(t, MAX_TAG) for t in item["tags"]):
            raise ValueError(f"item {item['id']}: invalid tags")
        if item.get("publishedAt") is not None and not _is_iso_z(item.get("publishedAt")):
            raise ValueError("publishedAt must be ISO8601Z or null")
        if not _is_iso_z(item["fetchedAt"]):
            raise ValueError(f"item {item['id']}: invalid fetchedAt")
        ids.add(item["id"])
        counts[sid] += 1
    for source in doc["sources"]:
        if source["itemCount"] != counts[source["id"]]:
            raise ValueError(f"source {source['id']}: itemCount does not match items")


def to_discovery_items(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Map dated items to the frozen discovery shape. Undated items are never given a date."""
    out: list[dict[str, Any]] = []
    for item in doc["items"]:
        if not item.get("publishedAt"):
            continue
        summary = item["summary"] or "摘要请见原文"
        entry: dict[str, Any] = {
            "id": "resource:" + hashlib.sha256(("external:" + item["id"]).encode()).hexdigest()[:24],
            "kind": "resource",
            "title": item["title"],
            "summary": f"外部公开来源 · {item['sourceName']}：{summary}",
            "url": f"/sources/#{item['id']}",
            "date": item["publishedAt"][:10],
            "tags": list(dict.fromkeys(["外部来源", item["sourceName"], *item["tags"]])),
        }
        if item["url"].startswith("https://"):
            entry["sourceUrl"] = item["url"]
        out.append(entry)
    return out
