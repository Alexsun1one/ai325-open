# -*- coding: utf-8 -*-
"""Reading-loop vitality: caps, unique-per-day, multi-person bonus."""
from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reading_vitality as rv

SETTINGS = {
    "weights": {
        "highlight": 2,
        "highlight_daily_cap": 6,
        "note": 8,
        "note_daily_cap": 3,
        "comment": 4,
        "comment_daily_cap": 4,
        "favorite": 1,
        "favorite_daily_cap": 5,
        "multi_highlight_bonus": 2,
        "reading_burst_threshold": 20,
        "reading_burst_discount": 0.3,
    }
}

SCHEMA = """
CREATE TABLE annotations(
  id INTEGER PRIMARY KEY, user_id INT, username TEXT, date TEXT, anchor TEXT,
  quote TEXT, note TEXT, kind TEXT, visibility TEXT, status TEXT, deleted INT,
  created_at TEXT
);
CREATE TABLE comments(
  id INTEGER PRIMARY KEY, user_id INT, username TEXT, anchor TEXT,
  status TEXT, deleted INT, created_at TEXT
);
CREATE TABLE favorites(
  id INTEGER PRIMARY KEY, user_id INT, anchor TEXT, created_at TEXT
);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


class ReadingVitalityTests(unittest.TestCase):
    def test_highlight_daily_cap_and_unique_anchor(self) -> None:
        c = _conn()
        for i in range(8):
            c.execute(
                "INSERT INTO annotations(user_id,anchor,note,status,deleted,created_at) VALUES(1,?,?,?,?,?)",
                (f"2026-08-30#themes-p{i}", "", "accepted", 0, "2026-08-30T10:00:00"),
            )
        # same anchor twice same day — only once
        c.execute(
            "INSERT INTO annotations(user_id,anchor,note,status,deleted,created_at) VALUES(1,?,?,?,?,?)",
            ("2026-08-30#themes-p0", "", "accepted", 0, "2026-08-30T11:00:00"),
        )
        parts = rv.compute_reading_parts(c, 1, SETTINGS)
        self.assertEqual(parts["highlight"], 6 * 2)
        self.assertEqual(parts["note"], 0)

    def test_note_scores_higher_than_highlight(self) -> None:
        c = _conn()
        c.execute(
            "INSERT INTO annotations(user_id,anchor,note,status,deleted,created_at) VALUES(1,?,?,?,?,?)",
            ("2026-08-30#themes-p1", "这段让我想起知识库的边界问题。", "accepted", 0, "2026-08-30T10:00:00"),
        )
        parts = rv.compute_reading_parts(c, 1, SETTINGS)
        self.assertEqual(parts["note"], 8)
        self.assertEqual(parts["highlight"], 0)

    def test_comment_and_favorite_caps(self) -> None:
        c = _conn()
        for i in range(6):
            c.execute(
                "INSERT INTO comments(user_id,anchor,status,deleted,created_at) VALUES(2,?,?,?,?)",
                (f"2026-08-30#themes-p{i}", "accepted", 0, "2026-08-30T10:00:00"),
            )
            c.execute(
                "INSERT INTO favorites(user_id,anchor,created_at) VALUES(2,?,?)",
                (f"2026-08-30#themes-p{i}", "2026-08-30T10:00:00"),
            )
        parts = rv.compute_reading_parts(c, 2, SETTINGS)
        self.assertEqual(parts["comment"], 4 * 4)
        self.assertEqual(parts["favorite"], 5 * 1)

    def test_multi_person_same_anchor_bonus(self) -> None:
        c = _conn()
        c.execute(
            "INSERT INTO annotations(user_id,anchor,note,status,deleted,created_at) VALUES(1,?,?,?,?,?)",
            ("2026-08-25#themes-p2", "", "accepted", 0, "2026-08-30T10:00:00"),
        )
        c.execute(
            "INSERT INTO comments(user_id,anchor,status,deleted,created_at) VALUES(2,?,?,?,?)",
            ("2026-08-25#themes-p2", "accepted", 0, "2026-08-30T11:00:00"),
        )
        mine = rv.compute_reading_parts(c, 1, SETTINGS)
        other = rv.compute_reading_parts(c, 2, SETTINGS)
        self.assertEqual(mine["multi_highlight"], 2)
        self.assertEqual(other["multi_highlight"], 0)  # bonus only for highlighters

    def test_deleted_and_pending_do_not_score(self) -> None:
        c = _conn()
        c.execute(
            "INSERT INTO annotations(user_id,anchor,note,status,deleted,created_at) VALUES(1,?,?,?,?,?)",
            ("2026-08-30#themes-p1", "", "accepted", 1, "2026-08-30T10:00:00"),
        )
        c.execute(
            "INSERT INTO annotations(user_id,anchor,note,status,deleted,created_at) VALUES(1,?,?,?,?,?)",
            ("2026-08-30#themes-p2", "", "pending", 0, "2026-08-30T10:00:00"),
        )
        parts = rv.compute_reading_parts(c, 1, SETTINGS)
        self.assertEqual(parts["highlight"], 0)

    def test_burst_discount(self) -> None:
        c = _conn()
        for i in range(20):
            c.execute(
                "INSERT INTO annotations(user_id,anchor,note,status,deleted,created_at) VALUES(1,?,?,?,?,?)",
                (f"2026-08-30#themes-p{i}", "", "accepted", 0, "2026-08-30T10:00:00"),
            )
        parts = rv.compute_reading_parts(c, 1, SETTINGS)
        self.assertEqual(parts["highlight"], int(6 * 2 * 0.3))

    def test_merge_replaces_legacy_annotation(self) -> None:
        merged = rv.merge_reading_into_parts(
            {"annotation": 10, "message": 3},
            {"highlight": 4, "note": 8, "comment": 0, "favorite": 1, "multi_highlight": 0},
        )
        self.assertNotIn("annotation", merged)
        self.assertEqual(merged["highlight"], 4)
        self.assertEqual(merged["message"], 3)

    def test_heatmap_is_counts_only_no_identity_no_note(self) -> None:
        rows = [
            {"anchor": "d#p1", "quote": "句子甲", "user_id": 1, "note": "秘密想法"},
            {"anchor": "d#p1", "quote": "句子甲", "user_id": 2, "note": "另一条笔记"},
            {"anchor": "d#p1", "quote": "句子乙较短", "user_id": 3, "note": ""},
            {"anchor": "d#p2", "quote": "独句", "user_id": 1, "note": "不该出现"},
        ]
        anon = rv.build_heatmap(rows, me_id=None)
        self.assertNotIn("mine", anon)
        blob = str(anon)
        self.assertNotIn("秘密", blob)
        self.assertNotIn("笔记", blob)
        self.assertNotIn("user", blob)
        self.assertEqual(anon["items"][0]["anchor"], "d#p1")
        self.assertEqual(anon["items"][0]["count"], 3)
        self.assertEqual(anon["items"][0]["quote"], "句子甲")  # 两人划过，压过一人的乙
        logged = rv.build_heatmap(rows, me_id=1)
        self.assertIn("mine", logged)
        self.assertEqual({(m["anchor"], m["quote"]) for m in logged["mine"]}, {("d#p1", "句子甲"), ("d#p2", "独句")})
        self.assertTrue(all(set(item) <= {"anchor", "count", "quote"} for item in logged["items"]))


if __name__ == "__main__":
    unittest.main()
