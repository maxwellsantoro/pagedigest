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
- `validate_manifest`, `resolve_url_key`, `manifest_url` — validation and URL helpers
- `format_state_header`, `parse_state_header` — strict optional `PageDigest-State` helpers

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

After a successful manifest check, an integration may make its observed state
visible on subsequent page requests:

```python
from pagedigest import format_state_header

headers = {
    "PageDigest-State": format_state_header(
        decision["manifest"]["site_rev"],
        "/.well-known/pagedigest.json",
    )
}
```

This is a corroborating observation signal, not authentication. See
[SPEC.md §5.4](../../SPEC.md#54-optional-cooperation-request-header).

Conformance fixtures: `tests/test_vectors.py` exercises `../../test-vectors/`.

## Persistent cache example

```bash
uv run python examples/cache_persistence.py https://example.com ./pagedigest-cache.json
```

The example stores `site_rev`, per-URL `rev`, `ETag`, and `Last-Modified`
between runs. It prints page fetch decisions so crawler/indexer integrations can
replace the `print` calls with their own fetch pipeline.
