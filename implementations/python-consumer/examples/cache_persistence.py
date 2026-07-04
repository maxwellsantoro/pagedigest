#!/usr/bin/env python3
"""Persistent PageDigest consumer cache with failure-safe state updates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import requests

from pagedigest import check_site, resolve_url_key

DEFAULT_MAX_PAGE_BYTES = 10 * 1024 * 1024


def empty_state() -> dict[str, Any]:
    return {"site_rev": None, "revs": {}, "etag": None, "last_modified": None, "pages": {}}


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_state()
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise ValueError("cache state must be a JSON object")

    site_rev = state.get("site_rev")
    revs = state.get("revs")
    pages = state.get("pages", {})
    if site_rev is not None and (type(site_rev) is not int or site_rev < 0):
        raise ValueError("cache state has an invalid site_rev")
    if not isinstance(revs, dict) or any(
        not isinstance(key, str) or type(value) is not int or value < 0 for key, value in revs.items()
    ):
        raise ValueError("cache state has an invalid rev map")
    if not isinstance(pages, dict) or any(
        not isinstance(key, str)
        or not isinstance(value, str)
        or len(value) != 69
        or not value.endswith(".body")
        or any(ch not in "0123456789abcdef" for ch in value[:-5])
        for key, value in pages.items()
    ):
        raise ValueError("cache state has an invalid page map")
    for field in ("etag", "last_modified"):
        if state.get(field) is not None and not isinstance(state[field], str):
            raise ValueError(f"cache state has an invalid {field}")
    return {**empty_state(), **state, "pages": pages}


def save_state(path: Path, state: dict[str, Any]) -> None:
    """Atomically replace cache state after all required page fetches succeed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temp:
            temp_name = temp.name
            json.dump(state, temp, indent=2, sort_keys=True)
            temp.write("\n")
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_name, path)
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)


def next_revs(previous_revs: dict[str, int], manifest: dict[str, Any]) -> dict[str, int]:
    manifest_revs = {url_key: entry["rev"] for url_key, entry in manifest["entries"].items()}
    if (manifest.get("coverage") or {}).get("mode") == "complete":
        return manifest_revs
    return {**previous_revs, **manifest_revs}


def page_filename(url_key: str) -> str:
    return hashlib.sha256(url_key.encode("utf-8")).hexdigest() + ".body"


def fetch_page(
    session: requests.Session,
    url: str,
    destination: Path,
    *,
    timeout: int = 15,
    max_bytes: int = DEFAULT_MAX_PAGE_BYTES,
) -> None:
    """Fetch one page without redirects and atomically replace its cached body."""
    response = session.get(
        url,
        headers={"Accept-Encoding": "identity"},
        timeout=timeout,
        allow_redirects=False,
        stream=True,
    )
    temp_name: str | None = None
    try:
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"page fetch returned HTTP {response.status_code}: {url}")
        content_length = response.headers.get("Content-Length")
        if content_length is not None:
            try:
                if int(content_length) > max_bytes:
                    raise RuntimeError(f"page exceeds {max_bytes} bytes: {url}")
            except ValueError as exc:
                raise RuntimeError(f"page has invalid Content-Length: {url}") from exc

        destination.parent.mkdir(parents=True, exist_ok=True)
        total = 0
        with tempfile.NamedTemporaryFile("wb", dir=destination.parent, delete=False) as temp:
            temp_name = temp.name
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError(f"page exceeds {max_bytes} bytes: {url}")
                temp.write(chunk)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_name, destination)
        temp_name = None
    finally:
        response.close()
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)


def run_cycle(
    base_url: str,
    state_path: Path,
    pages_dir: Path,
    *,
    session: requests.Session | None = None,
    max_page_bytes: int = DEFAULT_MAX_PAGE_BYTES,
) -> int:
    state = load_state(state_path)
    client = session or requests.Session()
    decision = check_site(
        base_url,
        cached_site_rev=state["site_rev"],
        cached_revs=state["revs"],
        etag=state["etag"],
        last_modified=state["last_modified"],
        sample_audit_rate=0.01,
        session=client,
    )

    if decision.get("fallback"):
        print(f"fallback to normal crawl: {decision.get('error')}")
        return 1

    if decision.get("not_modified"):
        state["etag"] = decision.get("etag") or state["etag"]
        state["last_modified"] = decision.get("last_modified") or state["last_modified"]
        save_state(state_path, state)
        print("manifest not modified; no page fetches needed")
        return 0

    manifest = decision["manifest"]
    updated_pages = dict(state["pages"])
    try:
        for url_key in decision["new"] + decision["changed"]:
            filename = page_filename(url_key)
            fetch_page(
                client,
                resolve_url_key(base_url, url_key),
                pages_dir / filename,
                max_bytes=max_page_bytes,
            )
            updated_pages[url_key] = filename
            print(f"fetched {url_key} -> {filename}")
    except (OSError, requests.RequestException, RuntimeError) as exc:
        print(f"page fetch failed; cache state not advanced: {exc}")
        return 1

    if (manifest.get("coverage") or {}).get("mode") == "complete":
        updated_pages = {key: value for key, value in updated_pages.items() if key in manifest["entries"]}

    new_state = {
        "site_rev": decision["site_rev"],
        "revs": next_revs(state["revs"], manifest),
        "etag": decision.get("etag"),
        "last_modified": decision.get("last_modified"),
        "pages": updated_pages,
    }
    save_state(state_path, new_state)

    for url_key in decision["removed"]:
        old_filename = state["pages"].get(url_key)
        if old_filename:
            (pages_dir / old_filename).unlink(missing_ok=True)
        print(f"removed cached entry {url_key}")

    print(f"saved state to {state_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("state", type=Path)
    parser.add_argument("--pages", type=Path, help="cached body directory (default: <state>.pages)")
    parser.add_argument("--max-page-bytes", type=int, default=DEFAULT_MAX_PAGE_BYTES)
    args = parser.parse_args()
    if args.max_page_bytes < 1:
        parser.error("--max-page-bytes must be positive")
    pages_dir = args.pages or Path(str(args.state) + ".pages")
    try:
        return run_cycle(args.base_url, args.state, pages_dir, max_page_bytes=args.max_page_bytes)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"invalid cache state: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
