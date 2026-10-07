"""Bounded official-article extraction. No arbitrary URLs, JS execution, or cookies."""
import ipaddress
import re
import socket
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from app.external_sources import clean_text, safe_http_url


class ArticleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scope = 0
        self.blocked = 0
        self.stack = []
        self.parts = []
        self.fallback = []
        self.paragraph = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('meta', 'link', 'img', 'br', 'hr', 'input', 'source', 'wbr', 'area', 'base', 'embed', 'param', 'track', 'col'):
            return
        attrs = dict(attrs)
        scope = tag in ('main', 'article') or attrs.get('role') == 'main'
        blocked = tag in ('script', 'style', 'nav', 'footer', 'header', 'aside', 'form', 'noscript', 'svg', 'button') or 'hidden' in attrs or attrs.get('aria-hidden') == 'true'
        paragraph = tag in ('p', 'h1', 'h2', 'h3', 'li', 'pre')
        self.stack.append((tag, scope, blocked, paragraph))
        self.scope += int(scope)
        self.blocked += int(blocked)
        self.paragraph += int(paragraph)
    def handle_startendtag(self, tag, attrs):
        pass
    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                for _, scope, blocked, paragraph in self.stack[index:]:
                    self.scope -= int(scope)
                    self.blocked -= int(blocked)
                    self.paragraph -= int(paragraph)
                del self.stack[index:]
                self.parts.append('\n')
                self.fallback.append('\n')
                break
    def handle_data(self, data):
        if not self.blocked:
            if self.scope:
                self.parts.append(data)
            if self.paragraph:
                self.fallback.append(data)
    def result(self, limit):
        primary = clean_text(' '.join(self.parts), limit)
        return primary if len(primary) >= 120 else clean_text(' '.join(self.fallback), limit)


def approved_url(url, hosts, *, resolve=True):
    if not safe_http_url(url):
        raise ValueError('unsafe_article_url')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.port not in (None, 443):
        raise ValueError('article_host_not_approved')
    if resolve:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('nonpublic_article_address')
    return url


def extract_article(body, max_chars):
    parser = ArticleText()
    parser.feed(body.decode('utf-8', errors='replace'))
    result = parser.result(max_chars)
    if len(result) < 120:
        raise ValueError('article_body_missing')
    return result


def fetch_article(item, source, policy):
    host = urllib.parse.urlsplit(source['homepage']).hostname
    base = host.removeprefix('www.')
    hosts = {base, 'www.' + base, *source.get('articleHosts', [])}
    url = approved_url(item['url'], hosts)
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            approved_url(newurl, hosts)
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    request = urllib.request.Request(url, headers={'User-Agent': 'ai325-public-curation/1.0 (+https://ai325.com)', 'Accept': 'text/html', 'Accept-Encoding': 'identity'})
    with urllib.request.build_opener(Redirect).open(request, timeout=policy['articleTimeoutSeconds']) as response:
        if response.headers.get_content_type() not in ('text/html', 'application/xhtml+xml'):
            raise ValueError('article_not_html')
        body = response.read(policy['articleMaxBytes'] + 1)
    if len(body) > policy['articleMaxBytes']:
        raise ValueError('article_too_large')
    return extract_article(body, policy['articleMaxChars'])
