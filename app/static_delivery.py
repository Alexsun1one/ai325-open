"""Versioned public asset caching and compression; API responses bypass this layer."""
import mimetypes
from pathlib import PurePosixPath

from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Minimal container images may lack the system MIME database entry for WebP.
# FileResponse consults this registry when serving the exported brand artwork.
mimetypes.add_type('image/webp', '.webp')


class PublicStaticDeliveryMiddleware:
    PUBLIC_PAGES = {'', '/learn', '/community', '/skills', '/arsenal', '/agents', '/readings'}
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.compressed = GZipMiddleware(self._deliver, minimum_size=1024, compresslevel=5)

    async def _deliver(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def with_headers(message: Message) -> None:
            if message['type'] == 'http.response.start':
                headers = MutableHeaders(scope=message)
                content_type = headers.get('content-type', '').lower()
                if message['status'] in (200, 304) and 'text/html' not in content_type:
                    if scope['path'].startswith(('/_next/static/', '/fonts/')):
                        headers['cache-control'] = 'public, max-age=31536000, immutable'
                    else:
                        # Catalog and package names may be replaced by the next export.
                        headers['cache-control'] = 'no-cache'
                elif 'text/html' in content_type:
                    # The site's SPA fallback can answer a missing asset with HTML.
                    headers['cache-control'] = 'no-cache'
                if self._compressible(scope):
                    headers.add_vary_header('Accept-Encoding')
                    etag = headers.get('etag')
                    if etag and not etag.startswith('W/'):
                        headers['etag'] = f'W/{etag}'
            await send(message)

        await self.app(scope, receive, with_headers)

    @classmethod
    def _compressible(cls, scope: Scope) -> bool:
        return scope['path'].rstrip('/') in cls.PUBLIC_PAGES or scope['path'].startswith(('/learn/entries/', '/learn/topics/', '/readings/', '/book-notes/')) or PurePosixPath(scope['path']).suffix.lower() in {'.js', '.css', '.json', '.svg', '.txt', '.map'}

    @staticmethod
    def _accepts_gzip(value: str) -> bool:
        # Respect gzip;q=0 even though Starlette's default checks substrings only.
        for entry in value.lower().split(','):
            encoding, *parameters = entry.strip().split(';')
            if encoding != 'gzip':
                continue
            quality = 1.0
            for parameter in parameters:
                key, separator, raw = parameter.strip().partition('=')
                if key == 'q' and separator:
                    try:
                        quality = float(raw)
                    except ValueError:
                        return False
            return quality > 0
        return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http' or scope.get('method') not in ('GET', 'HEAD'):
            await self.app(scope, receive, send)
            return
        path = scope['path']
        if (path.rstrip('/') not in self.PUBLIC_PAGES and not path.startswith(('/_next/static/', '/fonts/', '/skills/', '/learn/', '/discover/', '/readings/', '/book-notes/', '/brand/'))) or '..' in PurePosixPath(path).parts:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        if self._compressible(scope) and 'range' not in headers and self._accepts_gzip(headers.get('accept-encoding', '')):
            await self.compressed(scope, receive, send)
        else:
            await self._deliver(scope, receive, send)
