from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests


MANIFEST_PATH = "/.well-known/pagedigest.json"
DEFAULT_MAX_MANIFEST_BYTES = 10 * 1024 * 1024
URL_KEY_PATTERN = re.compile(r"^/([^#]*)?$")
DIGEST_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")
TIMESTAMP_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)$"
)
UNRESERVED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


@dataclass
class FetchResult:
    ok: bool
    status_code: int | None
    manifest: dict[str, Any] | None
    etag: str | None
    last_modified: str | None
    error: str | None


def _is_non_negative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _valid_percent_encoding(value: str, index: int) -> bool:
    if index + 2 >= len(value):
        return False
    return all(ch in "0123456789ABCDEFabcdef" for ch in value[index + 1 : index + 3])


def _validate_url_key(key: Any) -> str | None:
    if not isinstance(key, str):
        return "invalid-url-key-type"
    if not URL_KEY_PATTERN.match(key):
        return "invalid-url-key-pattern"
    if " " in key:
        return "invalid-url-key-space"

    index = 0
    while index < len(key):
        ch = key[index]
        if ch == "%":
            if not _valid_percent_encoding(key, index):
                return "invalid-url-key-encoding"
            index += 3
            continue
        if ord(ch) > 127:
            return "invalid-url-key-unencoded"
        if ch not in UNRESERVED and ch not in {"/", "?", "&", "=", ":", "@", "!", "$", "'", "(", ")", "*", "+", ",", ";"}:
            return "invalid-url-key-unencoded"
        index += 1
    return None


def resolve_url_key(base_url: str, url_key: str) -> str:
    """Resolve a manifest key without allowing it to escape the base origin."""
    if (validation_error := _validate_url_key(url_key)) is not None:
        raise ValueError(validation_error)

    base = urlsplit(base_url)
    if base.scheme.lower() not in {"http", "https"} or not base.netloc:
        raise ValueError("invalid-base-url")

    origin = urlunsplit((base.scheme, base.netloc, "/", "", ""))
    resolved = urljoin(origin, url_key)
    target = urlsplit(resolved)
    if target.scheme.lower() != base.scheme.lower() or target.netloc.lower() != base.netloc.lower():
        raise ValueError("url-key-origin-escape")
    return resolved


def _validate_timestamp(value: Any, field: str) -> str | None:
    if not isinstance(value, str) or not TIMESTAMP_PATTERN.match(value):
        return f"invalid-{field}"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return f"invalid-{field}"
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        return f"invalid-{field}"
    return None


def _validate_coverage(coverage: Any) -> str | None:
    if not isinstance(coverage, dict):
        return "invalid-coverage-type"

    mode = coverage.get("mode")
    if mode == "complete":
        return None
    if mode == "prefixes":
        prefixes = coverage.get("prefixes")
        if not isinstance(prefixes, list) or not prefixes:
            return "invalid-coverage-prefixes"
        for prefix in prefixes:
            if not isinstance(prefix, str) or not prefix.startswith("/"):
                return "invalid-coverage-prefix"
        return None
    return "invalid-coverage-mode"


def validate_manifest(manifest: dict[str, Any]) -> str | None:
    """Return an error code when the manifest is structurally invalid."""
    for field in ("version", "generated", "site_rev", "entries"):
        if field not in manifest:
            return f"missing-{field}"

    if manifest.get("version") != 1:
        return "unsupported-version"

    if (err := _validate_timestamp(manifest.get("generated"), "generated")) is not None:
        return err

    if not _is_non_negative_int(manifest.get("site_rev")):
        return "invalid-site-rev"

    entries = manifest.get("entries")
    if not isinstance(entries, dict):
        return "invalid-entries"

    if "coverage" in manifest:
        if (err := _validate_coverage(manifest.get("coverage"))) is not None:
            return err

    for url_key, entry in entries.items():
        if (err := _validate_url_key(url_key)) is not None:
            return err
        if not isinstance(entry, dict):
            return "invalid-entry-type"
        if not _is_non_negative_int(entry.get("rev")):
            return "invalid-rev"
        if "digest" in entry:
            digest = entry.get("digest")
            if not isinstance(digest, str) or not DIGEST_PATTERN.match(digest):
                return "invalid-digest"
        if "modified" in entry:
            if (err := _validate_timestamp(entry.get("modified"), "modified")) is not None:
                return err

    return None


def _read_manifest_body(response: requests.Response, max_bytes: int) -> tuple[bytes | None, str | None]:
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                return None, "manifest-too-large"
        except ValueError:
            return None, "invalid-content-length"

    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            return None, "manifest-too-large"
        chunks.append(chunk)
    return b"".join(chunks), None


def fetch(
    base_url: str,
    timeout: int = 10,
    etag: str | None = None,
    last_modified: str | None = None,
    session: requests.Session | None = None,
    max_bytes: int = DEFAULT_MAX_MANIFEST_BYTES,
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
        r = s.get(url, headers=headers, timeout=timeout, stream=True)
    except requests.RequestException as exc:
        return FetchResult(False, None, None, None, None, str(exc))

    if r.status_code == 304:
        return FetchResult(True, 304, None, r.headers.get("ETag"), r.headers.get("Last-Modified"), None)

    if r.status_code != 200:
        return FetchResult(False, r.status_code, None, r.headers.get("ETag"), r.headers.get("Last-Modified"), "manifest-unavailable")

    body, size_error = _read_manifest_body(r, max_bytes)
    if size_error is not None:
        return FetchResult(False, r.status_code, None, r.headers.get("ETag"), r.headers.get("Last-Modified"), size_error)

    assert body is not None
    try:
        manifest = json.loads(body)
    except ValueError:
        return FetchResult(False, r.status_code, None, r.headers.get("ETag"), r.headers.get("Last-Modified"), "invalid-json")

    if not isinstance(manifest, dict):
        return FetchResult(False, r.status_code, None, r.headers.get("ETag"), r.headers.get("Last-Modified"), "invalid-manifest-type")

    if (validation_error := validate_manifest(manifest)) is not None:
        return FetchResult(False, r.status_code, None, r.headers.get("ETag"), r.headers.get("Last-Modified"), validation_error)

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

    if cached_site_rev is not None and site_rev < cached_site_rev:
        return {
            "site_changed": False,
            "changed": [],
            "new": [],
            "unchanged": [],
            "removed": [],
            "anomalies": [
                {
                    "reason": "site-rev-decrease",
                    "cached": cached_site_rev,
                    "manifest": site_rev,
                }
            ],
            "site_anomaly": "site-rev-decrease",
            "site_rev": site_rev,
        }

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
        rev = entry.get("rev")
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
    try:
        url = resolve_url_key(base_url, url_key)
    except ValueError as exc:
        return {"result": "inconclusive", "reason": str(exc)}
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


def _sample_audit_candidates(
    manifest: dict[str, Any],
    unchanged: list[str],
    sample_audit_rate: float,
    rng: random.Random | None = None,
) -> list[dict[str, str]]:
    if sample_audit_rate <= 0:
        return []

    entries = manifest["entries"]
    pool: list[dict[str, str]] = []
    for url_key in unchanged:
        entry = entries.get(url_key)
        if not isinstance(entry, dict):
            continue
        digest = entry.get("digest")
        if isinstance(digest, str) and DIGEST_PATTERN.match(digest):
            pool.append({"url": url_key, "digest": digest})

    if not pool:
        return []

    sample_size = max(1, int(len(pool) * sample_audit_rate)) if sample_audit_rate < 1 else len(pool)
    sample_size = min(sample_size, len(pool))
    picker = rng or random.Random()
    return picker.sample(pool, sample_size)


def check_site(
    base_url: str,
    cached_site_rev: int | None,
    cached_revs: dict[str, int] | None,
    timeout: int = 10,
    etag: str | None = None,
    last_modified: str | None = None,
    sample_audit_rate: float = 0.0,
    session: requests.Session | None = None,
    max_bytes: int = DEFAULT_MAX_MANIFEST_BYTES,
    rng: random.Random | None = None,
) -> dict[str, Any]:
    """High-level convenience API: fetch + diff + optional sampled audit plan."""
    result = fetch(
        base_url,
        timeout=timeout,
        etag=etag,
        last_modified=last_modified,
        session=session,
        max_bytes=max_bytes,
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

    if decisions.get("site_anomaly") or decisions.get("anomalies"):
        return {
            "fallback": True,
            "error": decisions.get("site_anomaly") or "manifest-anomaly",
            "status_code": result.status_code,
            "etag": result.etag,
            "last_modified": result.last_modified,
            "manifest": result.manifest,
            "anomalies": decisions.get("anomalies", []),
        }

    audit_candidates = _sample_audit_candidates(
        result.manifest,
        decisions["unchanged"],
        sample_audit_rate,
        rng=rng,
    )

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
