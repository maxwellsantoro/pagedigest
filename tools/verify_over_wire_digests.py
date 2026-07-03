#!/usr/bin/env python3
"""Verify pagedigest digest accuracy against live identity-encoded responses.

This tool is intended for dogfood/pre-production checks on a real deployment.
It fetches the manifest, samples URLs that include digest values, then fetches
those URLs with Accept-Encoding: identity and compares SHA-256 values.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass
from typing import Any

import requests
from pagedigest import identity_digest
from pagedigest import manifest_url as default_manifest_url
from pagedigest import resolve_url_key, validate_manifest

MAX_AUDIT_BYTES = 10 * 1024 * 1024


@dataclass
class AuditResult:
    url: str
    status: str
    detail: str


def build_manifest_url(base_url: str, manifest_url: str | None) -> str:
    if manifest_url:
        return manifest_url
    return default_manifest_url(base_url)


def fetch_manifest(url: str, timeout: int) -> dict[str, Any]:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    if not isinstance(data.get("entries"), dict):
        raise ValueError("manifest missing object entries")
    if (validation_error := validate_manifest(data)) is not None:
        raise ValueError(f"invalid manifest: {validation_error}")
    return data


def audit_entry(
    base_url: str,
    path: str,
    expected_digest: str,
    timeout: int,
    max_bytes: int = MAX_AUDIT_BYTES,
) -> AuditResult:
    try:
        url = resolve_url_key(base_url, path)
    except ValueError as exc:
        return AuditResult(path, "inconclusive", str(exc))
    try:
        r = requests.get(
            url,
            headers={"Accept-Encoding": "identity"},
            allow_redirects=False,
            timeout=timeout,
            stream=True,
        )
    except requests.RequestException as exc:
        return AuditResult(url, "inconclusive", f"network-error: {exc}")

    try:
        if 300 <= r.status_code < 400:
            return AuditResult(url, "inconclusive", f"redirect:{r.status_code}")
        if r.status_code < 200 or r.status_code >= 300:
            return AuditResult(url, "inconclusive", f"non-success:{r.status_code}")

        computed, size_error = identity_digest(r, max_bytes)
        if size_error is not None:
            return AuditResult(url, "inconclusive", size_error)
        if computed == expected_digest:
            return AuditResult(url, "match", "ok")
        return AuditResult(
            url, "mismatch", f"expected={expected_digest} computed={computed}"
        )
    finally:
        r.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify pagedigest digest values over the wire"
    )
    parser.add_argument("base_url", help="Site base URL, e.g. https://example.com")
    parser.add_argument(
        "--manifest-url",
        help="Override manifest URL (defaults to /.well-known/pagedigest.json)",
    )
    parser.add_argument(
        "--sample-size", type=int, default=25, help="Number of digest entries to sample"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for deterministic sampling"
    )
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=MAX_AUDIT_BYTES,
        help="Abort identity fetches larger than this many bytes",
    )
    args = parser.parse_args()

    manifest_url = build_manifest_url(args.base_url, args.manifest_url)
    manifest = fetch_manifest(manifest_url, timeout=args.timeout)

    digest_entries: list[tuple[str, str]] = []
    for path, entry in manifest["entries"].items():
        if not isinstance(entry, dict):
            continue
        digest = entry.get("digest")
        if isinstance(path, str) and isinstance(digest, str):
            digest_entries.append((path, digest))

    if not digest_entries:
        print("no digest entries found")
        return 0

    random.seed(args.seed)
    sample_size = min(args.sample_size, len(digest_entries))
    sample = random.sample(digest_entries, sample_size)

    results = [
        audit_entry(
            args.base_url, path, digest, timeout=args.timeout, max_bytes=args.max_bytes
        )
        for path, digest in sample
    ]

    match_count = sum(r.status == "match" for r in results)
    mismatch_count = sum(r.status == "mismatch" for r in results)
    inconclusive_count = sum(r.status == "inconclusive" for r in results)

    print(f"manifest: {manifest_url}")
    print(f"sampled: {sample_size}")
    print(f"match: {match_count}")
    print(f"mismatch: {mismatch_count}")
    print(f"inconclusive: {inconclusive_count}")

    for r in results:
        if r.status != "match":
            print(f"- {r.status}: {r.url} ({r.detail})")

    # Non-zero on mismatches so this can be used as a deployment gate.
    if mismatch_count > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
