"""Offline tests for external RSS/Atom collection (no network)."""
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app import external_sources as ext

NOW = datetime(2026, 10, 7, 6, 0, tzinfo=timezone.utc)
SRC = {"id": "s1", "name": "示例源", "tags": ["官方博客"]}
CFG = {"schemaVersion": 1, "sources": [
    {"id": "a", "name": "Source A", "feedUrl": "https://a.example/feed", "homepage": "https://a.example/", "tags": ["甲"]},
    {"id": "b", "name": "Source B", "feedUrl": "https://b.example/feed", "homepage": "https://b.example/", "tags": ["乙"]},
]}


def rss(*items: str) -> bytes:
    return ("<?xml version='1.0'?><rss version='2.0'><channel><title>t</title>" + "".join(items) + "</channel></rss>").encode()


def item(title="Hello", link="https://a.example/p/1", date="Tue, 06 Oct 2026 10:00:00 GMT", desc="body", extra=""):
    d = f"<pubDate>{date}</pubDate>" if date else ""
    return f"<item><title>{title}</title><link>{link}</link>{d}<description>{desc}</description>{extra}</item>"


class ParseTests(unittest.TestCase):
    def test_rss_fields_and_clean_text(self):
        xml = rss(item(title="A &amp;amp; B &lt;b&gt;x&lt;/b&gt;", desc="&lt;p&gt;Hi &lt;script&gt;alert(1)&lt;/script&gt; there&lt;/p&gt;", extra="<category>Agents</category>"))
        [it] = ext.parse_feed(xml, SRC, NOW)
        self.assertEqual(it["title"], "A & B x")
        self.assertEqual(it["summary"], "Hi there")
        self.assertEqual(it["publishedAt"], "2026-10-06T10:00:00Z")
        self.assertEqual(it["tags"], ["官方博客", "Agents"])
        self.assertEqual((it["sourceId"], it["sourceName"], it["fetchedAt"]), ("s1", "示例源", "2026-10-07T06:00:00Z"))
        self.assertTrue(it["id"].startswith("ext-s1-"))

    def test_atom(self):
        xml = b"""<feed xmlns='http://www.w3.org/2005/Atom'><entry><title>T</title>
        <link rel='self' href='https://x.example/self'/><link rel='alternate' href='https://x.example/post?utm_source=a#frag'/>
        <updated>2026-10-05T01:02:03+08:00</updated><summary>S</summary><category term='ml'/></entry></feed>"""
        [it] = ext.parse_feed(xml, SRC, NOW)
        self.assertEqual(it["canonicalUrl"], "https://x.example/post")
        self.assertEqual(it["publishedAt"], "2026-10-04T17:02:03Z")
        self.assertIn("ml", it["tags"])

    def test_missing_or_bad_date_stays_null(self):
        xml = rss(item(date=""), item(link="https://a.example/2", date="not a date"),
                  item(link="https://a.example/3", date="Tue, 06 Oct 2026 10:00:00"),
                  item(link="https://a.example/4", date="Tue, 06 Oct 2030 10:00:00 GMT"))
        self.assertEqual([i["publishedAt"] for i in ext.parse_feed(xml, SRC, NOW)], [None] * 4)

    def test_unsafe_urls_dropped(self):
        bad = ["javascript:alert(1)", "file:///etc/passwd", "ftp://a.example/x", "https://u:p@a.example/x", "//a.example/x", "/relative", "https://a.example/a b", ""]
        xml = rss(*[item(link=u) for u in bad], item(title="ok", link="http://a.example/ok"))
        self.assertEqual([i["title"] for i in ext.parse_feed(xml, SRC, NOW)], ["ok"])

    def test_doctype_and_entities_refused(self):
        bomb = b"<?xml version='1.0'?><!DOCTYPE r [<!ENTITY a 'aaaa'><!ENTITY b '&a;&a;'>]><rss><channel><item><title>&b;</title><link>https://a.example/1</link></item></channel></rss>"
        with self.assertRaises(ValueError):
            ext.parse_feed(bomb, SRC, NOW)
        with self.assertRaises(ValueError):
            ext.parse_feed(b"<!-- <x --><!DOCTYPE r [<!ENTITY a 'b'>]><rss/>", SRC, NOW)

    def test_doctype_text_inside_item_body_is_fine(self):
        xml = rss(item(desc="<![CDATA[<!DOCTYPE html><p>page</p>]]>"))
        self.assertEqual(ext.parse_feed(xml, SRC, NOW)[0]["summary"], "page")

    def test_not_a_feed_and_garbage(self):
        for body in (b"<html><body/></html>", b"not xml", b""):
            with self.assertRaises(ValueError):
                ext.parse_feed(body, SRC, NOW)

    def test_response_size_limit(self):
        with self.assertRaises(ValueError):
            ext._read_limited(io.BytesIO(b"x" * 11), 10)
        self.assertEqual(ext._read_limited(io.BytesIO(b"x" * 10), 10), b"x" * 10)

    def test_fetch_rejects_unsafe_scheme(self):
        with self.assertRaises(ValueError):
            ext.fetch_feed("file:///etc/passwd")


class CollectTests(unittest.TestCase):
    def fetcher(self, feeds):
        def fetch(url, **_):
            value = feeds[url]
            if isinstance(value, Exception):
                raise value
            return value
        return fetch

    def test_dedup_across_sources_and_tracking_params(self):
        feeds = {"https://a.example/feed": rss(item(link="https://a.example/p/1?utm_source=x"), item(title="Two", link="https://a.example/p/2")),
                 "https://b.example/feed": rss(item(title="dup", link="https://A.example/p/1/#top"))}
        doc, failures = ext.collect(CFG, None, NOW, self.fetcher(feeds))
        self.assertEqual(failures, [])
        self.assertEqual(len(doc["items"]), 2)
        self.assertEqual({s["itemCount"] for s in doc["sources"]}, {2, 0})
        ext.validate_document(doc)

    def test_undated_sorted_last_and_never_today(self):
        feeds = {"https://a.example/feed": rss(item(title="nodate", link="https://a.example/n", date=""), item()), "https://b.example/feed": rss()}
        doc, _ = ext.collect(CFG, None, NOW, self.fetcher(feeds))
        self.assertEqual([i["title"] for i in doc["items"]], ["Hello", "nodate"])
        self.assertIsNone(doc["items"][1]["publishedAt"])

    def test_failure_keeps_previous_and_reports(self):
        ok = {"https://a.example/feed": rss(item()), "https://b.example/feed": rss(item(title="B1", link="https://b.example/1"))}
        first, _ = ext.collect(CFG, None, NOW, self.fetcher(ok))
        later = datetime(2026, 10, 8, tzinfo=timezone.utc)
        bad = {"https://a.example/feed": OSError("boom <script>"), "https://b.example/feed": rss(item(title="B2", link="https://b.example/2"))}
        second, failures = ext.collect(CFG, first, later, self.fetcher(bad))
        self.assertEqual([f["sourceId"] for f in failures], ["a"])
        a = next(s for s in second["sources"] if s["id"] == "a")
        self.assertEqual((a["status"], a["lastSuccessAt"], a["lastAttemptAt"]), ("failed", "2026-10-07T06:00:00Z", "2026-10-08T00:00:00Z"))
        self.assertIn("boom", a["lastError"])
        self.assertNotIn("<", a["lastError"])
        self.assertIn("Hello", [i["title"] for i in second["items"]])  # old items kept
        self.assertIn("B2", [i["title"] for i in second["items"]])
        self.assertEqual(second["updatedAt"], "2026-10-08T00:00:00Z")

    def test_first_fetch_time_preserved(self):
        feeds = {"https://a.example/feed": rss(item()), "https://b.example/feed": rss()}
        first, _ = ext.collect(CFG, None, NOW, self.fetcher(feeds))
        second, _ = ext.collect(CFG, first, datetime(2026, 10, 9, tzinfo=timezone.utc), self.fetcher(feeds))
        self.assertEqual(second["items"][0]["fetchedAt"], "2026-10-07T06:00:00Z")

    def test_all_fail_without_previous_yields_valid_empty_doc(self):
        feeds = {u["feedUrl"]: OSError("down") for u in CFG["sources"]}
        doc, failures = ext.collect(CFG, None, NOW, self.fetcher(feeds))
        self.assertEqual((len(failures), doc["items"]), (2, []))
        self.assertIsNone(doc["updatedAt"])
        self.assertTrue(all(s["lastSuccessAt"] is None for s in doc["sources"]))
        ext.validate_document(doc)

    def test_all_fail_keeps_previous_success_time(self):
        ok = {"https://a.example/feed": rss(item()), "https://b.example/feed": rss()}
        first, _ = ext.collect(CFG, None, NOW, self.fetcher(ok))
        later = datetime(2026, 10, 8, tzinfo=timezone.utc)
        down = {u["feedUrl"]: OSError("down") for u in CFG["sources"]}
        second, failures = ext.collect(CFG, first, later, self.fetcher(down))
        self.assertEqual(len(failures), 2)
        self.assertEqual(second["updatedAt"], first["updatedAt"])
        ext.validate_document(second)

    def test_config_validation(self):
        ext.validate_config(CFG)
        for bad in ({"schemaVersion": 1, "sources": []}, {"schemaVersion": 1, "sources": [{"id": "x", "name": "n", "feedUrl": "http://a.example/f"}]},
                    {"schemaVersion": 1, "sources": [CFG["sources"][0], CFG["sources"][0]]},
                    {"schemaVersion": 1, "sources": [{"id": "x", "name": "n", "feedUrl": "https://a.example/f"}]},
                    {"schemaVersion": 1, "limits": {"timeoutSeconds": -1}, "sources": CFG["sources"]}):
            with self.assertRaises(ValueError):
                ext.validate_config(bad)

    def test_validate_document_rejects_unsafe_and_inconsistent_fields(self):
        feeds = {"https://a.example/feed": rss(item()), "https://b.example/feed": rss()}
        doc, _ = ext.collect(CFG, None, NOW, self.fetcher(feeds))
        ext.validate_document(doc)
        broken = json.loads(json.dumps(doc))
        cases = [
            lambda d: d["items"][0].pop("canonicalUrl"),
            lambda d: d["items"][0].__setitem__("sourceId", "no-such-source"),
            lambda d: d["items"][0].__setitem__("title", "<script>x</script>"),
            lambda d: d["items"][0].__setitem__("publishedAt", "2026-10-06"),
            lambda d: d["sources"][0].__setitem__("homepage", "javascript:alert(1)"),
            lambda d: d["sources"][0].__setitem__("lastSuccessAt", "soon"),
            lambda d: d.__setitem__("updatedAt", NOW.strftime("%Y-%m-%d")),
        ]
        for mutate in cases:
            copy = json.loads(json.dumps(broken))
            mutate(copy)
            with self.assertRaises(ValueError):
                ext.validate_document(copy)


class MappingTests(unittest.TestCase):
    def doc(self):
        feeds = rss(item(), item(title="nodate", link="https://a.example/n", date=""), item(title="plain http", link="http://a.example/h", desc=""))
        doc, _ = ext.collect({"schemaVersion": 1, "sources": [CFG["sources"][0]]}, None, NOW, lambda *a, **k: feeds)
        return doc

    def test_discovery_contract(self):
        doc = self.doc()
        mapped = ext.to_discovery_items(doc)
        self.assertEqual(len(mapped), 2)  # undated excluded
        by_title = {m["title"]: m for m in mapped}
        hello = by_title["Hello"]
        src = next(i for i in doc["items"] if i["title"] == "Hello")
        self.assertEqual(hello["url"], f"/sources/#{src['id']}")
        self.assertTrue(hello["url"].startswith("/") and not hello["url"].startswith("//"))
        self.assertEqual(hello["sourceUrl"], "https://a.example/p/1")
        self.assertEqual(hello["date"], "2026-10-06")
        self.assertEqual(hello["kind"], "resource")
        self.assertIn("Source A", hello["summary"])
        self.assertEqual(hello["tags"][:2], ["外部来源", "Source A"])
        self.assertEqual(hello["id"], "resource:" + hashlib.sha256(("external:" + src["id"]).encode()).hexdigest()[:24])
        self.assertNotIn("sourceUrl", by_title["plain http"])
        self.assertIn("摘要请见原文", by_title["plain http"]["summary"])
        self.assertEqual(len({m["id"] for m in mapped}), 2)


class CliTests(unittest.TestCase):
    def load_cli(self):
        spec = importlib.util.spec_from_file_location("collect_cli", Path(__file__).resolve().parents[1] / "scripts/ops/collect_external_sources.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_partial_failure_exit_1_writes_atomically_and_keeps_old(self):
        cli = self.load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            conf, out = Path(tmp) / "c.json", Path(tmp) / "out" / "d.json"
            conf.write_text(json.dumps(CFG))
            feeds = {"https://a.example/feed": rss(item()), "https://b.example/feed": rss(item(title="B", link="https://b.example/1"))}
            fetch = lambda url, **_: feeds[url] if not isinstance(feeds[url], Exception) else (_ for _ in ()).throw(feeds[url])
            self.assertEqual(cli.main(["--config", str(conf), "--output", str(out)], fetch, NOW), 0)
            feeds["https://a.example/feed"] = OSError("down")
            self.assertEqual(cli.main(["--config", str(conf), "--output", str(out)], fetch, NOW), 1)
            doc = json.loads(out.read_text())
            self.assertEqual({s["id"]: s["status"] for s in doc["sources"]}, {"a": "failed", "b": "ok"})
            self.assertEqual(len(doc["items"]), 2)
            self.assertEqual([p.name for p in out.parent.iterdir()], ["d.json"])  # no temp leftovers

    def test_dry_run_and_fatal(self):
        cli = self.load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            conf, out = Path(tmp) / "c.json", Path(tmp) / "d.json"
            self.assertEqual(cli.main(["--config", str(conf), "--output", str(out)]), 2)  # missing config
            conf.write_text(json.dumps(CFG))
            fetch = lambda url, **_: rss(item())
            self.assertEqual(cli.main(["--config", str(conf), "--output", str(out), "--dry-run"], fetch, NOW), 0)
            self.assertFalse(out.exists())
            out.write_text("{broken")
            self.assertEqual(cli.main(["--config", str(conf), "--output", str(out)], fetch, NOW), 2)
            self.assertEqual(out.read_text(), "{broken")  # untouched on fatal

    def test_committed_config_valid(self):
        ext.validate_config(json.loads((Path(__file__).resolve().parents[1] / "config/external-sources.json").read_text()))
        self.assertGreaterEqual(len(json.loads((Path(__file__).resolve().parents[1] / "config/external-sources.json").read_text())["sources"]), 3)

    def test_committed_document_valid(self):
        raw = json.loads((Path(__file__).resolve().parents[1] / "site/public/data/external-knowledge.json").read_text())
        ext.validate_document(raw)
        self.assertEqual(len(raw["sources"]), 5)
        self.assertEqual(len(raw["items"]), 120)

    def test_cli_rejects_bad_timeout_and_max_bytes(self):
        cli = self.load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            conf, out = Path(tmp) / "c.json", Path(tmp) / "d.json"
            conf.write_text(json.dumps(CFG))
            self.assertEqual(cli.main(["--config", str(conf), "--output", str(out), "--timeout", "-1"]), 2)
            self.assertFalse(out.exists())
            self.assertEqual(cli.main(["--config", str(conf), "--output", str(out), "--max-bytes", "0"]), 2)
            self.assertFalse(out.exists())
            self.assertEqual(cli.main(["--config", str(conf), "--output", str(out), "--timeout", "0"]), 2)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
