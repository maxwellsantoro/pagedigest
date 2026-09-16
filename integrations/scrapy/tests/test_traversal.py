import json
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'integrations/scrapy'))

if len(sys.argv) > 1 and sys.argv[1] == 'crawl':
    import scrapy
    from scrapy.crawler import CrawlerProcess
    seen = []
    class Spider(scrapy.Spider):
        name = 'review_probe'
        start_urls = [sys.argv[2] + '/']
        def parse(self, response):
            seen.append({'url': response.url, 'body': response.text})
            return [response.follow(href, self.parse) for href in response.css('a::attr(href)').getall()]
    proc = CrawlerProcess(settings={
        'ROBOTSTXT_OBEY': False, 'LOG_ENABLED': False,
        'DOWNLOADER_MIDDLEWARES': {'pagedigest_scrapy.middleware.PageDigestMiddleware': 585},
        'PAGEDIGEST_STORE': sys.argv[3], 'PAGEDIGEST_AUDIT_RATE': 0,
        'PAGEDIGEST_BOOTSTRAP_AUDIT_RATE': 0,
    })
    proc.crawl(Spider)
    proc.start()
    print(json.dumps({'callbacks': seen}))
    sys.exit(0)

cycle = 1
requests_seen = []
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def do_GET(self):
        requests_seen.append(self.path)
        if self.path == '/.well-known/pagedigest.json':
            body = json.dumps({'version': 1, 'generated': '2026-09-16T12:00:00Z', 'site_rev': cycle,
                              'entries': {'/': {'rev': 1}, '/a': {'rev': cycle}}, 'coverage': {'mode': 'complete'}}).encode()
            content_type = 'application/json'
        else:
            body = b'<a href="/a">child</a>' if self.path == '/' else f'<p>child version {cycle}</p>'.encode()
            content_type = 'text/html'
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
with tempfile.TemporaryDirectory(prefix='pagedigest-review-') as tmp:
    for cycle in [1, 2]:
        requests_seen.clear()
        child = subprocess.run([sys.executable, __file__, 'crawl', f'http://127.0.0.1:{server.server_port}', str(Path(tmp) / 'crawl.db')], capture_output=True, text=True, check=True)
        result = json.loads(child.stdout.strip())
        assert len(result["callbacks"]) == 2, result
        assert result["callbacks"][1]["body"] == f"<p>child version {cycle}</p>", result
        expected = ["/.well-known/pagedigest.json", "/", "/a"] if cycle == 1 else ["/.well-known/pagedigest.json", "/a"]
        assert requests_seen == expected, requests_seen
        print(f"cycle {cycle}: equivalent traversal and fresh child; requests={requests_seen}")
server.shutdown()
