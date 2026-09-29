"""Local HTTP acceptance for new agent tools: discussions/profile/comment --reply-to."""
import asyncio
import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
AGENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AGENT_DIR))

TOKEN = "test-only-token"

captured: list[dict] = []


class _Handler(BaseHTTPRequestHandler):
    def _send(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        request = urlparse(self.path)
        captured.append({"method": "GET", "path": request.path,
                         "query": parse_qs(request.query),
                         "auth": self.headers.get("Authorization")})
        if request.path == "/discuss/directory.json":
            self._send({"items": [
                {"id": "j1", "kind": "journey", "title": "人民需要AI群",
                 "url": "/journey/", "anchor": "article:journey:people-need-ai", "date": "2026-09-22"},
                {"id": "r1", "kind": "reading", "title": "精读一篇",
                 "url": "/readings/r1/", "anchor": "article:reading:r1", "date": "2026-09-20"},
                {"id": "k1", "kind": "knowledge", "title": "AI 学习法",
                 "url": "/learn/entries/k1/", "anchor": "article:knowledge:k1", "date": "2026-09-21"},
            ], "count": 3, "total": 3})
            return
        self._send({"detail": "not found"})

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        captured.append({"method": "POST", "path": urlparse(self.path).path,
                         "body": payload, "auth": self.headers.get("Authorization")})
        self._send({"id": 7, "anchor": payload.get("anchor"), "status": "pending"})

    def do_PATCH(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length) or b"{}")
        captured.append({"method": "PATCH", "path": urlparse(self.path).path,
                         "body": payload, "auth": self.headers.get("Authorization")})
        self._send({"id": 1, "avatar_key": payload.get("avatar_key", ""),
                    "display_name": payload.get("display_name", "x")})

    def log_message(self, *_args):
        return


class AgentToolsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.env = os.environ | {"AI325_BASE_URL": cls.base, "AI325_TOKEN": TOKEN}

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join(timeout=3)

    def setUp(self):
        captured.clear()

    def cli(self, *argv):
        return subprocess.run([sys.executable, "agent/ai325.py", *argv, "--json"],
                              cwd=ROOT, env=self.env, capture_output=True, text=True, timeout=15)

    def test_discussions_public_client_filter(self):
        # 静态目录不带 query；客户端按 kind/q 过滤、offset/limit 切页
        result = self.cli("discussions", "--kind", "journey", "--limit", "5")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["total"], 1)  # 3 条 fixture 中仅 1 条 journey
        self.assertEqual(data["items"][0]["anchor"], "article:journey:people-need-ai")
        req = captured[-1]
        self.assertEqual(req["path"], "/discuss/directory.json")
        self.assertEqual(req["query"], {})  # 静态文件不接收 query
        self.assertIsNone(req["auth"])  # 公开目录不带 token
        # 关键词过滤 + 分页
        data = json.loads(self.cli("discussions", "--q", "AI").stdout)
        self.assertEqual(data["total"], 2)  # 人民需要AI群 + AI 学习法
        data = json.loads(self.cli("discussions", "--limit", "1", "--offset", "1").stdout)
        self.assertEqual(data["count"], 1) and self.assertTrue(data["has_more"])
        self.assertEqual(data["total"], 3)
        # CLI 校验
        self.assertEqual(self.cli("discussions", "--limit", "0").returncode, 1)
        self.assertEqual(self.cli("discussions", "--limit", "101").returncode, 1)
        self.assertEqual(self.cli("discussions", "--offset", "-1").returncode, 1)
        self.assertEqual(self.cli("discussions", "--kind", "bad").returncode, 2)  # argparse choices

    def test_profile_patch_and_whitelist(self):
        result = self.cli("profile", "--avatar", "owl", "--display-name", "新名")
        self.assertEqual(result.returncode, 0, result.stderr)
        req = captured[-1]
        self.assertEqual((req["method"], req["path"]), ("PATCH", "/api/agent/profile"))
        self.assertEqual(req["body"], {"avatar_key": "owl", "display_name": "新名"})
        self.assertEqual(req["auth"], f"Bearer {TOKEN}")
        # 非法头像本地即拒（不发请求）
        bad = self.cli("profile", "--avatar", "http://evil")
        self.assertEqual(bad.returncode, 1)
        self.assertIn("头像", bad.stderr)
        self.assertEqual(len([c for c in captured if c["method"] == "PATCH"]), 1)
        # 空更新本地即拒
        empty = self.cli("profile")
        self.assertEqual(empty.returncode, 1)
        self.assertIn("至少提供一个名片字段", empty.stderr)

    def test_comment_reply_to_passthrough(self):
        result = self.cli("comment", "article:journey:people-need-ai", "回一条", "--date", "2026-09-22", "--reply-to", "42")
        self.assertEqual(result.returncode, 0, result.stderr)
        req = captured[-1]
        self.assertEqual(req["body"]["reply_to"], 42)
        self.assertEqual(req["body"]["anchor"], "article:journey:people-need-ai")

    def test_comment_article_anchor_uses_directory_date(self):
        # article:* 锚点不给 --date：从目录解析真实 date，不回落最新日报
        result = self.cli("comment", "article:journey:people-need-ai", "文章级评论")
        self.assertEqual(result.returncode, 0, result.stderr)
        post = [c for c in captured if c["method"] == "POST"][-1]
        self.assertEqual(post["body"]["date"], "2026-09-22")  # fixture 真实日期
        # 目录找不到锚点 → 明确要求 --date
        missing = self.cli("comment", "article:knowledge:nope", "找不到锚点")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("--date", missing.stderr)

    def test_mcp_tools(self):
        import types
        from unittest.mock import AsyncMock, patch
        try:
            from mcp.server.fastmcp import FastMCP as _FastMCP  # noqa: F401
        except ModuleNotFoundError:
            class _FastMCP:
                def __init__(self, *_a, **_k): pass
                def tool(self, *_a, **_k): return lambda f: f
            mcp_module = types.ModuleType('mcp')
            server_module = types.ModuleType('mcp.server')
            fastmcp_module = types.ModuleType('mcp.server.fastmcp')
            fastmcp_module.FastMCP = _FastMCP
            sys.modules.update({'mcp': mcp_module, 'mcp.server': server_module,
                                'mcp.server.fastmcp': fastmcp_module})
        from agent import mcp_server as server  # noqa: E402

        async def run_all():
            fixture = {'items': [
                {'id': 'j1', 'kind': 'journey', 'title': '人民需要AI群',
                 'anchor': 'article:journey:people-need-ai', 'date': '2026-09-22'},
                {'id': 'r1', 'kind': 'reading', 'title': '精读一篇',
                 'anchor': 'article:reading:r1', 'date': '2026-09-20'},
                {'id': 'k1', 'kind': 'knowledge', 'title': 'AI 学习法',
                 'anchor': 'article:knowledge:k1', 'date': '2026-09-21'},
            ], 'total': 3}
            with patch.object(server, '_request', AsyncMock(return_value=fixture)) as req:
                out = await server.list_discussion_targets(kind='journey', limit=5)
                args, kwargs = req.call_args
                assert args[:2] == ('GET', '/discuss/directory.json')
                assert kwargs.get('authenticated') in (None, False)
                assert kwargs.get('params') is None  # 静态文件不传 query
                assert out['total'] == 1 and out['count'] == 1 and not out['has_more']
                out = await server.list_discussion_targets(query='AI', limit=10)
                assert out['total'] == 2, out
                out = await server.list_discussion_targets(limit=1, offset=1)
                assert out['total'] == 3 and out['has_more'] and out['items'][0]['id'] == 'r1'
                with self.assertRaises(Exception):
                    await server.list_discussion_targets(kind='bad')
            with patch.object(server, '_request', AsyncMock(return_value={'avatar_key': 'spark'})) as req:
                await server.set_agent_profile(avatar_key='spark', display_name='M')
                _, kwargs = req.call_args
                assert kwargs['json_body'] == {'avatar_key': 'spark', 'display_name': 'M'}
                assert kwargs['authenticated'] is True
            with self.assertRaises(Exception):
                await server.set_agent_profile(avatar_key='bad')
            with self.assertRaises(Exception):
                await server.set_agent_profile()
            with patch.object(server, '_request', AsyncMock(return_value={'id': 7})) as req:
                await server.post_comment(anchor='article:knowledge:k1', date='2026-09-23',
                                          text='回复', reply_to=9)
                assert req.call_args.kwargs['json_body']['reply_to'] == 9
            # reply_question reply_to 透传（同串引用，后端校验归属）
            with patch.object(server, '_request', AsyncMock(return_value={'ok': True})) as req:
                await server.reply_question(thread_id=3, text='接话', reply_to=11)
                assert req.call_args.kwargs['json_body'] == {'text': '接话', 'reply_to': 11}
                await server.reply_question(thread_id=3, text='不接话')
                assert req.call_args.kwargs['json_body'] == {'text': '不接话'}
        asyncio.run(run_all())


if __name__ == "__main__":
    unittest.main()
