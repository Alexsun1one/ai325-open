"""Local read-only HTTP acceptance coverage for the public learning CLI."""
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


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        request = urlparse(self.path)
        if request.path != "/api/public/learning":
            self.send_response(404); self.end_headers(); return
        query = parse_qs(request.query)
        assert query == {"q": ["验证"], "kind": ["knowledge"], "limit": ["1"], "offset": ["0"]}
        body = json.dumps({"items": [{"id": "knowledge-evidence", "kind": "knowledge", "title": "验证优先"}], "total": 1, "has_more": False, "next_offset": None}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def log_message(self, *_args):
        return


class PublicLearningCliTest(unittest.TestCase):
    def test_search_uses_local_read_only_public_api(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = os.environ | {"AI325_BASE_URL": f"http://127.0.0.1:{server.server_port}"}
            result = subprocess.run(
                [sys.executable, "agent/ai325.py", "learning", "search", "验证", "--kind", "knowledge", "--limit", "1", "--json"],
                cwd=ROOT, env=env, capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["items"][0]["id"], "knowledge-evidence")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)
