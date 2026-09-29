# -*- coding: utf-8 -*-
"""Regression: Anna pseudo-key, 玥 QQ-style key, rename unbroken, avatar merge."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import identity_anchor as ia  # noqa: E402


SCHEMA = """
CREATE TABLE members(
  username TEXT PRIMARY KEY,
  display TEXT, nickname TEXT, avatar TEXT,
  msgs INT, last_active TEXT, profile TEXT, tags TEXT, quote TEXT,
  name_source TEXT, identity_flags TEXT, name_history TEXT, called_names TEXT
);
CREATE TABLE messages(
  id INTEGER PRIMARY KEY, sender TEXT, sender_name TEXT, cst TEXT, create_time INT, content TEXT
);
CREATE TABLE essays(
  id INTEGER PRIMARY KEY, cst TEXT, author TEXT, name TEXT, content TEXT,
  source_sender TEXT, source_message_ids TEXT
);
CREATE TABLE users(
  id INTEGER PRIMARY KEY, username TEXT, display_name TEXT, member_key TEXT
);
CREATE TABLE annotations(
  id INTEGER PRIMARY KEY, user_id INT, username TEXT, date TEXT, anchor TEXT, quote TEXT, deleted INT DEFAULT 0
);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


class KeyFormsTest(unittest.TestCase):
    def test_allowed_forms(self) -> None:
        self.assertTrue(ia.is_stable_member_key("wxid_nowlwctf8h0n22"))
        self.assertTrue(ia.is_stable_member_key("y952346088"))  # 玥 · QQ 形态
        self.assertTrue(ia.is_stable_member_key("sunwuyuan521"))
        self.assertTrue(ia.is_stable_member_key("qq514886787"))
        self.assertTrue(ia.is_stable_member_key("win591"))
        self.assertEqual(ia.key_kind("y952346088"), "wechat_username")

    def test_forbidden_display_as_key(self) -> None:
        self.assertFalse(ia.is_stable_member_key("广州-Anna"))
        self.assertFalse(ia.is_stable_member_key("明野"))
        self.assertFalse(ia.is_stable_member_key("范振华(院长)"))
        self.assertTrue(ia.is_pseudo_display_key("广州-Anna", "广州-Anna"))


class AnnaSampleTest(unittest.TestCase):
    """Sun 亲验：伪行 username=展示名，真行 wxid；小作文锚在真 wxid。"""

    def setUp(self) -> None:
        self.c = _conn()
        avatar = "data:image/jpeg;base64,/9j/4AAQAnnaSameAvatar"
        self.c.execute(
            "INSERT INTO members VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "wxid_nowlwctf8h0n22", "广州-Anna", "广州-Anna", avatar,
                26, "2026-08-27", "", "", "", "room_nickname", "[]",
                '["广州-Anna"]', '[{"name":"Anna","count":2}]',
            ),
        )
        self.c.execute(
            "INSERT INTO members VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "广州-Anna", "广州-Anna", "", avatar,
                25, "2026-08-26", "", "", "", "masked_wxid", '["legacy_display_key"]',
                "[]", "[]",
            ),
        )
        self.c.execute(
            "INSERT INTO messages VALUES(?,?,?,?,?,?)",
            (497, "wxid_nowlwctf8h0n22", "广州-Anna", "2026-08-23 01:30", 1,
             "大家好，我是Anna 看完群里几位伙伴的分享，确实是大神云集。" + ("字" * 200)),
        )
        self.c.execute(
            "INSERT INTO essays VALUES(?,?,?,?,?,?,?)",
            (757, "2026-08-23 01:30", "广州-Anna", "大家好，我是Anna",
             "大家好，我是Anna 看完群里几位伙伴的分享" + ("内容" * 400),
             "wxid_nowlwctf8h0n22", "[497]"),
        )
        self.c.execute(
            "INSERT INTO users VALUES(?,?,?,?)",
            (31, "广州-Anna", "广州-Anna", "wxid_nowlwctf8h0n22"),
        )
        self.c.commit()

    def test_merge_clears_pseudo_and_keeps_essay(self) -> None:
        pairs = ia.merge_candidates(self.c)
        self.assertTrue(any(p["pseudo_username"] == "广州-Anna" for p in pairs))
        results = ia.apply_merges(self.c, pairs)
        self.assertTrue(any(r["canonical_username"] == "wxid_nowlwctf8h0n22" for r in results))
        left = [r["username"] for r in self.c.execute("SELECT username FROM members")]
        self.assertIn("wxid_nowlwctf8h0n22", left)
        self.assertNotIn("广州-Anna", left)
        essay = ia.governed_essay_dict(
            self.c, self.c.execute("SELECT * FROM essays WHERE id=757").fetchone()
        )
        self.assertEqual(essay["member_key"], "wxid_nowlwctf8h0n22")
        self.assertEqual(essay["author"], "广州-Anna")

    def test_rename_does_not_break_essay_link(self) -> None:
        ia.apply_merges(self.c)
        self.c.execute(
            "UPDATE members SET display=? WHERE username=?",
            ("Anna·广州", "wxid_nowlwctf8h0n22"),
        )
        essay = ia.governed_essay_dict(
            self.c, self.c.execute("SELECT * FROM essays WHERE id=757").fetchone()
        )
        self.assertEqual(essay["member_key"], "wxid_nowlwctf8h0n22")
        self.assertEqual(essay["author"], "Anna·广州")
        self.assertEqual(essay["author_snapshot"], "广州-Anna")


class YueSampleTest(unittest.TestCase):
    """玥：y952346088 是合法 wechat_username，不是伪身份。"""

    def setUp(self) -> None:
        self.c = _conn()
        self.c.execute(
            "INSERT INTO members VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "y952346088", "玥", "玥", "",
                7, "2026-08-30", "", "", "", "room_nickname", "[]",
                '["玥"]', "[]",
            ),
        )
        self.c.execute(
            "INSERT INTO messages VALUES(?,?,?,?,?,?)",
            (800, "y952346088", "玥", "2026-08-23 03:01", 2, "大家好，我主要从事数据分析" + ("x" * 100)),
        )
        self.c.execute(
            "INSERT INTO essays VALUES(?,?,?,?,?,?,?)",
            (761, "2026-08-23 03:01", "玥", "大家好，我主要从事数据分析",
             "大家好，我主要从事数据分析与算法研究方面的工作" + ("字" * 100),
             "y952346088", "[800]"),
        )
        self.c.execute("INSERT INTO users VALUES(?,?,?,?)", (29, "玥", "玥", "y952346088"))
        self.c.commit()

    def test_qq_style_key_is_stable_and_not_merged_away(self) -> None:
        self.assertTrue(ia.is_stable_member_key("y952346088"))
        pairs = ia.merge_candidates(self.c)
        self.assertFalse(any(p["canonical_username"] == "y952346088" and p["pseudo_username"] == "玥" for p in pairs))
        self.assertFalse(any(p["pseudo_username"] == "y952346088" for p in pairs))
        essay = ia.governed_essay_dict(
            self.c, self.c.execute("SELECT * FROM essays WHERE id=761").fetchone()
        )
        self.assertEqual(essay["member_key"], "y952346088")
        self.assertEqual(essay["author"], "玥")

    def test_rename_yue_keeps_member_key(self) -> None:
        self.c.execute("UPDATE members SET display=? WHERE username=?", ("玥玥", "y952346088"))
        essay = ia.governed_essay_dict(
            self.c, self.c.execute("SELECT * FROM essays WHERE id=761").fetchone()
        )
        self.assertEqual(essay["member_key"], "y952346088")
        self.assertEqual(essay["author"], "玥玥")


class AvatarHashMergeTest(unittest.TestCase):
    def test_mingye_avatar_dup_merges(self) -> None:
        c = _conn()
        av = "data:image/jpeg;base64,/9j/4AAQMingyeSameBytesXXXX"
        c.execute(
            "INSERT INTO members VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("wxid_ylsq6b288a3o22", "明野", "明野", av, 18, "2026-08-30", "", "", "", "room_nickname", "[]", "[]", "[]"),
        )
        c.execute(
            "INSERT INTO members VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("明野", "明野", "", av, 16, "2026-08-29", "", "", "", "masked_wxid", '["legacy_display_key"]', "[]", "[]"),
        )
        c.execute(
            "INSERT INTO messages VALUES(?,?,?,?,?,?)",
            (1, "wxid_ylsq6b288a3o22", "明野", "2026-08-25", 1, "hi"),
        )
        c.commit()
        self.assertEqual(ia.avatar_hash(av), ia.avatar_hash(av))
        pairs = ia.merge_candidates(c)
        self.assertTrue(any(
            p["pseudo_username"] == "明野" and p["canonical_username"] == "wxid_ylsq6b288a3o22"
            and "avatar_hash" in p["reasons"]
            for p in pairs
        ))
        ia.apply_merges(c, pairs)
        self.assertEqual(
            [r[0] for r in c.execute("SELECT username FROM members")],
            ["wxid_ylsq6b288a3o22"],
        )


class AnnotationRenameTest(unittest.TestCase):
    def test_user_id_anchor_survives_display_rename(self) -> None:
        c = _conn()
        c.execute(
            "INSERT INTO members VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("wxid_a", "旧名", "旧名", "", 1, "2026-08-01", "", "", "", "room_nickname", "[]", '["旧名"]', "[]"),
        )
        c.execute("INSERT INTO users VALUES(?,?,?,?)", (8, "mingye", "旧名", "wxid_a"))
        c.execute(
            "INSERT INTO annotations VALUES(?,?,?,?,?,?,?)",
            (1, 8, "mingye", "2026-08-30", "2026-08-30#themes-p1", "一句原文", 0),
        )
        c.execute("UPDATE members SET display=? WHERE username=?", ("新名", "wxid_a"))
        c.execute("UPDATE users SET display_name=? WHERE id=?", ("新名", 8))
        c.commit()
        ann = c.execute("SELECT user_id FROM annotations WHERE id=1").fetchone()
        self.assertEqual(ann["user_id"], 8)
        self.assertEqual(ia.resolve_display_name(c, "wxid_a"), "新名")


if __name__ == "__main__":
    unittest.main()
