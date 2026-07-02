#!/usr/bin/env python3
"""Minimal persistent-cache example for a pagedigest consumer.

This intentionally prints fetch decisions instead of downloading pages, so it
can be adapted to crawlers, indexers, mirrors, or agent caches.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pagedigest import check_site, resolve_url_key


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"site_rev": None, "revs": {}, "etag": None, "last_modified": None}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def next_revs(
    previous_revs: dict[str, int],
    manifest: dict[str, Any],
) -> dict[str, int]:
    manifest_revs = {url_key: entry["rev"] for url_key, entry in manifest["entries"].items()}
    coverage_mode = (manifest.get("coverage") or {}).get("mode")
    if coverage_mode == "complete":
        return manifest_revs
    return {**previous_revs, **manifest_revs}


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: cache_persistence.py https://example.com ./pagedigest-cache.json", file=sys.stderr)
        return 2

    base_url = sys.argv[1]
    state_path = Path(sys.argv[2])
    state = load_state(state_path)

    decision = check_site(
        base_url,
        cached_site_rev=state.get("site_rev"),
        cached_revs=state.get("revs") or {},
        etag=state.get("etag"),
        last_modified=state.get("last_modified"),
        sample_audit_rate=0.01,
    )

    if decision.get("fallback"):
        print(f"fallback to normal crawl: {decision.get('error')}")
        return 1

    state["etag"] = decision.get("etag")
    state["last_modified"] = decision.get("last_modified")

    if decision.get("not_modified"):
        print("manifest not modified; no page fetches needed")
        save_state(state_path, state)
        return 0

    for url_key in decision["new"] + decision["changed"]:
        print(f"fetch {resolve_url_key(base_url, url_key)}")

    for url_key in decision["removed"]:
        print(f"remove cached entry {url_key}")

    manifest = decision["manifest"]
    state["site_rev"] = decision["site_rev"]
    state["revs"] = next_revs(state.get("revs") or {}, manifest)
    save_state(state_path, state)
    print(f"saved state to {state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
