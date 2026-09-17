#!/usr/bin/env python3
"""Local HTTP benchmark. Every reported cycle must reproduce the full current collection.

Wire-body counts are server-observed gzip payload bytes, including discovery,
manifest, conditional and audit responses. Header bytes and elapsed seconds are
reported separately. This controlled fixture is not independent adoption evidence.
"""

from __future__ import annotations

import argparse
import gzip
import contextlib
import importlib.util
import io
import hashlib
import json
import random
import threading
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
from pagedigest import audit, check_site


def fingerprint(body):
    return "sha256:" + hashlib.sha256(body).hexdigest()


def load_persistent_example():
    path = (
        Path(__file__).resolve().parents[1]
        / "implementations/python-consumer/examples/cache_persistence.py"
    )
    spec = importlib.util.spec_from_file_location("persistent_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.pages < 10:
        parser.error("at least 10 pages required")
    pages = {
        f"/p/{i}": (f"<h1>Document {i}</h1>" + "stable documentation " * 100).encode()
        for i in range(args.pages)
    }
    revs = dict.fromkeys(pages, 1)
    site_rev = 1
    counts = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == "/.well-known/pagedigest.json":
                body = json.dumps(
                    {
                        "version": 1,
                        "generated": "2026-09-16T00:00:00Z",
                        "site_rev": site_rev,
                        "coverage": {"mode": "complete"},
                        "entries": {
                            key: {"rev": revs[key], "digest": fingerprint(value)}
                            for key, value in pages.items()
                        },
                    }
                ).encode()
            elif self.path == "/fingerprints.json":
                body = json.dumps(
                    {key: fingerprint(value) for key, value in pages.items()}
                ).encode()
            elif self.path == "/sitemap.xml":
                body = (
                    "<urlset>"
                    + "".join(
                        f"<url><loc>{key}</loc><lastmod>2026-09-{revs[key]:02d}</lastmod></url>"
                        for key in pages
                    )
                    + "</urlset>"
                ).encode()
            else:
                body = pages[self.path]
            etag = '"' + fingerprint(body) + '"'
            unchanged = self.headers.get("If-None-Match") == etag
            payload = (
                b""
                if unchanged
                else gzip.compress(body, mtime=0)
                if "gzip" in self.headers.get("Accept-Encoding", "")
                else body
            )
            self.send_response(304 if unchanged else 200)
            self.send_header("ETag", etag)
            if payload and "gzip" in self.headers.get("Accept-Encoding", ""):
                self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(payload)))
            counts["requests"] += 1
            counts["response_body_wire_bytes"] += len(payload)
            counts["response_header_bytes"] += sum(map(len, self._headers_buffer)) + 2
            self.end_headers()
            if payload:
                self.wfile.write(payload)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    modes = [
        "full",
        "conditional-http",
        "sitemap-lastmod",
        "fingerprint-manifest",
        "fingerprint-manifest-audited",
        "pagedigest",
        "pagedigest-persistent",
    ]
    states = {
        mode: {"bodies": {}, "signals": {}, "manifest": None, "etag": None}
        for mode in modes
    }
    rows = []
    persistent = load_persistent_example()
    persistent_tmp = tempfile.TemporaryDirectory(
        prefix="pagedigest-persistent-benchmark-"
    )
    persistent_root = Path(persistent_tmp.name)
    persistent_state = persistent_root / "state.json"
    persistent_bodies = persistent_root / "bodies"
    session = requests.Session()
    scenarios = [
        "cold",
        "no-change",
        "sparse-change",
        "template-change",
        "add-remove",
        "cache-eviction",
    ]
    try:
        for scenario in scenarios:
            if scenario in ("sparse-change", "template-change"):
                keys = (
                    list(pages)[: max(1, args.pages // 50)]
                    if scenario == "sparse-change"
                    else list(pages)
                )
                for key in keys:
                    pages[key] += f"<p>{scenario}</p>".encode()
                    revs[key] += 1
                site_rev += 1
            elif scenario == "add-remove":
                del pages["/p/0"]
                pages["/new"] = b"<h1>New document</h1>"
                revs["/new"] = 1
                site_rev += 1
            elif scenario == "cache-eviction":
                for state in states.values():
                    state["bodies"].pop("/p/1", None)
                snapshot = persistent.load_state(persistent_state)
                (persistent_bodies / snapshot["pages"]["/p/1"]).unlink()
            for mode in modes:
                counts.update(
                    requests=0, response_body_wire_bytes=0, response_header_bytes=0
                )
                state = states[mode]
                started = time.perf_counter()
                cpu_started = time.thread_time()
                metrics = {}
                audits = 0
                if mode == "pagedigest":
                    d = check_site(
                        origin,
                        state["manifest"]["site_rev"] if state["manifest"] else None,
                        {key: state["signals"][key] for key in state["bodies"]},
                        etag=state["etag"],
                        cached_manifest=state["manifest"],
                        session=session,
                        sample_audit_rate=0.01,
                        rng=random.Random(42),
                    )
                    assert not d["fallback"], d
                    signals = {
                        key: entry["rev"]
                        for key, entry in d["manifest"]["entries"].items()
                    }
                    needed = d["new"] + d["changed"]
                    for candidate in d["audit_candidates"]:
                        result = audit(
                            origin,
                            candidate["url"],
                            candidate["digest"],
                            session=session,
                        )
                        assert result["result"] == "match"
                        assert result["computed"] == fingerprint(
                            state["bodies"][candidate["url"]]
                        )
                        audits += 1
                    state["manifest"] = d["manifest"]
                    state["etag"] = d["etag"] or state["etag"]
                elif mode.startswith("fingerprint-manifest"):
                    r = session.get(
                        origin + "/fingerprints.json",
                        headers={"If-None-Match": state["etag"]}
                        if state["etag"]
                        else {},
                    )
                    signals = state["signals"] if r.status_code == 304 else r.json()
                    state["etag"] = r.headers["ETag"]
                    needed = [
                        key
                        for key, value in signals.items()
                        if key not in state["bodies"]
                        or state["signals"].get(key) != value
                    ]
                    if mode.endswith("-audited"):
                        pool = [key for key in signals if key not in needed]
                        count = (
                            min(len(pool), max(1, int(len(pool) * 0.01))) if pool else 0
                        )
                        for key in random.Random(42).sample(pool, count):
                            result = audit(origin, key, signals[key], session=session)
                            assert result["result"] == "match"
                            assert result["computed"] == fingerprint(
                                state["bodies"][key]
                            )
                            audits += 1
                elif mode == "pagedigest-persistent":
                    with contextlib.redirect_stdout(io.StringIO()):
                        assert (
                            persistent.run_cycle(
                                origin,
                                persistent_state,
                                persistent_bodies,
                                session=session,
                                metrics=metrics,
                            )
                            == 0
                        )
                    audits = metrics["audit_requests"]
                    # End the measured cycle before loading bodies for the benchmark's
                    # independent equivalence assertion.
                    elapsed = time.perf_counter() - started
                    cpu = time.thread_time() - cpu_started
                    snapshot = persistent.load_state(persistent_state)
                    signals = snapshot["revs"]
                    state["bodies"] = {
                        key: (persistent_bodies / filename).read_bytes()
                        for key, filename in snapshot["pages"].items()
                    }
                    needed = []
                else:
                    # Baselines also pay for discovery of additions and removals.
                    r = session.get(
                        origin + "/sitemap.xml",
                        headers={"If-None-Match": state["etag"]}
                        if state["etag"]
                        else {},
                    )
                    signals = (
                        state["signals"]
                        if r.status_code == 304
                        else {
                            node.findtext("loc"): node.findtext("lastmod")
                            for node in ET.fromstring(r.content)
                        }
                    )
                    state["etag"] = r.headers["ETag"]
                    needed = (
                        list(signals)
                        if mode != "sitemap-lastmod"
                        else [
                            key
                            for key, value in signals.items()
                            if key not in state["bodies"]
                            or state["signals"].get(key) != value
                        ]
                    )
                for key in needed:
                    headers = {}
                    if mode == "conditional-http" and key in state["bodies"]:
                        headers["If-None-Match"] = (
                            '"' + fingerprint(state["bodies"][key]) + '"'
                        )
                    r = session.get(origin + key, headers=headers)
                    if r.status_code != 304:
                        r.raise_for_status()
                        state["bodies"][key] = r.content
                state["bodies"] = {
                    key: value
                    for key, value in state["bodies"].items()
                    if key in signals
                }
                state["signals"] = signals
                if mode != "pagedigest-persistent":
                    elapsed = time.perf_counter() - started
                    cpu = time.thread_time() - cpu_started
                assert state["bodies"] == pages, (
                    f"incorrect result: {mode} / {scenario}"
                )
                rows.append(
                    {
                        "scenario": scenario,
                        "consumer": mode,
                        **counts,
                        "audit_requests": audits,
                        "elapsed_seconds": round(elapsed, 6),
                        "consumer_thread_cpu_seconds": round(cpu, 6),
                        **metrics,
                        "equivalent": True,
                    }
                )
    finally:
        session.close()
        server.shutdown()
        server.server_close()
        thread.join()
        persistent_tmp.cleanup()
    report = {
        "fixture_pages": args.pages,
        "strategies": len(modes),
        "sitemap_fetch": "ETag conditional after the cold cycle for all sitemap-based strategies",
        "local_work": "consumer-thread CPU excludes HTTP-server threads; persistent mode includes real disk integrity checks and writes",
        "body_profile": "repetitive static HTML, gzip enabled",
        "scope": "controlled local HTTP experiment; not production, model-token, or independent-adoption evidence",
        "freshness": "exact current bytes and resource set after every completed cycle",
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"{len(rows)} equivalent consumer cycles verified; report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
