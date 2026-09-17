#!/usr/bin/env python3
"""Persistent PageDigest consumer cache with failure-safe state updates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import requests

from pagedigest import audit, check_site, manifest_url, resolve_url_key

DEFAULT_MAX_PAGE_BYTES = 10 * 1024 * 1024


def empty_state() -> dict[str, Any]:
    return {
        "site_rev": None,
        "revs": {},
        "etag": None,
        "last_modified": None,
        "pages": {},
        "body_hashes": {},
        "manifest": None,
        "origin": None,
        "distrusted": False,
    }


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
    hashes = state.get("body_hashes", {})
    if not isinstance(hashes, dict) or any(
        not isinstance(key, str)
        or not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(ch not in "0123456789abcdef" for ch in value[7:])
        for key, value in hashes.items()
    ):
        raise ValueError("cache state has invalid body hashes")
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
    sample_audit_rate: float = 0.01,
    metrics: dict[str, Any] | None = None,
) -> int:
    """Serialize writers; a stale lock after a crash requires operator review."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock = Path(str(state_path) + ".lock")
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        return _run_cycle(
            base_url,
            state_path,
            pages_dir,
            session=session,
            max_page_bytes=max_page_bytes,
            sample_audit_rate=sample_audit_rate,
            metrics=metrics,
        )
    finally:
        os.close(descriptor)
        lock.unlink()


def _run_cycle(base_url, state_path, pages_dir, *, session, max_page_bytes, sample_audit_rate, metrics):
    state = load_state(state_path)
    origin = manifest_url(base_url)
    if state.get("origin") not in (None, origin):
        raise ValueError("cache belongs to another origin; use a separate state file")
    client = session or requests.Session()
    # Metadata is reusable only while its corresponding body is still present
    # and intact. Legacy state without body hashes is refreshed once.
    available = {}
    integrity_started = time.perf_counter()
    integrity_bytes = 0
    integrity_bodies = 0
    for key, rev in state["revs"].items():
        filename = state["pages"].get(key)
        expected = state.get("body_hashes", {}).get(key)
        if filename and expected and not state.get("distrusted"):
            try:
                body = (pages_dir / filename).read_bytes()
                integrity_bytes += len(body)
                integrity_bodies += 1
                actual = "sha256:" + hashlib.sha256(body).hexdigest()
                if actual == expected:
                    available[key] = rev
            except FileNotFoundError:
                pass
    if metrics is not None:
        metrics.update(
            cache_integrity_bytes=integrity_bytes,
            cache_integrity_bodies=integrity_bodies,
            cache_integrity_seconds=time.perf_counter() - integrity_started,
        )
    decision = check_site(
        base_url,
        cached_site_rev=state["site_rev"],
        cached_revs=available,
        etag=state["etag"],
        last_modified=state["last_modified"],
        sample_audit_rate=sample_audit_rate,
        session=client,
        cached_manifest=state.get("manifest"),
    )
    if decision.get("fallback"):
        print(f"fallback to normal crawl required: {decision.get('error')}")
        return 1

    # Audits run even after a 304. A matching current digest alone is insufficient:
    # also compare the observed bytes with the local representation being reused.
    for candidate in decision.get("audit_candidates", []):
        result = audit(base_url, candidate["url"], candidate["digest"], session=client, max_bytes=max_page_bytes)
        if result["result"] == "inconclusive":
            print(f"audit inconclusive; retry cycle: {candidate['url']}")
            return 1
        if result["result"] == "mismatch" or result.get("computed") != state["body_hashes"].get(candidate["url"]):
            state["distrusted"] = True
            save_state(state_path, state)
            print("audit failed; revisions retained; next cycle refreshes all covered bodies")
            return 1

    if metrics is not None:
        metrics.update(
            audit_requests=len(decision.get("audit_candidates", [])),
            manifest_not_modified=decision.get("not_modified", False),
            fetched_urls=decision["new"] + decision["changed"],
        )
    manifest = decision["manifest"]
    updated_pages = dict(state["pages"])
    body_hashes = dict(state.get("body_hashes", {}))
    pages_dir.mkdir(parents=True, exist_ok=True)
    try:
        # Content-addressed bodies keep the last committed snapshot intact if a
        # later fetch fails. Unreferenced bodies can be garbage-collected offline.
        with tempfile.TemporaryDirectory(dir=pages_dir) as staging:
            for url_key in decision["new"] + decision["changed"]:
                destination = Path(staging) / "body"
                fetch_page(client, resolve_url_key(base_url, url_key), destination, max_bytes=max_page_bytes)
                digest = "sha256:" + hashlib.sha256(destination.read_bytes()).hexdigest()
                expected = manifest["entries"][url_key].get("digest")
                if expected and expected != digest:
                    state["distrusted"] = True
                    save_state(state_path, state)
                    print(f"download digest mismatch; retry after publisher repair: {url_key}")
                    return 1
                filename = digest.removeprefix("sha256:") + ".body"
                os.replace(destination, pages_dir / filename)
                updated_pages[url_key] = filename
                body_hashes[url_key] = digest
                print(f"fetched {url_key}")
    except (OSError, requests.RequestException, RuntimeError, ValueError) as exc:
        print(f"page fetch failed; cache revisions not advanced: {exc}")
        return 1

    if (manifest.get("coverage") or {}).get("mode") == "complete":
        updated_pages = {key: value for key, value in updated_pages.items() if key in manifest["entries"]}
        body_hashes = {key: value for key, value in body_hashes.items() if key in manifest["entries"]}
    save_state(
        state_path,
        {
            "site_rev": decision["site_rev"],
            "revs": next_revs(state["revs"], manifest),
            "etag": decision.get("etag") or (state["etag"] if decision.get("not_modified") else None),
            "last_modified": decision.get("last_modified")
            or (state["last_modified"] if decision.get("not_modified") else None),
            "pages": updated_pages,
            "body_hashes": body_hashes,
            "manifest": manifest,
            "origin": origin,
            "distrusted": False,
        },
    )
    print(f"saved completed snapshot to {state_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    parser.add_argument("state", type=Path)
    parser.add_argument("--pages", type=Path, help="cached body directory (default: <state>.pages)")
    parser.add_argument("--max-page-bytes", type=int, default=DEFAULT_MAX_PAGE_BYTES)
    parser.add_argument("--audit-rate", type=float, default=0.01)
    args = parser.parse_args()
    if not 0 <= args.audit_rate <= 1:
        parser.error("--audit-rate must be between 0 and 1")
    if args.max_page_bytes < 1:
        parser.error("--max-page-bytes must be positive")
    pages_dir = args.pages or Path(str(args.state) + ".pages")
    try:
        return run_cycle(
            args.base_url, args.state, pages_dir, max_page_bytes=args.max_page_bytes, sample_audit_rate=args.audit_rate
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"invalid cache state: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
