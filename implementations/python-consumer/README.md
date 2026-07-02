# Python Consumer (Minimal Reference)

## Install (from repo)

```bash
cd implementations/python-consumer
uv sync
uv pip install -e .
```

Requires Python ≥3.9. Runtime dependency: `requests`.

## API

- `fetch` — fetch and validate manifest; graceful fallback on errors
- `diff` — compare manifest to cached `site_rev` / per-URL `rev`
- `audit` — identity-encoding digest check
- `check_site` — `fetch` + `diff` + optional sampled audit plan
- `validate_manifest`, `resolve_url_key` — validation helpers

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

Conformance fixtures: `tests/test_vectors.py` exercises `../../test-vectors/`.