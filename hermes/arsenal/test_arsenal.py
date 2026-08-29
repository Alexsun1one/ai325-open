from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from collect import CollectionError, canonical_url, collect, deduplicate, source_attempts
from distill import (
    DRY_BY,
    LEGACY_DRY_BY,
    REAL_BY,
    ValidationFailure,
    call_deepseek,
    dry_run_entries,
    extract_json,
    load_threads,
    normalize_system_fields,
    sentence_count,
    validate_entries,
)


THREADS = [
    {"id": "brain-swap", "title": "换脑工程", "theme": "第一幕", "status": "ongoing"},
    {"id": "knowledge-base", "title": "知识库远征", "theme": "第二幕", "status": "ongoing"},
    {"id": "ai-economics", "title": "AI 经济学", "theme": "第四幕", "status": "ongoing"},
]


class CollectTests(unittest.TestCase):
    def test_source_attempts_preserve_identity_and_override_transport(self) -> None:
        source = {
            "name": "中文源",
            "url": "https://origin.example/",
            "kind": "html",
            "lang": "zh",
            "parser": "html_links",
            "fallbacks": [{"url": "https://mirror.example/feed", "parser": "feed"}],
        }
        attempts = source_attempts(source)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[1]["name"], "中文源")
        self.assertEqual(attempts[1]["parser"], "feed")

    def test_collect_uses_feed_fallback_without_failing_batch(self) -> None:
        source = {
            "name": "中文源",
            "url": "https://origin.example/",
            "kind": "html",
            "lang": "zh",
            "parser": "html_links",
            "fallbacks": [{"url": "https://mirror.example/feed", "parser": "feed"}],
        }

        class FakeResponse:
            content = b"<rss><channel><item><title>Fallback AI item</title><link>https://article.example/1</link></item></channel></rss>"
            text = content.decode()

        def fake_fetch(_session, url, _timeout):
            if url == source["url"]:
                raise CollectionError("origin timeout")
            return FakeResponse()

        with patch("collect.build_session", return_value=object()), patch("collect.fetch", side_effect=fake_fetch):
            items, failures, fallbacks = collect([source], 1, 120)
        self.assertEqual(len(items), 1)
        self.assertEqual(failures, [])
        self.assertEqual(fallbacks, ["中文源: https://mirror.example/feed"])

    def test_canonical_url_removes_tracking_and_fragment(self) -> None:
        self.assertEqual(
            canonical_url("HTTPS://Example.COM/a/?utm_source=x&b=2&a=1#part"),
            "https://example.com/a?a=1&b=2",
        )

    def test_near_duplicate_title_is_removed(self) -> None:
        base = {
            "source": "x",
            "published": "",
            "summary_raw": "",
            "lang": "en",
        }
        items = [
            {**base, "title": "Building Reliable Agents in Production", "url": "https://a.example/1"},
            {**base, "title": "Building reliable agents in production!", "url": "https://b.example/2"},
        ]
        self.assertEqual(len(deduplicate(items, 120)), 1)

    def test_global_limit_round_robins_sources(self) -> None:
        titles = {
            "english": ["Reliable agent evaluation", "Context windows in practice", "Tool calling safety", "Retrieval system design"],
            "中文": ["知识库切片应该保留上下文", "销售流程如何形成判断样本", "智能体委托需要验收证据", "小作文怎样沉淀个人经验"],
        }
        items = []
        for source in ("english", "中文"):
            for index in range(4):
                items.append(
                    {
                        "source": source,
                        "published": "",
                        "summary_raw": "",
                        "lang": "zh" if source == "中文" else "en",
                        "title": titles[source][index],
                        "url": f"https://{index}.{source == '中文'}.example/item",
                    }
                )
        selected = deduplicate(items, 4)
        self.assertEqual([item["source"] for item in selected], ["english", "中文", "english", "中文"])


class DistillTests(unittest.TestCase):
    def test_fixed_dry_run_passes_schema(self) -> None:
        entries = dry_run_entries("2026-08-23", THREADS)
        self.assertEqual(len(entries), 8)
        self.assertTrue(all(item["by"] == DRY_BY for item in entries))

    def test_soft_rules_are_normalized_with_warnings(self) -> None:
        entries = dry_run_entries("2026-08-23", THREADS)
        entries[0]["one_line"] = "字" * 41
        entries[0]["why"] = "只有一句判断"
        entries[0]["quote"] = "没有逐字证据的引语"
        entries[0]["threads"] = ["not-real"]
        warnings: list[str] = []
        normalize_system_fields(entries, "2026-08-23", [], THREADS, warnings)
        self.assertEqual(len(entries[0]["one_line"]), 40)
        self.assertEqual(sentence_count(entries[0]["why"]), 2)
        self.assertTrue(entries[0]["why"].endswith("。"))
        self.assertEqual(entries[0]["quote"], "")
        self.assertEqual(entries[0]["threads"], [])
        self.assertTrue(any("one_line" in item for item in warnings))
        self.assertTrue(any("why" in item for item in warnings))
        self.assertTrue(any("quote" in item for item in warnings))

    def test_takeaways_count_remains_a_hard_error(self) -> None:
        entries = dry_run_entries("2026-08-23", THREADS)
        entries[0]["takeaways"] = ["太少", "仍然太少"]
        with self.assertRaises(ValidationFailure):
            validate_entries(
                entries,
                [],
                THREADS,
                "2026-08-23",
                enforce_candidate_urls=False,
                expected_by=DRY_BY,
            )

    def test_legacy_hermes_by_remains_valid(self) -> None:
        entries = dry_run_entries("2026-08-23", THREADS)
        for entry in entries:
            entry["by"] = LEGACY_DRY_BY
        validate_entries(
            entries,
            [],
            THREADS,
            "2026-08-23",
            enforce_candidate_urls=False,
            expected_by=LEGACY_DRY_BY,
        )

    def test_system_fields_are_locked_to_candidate_truth(self) -> None:
        entries = dry_run_entries("2026-08-23", THREADS)
        entries[0]["source"] = {
            "name": "invented",
            "url": "https://example.com/item?utm_source=noise",
            "author": "invented",
            "published_at": "2099-01-01",
        }
        candidates = [
            {
                "title": "real",
                "url": "https://example.com/item",
                "source": "real source",
                "published": "2026-08-20",
                "summary_raw": "",
                "lang": "en",
            }
        ]
        warnings: list[str] = []
        normalized = normalize_system_fields(entries, "2026-08-23", candidates, THREADS, warnings)
        self.assertEqual(normalized[0]["by"], REAL_BY)
        self.assertEqual(
            normalized[0]["source"],
            {"name": "real source", "url": "https://example.com/item", "author": "", "published_at": "2026-08-20"},
        )
        self.assertTrue(normalized[0]["id"].endswith("-202608"))
        self.assertTrue(any("author" in item for item in warnings))

    def test_retry_keeps_previous_output_and_feeds_back_hard_errors(self) -> None:
        candidate = {
            "title": "Real candidate",
            "url": "https://example.com/real",
            "source": "Real Source",
            "published": "2026-08-20",
            "summary_raw": "A real summary",
            "lang": "en",
        }
        entry = dry_run_entries("2026-08-23", THREADS)[0]
        entry["source"] = {"name": "Real Source", "url": candidate["url"], "author": "", "published_at": candidate["published"]}
        bad = json.loads(json.dumps(entry))
        bad["takeaways"] = ["one", "two"]

        class FakeResponse:
            def __init__(self, content: str):
                self.content = content

            def raise_for_status(self) -> None:
                return None

            def json(self):
                return {"choices": [{"message": {"content": self.content}}]}

        with patch(
            "distill.requests.post",
            side_effect=[FakeResponse(json.dumps({"items": [bad]})), FakeResponse(json.dumps({"items": [entry]}))],
        ) as post:
            result, warnings = call_deepseek([candidate], THREADS, "2026-08-23", "test-key", 2, 1)
        self.assertEqual(len(result), 1)
        self.assertTrue(any("低于建议 8 条" in item for item in warnings))
        retry_messages = post.call_args_list[1].kwargs["json"]["messages"]
        self.assertEqual(retry_messages[-2]["role"], "assistant")
        self.assertIn("takeaways", retry_messages[-1]["content"])

    def test_sun_deposit_exception_matches_schema(self) -> None:
        entry = dry_run_entries("2026-08-23", THREADS)[0]
        entry["by"] = "Sun"
        entry["source"] = {"name": "Sun 的沉淀", "url": "", "author": "Sun", "published_at": "2026-08-20"}
        entry["body_md"] = "完整正文"
        validate_entries(
            [entry],
            [],
            THREADS,
            "2026-08-23",
            enforce_candidate_urls=True,
            expected_by=None,
        )

    def test_fenced_json_is_accepted(self) -> None:
        self.assertEqual(extract_json('```json\n{"items": []}\n```'), [])

    def test_bad_ledgers_are_skipped_and_latest_thread_wins(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "bad.json").write_text("{", encoding="utf-8")
            (root / "one.json").write_text(
                json.dumps(
                    {
                        "date": "2026-08-22",
                        "issue": 1,
                        "threads": [{"id": "x", "title": "旧", "theme": "", "status": "ongoing"}, None],
                    }
                ),
                encoding="utf-8",
            )
            (root / "two.json").write_text(
                json.dumps(
                    {
                        "date": "2026-08-23",
                        "issue": 2,
                        "threads": [{"id": "x", "title": "新", "theme": "", "status": "ongoing"}],
                    }
                ),
                encoding="utf-8",
            )
            threads = load_threads(root)
            self.assertEqual(threads[0]["title"], "新")


if __name__ == "__main__":
    unittest.main()
