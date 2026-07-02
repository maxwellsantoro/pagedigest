# Python Consumer (Minimal Reference)

This is the minimal consumer reference implementation.

## API

- `fetch(base_url, ...)`: fetch and validate manifest with graceful fallback signals.
- `diff(manifest, cached_site_rev, cached_revs)`: compute changed/new/unchanged/removed/anomalous URLs.
- `audit(base_url, url_key, expected_digest, ...)`: identity-encoding digest audit helper.
- `check_site(base_url, cached_site_rev, cached_revs, ...)`: convenience wrapper around fetch + diff.

Conformance fixtures in `../../test-vectors/` are exercised by `tests/test_vectors.py` (validation and diff semantics).

## Example

```python
from pagedigest import check_site

decision = check_site(
    "https://example.com",
    cached_site_rev=12,
    cached_revs={"/": 3, "/about": 1},
    sample_audit_rate=0.01,
)
```
