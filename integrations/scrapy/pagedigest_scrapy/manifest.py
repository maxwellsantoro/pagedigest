"""Fetch, validate, and interpret a pagedigest manifest.

Every validation failure returns an *unusable* result so the caller falls back to
normal crawling. That is not defensive politeness; section 5.3 requires it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Dict, Optional

import requests

WELL_KNOWN = "/.well-known/pagedigest.json"
MAX_BYTES = 10 * 1024 * 1024  # spec 7.3 baseline: consumers MAY refuse >10MB
DIGEST_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")


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


class Unusable(Exception):
    """Raised internally to signal fall-back-to-normal-crawling."""


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
    """Validate per spec section 3. Returns a Manifest or None (unusable).

    `prev_site_rev` enforces monotonicity (4.1): a decrease is anomalous and
    triggers fallback for the whole site.
    """
    try:
        doc = json.loads(raw)
    except (ValueError, TypeError):
        return None
    try:
        if not isinstance(doc, dict):
            raise Unusable
        if doc.get("version") != 1:  # 3.1: unknown version -> unreadable
            raise Unusable
        site_rev = doc.get("site_rev")
        if not _is_int(site_rev):  # 5.3: non-integer -> fallback
            raise Unusable
        if prev_site_rev is not None and site_rev < prev_site_rev:
            raise Unusable  # 4.1: decrease -> anomaly

        entries_doc = doc.get("entries")
        if not isinstance(entries_doc, dict):
            raise Unusable
        entries: Dict[str, Entry] = {}
        for key, ent in entries_doc.items():
            if (
                not isinstance(key, str)
                or not key.startswith("/")
                or key.startswith("//")
            ):
                continue  # skip malformed keys, don't fail whole manifest
            if not isinstance(ent, dict) or not _is_int(ent.get("rev")):
                continue
            digest = ent.get("digest")
            if digest is not None:
                if not (isinstance(digest, str) and DIGEST_PATTERN.match(digest)):
                    digest = None  # only well-formed sha256 in v1
            entries[key] = Entry(rev=ent["rev"], digest=digest)

        if "coverage" not in doc:
            mode, prefixes = "unspecified", None
        else:
            cov = doc.get("coverage")
            if not isinstance(cov, dict):
                raise Unusable
            mode = cov.get("mode")
            prefixes = cov.get("prefixes")
            if mode == "complete":
                prefixes = None
            elif mode == "prefixes":
                if not (isinstance(prefixes, list) and prefixes):
                    raise Unusable  # malformed coverage -> unusable
                if not all(isinstance(p, str) and p.startswith("/") for p in prefixes):
                    raise Unusable
            else:
                raise Unusable
        return Manifest(
            site_rev=site_rev, entries=entries, coverage_mode=mode, prefixes=prefixes
        )
    except Unusable:
        return None


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)
