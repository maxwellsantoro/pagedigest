from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests


MANIFEST_PATH = "/.well-known/pagedigest.json"


@dataclass
class FetchResult:
    ok: bool
    status_code: int | None
    manifest: dict[str, Any] | None
    etag: str | None
    last_modified: str | None
    error: str | None


def fetch(
    base_url: str,
    timeout: int = 10,
    etag: str | None = None,
    last_modified: str | None = None,
    session: requests.Session | None = None,
) -> FetchResult:
    """Fetch the pagedigest manifest with graceful fallback semantics."""
    s = session or requests.Session()
    headers: dict[str, str] = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    url = urljoin(base_url.rstrip("/") + "/", MANIFEST_PATH.lstrip("/"))
    try:
        r = s.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        return FetchResult(False, None, None, None, None, str(exc))

    if r.status_code == 304:
        return FetchResult(True, 304, None, r.headers.get("ETag"), r.headers.get("Last-Modified"), None)

    if r.status_code != 200:
        return FetchResult(False, r.status_code, None, r.headers.get("ETag"), r.headers.get("Last-Modified"), "manifest-unavailable")

    try:
        manifest = r.json()
    except ValueError:
        return FetchResult(False, r.status_code, None, r.headers.get("ETag"), r.headers.get("Last-Modified"), "invalid-json")

    if not isinstance(manifest, dict):
        return FetchResult(False, r.status_code, None, r.headers.get("ETag"), r.headers.get("Last-Modified"), "invalid-manifest-type")

    for field in ("version", "generated", "site_rev", "entries"):
        if field not in manifest:
            return FetchResult(False, r.status_code, None, r.headers.get("ETag"), r.headers.get("Last-Modified"), f"missing-{field}")

    if manifest.get("version") != 1:
        return FetchResult(False, r.status_code, None, r.headers.get("ETag"), r.headers.get("Last-Modified"), "unsupported-version")

    if not isinstance(manifest.get("site_rev"), int):
        return FetchResult(False, r.status_code, None, r.headers.get("ETag"), r.headers.get("Last-Modified"), "invalid-site-rev")
    if not isinstance(manifest.get("entries"), dict):
        return FetchResult(False, r.status_code, None, r.headers.get("ETag"), r.headers.get("Last-Modified"), "invalid-entries")

    return FetchResult(True, r.status_code, manifest, r.headers.get("ETag"), r.headers.get("Last-Modified"), None)


def diff(
    manifest: dict[str, Any],
    cached_site_rev: int | None,
    cached_revs: dict[str, int] | None,
) -> dict[str, Any]:
    """Compare a manifest against cached state and return crawl decisions."""
    cached_revs = cached_revs or {}
    site_rev = manifest["site_rev"]
    entries: dict[str, Any] = manifest["entries"]
    coverage_mode = (manifest.get("coverage") or {}).get("mode")

    if cached_site_rev is not None and site_rev == cached_site_rev:
        return {
            "site_changed": False,
            "changed": [],
            "new": [],
            "unchanged": sorted(entries.keys()),
            "removed": [],
            "anomalies": [],
            "site_rev": site_rev,
        }

    changed: list[str] = []
    new: list[str] = []
    unchanged: list[str] = []
    anomalies: list[dict[str, Any]] = []

    for url_key, entry in entries.items():
        rev = entry.get("rev") if isinstance(entry, dict) else None
        if not isinstance(rev, int):
            anomalies.append({"url": url_key, "reason": "invalid-rev"})
            continue

        prev = cached_revs.get(url_key)
        if prev is None:
            new.append(url_key)
        elif rev > prev:
            changed.append(url_key)
        elif rev == prev:
            unchanged.append(url_key)
        else:
            anomalies.append({"url": url_key, "reason": "rev-decrease", "cached": prev, "manifest": rev})

    removed = sorted(set(cached_revs) - set(entries))
    if removed and coverage_mode != "complete":
        # Outside complete coverage mode, omission is ambiguous.
        removed = []

    return {
        "site_changed": cached_site_rev is None or site_rev != cached_site_rev,
        "changed": sorted(changed),
        "new": sorted(new),
        "unchanged": sorted(unchanged),
        "removed": removed,
        "anomalies": anomalies,
        "site_rev": site_rev,
    }


def audit(base_url: str, url_key: str, expected_digest: str, timeout: int = 10, session: requests.Session | None = None) -> dict[str, Any]:
    """Audit a digest claim using identity-encoding fetch semantics."""
    s = session or requests.Session()
    url = urljoin(base_url.rstrip("/") + "/", url_key.lstrip("/"))
    try:
        r = s.get(url, headers={"Accept-Encoding": "identity"}, timeout=timeout, allow_redirects=False)
    except requests.RequestException as exc:
        return {"result": "inconclusive", "reason": "network-error", "error": str(exc)}

    if 300 <= r.status_code < 400:
        return {"result": "inconclusive", "reason": "redirect", "status_code": r.status_code}
    if r.status_code < 200 or r.status_code >= 300:
        return {"result": "inconclusive", "reason": "non-success", "status_code": r.status_code}

    computed = "sha256:" + hashlib.sha256(r.content).hexdigest()
    if computed == expected_digest:
        return {"result": "match", "computed": computed}
    return {"result": "mismatch", "computed": computed, "expected": expected_digest}


def check_site(
    base_url: str,
    cached_site_rev: int | None,
    cached_revs: dict[str, int] | None,
    timeout: int = 10,
    etag: str | None = None,
    last_modified: str | None = None,
    sample_audit_rate: float = 0.0,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """High-level convenience API: fetch + diff + optional sampled audit plan."""
    result = fetch(
        base_url,
        timeout=timeout,
        etag=etag,
        last_modified=last_modified,
        session=session,
    )
    if not result.ok:
        return {
            "fallback": True,
            "error": result.error,
            "status_code": result.status_code,
            "etag": result.etag,
            "last_modified": result.last_modified,
        }

    if result.status_code == 304:
        return {
            "fallback": False,
            "not_modified": True,
            "changed": [],
            "etag": result.etag,
            "last_modified": result.last_modified,
        }

    assert result.manifest is not None
    decisions = diff(result.manifest, cached_site_rev, cached_revs)

    # This minimal reference returns an audit candidate list; caller can decide sampling policy.
    audit_candidates = []
    if sample_audit_rate > 0:
        for url_key, entry in result.manifest["entries"].items():
            digest = entry.get("digest") if isinstance(entry, dict) else None
            if isinstance(digest, str):
                audit_candidates.append({"url": url_key, "digest": digest})

    decisions.update(
        {
            "fallback": False,
            "manifest": result.manifest,
            "etag": result.etag,
            "last_modified": result.last_modified,
            "audit_candidates": audit_candidates,
            "sample_audit_rate": sample_audit_rate,
        }
    )
    return decisions
