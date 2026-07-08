"""Fetch, validate, and interpret a pagedigest manifest.

Validation and URL-key rules come from the published `pagedigest` consumer so
this adapter cannot drift from the reference library. Every validation failure
returns an *unusable* result so the caller falls back to normal crawling
(SPEC §5.3).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Optional

import requests
from pagedigest import validate_manifest

WELL_KNOWN = "/.well-known/pagedigest.json"
MAX_BYTES = 10 * 1024 * 1024  # SPEC §7.3 baseline: consumers MAY refuse >10MB


@dataclass
class Entry:
    rev: int
    digest: Optional[str] = None


@dataclass
class Manifest:
    site_rev: int
    entries: Dict[str, Entry]
    # "complete" | "prefixes" | "unspecified" (coverage absent)
    coverage_mode: str = "unspecified"
    prefixes: Optional[list] = None
    manifest_path: str = WELL_KNOWN

    def covers(self, path: str) -> bool:
        if self.coverage_mode == "prefixes":
            return any(path.startswith(p) for p in (self.prefixes or []))
        # complete: covered iff listed. unspecified: same for skip decisions
        # (omission is not "removed" and not "implicitly unchanged").
        return path in self.entries

    def entry_for(self, path: str) -> Optional[Entry]:
        return self.entries.get(path)


def fetch(
    origin: str,
    timeout: float = 10.0,
    session: Optional[requests.Session] = None,
    max_bytes: int = MAX_BYTES,
) -> Optional[bytes]:
    """GET the well-known manifest with a hard size cap. Returns raw bytes, or
    None on any transport/size failure (-> fallback). Redirects are not followed.
    """
    s = session or requests
    url = origin.rstrip("/") + WELL_KNOWN
    try:
        r = s.get(
            url,
            timeout=timeout,
            stream=True,
            allow_redirects=False,
            headers={"Accept": "application/json"},
        )
        if r.status_code != 200:
            return None
        buf = bytearray()
        for chunk in r.iter_content(8192):
            buf += chunk
            if len(buf) > max_bytes:
                return None  # 7.3: abort oversized manifests
        return bytes(buf)
    except requests.RequestException:
        return None


def parse(raw: bytes, prev_site_rev: Optional[int]) -> Optional[Manifest]:
    """Validate with the reference consumer, then apply site_rev monotonicity.

    `prev_site_rev` enforces SPEC §4.1: a decrease is anomalous and triggers
    fallback for the whole site.
    """
    try:
        doc = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if not isinstance(doc, dict):
        return None
    if validate_manifest(doc) is not None:
        return None

    site_rev = doc["site_rev"]
    if prev_site_rev is not None and site_rev < prev_site_rev:
        return None

    entries: Dict[str, Entry] = {}
    for key, ent in doc["entries"].items():
        digest = ent.get("digest") if isinstance(ent, dict) else None
        entries[key] = Entry(
            rev=ent["rev"],
            digest=digest if isinstance(digest, str) else None,
        )

    if "coverage" not in doc:
        mode, prefixes = "unspecified", None
    else:
        cov = doc["coverage"]
        mode = cov["mode"]
        prefixes = None if mode == "complete" else list(cov.get("prefixes") or [])

    return Manifest(
        site_rev=site_rev,
        entries=entries,
        coverage_mode=mode,
        prefixes=prefixes,
    )
