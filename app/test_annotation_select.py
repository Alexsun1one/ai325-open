import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent


class AnnotationSelectSQLiteRegressionTest(unittest.TestCase):
    def test_avatar_lookup_does_not_correlate_from_scalar_subquery_order_by(self):
        """SQLite must support username lookup, display-name fallback, and no match."""
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
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            script = textwrap.dedent(
                """
                import datetime
                import main

                conn = main.db()
                now = datetime.datetime.now(main.CST).isoformat()

                def add_user(username, display_name):
                    cursor = conn.execute(
                        "INSERT INTO users(username,password_hash,role,display_name,created_at) "
                        "VALUES(?,?,?,?,?)",
                        (username, "hash", "member", display_name, now),
                    )
                    return cursor.lastrowid

                def add_annotation(user_id, username):
                    cursor = conn.execute(
                        "INSERT INTO annotations("
                        "user_id,username,date,anchor,quote,note,kind,visibility,"
                        "created_at,updated_at,deleted,status"
                        ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            user_id, username, "2026-08-23", "p-1", "quote", "note",
                            "comment", "public", now, now, 0, "accepted",
                        ),
                    )
                    return cursor.lastrowid

                direct_id = add_user("direct-user", "Direct Display")
                fallback_id = add_user("fallback-user", "Fallback Display")
                missing_id = add_user("missing-user", "Missing Display")
                conn.executemany(
                    "INSERT INTO members(username,display,avatar) VALUES(?,?,?)",
                    (
                        ("direct-user", "Different Display", "/direct.png"),
                        ("profile-fallback", "Fallback Display", "/fallback.png"),
                    ),
                )
                annotation_ids = (
                    add_annotation(direct_id, "direct-user"),
                    add_annotation(fallback_id, "fallback-user"),
                    add_annotation(missing_id, "missing-user"),
                )
                conn.commit()

                rows = conn.execute(
                    main.annotation_select("a.id IN (?,?,?)") + " ORDER BY a.id",
                    annotation_ids,
                ).fetchall()
                assert [row["avatar"] for row in rows] == [
                    "/direct.png", "/fallback.png", None
                ]
                conn.close()
                """
            )

            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=APP_DIR,
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
            )
            self.assertEqual(
                result.returncode,
                0,
                f"SQLite regression subprocess failed:\n{result.stdout}{result.stderr}",
            )


if __name__ == "__main__":
    unittest.main()
