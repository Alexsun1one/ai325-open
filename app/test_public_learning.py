"""Fixture-only acceptance tests for the anonymous public learning API."""
import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from app.test_product_performance import _env, _run


DIRECTORY = {
    "schemaVersion": 1,
    "updatedAt": "2026-09-22T12:00:00+08:00",
    "items": [
        {
            "id": "knowledge-escaping",
            "kind": "knowledge",
            "title": "<知识 & 证据>",
            "summary": "摘要含 <tag> & 字符，不能变成 RSS 标记。",
            "url": "/learn/knowledge-escaping/",
            "date": "2026-09-22",
            "tags": ["证据", "方法"],
            "sourceUrl": "https://example.com/source",
            "topicId": "evidence",
        },
        {
            "id": "skill-search",
            "kind": "skill",
            "title": "检索工具",
            "summary": "公开技能目录。",
            "url": "/skills/search/",
            "date": "2026-09-21",
            "tags": ["检索"],
            "topicId": "tools",
        },
        {
            "id": "knowledge-old",
            "kind": "knowledge",
            "title": "旧知识",
            "summary": "用于分页边界验证。",
            "url": "/learn/knowledge-old/",
            "date": "2026-09-20",
            "tags": ["证据"],
            "topicId": "evidence",
        },
    ],
}


class PublicLearningApiTest(unittest.TestCase):
    def test_public_directory_contract_and_failure_boundaries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "static" / "discover" / "directory.json"
            directory.parent.mkdir(parents=True)
            directory.write_text(json.dumps(DIRECTORY, ensure_ascii=False), encoding="utf-8")
            env = _env(root)
            result = _run(env, textwrap.dedent("""
                import json
                from pathlib import Path
                from starlette.testclient import TestClient
                import main

                static = Path(main.os.environ['XF_STATIC_DIR'])
                directory = static / 'discover' / 'directory.json'
                client = TestClient(main.app)

                page = client.get('/api/public/learning')
                assert page.status_code == 200, page.text
                data = page.json()
                assert data['total'] == 3 and data['items'][0]['id'] == 'knowledge-escaping', data
                assert page.headers['cache-control'].startswith('public, max-age=60')
                assert page.headers['last-modified'] and page.headers['etag']
                from email.utils import parsedate_to_datetime
                assert parsedate_to_datetime(page.headers['last-modified']).tzinfo is not None
                private = main.db()
                private.execute('CREATE TABLE private_probe(value TEXT)')
                private.execute("INSERT INTO private_probe(value) VALUES('never-public')")
                private.commit(); private.close()
                assert 'never-public' not in page.text
                assert client.get('/api/public/learning', params={'q': '检索', 'kind': 'skill'}).json()['total'] == 1
                assert client.get('/api/public/learning', params={'topic': 'evidence', 'since': '2026-09-21'}).json()['total'] == 1
                edge = client.get('/api/public/learning', params={'limit': 1, 'offset': 2}).json()
                assert edge['total'] == 3 and len(edge['items']) == 1 and not edge['has_more'] and edge['next_offset'] is None, edge
                assert client.get('/api/public/learning', params={'limit': 0}).status_code == 422
                assert client.get('/api/public/learning', params={'limit': 101}).status_code == 422
                assert client.get('/api/public/learning', params={'offset': -1}).status_code == 422
                assert client.get('/api/public/learning', params={'since': 'not-a-date'}).status_code == 422
                assert client.get('/api/public/learning/missing').status_code == 404

                not_modified = client.get('/api/public/learning', headers={'If-None-Match': page.headers['etag']})
                assert not_modified.status_code == 304 and not_modified.headers['etag'] == page.headers['etag']
                rss = client.get('/feed/learning.xml')
                assert rss.status_code == 200
                # charset=utf-8 必须显式：客户端把 application/rss+xml 当 text/plain 时中文不乱码
                assert rss.headers['content-type'] == 'application/rss+xml; charset=utf-8', rss.headers['content-type']
                from xml.etree import ElementTree as ET
                root = ET.fromstring(rss.content)
                assert '公开学习目录' in rss.content.decode('utf-8')  # UTF-8 中文字节可读
                # 304 条件请求同样带新 charset——旧缓存类型不沿用
                rss304 = client.get('/feed/learning.xml', headers={'If-None-Match': rss.headers['etag']})
                assert rss304.status_code == 304
                assert rss304.headers['content-type'] == 'application/rss+xml; charset=utf-8'
                # UTF-8 BOM 前缀存在且 XML 解析正常（bytes([..]) 防外层字符串转义）
                BOM = bytes([0xEF, 0xBB, 0xBF])
                assert rss.content.startswith(BOM), 'feed 缺 UTF-8 BOM'
                # feed ETag 独立于 JSON 目录 ETag：持旧目录 ETag 请求 feed → 200 重发含 BOM
                assert rss.headers['etag'] != page.headers['etag'], rss.headers['etag']
                stale = client.get('/feed/learning.xml', headers={'If-None-Match': page.headers['etag']})
                assert stale.status_code == 200 and stale.content.startswith(BOM)
                assert stale.headers['etag'] == rss.headers['etag']
                entries = root.findall('./channel/item')
                assert len(entries) == 2 and '<知识 & 证据>' == entries[0].findtext('title'), rss.text
                assert all('skill-search' not in (entry.findtext('guid') or '') for entry in entries)

                changed = json.loads(directory.read_text(encoding='utf-8'))
                changed['updatedAt'] = '2026-09-22T13:00:00+08:00'
                changed['items'].append({'id':'resource-new','kind':'resource','title':'新资源','summary':'已更新','url':'/resources/new/','date':'2026-09-22','tags':['新'],'topicId':'tools'})
                directory.write_text(json.dumps(changed, ensure_ascii=False), encoding='utf-8')
                assert client.get('/api/public/learning').json()['total'] == 4

                directory.unlink()
                unavailable = client.get('/api/public/learning')
                assert unavailable.status_code == 503 and 'static' not in unavailable.text and 'directory.json' not in unavailable.text
                directory.parent.mkdir(parents=True, exist_ok=True)
                directory.write_text('{bad', encoding='utf-8')
                assert client.get('/api/public/learning').status_code == 503
            """))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
