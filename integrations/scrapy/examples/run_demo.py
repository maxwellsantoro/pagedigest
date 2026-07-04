"""Live end-to-end demo. Starts a localhost pagedigest publisher, then runs a
real Scrapy crawl through the middleware. Run it twice with the same --store:

    python examples/run_demo.py --store /tmp/pd.db     # run 1: cold, 0 skips
    python examples/run_demo.py --store /tmp/pd.db     # run 2: warm, skips unchanged

Reactor isn't restartable in-process, so each run is its own process; the shared
SQLite store carries crawl state between them -- exactly the stateful-consumer
model the spec targets.
"""
import argparse
import hashlib
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import scrapy
from scrapy.crawler import CrawlerProcess

PAGES = {
    "/": b"<h1>home</h1>",
    "/about": b"<h1>about</h1>",
    "/docs/a": b"<h1>doc a</h1>",
    "/docs/b": b"<h1>doc b</h1>",
    "/blog/post1": b"<h1>post one</h1>",
}
REVS = {"/": 5, "/about": 2, "/docs/a": 9, "/docs/b": 4, "/blog/post1": 1}


def manifest_doc():
    entries = {}
    for path, body in PAGES.items():
        entries[path] = {"rev": REVS[path],
                         "digest": "sha256:" + hashlib.sha256(body).hexdigest()}
    return {"version": 1, "generated": "2025-10-16T10:00:00Z",
            "site_rev": 100, "entries": entries,
            "coverage": {"mode": "complete"}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == "/.well-known/pagedigest.json":
            payload = json.dumps(manifest_doc()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers(); self.wfile.write(payload); return
        body = PAGES.get(self.path)
        if body is None:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)


class DemoSpider(scrapy.Spider):
    name = "demo"
    def __init__(self, base, **kw):
        super().__init__(**kw)
        self.start_urls = [base + p for p in PAGES]
    def parse(self, response):
        self.logger.info(f"FETCHED {response.url}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default="/tmp/pd_demo.db")
    ap.add_argument("--port", type=int, default=8731)
    args = ap.parse_args()

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{args.port}"

    proc = CrawlerProcess(settings={
        "ROBOTSTXT_OBEY": False,
        "LOG_LEVEL": "INFO",
        "DOWNLOADER_MIDDLEWARES": {"pagedigest_scrapy.middleware.PageDigestMiddleware": 585},
        "PAGEDIGEST_STORE": args.store,
        "PAGEDIGEST_AUDIT_RATE": 0.0,
        "PAGEDIGEST_BOOTSTRAP_AUDIT_RATE": 0.0,
        "PAGEDIGEST_MANIFEST_TTL": 300.0,
    })
    crawler = proc.create_crawler(DemoSpider)
    proc.crawl(crawler, base=base)
    proc.start()

    st = crawler.stats
    print("\n==== pagedigest stats ====")
    for k in ("pagedigest/manifests_loaded", "pagedigest/skipped",
              "pagedigest/bytes_saved_est", "pagedigest/audits",
              "pagedigest/audit_mismatch", "pagedigest/manifest_unusable"):
        print(f"  {k:32s} {st.get_value(k, 0)}")
    print(f"  {'downloader/request_count':32s} {st.get_value('downloader/request_count', 0)}")
    srv.shutdown()


if __name__ == "__main__":
    sys.exit(main())
