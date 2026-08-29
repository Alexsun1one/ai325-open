from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import distill_ledger as ledger


class LedgerDistillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sample = Path(__file__).resolve().parent / "sample"
        cls.material = ledger.load_materials(cls.sample)
        cls.date = "2026-08-23"

    def fixed(self) -> dict:
        return ledger.dry_run_content(self.date, self.material["stats"], {}, "deepseek-chat")

    def test_fixed_dry_run_passes_schema_and_self_check(self) -> None:
        warnings: list[str] = []
        content = ledger.normalize_content(
            self.fixed(), self.material["transcript"], self.material["stats"], {}, self.date, "deepseek-chat", warnings
        )
        ledger.validate_content(content, self.date)
        checks = ledger.self_check(content, self.material["transcript"])
        self.assertEqual(warnings, [])
        self.assertEqual(checks["quotes_verified"], 6)
        self.assertEqual(checks["tone_notes_spot_checked"], 3)
        self.assertEqual(checks["deep_unspoken_count"], 3)
        self.assertEqual(checks["one_day_actions"], 4)
        self.assertEqual(content["distilled_by"], "一一（Hermes × DeepSeek）")
        self.assertTrue(
            all(voice["g"] in ledger.TONE_CLASSES for theme in content["themes"] for voice in theme["voices"])
        )

    def test_false_or_sensitive_verbatim_is_soft_dropped(self) -> None:
        content = self.fixed()
        content["quotes"].append({"t": "模型编造的句子", "a": "不存在的人", "g": "s"})
        content["themes"][0]["voices"].append({"a": "孙务远", "v": "syntheticSecretToken12345"})
        content["members_focus"][0]["quote"] = "模型编造的句子"
        warnings: list[str] = []
        normalized = ledger.normalize_content(
            content, self.material["transcript"], self.material["stats"], {}, self.date, "deepseek-chat", warnings
        )
        self.assertEqual(len(normalized["quotes"]), 6)
        self.assertEqual(len(normalized["themes"][0]["voices"]), 1)
        self.assertEqual(normalized["members_focus"][0]["quote"], "")
        self.assertTrue(any("已丢弃" in warning for warning in warnings))
        ledger.validate_content(normalized, self.date)

    def test_missing_schema_field_is_hard_error(self) -> None:
        content = self.fixed()
        del content["growth"]
        with self.assertRaises(ledger.ValidationFailure) as raised:
            ledger.validate_content(content, self.date)
        self.assertIn("成长/行动", str(raised.exception))

    def test_named_newcomer_from_materials_must_have_a_card(self) -> None:
        content = self.fixed()
        warnings: list[str] = []
        ledger.validate_expected_newcomers(content, [{"name": "待登记新人"}], warnings)
        self.assertIn("待登记新人", {item["name"] for item in content["newcomers"]})
        self.assertTrue(any("自动补最小卡片" in warning for warning in warnings))

    def test_shallow_deep_and_non_action_are_soft_warnings(self) -> None:
        content = self.fixed()
        content["themes"][0]["deep"] = "只是复述。"
        content["growth"]["todo"][0]["items"][0] = "关于未来与世界的漫长思考"
        warnings: list[str] = []
        normalized = ledger.normalize_content(
            content, self.material["transcript"], self.material["stats"], {}, self.date, "deepseek-chat", warnings
        )
        ledger.validate_content(normalized, self.date)
        checks = ledger.self_check(normalized, self.material["transcript"], warnings)
        self.assertEqual(checks["one_day_actions"], 3)
        self.assertTrue(any("缺可执行动词" in warning for warning in warnings))
        self.assertTrue(any("没说破的" in warning for warning in warnings))

    def test_engineering_jargon_is_replaced_outside_verbatim_quotes(self) -> None:
        content = self.fixed()
        content["lead"] = "用赋能完成闭环，不改原话「赋能」"
        warnings: list[str] = []
        normalized = ledger.normalize_content(
            content, self.material["transcript"], self.material["stats"], {}, self.date, "deepseek-chat", warnings
        )
        self.assertEqual(normalized["lead"], "用帮助完成做完并检查，不改原话「赋能」")
        self.assertTrue(any("lead 已替换工程腔" in warning for warning in warnings))

    def test_theme_depth_issues_are_soft_and_bad_quote_markers_are_removed(self) -> None:
        content = self.fixed()
        content["themes"][1]["deep"] = "思想钢印是假的。没说破的：这是一句无证据断言。到此为止。"
        content["themes"][2]["deep"] = "模型声称「一段根本不存在的逐字原话」。没说破的：先保留判断。今天记录疑点。"
        warnings: list[str] = []
        ledger.strip_unverified_deep_quotes(content, self.material["transcript"], warnings)
        issues = ledger.validate_theme_depth(content, self.material["transcript"], warnings)
        self.assertTrue(any("判断缺逐字原话" in item for item in issues[1]))
        self.assertTrue(any("可执行动作" in item for item in issues[1]))
        self.assertNotIn("「一段根本不存在的逐字原话」", content["themes"][2]["deep"])
        self.assertIn("一段根本不存在的逐字原话", content["themes"][2]["deep"])
        self.assertTrue(any("已去掉引用标记" in warning for warning in warnings))
        ledger.validate_content(content, self.date)

    def test_theme_repair_stops_after_two_attempts_and_accepts_soft_issues(self) -> None:
        content = self.fixed()
        content["themes"][1]["deep"] = "只有一句。"
        warnings: list[str] = []
        with patch.object(ledger, "repair_themes_once", side_effect=lambda current, *_args: current) as mocked:
            result = ledger.repair_themes_best_effort(
                content,
                self.material["transcript"],
                {"quote_plan": [], "tone_plan": [], "theme_plan": []},
                [],
                "judge 原话",
                "key",
                "deepseek-chat",
                "https://example.invalid",
                1,
                warnings,
            )
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(result["themes"][1]["deep"], "只有一句。")
        self.assertTrue(any("已按软规则接受" in warning for warning in warnings))

    def test_partial_marker_uses_existing_complete_schema_field(self) -> None:
        warnings: list[str] = []
        partial = ledger.mark_partial(self.fixed(), "总时长超过 25 分钟", warnings)
        self.assertIs(partial["complete"], False)
        self.assertIn("[partial]", partial["coverage"]["note"])
        self.assertTrue(any("complete=false" in warning for warning in warnings))

    def test_timeout_without_prior_output_builds_truthful_partial_from_materials(self) -> None:
        warnings: list[str] = []
        partial = ledger.emergency_partial_content(
            self.date,
            self.material,
            {},
            "deepseek-chat",
            "总时长超过 25 分钟",
            warnings,
        )
        ledger.validate_content(partial, self.date)
        checks = ledger.self_check(partial, self.material["transcript"], warnings)
        self.assertIs(partial["complete"], False)
        self.assertGreaterEqual(checks["quotes_verified"], ledger.MIN_QUOTES)
        self.assertEqual(partial["title"], "部分蒸馏 · 等待重跑")
        self.assertNotIn("大一新人登船", json.dumps(partial, ensure_ascii=False))

    def test_theme_deep_repair_is_one_local_call_with_judge_text(self) -> None:
        content = self.fixed()
        untouched = json.loads(json.dumps(content["themes"][0], ensure_ascii=False))
        content["themes"][1]["deep"] = "思想钢印是假的。"
        content["themes"][1]["voices"][0].pop("g")
        line_index = ledger.transcript_line_index(self.material["transcript"])
        refs = [
            ("c01-e01", "L0059", "s"),
            ("c01-e02", "L0256", "s"),
        ]
        chunks = [
            {
                "evidence": [
                    {
                        "id": evidence_id,
                        "type": "quote",
                        "data": {
                            "line": line_id,
                            "a": line_index[line_id]["a"],
                            "t": line_index[line_id]["time"],
                            "v": line_index[line_id]["text"],
                            "g": tone,
                        },
                    }
                    for evidence_id, line_id, tone in refs
                ]
            }
        ]
        skeleton = {
            "quote_plan": ["c01-e01", "c01-e02"],
            "tone_plan": [],
            "theme_plan": [
                {"evidence_ids": ["c01-e01"]},
                {"evidence_ids": ["c01-e01", "c01-e02"]},
                {"evidence_ids": ["c01-e02"]},
            ],
        }
        response = {
            "themes": [
                {
                    "index": 1,
                    "deep": "原话「虽然是AI写的，也是你的积累啊」说明经历仍由人负责。没说破的：「交流的过程突然自己因为别人说的本来不相干的一句话，来灵感了」说明群体讨论能触发新判断。今天记录一条被他人观点触发的灵感。",
                    "voices": [
                        {"line": "L0059", "a": "孙务远", "g": "s", "fragment": "虽然是AI写的，也是你的积累啊"}
                    ],
                }
            ]
        }
        judge_text = 'themes[1].deep 需含“没说破”且至少 3 句'
        with patch.object(ledger, "deepseek_request", return_value=json.dumps(response, ensure_ascii=False)) as mocked:
            repaired = ledger.repair_themes_once(
                content,
                self.material["transcript"],
                skeleton,
                chunks,
                judge_text,
                "key",
                "deepseek-chat",
                "https://example.invalid",
                1,
            )
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(repaired["themes"][0], untouched)
        self.assertEqual(repaired["themes"][1]["voices"][0]["g"], "s")
        self.assertIn(judge_text, mocked.call_args.args[0][-1]["content"])
        ledger.validate_theme_depth(repaired, self.material["transcript"])

    def test_missing_presentation_fields_and_bad_dates_are_auto_filled(self) -> None:
        content = self.fixed()
        for field in ("title", "lead", "complete"):
            content.pop(field)
        content["coverage"] = {"from": "昨天", "to": "tomorrow", "cutoff": "", "note": ""}
        content["growth"]["todo"][0]["items"].append("关于远方的思考")
        warnings: list[str] = []
        normalized = ledger.normalize_content(
            content, self.material["transcript"], self.material["stats"], {}, self.date, "deepseek-chat", warnings
        )
        ledger.validate_content(normalized, self.date)
        ledger.self_check(normalized, self.material["transcript"], warnings)
        self.assertTrue(normalized["title"].startswith("第 001 批 ·"))
        self.assertTrue(normalized["lead"])
        self.assertIs(normalized["complete"], True)
        self.assertEqual(normalized["coverage"]["from"], self.date)
        self.assertEqual(normalized["coverage"]["to"], self.date)
        self.assertTrue(normalized["coverage"]["cutoff"].startswith(self.date))
        self.assertTrue(any("coverage.from" in warning for warning in warnings))

    def test_privacy_shape_and_illegal_tone_remain_hard_failures(self) -> None:
        content = self.fixed()
        content["lead"] = "password: syntheticSecretValue123"
        content["quotes"][0]["g"] = "x"
        with self.assertRaises(ledger.ValidationFailure) as raised:
            ledger.validate_content(content, self.date)
        self.assertIn("隐私形态", str(raised.exception))
        self.assertIn("quotes[0].g", str(raised.exception))

    def test_repair_keeps_previous_json_and_concrete_error(self) -> None:
        responses = [json.dumps({"wrong": []}), json.dumps({"ok": []})]

        def parse(raw: str) -> dict:
            payload = json.loads(raw)
            if "ok" not in payload:
                raise ledger.ValidationFailure(["缺少 ok 字段"])
            return payload

        with patch.object(ledger, "deepseek_request", side_effect=responses) as mocked:
            result = ledger.call_with_repair(
                [{"role": "user", "content": "start"}],
                parse,
                "key",
                "model",
                "https://example.invalid",
                1,
                2,
                "test",
            )
        self.assertEqual(result, {"ok": []})
        retry_messages = mocked.call_args_list[1].args[0]
        self.assertEqual(retry_messages[-2]["role"], "assistant")
        self.assertIn("wrong", retry_messages[-2]["content"])
        self.assertIn("缺少 ok 字段", retry_messages[-1]["content"])
        self.assertIn("只输出 JSON", retry_messages[-1]["content"])
        self.assertIn("控制长度", retry_messages[-1]["content"])

    def test_transcript_is_chunked_without_line_loss(self) -> None:
        source = self.material["transcript"]
        chunks = ledger.chunk_transcript(source, ledger.DEFAULT_CHUNK_SIZE)
        self.assertEqual("".join(chunks), source)
        self.assertGreaterEqual(len(chunks), 5)

    def test_truncated_json_drops_last_partial_object_and_closes(self) -> None:
        raw = '{"evidence":[{"type":"quote","data":{"a":"A","v":"完整"}},{"type":"event","data":{"t":"01:2'
        payload = ledger.extract_json(raw)
        self.assertEqual(
            payload,
            {"evidence": [{"type": "quote", "data": {"a": "A", "v": "完整"}}]},
        )

    def test_chunk_extraction_caps_total_evidence_at_25(self) -> None:
        response = {
            "evidence": [
                {"type": "event", "data": {"t": "00:01", "h": f"e{index}"}}
                for index in range(30)
            ]
        }
        with patch.object(ledger, "deepseek_request", return_value=json.dumps(response, ensure_ascii=False)):
            chunks = ledger.extract_chunks(
                "[08-23 00:01] A: 一条消息\n",
                self.date,
                "key",
                "model",
                "https://example.invalid",
                1,
                1,
                ledger.DEFAULT_CHUNK_SIZE,
            )
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]["evidence"]), 25)
        self.assertEqual(chunks[0]["evidence"][-1]["id"], "c01-e25")

    def test_chunk_extraction_salvages_truncated_last_evidence_without_retry(self) -> None:
        raw = '{"evidence":[{"type":"quote","data":{"line":"L0001","a":"A","fragment":"一条 消息...","g":"s"}},{"type":"event","data":{"t":"01:2'
        with patch.object(ledger, "deepseek_request", return_value=raw) as mocked:
            chunks = ledger.extract_chunks(
                "[08-23 00:01] A: 一条消息……\n",
                self.date,
                "key",
                "model",
                "https://example.invalid",
                1,
                2,
                ledger.DEFAULT_CHUNK_SIZE,
            )
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(len(chunks[0]["evidence"]), 1)
        self.assertEqual(chunks[0]["evidence"][0]["id"], "c01-e01")
        self.assertEqual(chunks[0]["evidence"][0]["data"]["v"], "一条消息……")

    def test_line_reference_uses_original_text_after_normalized_match(self) -> None:
        transcript = '[08-23 00:01] A: 前缀 “你好……世界”，后缀\n'
        index = ledger.transcript_line_index(transcript)
        resolved = ledger.resolve_line_reference(
            {"line": "L0001", "a": "A", "fragment": "你好... 世界"}, index
        )
        self.assertIsNotNone(resolved)
        source, exact = resolved  # type: ignore[misc]
        self.assertEqual(source["a"], "A")
        self.assertEqual(exact, "你好……世界")
        message = index["L0001"]["text"]
        start = message.index("你好")
        offset_resolved = ledger.resolve_line_reference(
            {"line": "L0001", "a": "A", "start": start, "end": start + len("你好……世界")}, index
        )
        self.assertEqual(offset_resolved[1], "你好……世界")  # type: ignore[index]
        self.assertTrue(ledger.quote_exists("你好... 世界", "A", ledger.parse_utterances(transcript)))
        self.assertTrue(ledger.numbered_transcript(transcript).startswith("L0001 [08-23"))

    def test_successful_chunks_are_reused_after_later_chunk_failure(self) -> None:
        transcript = "[08-23 00:01] A: 第一条消息\n[08-23 00:02] B: 第二条消息\n"
        success = json.dumps({"evidence": [{"type": "event", "data": {"t": "00:01", "h": "事件"}}]})
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = Path(temp_dir)
            with patch.object(ledger, "deepseek_request", side_effect=[success, ledger.LedgerError("boom")]):
                with self.assertRaises(ledger.LedgerError):
                    ledger.extract_chunks(
                        transcript, self.date, "key", "model", "https://example.invalid", 1, 1, 30, cache
                    )
            self.assertEqual(len(list(cache.glob("chunk-001-*.json"))), 1)
            with patch.object(ledger, "deepseek_request", return_value=success) as mocked:
                chunks = ledger.extract_chunks(
                    transcript, self.date, "key", "model", "https://example.invalid", 1, 1, 30, cache
                )
            self.assertEqual(len(chunks), 2)
            self.assertEqual(mocked.call_count, 1)

    def test_quote_supplement_uses_line_refs_and_judge_feedback(self) -> None:
        transcript = "\n".join(
            f"[08-23 00:0{index}] A: 这是第{index}条可以逐字引用的判断"
            for index in range(1, 7)
        )
        line_index = ledger.transcript_line_index(transcript)
        initial = {
            "evidence": [
                {
                    "id": f"c01-e{index:02d}",
                    "type": "quote",
                    "data": {
                        "line": f"L{index:04d}",
                        "a": "A",
                        "t": line_index[f"L{index:04d}"]["time"],
                        "v": line_index[f"L{index:04d}"]["text"],
                        "g": "s",
                    },
                }
                for index in range(1, 4)
            ]
        }
        supplement = {
            "quotes": [
                {"line": f"L{index:04d}", "a": "A", "g": "s", "fragment": f"第{index}条可以逐字引用"}
                for index in range(4, 7)
            ]
        }
        with patch.object(ledger, "deepseek_request", return_value=json.dumps(supplement, ensure_ascii=False)) as mocked:
            chunks = ledger.supplement_quote_evidence(
                [initial], transcript, {"speakers": [["A", 6]]}, "补足金句", "key", "model",
                "https://example.invalid", 1, 1, None
            )
        self.assertEqual(len(ledger.quote_evidence_items(chunks)), 6)
        self.assertIn("补足金句", mocked.call_args.args[0][-1]["content"])

    def test_deepseek_request_sets_json_mode_and_8192_tokens(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode()

        with patch.object(ledger.request, "urlopen", return_value=FakeResponse()) as mocked:
            self.assertEqual(
                ledger.deepseek_request(
                    [{"role": "user", "content": "test"}], "key", "model", "https://example.invalid", 1
                ),
                "{}",
            )
        request_object = mocked.call_args.args[0]
        body = json.loads(request_object.data)
        self.assertEqual(body["max_tokens"], 8192)
        self.assertEqual(body["response_format"], {"type": "json_object"})

    def test_real_assembly_calls_skeleton_then_fill(self) -> None:
        chunk_count = len(
            ledger.chunk_transcript(
                ledger.numbered_transcript(ledger.redact_for_model(self.material["transcript"])),
                ledger.DEFAULT_CHUNK_SIZE,
            )
        )
        numbered_chunks = ledger.chunk_transcript(
            ledger.numbered_transcript(ledger.redact_for_model(self.material["transcript"])),
            ledger.DEFAULT_CHUNK_SIZE,
        )
        line_index = ledger.transcript_line_index(self.material["transcript"])
        chunk_responses = []
        for chunk in numbered_chunks:
            line_ids = re.findall(r"(?m)^(L\d{4,})\b", chunk)
            chosen = next(
                line_index[line_id]
                for line_id in line_ids
                if line_id in line_index and 8 <= len(line_index[line_id]["text"]) <= 160
                and not ledger.is_sensitive(line_index[line_id]["text"])
            )
            chunk_responses.append(
                {
                    "evidence": [
                        {
                            "type": "quote",
                            "data": {
                                "line": chosen["line"],
                                "a": chosen["a"],
                                "fragment": chosen["text"],
                                "g": "s",
                            },
                        }
                    ]
                }
            )
        evidence_ids = [f"c{index:02d}-e01" for index in range(1, chunk_count + 1)]
        skeleton = {
            "title": "骨架标题",
            "lead_angle": "把讨论从工具引向判断与责任",
            "event_plan": [{"evidence_ids": [evidence_ids[0]], "angle": "时间线"}],
            "theme_plan": [
                {
                    "h": f"第{index}幕",
                    "thread_id": f"thread-{index}",
                    "thread_title": f"线索{index}",
                    "thread_status": "ongoing",
                    "evidence_ids": evidence_ids[:3],
                    "deep_question": "没说破的结构",
                }
                for index in range(1, 4)
            ],
            "tone_plan": [
                {"cls": "s", "evidence_id": evidence_ids[0], "reason": "认真判断"},
                {"cls": "j", "evidence_id": evidence_ids[1], "reason": "玩笑自嘲"},
                {"cls": "h", "evidence_id": evidence_ids[2], "reason": "玩笑壳认真芯"},
            ],
            "quote_plan": evidence_ids[:6],
            "member_plan": [{"name": "孙务远", "evidence_ids": [evidence_ids[0]]}],
            "growth_plan": {
                "takeaways": ["角度1", "角度2", "角度3"],
                "actions": ["记录动作", "验证动作", "整理动作"],
            },
            "extension_plan": {
                "insights": [],
                "glossary": [],
                "arsenal": [],
                "docket": [],
                "clashes": [],
                "newcomers": [],
            },
        }
        final_content = self.fixed()
        final_content["quotes"] = []  # 模型即使漏掉金句墙，也由 quote_plan 的行号引用结构性回填。
        responses = (
            [json.dumps(evidence, ensure_ascii=False) for evidence in chunk_responses]
            + [json.dumps(skeleton, ensure_ascii=False), json.dumps(final_content, ensure_ascii=False)]
        )
        with patch.object(ledger, "deepseek_request", side_effect=responses) as mocked:
            result, warnings, checks, used_chunks = ledger.assemble_real(
                self.date,
                self.material,
                {},
                "key",
                "deepseek-chat",
                "https://example.invalid",
                1,
                1,
                ledger.DEFAULT_CHUNK_SIZE,
            )
        self.assertEqual(used_chunks, chunk_count)
        self.assertEqual(mocked.call_count, chunk_count + 2)
        self.assertEqual(warnings, [])
        self.assertEqual(checks["quotes_verified"], 6)
        self.assertEqual(len(result["themes"]), 3)
        skeleton_prompt = mocked.call_args_list[chunk_count].args[0][-1]["content"]
        fill_prompt = mocked.call_args_list[chunk_count + 1].args[0][-1]["content"]
        self.assertIn("骨架", skeleton_prompt)
        self.assertIn("只按下列骨架填充", fill_prompt)
        self.assertIn("L000", fill_prompt)

    def test_redaction_removes_password_and_phone(self) -> None:
        sample = "[08-23 03:44] A: syntheticSecretToken12345\n[08-23 03:45] B: 电话 19999999999"
        redacted = ledger.redact_for_model(sample)
        self.assertNotIn("syntheticSecretToken12345", redacted)
        self.assertNotIn("19999999999", redacted)
        self.assertIn("已移除", redacted)

    def test_public_url_is_not_mistaken_for_a_secret(self) -> None:
        self.assertFalse(ledger.is_sensitive("https://github.com/example-owner/example-project"))


if __name__ == "__main__":
    unittest.main()
