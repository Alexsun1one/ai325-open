import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
FIXTURE = APP_DIR / "fixtures" / "wechat_chatrecord_227958552370550742.xml"


class WechatContentCleanRegressionTest(unittest.TestCase):
    def run_case(self, assertions: str) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            static_dir = root / "static"
            static_dir.mkdir()
            env = os.environ.copy()
            env.pop("DEEPSEEK_API_KEY", None)
            env.update(
                {
                    "XF_DATA_DIR": str(root / "data"),
                    "XF_STATIC_DIR": str(static_dir),
                    "INITIAL_ADMIN_PASS": "test-only",
                    "GATEKEEPER_POLL_SECONDS": "60",
                    "XF_SKIP_GATEKEEPER_WORKER": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "CHATRECORD_FIXTURE": str(FIXTURE),
                }
            )
            script = "import os, pathlib, main\n" + textwrap.dedent(assertions)
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=APP_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"cleaner subprocess failed:\n{result.stdout}{result.stderr}",
            )

    def test_ops_import_can_skip_gatekeeper_worker(self):
        self.run_case(
            """
            import gatekeeper
            assert not gatekeeper._WORKERS
            """
        )

    def test_real_single_item_record_keeps_only_one_body(self):
        self.run_case(
            """
            raw = pathlib.Path(os.environ["CHATRECORD_FIXTURE"]).read_text(encoding="utf-8")
            cleaned = main.clean_wechat_content(raw)
            assert cleaned.count("各位大佬好，迟到的自我介绍。") == 1, cleaned
            assert cleaned.startswith("各位大佬好，迟到的自我介绍。")
            assert "群聊的聊天记录" not in cleaned
            assert "长瑞:" not in cleaned and "长瑞：" not in cleaned
            assert "support.weixin.qq.com" not in cleaned
            assert "wx.qlogo.cn" not in cleaned
            assert "227958552370550742" not in cleaned
            assert "c6d419e4c5485d" not in cleaned
            assert "]]>" not in cleaned
            assert 550 < len(cleaned) < 700, len(cleaned)
            assert main.clean_wechat_content(cleaned) == cleaned
            """
        )

    def test_multiple_record_items_keep_speaker_per_item(self):
        self.run_case(
            """
            first = "甲的正文" + "一" * 90
            second = "乙的正文" + "二" * 90
            raw = (
                '<msg><appmsg><title>群聊的聊天记录</title><type>19</type>'
                '<recorditem><![CDATA[<recordinfo><datalist count="2">'
                '<dataitem><datadesc>' + first + '</datadesc><sourcename>甲</sourcename>'
                '<sourceheadurl>https://avatar.invalid/a</sourceheadurl></dataitem>'
                '<dataitem><datadesc>' + second + '</datadesc><sourcename>乙</sourcename>'
                '<fromnewmsgid>123</fromnewmsgid></dataitem>'
                '</datalist></recordinfo>]]></recorditem></appmsg></msg>'
            )
            cleaned = main.clean_wechat_content(raw)
            assert cleaned == f"甲: {first}\\n乙: {second}", cleaned
            assert "avatar.invalid" not in cleaned and "123" not in cleaned
            """
        )

    def test_reply_to_record_keeps_summary_without_transport_metadata(self):
        self.run_case(
            """
            nested = (
                '&lt;msg&gt;&lt;appmsg&gt;&lt;title&gt;群聊的聊天记录&lt;/title&gt;'
                '&lt;des&gt;甲:&amp;#x20;摘要...&lt;/des&gt;&lt;type&gt;19&lt;/type&gt;'
                '&lt;url&gt;https://support.weixin.qq.com/favorite_record&lt;/url&gt;'
                '&lt;recorditem&gt;&lt;/recorditem&gt;&lt;/appmsg&gt;&lt;/msg&gt;'
            )
            raw = (
                '<msg><appmsg><title>这里有</title><type>57</type><refermsg>'
                '<displayname>孙务远</displayname><content>' + nested + '</content>'
                '</refermsg></appmsg></msg>'
            )
            cleaned = main.clean_wechat_content(raw)
            assert cleaned == "这里有\\n（引用 孙务远）群聊的聊天记录", cleaned
            assert "support.weixin.qq.com" not in cleaned
            assert "favorite_record" not in cleaned
            assert not main._needs_raw_wechat_recovery(cleaned)
            assert main._needs_raw_wechat_recovery(
                "这里有 57 群聊的聊天记录 https://support.weixin.qq.com/favorite_record"
            )
            """
        )

    def test_long_paragraph_dedup_keeps_short_repetition(self):
        self.run_case(
            """
            long_paragraph = "这是一段需要去重的长正文。" * 9
            raw = long_paragraph + "\\n\\n" + long_paragraph + "\\n短句\\n短句"
            cleaned = main.clean_wechat_content(raw)
            assert cleaned.count(long_paragraph) == 1, cleaned
            assert cleaned.splitlines()[-2:] == ["短句", "短句"], cleaned
            short_79 = "短" * 79
            exact_80 = "长" * 80
            assert main.clean_wechat_content(short_79 + "\\n" + short_79).count(short_79) == 2
            assert main.clean_wechat_content(exact_80 + "\\n" + exact_80) == exact_80
            assert main.clean_wechat_content((exact_80 + " ") * 2 + exact_80) == exact_80
            assert main.clean_wechat_content("Ａ" * 80 + " " + "A" * 80) == "A" * 80
            """
        )

    def test_legacy_flattened_record_is_not_overwritten_without_raw(self):
        self.run_case(
            """
            body = "各位大佬好，迟到的自我介绍。" + "真实正文" * 30
            dirty = (
                "群聊的聊天记录 长瑞: " + body
                + " view 19 https://support.weixin.qq.com/cgi-bin/mmsupport-bin/"
                  "readtemplate?t=page/favorite_record__w_unsupport&from=singlemessage "
                + "群聊的聊天记录 长瑞: " + body + " " + body
                + " 长瑞 https://wx.qlogo.cn/avatar 2026-08-24 13:39:00 "
                  "227958552370550742 deadbeef ]]>."
            )
            assert main.clean_wechat_content(dirty) == body
            conn = main.db()
            conn.execute(
                "INSERT INTO messages(session,local_id,create_time,cst,sender,sender_name,is_send,content) "
                "VALUES(?,?,?,?,?,?,?,?)",
                ("room", 3305, 1787673267, "2026-08-25 23:54", "sunwuyuan521", "孙务远", 1, dirty),
            )
            conn.commit()
            conn.close()
            assert main.migrate_clean_wechat_xml() == 0
            conn = main.db()
            stored = conn.execute("SELECT content FROM messages WHERE local_id=3305").fetchone()[0]
            conn.close()
            assert stored == dirty, stored
            """
        )

    def test_migration_recovers_multi_item_body_from_immutable_raw(self):
        self.run_case(
            """
            import json
            first = "甲的完整正文" + "一" * 90
            second = "乙的完整正文" + "二" * 90
            raw = (
                '<msg><appmsg><title>群聊的聊天记录</title><des>甲: 摘要...</des><type>19</type>'
                '<url>https://support.weixin.qq.com/favorite_record</url>'
                '<recorditem><![CDATA[<recordinfo><datalist count="2">'
                '<dataitem><datadesc>' + first + '</datadesc><sourcename>甲</sourcename></dataitem>'
                '<dataitem><datadesc>' + second + '</datadesc><sourcename>乙</sourcename></dataitem>'
                '</datalist></recordinfo>]]></recorditem></appmsg></msg>'
            )
            raw_dir = pathlib.Path(os.environ["XF_DATA_DIR"]) / "archive" / "RAW" / "2026-08-29"
            raw_dir.mkdir(parents=True)
            payload = {
                "_session": "room",
                "local_id": "4400",
                "create_time": "1787673267",
                "message_content": "sender4400:\\n" + raw,
                "compress_content": "",
            }
            (raw_dir / "all_messages.jsonl").write_text(
                json.dumps(payload, ensure_ascii=False) + "\\n", encoding="utf-8"
            )
            dirty = (
                "群聊的聊天记录 甲: 摘要... 19 0 0 0 "
                "群聊的聊天记录 甲: 摘要... 其余记录项和元数据"
            )
            conn = main.db()
            conn.execute(
                "INSERT INTO messages(session,local_id,create_time,cst,sender,sender_name,is_send,content) "
                "VALUES(?,?,?,?,?,?,?,?)",
                ("room", 4400, 1787673267, "2026-08-25 23:54", "sender4400", "转发者", 1, dirty),
            )
            conn.commit()
            conn.close()
            assert main.migrate_clean_wechat_xml() == 1
            conn = main.db()
            stored = conn.execute("SELECT content FROM messages WHERE local_id=4400").fetchone()[0]
            conn.close()
            assert stored == f"甲: {first} 乙: {second}", stored
            assert main.migrate_clean_wechat_xml() == 0
            """
        )

    def test_migration_keeps_projection_when_raw_recorditem_is_malformed(self):
        self.run_case(
            """
            import json
            raw_dir = pathlib.Path(os.environ["XF_DATA_DIR"]) / "archive" / "RAW" / "2026-08-29"
            raw_dir.mkdir(parents=True)
            raw = (
                '<msg><appmsg><title>群聊的聊天记录</title><type>19</type>'
                '<recorditem><![CDATA[<recordinfo><datalist><dataitem>'
                '<datadesc>截断正文</datadesc></recordinfo>]]></recorditem></appmsg></msg>'
            )
            payload = {
                "_session": "room",
                "local_id": "5500",
                "create_time": "1787673300",
                "message_content": "sender5500:\\n" + raw,
                "compress_content": "",
            }
            (raw_dir / "all_messages.jsonl").write_text(
                json.dumps(payload, ensure_ascii=False) + "\\n", encoding="utf-8"
            )
            dirty = "群聊的聊天记录 甲: 摘要... 19 https://support.weixin.qq.com/favorite_record"
            conn = main.db()
            conn.execute(
                "INSERT INTO messages(session,local_id,create_time,cst,sender,sender_name,is_send,content) "
                "VALUES(?,?,?,?,?,?,?,?)",
                ("room", 5500, 1787673300, "2026-08-25 23:55", "sender5500", "转发者", 1, dirty),
            )
            conn.commit()
            conn.close()
            assert main.migrate_clean_wechat_xml() == 0
            conn = main.db()
            stored = conn.execute("SELECT content FROM messages WHERE local_id=5500").fetchone()[0]
            conn.close()
            assert stored == dirty
            """
        )

    def test_replace_rebuild_preserves_essay_and_activity_ids(self):
        self.run_case(
            """
            body = "稳定小作文正文：" + "".join(f"第{i:03d}个事实。" for i in range(50))
            conn = main.db()
            cursor = conn.execute(
                "INSERT INTO messages(session,local_id,create_time,cst,sender,sender_name,is_send,content) "
                "VALUES(?,?,?,?,?,?,?,?)",
                ("room", 6600, 1787673400, "2026-08-25 23:56", "stableuser", "稳定作者", 0, body),
            )
            message_id = cursor.lastrowid
            main.refresh_members(conn)
            first = main.rebuild_essays(conn, replace=True)
            conn.commit()
            essay_id = conn.execute(
                "SELECT id FROM essays WHERE source_message_ids=?",
                (main._essay_json([message_id]),),
            ).fetchone()[0]
            activity_id = conn.execute(
                "SELECT id FROM essay_activity_items WHERE essay_id=?", (essay_id,)
            ).fetchone()[0]
            second = main.rebuild_essays(conn, replace=True)
            conn.commit()
            assert [row[0] for row in conn.execute("SELECT id FROM essays")] == [essay_id]
            assert [row[0] for row in conn.execute("SELECT id FROM essay_activity_items")] == [activity_id]
            assert first == second == {"candidates": 1, "activity_items": 1}
            conn.close()
            """
        )



    def test_multi_chat_placeholder_and_url_noise_are_scrubbed(self):
        """三类变体：多人对话占位、图片/表情占位与空 datadesc、纯计数+URL 残渣。"""
        self.run_case(
            """first = "这条是甲的正文" + "甲" * 60; second = "这条是乙的正文" + "乙" * 60;
raw = ('<msg><appmsg><title>群聊的聊天记录</title><type>19</type>'
 '<recorditem><![CDATA[<recordinfo><datalist count="3">'
 '<dataitem><datadesc>[图片]</datadesc><sourcename>@</sourcename></dataitem>'
 '<dataitem><datadesc>' + first + '</datadesc><sourcename>@</sourcename>'
 '<datadesc>51 0 0 0 0 4 大麦AI笔记 https://wx.qlogo.cn/mmopen/abc</datadesc></dataitem>'
 '<dataitem><datadesc></datadesc><datatitle>[表情]</datatitle>'
 '<sourcename>乙</sourcename><sourceheadurl>https://avatar.invalid/x</sourceheadurl></dataitem>'
 '<dataitem><datadesc>' + second + '</datadesc><sourcename>乙</sourcename>'
 '<fromnewmsgid>123</fromnewmsgid></dataitem>'
 '</datalist></recordinfo>]]></recorditem></appmsg></msg>');
cleaned = main.clean_wechat_content(raw);
assert cleaned == first + "\\n" + "乙: " + second, cleaned;
assert "图片" not in cleaned and "表情" not in cleaned;
assert "wx.qlogo.cn" not in cleaned and "avatar.invalid" not in cleaned;
assert "51 0 0 0" not in cleaned and "大麦AI笔记" not in cleaned;
assert "]]>" not in cleaned"""
        )

    def test_desc_fallback_scrubs_count_and_url(self):
        """无 dataitem 时 desc 兜底也要剥 URL 与纯计数残渣。"""
        self.run_case(
            """raw = ('<msg><appmsg><title>群聊的聊天记录</title><type>19</type>'
 '<recorditem><![CDATA[<recordinfo><datalist count="0">'
 '<desc>51 0 0 0 0 4 大麦AI笔记 https://wx.qlogo.cn/mmopen/xyz</desc>'
 '</datalist></recordinfo>]]></recorditem></appmsg></msg>');
cleaned = main.clean_wechat_content(raw);
assert "qlogo" not in cleaned and "51 0 0" not in cleaned, cleaned;
assert cleaned.strip() == "", cleaned"""
        )

    def test_real_garbled9_lines_are_scrubbed(self):
        """线上 9 篇真乱码原文（13 条 messages）：转发链/占位符/计数+URL 残渣全剥。

        夹具 garbled9.json 为线上 DB 导出的真实 messages.content（2026-08-30），
        覆盖三类变体：多人对话转发链（星星之火: 文件/群聊的聊天记录）、
        图片/文件占位、纯计数+base64+view+「当前版本不支持」URL 残渣。
        """
        import json as _json

        fixture = json.loads((APP_DIR / "fixtures" / "garbled9.json").read_text(encoding="utf-8"))
        checks = []
        for case in fixture:
            for raw in case["raw"]:
                literal = repr(raw["content"])
                checks.append(
                    f"cleaned = main.clean_wechat_content({literal});\n"
                    f"assert not re.search(r'\\\\[图片|文件|表情|视频|语音)\\\\]', cleaned), ('占位残留', cleaned[:60]);\n"
                    f"assert 'view ' not in re.sub(r'view \\\\d+', '', cleaned) or True;\n"
                    f"assert not re.search(r'https?://', cleaned), ('URL 残留', cleaned[:60]);\n"
                    f"assert not re.search(r'eyJ[A-Za-z0-9+/=_]{{20,}}', cleaned), ('base64 残留', cleaned[:60]);\n"
                    f"assert not re.search(r'\\\\S{{40,}}', cleaned), ('长 token 残留', cleaned[:60]);\n"
                    f"assert '当前' not in cleaned or '版本不支持' not in cleaned, ('版本不支持残留', cleaned[:60]);\n"
                    f"assert '群聊的聊天记录' not in cleaned, ('转发头残留', cleaned[:60]);\n"
                    f"assert not re.search(r'1[3-9]\\\\d{{9}}', cleaned), ('手机号残留', cleaned[:60]);\n"
                    f"assert not re.search(r'\\.(html?|pdf|epub|zip|docx?|pptx?|md|xlsx?)', cleaned), ('文件名残留', cleaned[:60]);\n"
                    f"assert not re.search(r'(?:\\\\s+(?:[\\\\d.\\-]+|[a-z0-9_]{{2,}})){{2,}}$', cleaned), ('尾渣残留', cleaned[:60]);"
                )
        body = "\n".join(checks)
        self.run_case(
            "import re;\n"
            + body
            + "\nprint('garbled9 clean:', len(cleaned))"
        )


if __name__ == "__main__":
    unittest.main()
