import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

try:
    from mcp.server.fastmcp import FastMCP as _FastMCP  # noqa: F401
except ModuleNotFoundError:
    # Unit tests exercise our tool logic without requiring the optional stdio
    # runtime package; production still imports the documented mcp<2 package.
    class _FastMCP:
        def __init__(self, *_args, **_kwargs):
            pass

        def tool(self, *_args, **_kwargs):
            return lambda function: function

    mcp_module = types.ModuleType('mcp')
    server_module = types.ModuleType('mcp.server')
    fastmcp_module = types.ModuleType('mcp.server.fastmcp')
    fastmcp_module.FastMCP = _FastMCP
    sys.modules.update({'mcp': mcp_module, 'mcp.server': server_module, 'mcp.server.fastmcp': fastmcp_module})

from agent import mcp_server as server

class LearningToolsTest(unittest.IsolatedAsyncioTestCase):
    async def test_learning_session_uses_public_api_with_sources_and_no_write(self):
        public = {
            'items': [{
                'id': 'knowledge-evidence', 'kind': 'knowledge', 'title': '验证优先',
                'summary': '先做小实验。', 'url': '/learn/knowledge-evidence/',
                'date': '2026-09-22', 'tags': ['验证'],
                'sourceUrl': 'https://docs.python.org/3/', 'topicId': 'evidence',
            }],
            'total': 1, 'has_more': False, 'next_offset': None,
        }
        with patch.object(server, '_request', AsyncMock(return_value=public)) as request:
            data = await server.prepare_learning_session(question='验证', topic='evidence', limit=1)
            self.assertEqual(data['status'], 'ready')
            self.assertEqual(data['items'][0]['sourceUrl'], 'https://docs.python.org/3/')
            self.assertTrue(data['items'][0]['permalink'].endswith('/learn/knowledge-evidence/'))
            self.assertIn('实践卡', data['items'][0]['practice'])
            self.assertIn('未自动发帖', data['note'])
            request.assert_awaited_once_with('GET', '/api/public/learning', params={'q': '验证', 'topic': 'evidence', 'limit': 1, 'offset': 0})

    async def test_learning_session_empty_and_boundary_are_honest(self):
        with patch.object(server, '_request', AsyncMock(return_value={'items': [], 'total': 0, 'has_more': False})) as request:
            data = await server.prepare_learning_session(question='不存在')
            self.assertEqual(data['status'], 'no_matching_public_items')
            self.assertEqual(data['learning_steps'], [])
            request.assert_awaited_once_with('GET', '/api/public/learning', params={'q': '不存在', 'limit': 10, 'offset': 0})
        with self.assertRaises(server.AI325APIError):
            await server.prepare_learning_session(question='x' * 201)
        with self.assertRaises(server.AI325APIError):
            await server.prepare_learning_session(limit=101)
    async def test_shared_knowledge_filters_and_paginates_with_evidence(self):
        entries = [{'id': str(i), 'title': '验证', 'text': '先做实验', 'topicId':'evidence', 'sources':[{'date':'2026-09-17'}]} for i in range(3)]
        with patch.object(server, '_request', AsyncMock(return_value={'entries':entries,'topics':[], 'updatedAt':'2026-09-22'})) as request:
            data = await server.learn_knowledge(query='验证', topic='evidence', limit=1, offset=1)
            self.assertEqual(data['total'], 3)
            self.assertTrue(data['has_more'])
            self.assertEqual(data['items'][0]['id'], '1')
            self.assertTrue(data['items'][0]['sources'])
            request.assert_awaited_once_with('GET', '/learn/directory.json')
    async def test_skill_search_returns_full_count(self):
        items = [{'name':'pdf','description':'阅读文档','author':'official'} for _ in range(4)]
        with patch.object(server, '_request', AsyncMock(return_value={'items':items, 'generatedAt':'2026-09-22'})):
            data = await server.find_library_skills(query='pdf',limit=2,offset=2)
            self.assertEqual(data['total'], 4)
            self.assertFalse(data['has_more'])
            self.assertEqual(len(data['items']),2)
    async def test_discussion_topic_is_forwarded(self):
        with patch.object(server, '_request', AsyncMock(return_value={'items':[]})) as request:
            await server.list_questions(target='evidence', query='test', offset=20)
            self.assertEqual(request.call_args.kwargs['params']['target'], 'evidence')
            self.assertEqual(request.call_args.kwargs['params']['offset'], 20)
