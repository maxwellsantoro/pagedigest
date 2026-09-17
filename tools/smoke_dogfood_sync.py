#!/usr/bin/env python3
"""Cold/warm/changed sync against staged dogfood output over real local HTTP."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from generate_dogfood_manifest import ROOT, run_generator
from smoke_persistent_consumer import verify_cycle


def main():
    with tempfile.TemporaryDirectory(prefix="pagedigest-dogfood-sync-") as tmp:
        root = Path(tmp)
        site = root / "site"
        shutil.copytree(ROOT / "site", site)
        publisher_state = root / "publisher.json"
        shutil.copyfile(ROOT / "site-state/state.json", publisher_state)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                key = urlsplit(self.path).path
                if key == "/404.html":
                    self.send_response(308)
                    self.send_header("Location", "/404")
                    self.end_headers()
                    return
                path = site / (
                    key.lstrip("/") + ("index.html" if key.endswith("/") else "")
                )
                if not path.is_file():
                    self.send_error(404)
                    return
                body = path.read_bytes()
                etag = '"' + hashlib.sha256(body).hexdigest() + '"'
                unchanged = self.headers.get("If-None-Match") == etag
                self.send_response(304 if unchanged else 200)
                self.send_header("ETag", etag)
                self.send_header("Content-Length", str(0 if unchanged else len(body)))
                self.end_headers()
                if not unchanged:
                    self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            origin = f"http://127.0.0.1:{server.server_port}"
            state = root / "consumer.json"
            cold = verify_cycle(origin, state, "cold")
            warm = verify_cycle(origin, state, "warm")
            assert warm["manifest_not_modified"], warm
            with (site / "index.html").open("a") as output:
                output.write("\n<p>Controlled changed-resource smoke.</p>\n")
            run_generator(site, site / ".well-known/pagedigest.json", publisher_state)
            changed = verify_cycle(origin, state, "changed", "/")
            assert changed["resources"] == cold["resources"]
            assert changed["fetched_urls"] == ["/"]
            print("dogfood cold/warm/changed whole-collection synchronization passed")
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
