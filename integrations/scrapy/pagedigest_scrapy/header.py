"""The optional `PageDigest-State` cooperation header (spec 5.4).

    PageDigest-State = "site_rev=" 1*DIGIT [ "; manifest=" DQUOTE absolute-path DQUOTE ]

Rules that matter: no leading zeros except the value 0; the manifest value must
begin with `/` and contain no fragment, quote, backslash, CR, or LF. A consumer
MUST NOT send a site_rev it did not observe from that origin -- the caller is
responsible for only passing an observed value.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

_BAD = set('"\\\r\n#')
_HEADER_RE = re.compile(r'^site_rev=(0|[1-9]\d*)(?:; manifest="(/[^"\\\r\n#]*)")?$')


def build(site_rev: int, manifest_path: Optional[str] = None) -> str:
    if not isinstance(site_rev, int) or site_rev < 0:
        raise ValueError("site_rev must be a non-negative integer")
    h = f"site_rev={site_rev}"
    if manifest_path is not None:
        if not manifest_path.startswith("/") or _BAD & set(manifest_path):
            raise ValueError("invalid manifest path")
        h += f'; manifest="{manifest_path}"'
    return h


def parse(value: str) -> Optional[Tuple[int, Optional[str]]]:
    """Publisher-side parse. Returns (site_rev, manifest_path|None) or None if
    the header is malformed -- which the publisher MUST treat as no signal."""
    if not value:
        return None
    m = _HEADER_RE.match(value.strip())
    if not m:
        return None
    return int(m.group(1)), m.group(2)
