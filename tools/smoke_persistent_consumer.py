#!/usr/bin/env python3
"""Verify a whole-manifest persistent sync, separately from digest sampling.

Use a new state for --expect cold, then the same state for warm and changed.
The changed check requires a real publisher revision/body change; this tool
never mutates the publisher. Only complete manifests are accepted by this smoke.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

from benchmark_consumers import load_persistent_example


class RecordingSession(requests.Session):
    def __init__(self):
        super().__init__()
        self.observed = []

    def send(self, request, **kwargs):
        response = super().send(request, **kwargs)
        self.observed.append({"url": request.url, "status": response.status_code})
        return response


def verify_cycle(base_url, state_path, expect, changed_url=None):
    cache = load_persistent_example()
    pages_dir = Path(str(state_path) + ".pages")
    before = cache.load_state(state_path)
    if expect == "cold" and state_path.exists():
        raise ValueError("cold smoke requires a new state path")
    if expect != "cold" and not state_path.exists():
        raise ValueError("warm/changed smoke requires the previous completed state")
    metrics = {}
    with RecordingSession() as session:
        started = time.perf_counter()
        with contextlib.redirect_stdout(sys.stderr):
            code = cache.run_cycle(
                base_url,
                state_path,
                pages_dir,
                session=session,
                sample_audit_rate=1,
                metrics=metrics,
            )
        elapsed = time.perf_counter() - started
        if code:
            raise RuntimeError("persistent consumer could not complete the collection")
        state = cache.load_state(state_path)
        manifest = state["manifest"]
        if manifest.get("coverage", {}).get("mode") != "complete":
            raise ValueError("whole-collection smoke requires complete coverage")
        assert set(state["pages"]) == set(manifest["entries"]) == set(state["revs"])
        for key, entry in manifest["entries"].items():
            body = (pages_dir / state["pages"][key]).read_bytes()
            digest = "sha256:" + hashlib.sha256(body).hexdigest()
            assert digest == state["body_hashes"][key]
            assert not entry.get("digest") or digest == entry["digest"]
            assert state["revs"][key] == entry["rev"]
        if expect == "warm":
            assert state["site_rev"] == before["site_rev"], (
                "publisher changed during warm smoke"
            )
            assert not metrics["fetched_urls"], metrics
        if expect == "changed":
            assert changed_url, "--changed-url is required for changed smoke"
            assert changed_url in metrics["fetched_urls"], metrics
            assert state["revs"][changed_url] > before["revs"].get(changed_url, -1)
            assert state["body_hashes"][changed_url] != before["body_hashes"].get(
                changed_url
            )
        return {
            "cycle": expect,
            "base_url": base_url,
            "site_rev": state["site_rev"],
            "resources": len(state["pages"]),
            "completed": True,
            "elapsed_seconds": elapsed,
            **metrics,
            "http_requests": session.observed,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("state", type=Path)
    parser.add_argument("--expect", choices=("cold", "warm", "changed"), required=True)
    parser.add_argument("--changed-url")
    parser.add_argument("--expect-site-rev", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify_cycle(args.base_url, args.state, args.expect, args.changed_url)
    if args.expect_site_rev is not None:
        assert result["site_rev"] == args.expect_site_rev, result
    report = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(report)
    print(report, end="")


if __name__ == "__main__":
    main()
