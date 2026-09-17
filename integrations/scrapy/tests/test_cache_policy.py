"""Exercise replay policy through a real Scrapy downloader and HTTP origin."""
import json
import hashlib
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "integrations/scrapy"))

# Each step is (request headers, response headers, should replay).
PUBLIC = {"Cache-Control": "public"}
CASES = {
    "request-no-cache": [({}, PUBLIC, False), ({}, PUBLIC, True),
                         ({"Cache-Control": "no-cache"}, PUBLIC, False), ({}, PUBLIC, False)],
    "request-pragma": [({}, PUBLIC, False), ({"Pragma": "no-cache"}, PUBLIC, False)],
    "request-validator": [({}, PUBLIC, False), ({"If-None-Match": '"previous"'}, PUBLIC, False)],
    "request-no-store": [({}, PUBLIC, False), ({"Cache-Control": "no-store"}, PUBLIC, False),
                         ({}, PUBLIC, False), ({}, PUBLIC, True)],
    "initial-no-cache": [({}, {"Cache-Control": "no-cache"}, False)] * 2,
    "legacy-no-cache": [({}, PUBLIC, False), ({}, PUBLIC, True)],
    "audit-transition": [({}, PUBLIC, False), ({}, PUBLIC, True),
                         ({}, {"Cache-Control": "no-store"}, False),
                         ({}, {"Cache-Control": "no-store"}, False)],
}
for name, headers in {
    "no-store": {"Cache-Control": "no-store"},
    "private": {"Cache-Control": "private"},
    "no-cache": {"Cache-Control": "no-cache"},
    "qualified-no-cache": {"Cache-Control": 'no-cache="ETag, X-Internal"'},
    "multiple-fields": {"Cache-Control": ["public", "No-Cache"]},
    "must-revalidate": {"Cache-Control": "must-revalidate"},
    "max-age": {"Cache-Control": "max-age=0"},
    "vary": {"Vary": "Accept-Language"},
    "cookie": {"Set-Cookie": "example=1"},
}.items():
    CASES["transition-" + name] = [
        ({}, PUBLIC, False), ({}, PUBLIC, True),
        ({"Cache-Control": "no-cache"}, headers, False), ({}, headers, False),
    ]


def crawl():
    import scrapy
    from scrapy.crawler import CrawlerProcess
    from pagedigest_scrapy.store import Store
    from scrapy.http import Response

    origin, database = sys.argv[2:4]
    store = Store(database)
    store.set_rev(origin, "/legacy-no-cache", 1)
    store.set_response(origin, "/legacy-no-cache", Response(
        origin + "/legacy-no-cache", body=b"stable body",
        headers={"Cache-Control": "no-cache"}))
    store.close()
    observed = {}

    class Spider(scrapy.Spider):
        name = "cache_policy"

        def step(self, case, index):
            headers = {**CASES[case][index][0], "X-Fixture-Step": str(index)}
            return scrapy.Request(origin + "/" + case, headers=headers,
                                  callback=self.parse, dont_filter=True,
                                  meta={"case": case, "index": index, "dont_merge_cookies": True})

        def start_requests(self):
            for case in CASES:
                yield self.step(case, 0)

        async def start(self):
            for request in self.start_requests():
                yield request

        def parse(self, response):
            case, index = response.meta["case"], response.meta["index"]
            observed.setdefault(case, []).append({
                "replayed": "pagedigest_cached" in response.flags,
                "body": response.text,
            })
            if case == "audit-transition" and index == 1:
                # Trigger the real forced-audit recovery path without request
                # bypass headers, so response-policy invalidation is exercised.
                store = Store(database)
                store.mark_url_suspect(origin, "/" + case)
                store.close()
            if index + 1 < len(CASES[case]):
                yield self.step(case, index + 1)

    proc = CrawlerProcess(settings={
        "ROBOTSTXT_OBEY": False, "LOG_ENABLED": False, "COOKIES_ENABLED": False,
        "DOWNLOADER_MIDDLEWARES": {"pagedigest_scrapy.middleware.PageDigestMiddleware": 585},
        "PAGEDIGEST_STORE": database, "PAGEDIGEST_AUDIT_RATE": 0,
        "PAGEDIGEST_BOOTSTRAP_AUDIT_RATE": 0,
    })
    proc.crawl(Spider)
    proc.start()
    print(json.dumps(observed))


def main():
    requests_seen = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == "/.well-known/pagedigest.json":
                body = json.dumps({"version": 1, "generated": "2026-09-16T12:00:00Z",
                                   "site_rev": 1, "coverage": {"mode": "complete"},
                                   "entries": {"/" + case: {"rev": 1, "digest": "sha256:" + hashlib.sha256(b"stable body").hexdigest()} for case in CASES}}).encode()
                headers = {"Content-Type": "application/json"}
            else:
                case = self.path[1:]
                index = int(self.headers["X-Fixture-Step"])
                requests_seen.append((case, index))
                body = b"stable body"
                headers = {"Content-Type": "text/plain", **CASES[case][index][1]}
            self.send_response(200)
            for name, values in headers.items():
                for value in values if isinstance(values, list) else [values]:
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix="pagedigest-policy-") as tmp:
            child = subprocess.run([sys.executable, __file__, "crawl",
                                    f"http://127.0.0.1:{server.server_port}", str(Path(tmp) / "cache.db")],
                                   capture_output=True, text=True, check=True)
            observed = json.loads(child.stdout)
            assert set(observed) == set(CASES), (observed, child.stderr)
            for case, steps in CASES.items():
                assert observed[case] == [{"replayed": step[2], "body": "stable body"}
                                          for step in steps], (case, observed[case])
                assert sorted(index for name, index in requests_seen if name == case) == [
                    i for i, step in enumerate(steps) if not step[2]], (case, requests_seen)
            print(f"{len(CASES)} real middleware cache-policy scenarios passed; bodies and revisions unchanged")
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    crawl() if len(sys.argv) > 1 and sys.argv[1] == "crawl" else main()
