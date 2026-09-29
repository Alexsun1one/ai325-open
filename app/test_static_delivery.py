import unittest
import tempfile
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import FileResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

from app.static_delivery import PublicStaticDeliveryMiddleware


PAYLOAD = b'const reusable = "static asset content";\n' * 4000


def asset(request):
    path = request.url.path
    if 'missing' in path:
        return Response('<html>fallback</html>', media_type='text/html')
    if 'denied' in path:
        return Response('denied', status_code=403)
    if request.headers.get('range'):
        return Response(PAYLOAD[:100], status_code=206, headers={'Content-Range': f'bytes 0-99/{len(PAYLOAD)}'}, media_type='text/javascript')
    if request.headers.get('if-none-match'):
        return Response(status_code=304)
    return Response(PAYLOAD, media_type='text/javascript', headers={'ETag': '"test-content-hash"'})


class StaticDeliveryTest(unittest.TestCase):
    def test_webp_file_response_has_portable_image_type(self):
        with tempfile.TemporaryDirectory() as directory:
            artwork = Path(directory) / 'learning-ascent.webp'
            artwork.write_bytes(b'RIFF\x00\x00\x00\x00WEBP')
            app = Starlette(routes=[Route('/brand/learning-ascent.webp', lambda request: FileResponse(artwork))])
            app.add_middleware(PublicStaticDeliveryMiddleware)
            response = TestClient(app).get('/brand/learning-ascent.webp')
            self.assertEqual(response.headers['content-type'], 'image/webp')
            self.assertEqual(response.content, artwork.read_bytes())

    def setUp(self):
        app = Starlette(routes=[Route('/{path:path}', asset)])
        app.add_middleware(PublicStaticDeliveryMiddleware)
        self.client = TestClient(app)

    def test_compression_roundtrip_and_cache(self):
        response = self.client.get('/_next/static/chunks/hash.js', headers={'Accept-Encoding': 'gzip'})
        self.assertEqual(response.content, PAYLOAD)
        self.assertEqual(response.headers['content-encoding'], 'gzip')
        self.assertLess(int(response.headers['content-length']), len(PAYLOAD) // 10)
        self.assertIn('immutable', response.headers['cache-control'])
        self.assertIn('Accept-Encoding', response.headers['vary'])
        self.assertTrue(response.headers['etag'].startswith('W/'))

    def test_api_is_not_compressed_or_publicly_cached(self):
        response = self.client.get('/api/auth/me', headers={'Accept-Encoding': 'gzip'})
        self.assertNotIn('content-encoding', response.headers)
        self.assertNotIn('cache-control', response.headers)

    def test_book_notes_index_gzip_no_cache_content_identical(self):
        # /book-notes/index.json 是公开前缀内大 JSON：必须走 gzip 且 no-cache、内容一致
        response = self.client.get('/book-notes/index.json', headers={'Accept-Encoding': 'gzip'})
        self.assertEqual(response.headers['content-encoding'], 'gzip')
        self.assertEqual(response.headers['cache-control'], 'no-cache')
        self.assertEqual(response.content, PAYLOAD)
        # 详情页同 /readings/ 待遇：压缩 + no-cache
        page = self.client.get('/book-notes/sample-book/', headers={'Accept-Encoding': 'gzip'})
        self.assertEqual(page.headers['content-encoding'], 'gzip')
        self.assertEqual(page.headers['cache-control'], 'no-cache')
        self.assertEqual(page.content, PAYLOAD)

    def test_public_learning_pages_compress_but_revalidate(self):
        for path in ('/', '/learn/', '/learn/entries/kb-01/', '/learn/topics/kb-governance/', '/community/', '/skills/', '/arsenal/', '/agents/', '/readings/', '/readings/sample/'):
            with self.subTest(path=path):
                response = self.client.get(path, headers={'Accept-Encoding': 'gzip'})
                self.assertEqual(response.content, PAYLOAD)
                self.assertEqual(response.headers['content-encoding'], 'gzip')
                self.assertEqual(response.headers['cache-control'], 'no-cache')

    def test_quality_zero_and_range_are_not_compressed(self):
        response = self.client.get('/_next/static/chunks/hash.js', headers={'Accept-Encoding': 'gzip;q=0'})
        self.assertNotIn('content-encoding', response.headers)
        self.assertEqual(response.content, PAYLOAD)
        response = self.client.get('/_next/static/chunks/hash.js', headers={'Accept-Encoding': 'gzip', 'Range': 'bytes=0-99'})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, PAYLOAD[:100])
        self.assertNotIn('content-encoding', response.headers)

    def test_html_fallback_and_errors_are_not_immutable(self):
        response = self.client.get('/_next/static/chunks/missing.js')
        self.assertEqual(response.headers['cache-control'], 'no-cache')
        response = self.client.get('/_next/static/chunks/denied.js')
        self.assertNotIn('cache-control', response.headers)

    def test_catalog_revalidates_and_fonts_stay_binary(self):
        response = self.client.get('/skills/catalog.json')
        self.assertEqual(response.headers['cache-control'], 'no-cache')
        response = self.client.get('/fonts/nss/400/hash.woff2')
        self.assertIn('immutable', response.headers['cache-control'])
        self.assertNotIn('content-encoding', response.headers)

    def test_not_modified_keeps_cache_policy(self):
        response = self.client.get('/_next/static/chunks/hash.js', headers={'If-None-Match': '"test-content-hash"'})
        self.assertEqual(response.status_code, 304)
        self.assertIn('immutable', response.headers['cache-control'])


if __name__ == '__main__':
    unittest.main()
