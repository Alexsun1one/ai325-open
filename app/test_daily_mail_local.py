"""send-daily-mail-local + daily_mail_state 的离线回归测试。

全程 mock send/remote：不发真实邮件、不 SSH、不读凭证。
覆盖：先 sent 后 ack、ack 失败下轮只补 ack、uncertain 不重发、
failed 可重试、远端 sent 去重、订阅名单读失败一封不发、邮箱脱敏。
"""
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts/ops"))
from daily_mail_state import Journal, classify_error  # noqa: E402

spec = importlib.util.spec_from_file_location("sdml", REPO / "scripts/send-daily-mail-local.py")
sdml = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sdml)


def targets(*pairs):
    return [{"id": i, "email": e} for i, e in pairs]


class DailyMailStateTest(unittest.TestCase):
    def test_journal_states_and_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            j = Journal(td)
            j.record("批A", "1", "sent")
            j.record("批A", "2", "uncertain", "TimeoutExpired")
            j.record("批A", "1", "acked")
            j.close()
            j2 = Journal(td)  # 重开持久化
            self.assertEqual(j2.get("批A", "1"), "acked")
            self.assertEqual(j2.get("批A", "2"), "uncertain")
            self.assertEqual(j2.get("批A", "9"), "")
            j2.close()

    def test_classify_error(self):
        # 白名单：确定未发出才 failed
        self.assertEqual(classify_error("invalid_recipient"), "failed:invalid_recipient")
        self.assertEqual(classify_error("invalid_subject"), "failed:invalid_subject")
        self.assertEqual(classify_error("confirmation_token_missing"), "failed:confirmation_token_missing")
        # 其余全 uncertain：传输异常/服务端错误名/未知都可能确认已到达
        for et in ("TimeoutExpired", "CalledProcessError", "OSError",
                   "rate_limited", "agently_send_failed", "unknown", ""):
            self.assertEqual(classify_error(et), "uncertain", et)


class DeliverTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.journal = Journal(self.td.name)
        self.addCleanup(self.journal.close)
        self.addCleanup(self.td.cleanup)
        self.subj = "先锋队台账 · 第 001 批 · 测试"
        self.ts = targets((1, "aa@x.example"), (2, "bb@y.example"))

    def send_ok(self, email, subject, body):
        return True, ""

    def remote_ok(self, code):
        return ""

    def test_send_then_ack_persisted(self):
        # 断言每次调 transport 前该收件人 pending 已 durable 落盘
        states = []
        def send_checks_pending(email, subject, body):
            states.append(self.journal.get(self.subj, "1" if email.startswith("aa") else "2"))
            return True, ""
        c = sdml.deliver(self.ts, self.subj, "b", self.journal,
                         send=send_checks_pending, remote=self.remote_ok, pause=0)
        self.assertEqual(states, ["pending", "pending"])
        self.assertEqual((c["sent"], c["acked"]), (2, 2))
        self.assertEqual(self.journal.get(self.subj, "1"), "acked")

    def test_ack_failure_only_reacks_no_resend(self):
        calls = []
        def flaky_remote(code):
            calls.append(code)
            raise RuntimeError("ssh down")
        c = sdml.deliver(self.ts, self.subj, "b", self.journal,
                         send=self.send_ok, remote=flaky_remote, pause=0)
        self.assertEqual((c["sent"], c["acked"], c["ack_failed"]), (2, 0, 2))
        # 第二轮：send 不再被调，只补 ack
        sends = []
        c2 = sdml.deliver(self.ts, self.subj, "b", self.journal,
                          send=lambda *a: sends.append(a) or (True, ""),
                          remote=self.remote_ok, pause=0)
        self.assertEqual(sends, [])
        self.assertEqual(c2["acked"], 2)

    def test_uncertain_never_resent(self):
        c = sdml.deliver(self.ts[:1], self.subj, "b", self.journal,
                         send=lambda *a: (False, "TimeoutExpired"), remote=self.remote_ok, pause=0)
        self.assertEqual(c["uncertain"], 1)
        sends = []
        sdml.deliver(self.ts[:1], self.subj, "b", self.journal,
                     send=lambda *a: sends.append(a) or (True, ""),
                     remote=self.remote_ok, pause=0)
        self.assertEqual(sends, [])  # uncertain 不自动重发

    def test_failed_retries_and_remote_dedup(self):
        # failed: 可重试
        c = sdml.deliver(self.ts[:1], self.subj, "b", self.journal,
                         send=lambda *a: (False, "invalid_recipient"), remote=self.remote_ok, pause=0)
        self.assertEqual(c["failed"], 1)
        sends = []
        sdml.deliver(self.ts[:1], self.subj, "b", self.journal,
                     send=lambda *a: sends.append(a) or (True, ""),
                     remote=self.remote_ok, pause=0)
        self.assertEqual(len(sends), 1)
        # 远端已 sent → 本地 reconcile 成 acked，不发
        c = sdml.deliver(self.ts[1:], self.subj, "b", self.journal,
                         send=lambda *a: sends.append(a) or (True, ""),
                         remote=self.remote_ok, remote_sent={2}, pause=0)
        self.assertEqual(c["dup_remote"], 1)
        self.assertEqual(self.journal.get(self.subj, "2"), "acked")

    def test_crash_residue_pending_becomes_uncertain(self):
        # 模拟 send 成功返回后进程死在 record(sent) 之前：journal 只留 pending
        self.journal.record(self.subj, "1", "pending")
        sends = []
        c = sdml.deliver(self.ts[:1], self.subj, "b", self.journal,
                         send=lambda *a: sends.append(a) or (True, ""),
                         remote=self.remote_ok, pause=0)
        self.assertEqual(sends, [])           # 不盲重发
        self.assertEqual(c["uncertain"], 1)
        self.assertEqual(self.journal.get(self.subj, "1"), "uncertain")

    def test_journal_stores_no_raw_email(self):
        # --to 手动目标（id=None）键为哈希、只本地回执（remote 零调用），落盘无地址
        remote_calls = []
        sdml.deliver([{"id": None, "email": "real.person@example.org"}], self.subj, "b",
                     self.journal, send=self.send_ok,
                     remote=lambda c: remote_calls.append(c), pause=0)
        self.assertEqual(remote_calls, [])
        raw = (Path(self.td.name) / "journal.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("real.person@example.org", raw)
        self.assertNotIn("@", raw)

    def test_mask_email(self):
        self.assertEqual(sdml.mask_email("someone@example.com"), "s***@e***")
        self.assertNotIn("example.com", sdml.mask_email("a@example.com"))


class AckAndMainTest(unittest.TestCase):
    def test_ack_sql_idempotent_on_real_sqlite(self):
        # 真实执行 ack_recipient 生成的代码两遍（模拟远端 commit 成功但回包丢失后重试）→ 只一行
        with tempfile.TemporaryDirectory() as td:
            dbp = Path(td) / "xf.db"
            c = sqlite3.connect(dbp)
            c.execute("CREATE TABLE email_log(id INTEGER PRIMARY KEY AUTOINCREMENT, "
                      "subscriber_id INT, subject TEXT, sent_at TEXT, status TEXT)")
            c.commit(); c.close()
            captured = []
            sdml.ack_recipient(7, "批B", "2026-09-30T08:00:00+08:00",
                               remote=lambda code: captured.append(code))
            code = captured[0].replace("/data/xf.db", str(dbp))
            for _ in range(2):
                r = subprocess.run([sys.executable, "-c", code],
                                   capture_output=True, text=True, timeout=30)
                self.assertEqual(r.returncode, 0, r.stderr)
            c = sqlite3.connect(dbp)
            self.assertEqual(
                c.execute("SELECT COUNT(*) FROM email_log WHERE subscriber_id=7 AND subject='批B'").fetchone()[0], 1)
            c.close()

    def test_main_ack_failed_nonzero(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "site/content/ledgers"
            ledger.mkdir(parents=True)
            (ledger / "2026-09-30.json").write_text(json.dumps({
                "title": "t", "issue": 1, "lead": "l", "quality": {"overall": 0},
            }), encoding="utf-8")
            fake_counts = {"sent": 1, "acked": 0, "failed": 0, "uncertain": 0,
                           "dup_remote": 0, "ack_failed": 1}
            with mock.patch.object(sdml, "REPO", Path(td)), \
                 mock.patch.object(sdml, "fetch_subscribers", return_value={"subs": [], "sent": []}), \
                 mock.patch.object(sdml, "Journal", return_value=mock.MagicMock()), \
                 mock.patch.object(sdml, "deliver", return_value=fake_counts), \
                 mock.patch.object(sys, "argv", ["x", "--date", "2026-09-30"]):
                self.assertEqual(sdml.main(), 1)

    def test_journal_flock_excludes_second_opener(self):
        with tempfile.TemporaryDirectory() as td:
            j1 = Journal(td)
            probe = ("import sys;sys.path.insert(0,%r);"
                     "from daily_mail_state import Journal;Journal(%r).close();print('ok')"
                     % (str(REPO / "scripts/ops"), td))
            with self.assertRaises(subprocess.TimeoutExpired):
                subprocess.run([sys.executable, "-c", probe],
                               capture_output=True, text=True, timeout=3)
            j1.close()
            r = subprocess.run([sys.executable, "-c", probe],
                               capture_output=True, text=True, timeout=10)
            self.assertEqual(r.returncode, 0, r.stderr)


class MainGuardsTest(unittest.TestCase):
    def test_subscriber_fetch_failure_sends_nothing(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "site/content/ledgers"
            ledger.mkdir(parents=True)
            (ledger / "2026-09-30.json").write_text(json.dumps({
                "title": "t", "issue": 1, "lead": "l", "quality": {"overall": 0},
            }), encoding="utf-8")
            with mock.patch.object(sdml, "REPO", Path(td)), \
                 mock.patch.object(sdml, "fetch_subscribers", side_effect=RuntimeError("ssh")), \
                 mock.patch.object(sdml, "agently_send") as send, \
                 mock.patch.object(sdml, "Journal", return_value=mock.MagicMock()), \
                 mock.patch.object(sys, "argv", ["x", "--date", "2026-09-30"]):
                self.assertEqual(sdml.main(), 2)
                send.assert_not_called()

    def test_dry_run_zero_network(self):
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "site/content/ledgers"
            ledger.mkdir(parents=True)
            (ledger / "2026-09-30.json").write_text(json.dumps({
                "title": "t", "issue": 1, "lead": "l", "quality": {"overall": 0},
            }), encoding="utf-8")
            with mock.patch.object(sdml, "REPO", Path(td)), \
                 mock.patch.object(sdml, "fetch_subscribers") as fetch, \
                 mock.patch.object(sdml, "remote_py") as remote, \
                 mock.patch.object(sdml, "agently_send") as send, \
                 mock.patch.object(sys, "argv", ["x", "--date", "2026-09-30", "--dry-run"]):
                self.assertEqual(sdml.main(), 0)
                fetch.assert_not_called(); remote.assert_not_called(); send.assert_not_called()


class SshRouteTest(unittest.TestCase):
    """ssh_route + 两调用方的 fake-ssh fixture：默认直连、env 注入 ProxyCommand、失败显式报错。"""

    def _load_route(self):
        spec = importlib.util.spec_from_file_location("ssh_route", REPO / "scripts/ops/ssh_route.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_default_direct_no_proxy(self):
        route = self._load_route()
        with mock.patch.dict("os.environ", {}, clear=True):
            argv = route.ssh_argv("root@fuidc-hk")
        self.assertEqual(argv[:3], ["ssh", "-o", "BatchMode=yes"])
        self.assertEqual(argv[-1], "root@fuidc-hk")
        self.assertFalse(any("ProxyCommand" in a for a in argv), argv)

    def test_env_proxy_injects_proxycommand(self):
        route = self._load_route()
        with mock.patch.dict("os.environ", {"AI325_SSH_PROXY": "nc -X connect -x 127.0.0.1:7897 %h %p"}):
            argv = route.ssh_argv("root@fuidc-hk")
        joined = " ".join(argv)
        self.assertIn("ProxyCommand=nc -X connect -x 127.0.0.1:7897 %h %p", joined)

    def test_remote_py_uses_route_and_reports_nonzero(self):
        route = self._load_route()
        with mock.patch.dict("os.environ", {"AI325_SSH_PROXY": "nc -X connect -x 127.0.0.1:7897 %h %p"}), \
             mock.patch.object(sdml.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=255, stdout="")
            with self.assertRaises(RuntimeError):
                sdml.remote_py("print(1)")
        argv = run.call_args[0][0]
        self.assertTrue(any("ProxyCommand=nc -X connect" in a for a in argv), argv)
        self.assertIn("docker exec -i xfsite python3 -", argv)

    def test_courier_remote_call_uses_route_and_reports_nonzero(self):
        spec = importlib.util.spec_from_file_location("courier", REPO / "scripts/ops/alert-courier-local.py")
        courier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(courier)
        args = mock.Mock(ssh_target="root@fuidc-hk", remote_script="/opt/x/r.py", remote_outbox="/opt/x/ob")
        with mock.patch.dict("os.environ", {"AI325_SSH_PROXY": "nc -X connect -x 127.0.0.1:7897 %h %p"}), \
             mock.patch.object(courier.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="[]")
            self.assertEqual(courier.remote_call(args, "claim"), [])
        argv = run.call_args[0][0]
        self.assertTrue(any("ProxyCommand=nc -X connect" in a for a in argv), argv)
        self.assertIn("claim", argv)
        run.return_value = mock.Mock(returncode=255, stdout="")
        with self.assertRaises(RuntimeError) as ctx:
            courier.remote_call(args, "claim")
        self.assertIn("255", str(ctx.exception))

    def test_courier_remote_call_direct_default(self):
        spec = importlib.util.spec_from_file_location("courier", REPO / "scripts/ops/alert-courier-local.py")
        courier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(courier)
        args = mock.Mock(ssh_target="root@fuidc-hk", remote_script="/opt/x/r.py", remote_outbox="/opt/x/ob")
        with mock.patch.dict("os.environ", {}, clear=True), \
             mock.patch.object(courier.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="[]")
            courier.remote_call(args, "claim")
        self.assertFalse(any("ProxyCommand" in a for a in run.call_args[0][0]))

    def test_remote_py_direct_argv_compatible(self):
        with mock.patch.dict("os.environ", {}, clear=True), \
             mock.patch.object(sdml.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="{}")
            self.assertEqual(sdml.remote_py("print(1)"), "{}")
        argv = run.call_args[0][0]
        self.assertFalse(any("ProxyCommand" in a for a in argv), argv)
        self.assertEqual(argv[:4], ["ssh", "-o", "BatchMode=yes", "-o"])


if __name__ == "__main__":
    unittest.main()
