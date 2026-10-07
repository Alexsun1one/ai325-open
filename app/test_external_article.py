import unittest
from unittest.mock import patch
from app.external_article import approved_url, extract_article


class ArticleTest(unittest.TestCase):
    def test_extracts_main_without_navigation_scripts(self):
        raw = ('<nav>ignore menu</nav><main><h1>Release</h1><script>ignore script</script><p>' + 'Evidence for a concrete model release. ' * 10 + '</p><aside>ignore promo</aside></main><footer>ignore footer</footer>').encode()
        result = extract_article(raw, 1000)
        self.assertIn('Evidence', result)
        self.assertNotIn('ignore', result)
    def test_malformed_nesting_and_html_entities(self):
        raw = ('<article><section><p>' + 'A &amp; B have released a model. ' * 10 + '</article>').encode()
        result = extract_article(raw, 300)
        self.assertIn('A & B', result)
        self.assertLessEqual(len(result), 300)
    def test_empty_or_script_only_rejected(self):
        with self.assertRaises(ValueError):
            extract_article(b'<main><script>some fake evidence</script></main>', 6000)
    def test_no_ssrf_or_credentials_or_ports(self):
        for value in ('http://example.com', 'https://other.com', 'https://user:pass@example.com', 'https://example.com:8443'):
            with self.assertRaises(ValueError):
                approved_url(value, {'example.com'}, resolve=False)
    def test_private_resolution_rejected(self):
        for address in ('127.0.0.1', '169.254.169.254', '10.0.0.2', '::1'):
            with patch('socket.getaddrinfo', return_value=[(2,1,6,'',(address,443))]):
                with self.assertRaises(ValueError):
                    approved_url('https://example.com/a', {'example.com'})
    def test_configured_redirect_host_is_explicit(self):
        from app.external_sources import validate_article_hosts
        validate_article_hosts(['blog.google'])
        self.assertEqual(approved_url('https://blog.google/article', {'deepmind.google', 'blog.google'}, resolve=False), 'https://blog.google/article')
        for hosts in (['127.0.0.1'], ['blog.google:443'], ['*'], 'blog.google'):
            with self.assertRaises(ValueError): validate_article_hosts(hosts)
    def test_public_resolution_allowed(self):
        with patch('socket.getaddrinfo', return_value=[(2,1,6,'',('8.8.8.8',443))]):
            self.assertEqual(approved_url('https://example.com/a', {'example.com'}), 'https://example.com/a')


if __name__ == '__main__':
    unittest.main()
