from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import admin_ops  # noqa: E402


class AdminOpsHelpersTest(unittest.TestCase):
    def test_identity_unresolved_matches_missing_wxid_not_named_collision(self) -> None:
        self.assertTrue(admin_ops.identity_unresolved(["missing_wxid"], "孙务远", "room_nickname"))
        self.assertFalse(admin_ops.identity_unresolved(["name_collision"], "孙务远②", "room_nickname"))
        self.assertTrue(admin_ops.identity_unresolved([], "wxid_raw0002", "masked_wxid"))

    def test_members_payload_counts_and_limit_label(self) -> None:
        with tempfile.TemporaryDirectory(prefix="admin-ops-api-") as root:
            db_path = Path(root) / "xf.db"
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.executescript(
                """
                CREATE TABLE members(username TEXT, display TEXT, nickname TEXT, msgs INT, last_active TEXT, name_source TEXT, identity_flags TEXT);
                CREATE TABLE users(id INT, username TEXT, display_name TEXT, member_key TEXT, last_login TEXT, active INT, role TEXT);
                CREATE TABLE agent_tokens(user_id INT, revoked INT);
                """
            )
            conn.execute("INSERT INTO members VALUES(?,?,?,?,?,?,?)", ("wxid_a", "甲", "甲", 10, "2026-08-31", "room_nickname", "[]"))
            conn.execute("INSERT INTO members VALUES(?,?,?,?,?,?,?)", ("wxid_b", "wxid_b", "", 1, "2026-08-01", "masked_wxid", '["missing_wxid"]'))
            conn.execute("INSERT INTO users VALUES(?,?,?,?,?,?,?)", (1, "jia", "甲", "wxid_a", "2026-08-31", 1, "member"))
            conn.commit()
            all_rows = admin_ops.members_payload(conn, date(2026, 8, 31), limit=200)
            self.assertEqual(all_rows["total"], 2)
            self.assertEqual(all_rows["filters"]["no_account"], 1)
            self.assertEqual(all_rows["filters"]["unresolved"], 1)
            self.assertEqual(all_rows["bulk_forbidden"], ["批量出认领链接"])
            none = admin_ops.members_payload(conn, date(2026, 8, 31), has_account=False)
            self.assertEqual(none["total"], 1)
            self.assertEqual(none["items"][0]["display"], "wxid_b")
            conn.close()


if __name__ == "__main__":
    unittest.main()
