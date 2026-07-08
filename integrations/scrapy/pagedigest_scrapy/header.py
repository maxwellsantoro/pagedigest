"""Optional `PageDigest-State` cooperation header (SPEC §5.4).

Thin wrappers around the published `pagedigest` consumer helpers so Scrapy and
the reference library share one ABNF implementation.
"""

from __future__ import annotations

from typing import Optional, Tuple

from pagedigest import format_state_header, parse_state_header


def build(site_rev: int, manifest_path: Optional[str] = None) -> str:
    return format_state_header(site_rev, manifest_path)


def parse(value: str) -> Optional[Tuple[int, Optional[str]]]:
    """Publisher-side parse. Returns (site_rev, manifest_path|None) or None if
    the header is malformed — which the publisher MUST treat as no signal."""
    if not value:
        return None
    try:
        parsed = parse_state_header(value.strip())
    except ValueError:
        return None
    return parsed["site_rev"], parsed.get("manifest")
