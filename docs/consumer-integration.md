# Consumer integration guide

This guide is for crawlers, indexers, mirrors, and agents that want to avoid
re-fetching unchanged pages from publishers that expose
`/.well-known/pagedigest.json`.

The rule of thumb is simple: treat PageDigest as an optimization hint, never as
an authorization or correctness boundary. If the manifest is missing, invalid,
stale in an impossible way, or inconsistent with what you observe, fall back to
your normal crawl behavior.

## Minimal loop

1. Fetch the manifest from the origin root.
2. Validate the wire format.
3. Compare `site_rev` and per-URL `rev` values with your cached state.
4. Fetch only new and changed URLs.
5. Remove cached URLs only when manifest `coverage.mode` is `complete`.
6. Persist the new manifest state after the fetch cycle succeeds.

The Python reference consumer packages that loop as `check_site`:

```python
from pagedigest import check_site, resolve_url_key

decision = check_site(
    "https://example.com",
    cached_site_rev=state.get("site_rev"),
    cached_revs=state.get("revs") or {},
    etag=state.get("etag"),
    last_modified=state.get("last_modified"),
    sample_audit_rate=0.01,
)

if decision.get("fallback"):
    run_normal_crawl(reason=decision.get("error"))
elif decision.get("not_modified"):
    skip_cycle()
else:
    for url_key in decision["new"] + decision["changed"]:
        fetch_page(resolve_url_key("https://example.com", url_key))
```

See the persistent cache example at
[`implementations/python-consumer/examples/cache_persistence.py`](../implementations/python-consumer/examples/cache_persistence.py).

## State to persist

Persist only enough to make the next comparison deterministic:

| Field | Purpose |
|---|---|
| `site_rev` | Fast whole-site no-op detection. |
| per-URL `rev` map | Detect new, changed, unchanged, and removed entries. |
| `ETag` | Conditional manifest requests when the publisher supports them. |
| `Last-Modified` | Conditional manifest requests when `ETag` is unavailable. |

For `coverage.mode: "complete"`, URLs missing from the next manifest are
removals. For partial or prefix coverage, absence outside the declared coverage
is not evidence of removal.

## Safe fallback policy

Fall back to your existing crawl/index path when any of these occur:

- manifest request fails or returns a non-2xx status;
- manifest JSON is invalid or violates the spec;
- `site_rev` decreases;
- a per-entry `rev` decreases;
- URL keys cannot be resolved on the publisher origin;
- digest audits produce sustained mismatches.

Fallback means "do the conservative thing you already did before PageDigest."
It does not mean block the publisher or delete your cache.

## Digest auditing

`digest` is optional. When present, it is the SHA-256 of identity-encoded
response bytes. Consumers can sample audit unchanged entries to detect broken
publisher pipelines, CDN rewrites, or malicious manifests:

```python
from pagedigest import audit

out = audit(
    "https://example.com",
    "/docs/",
    "sha256:...",
)

if out["result"] == "mismatch":
    mark_manifest_untrusted_for_this_origin()
```

For deployment gates and operational checks, use the packaged CLI:

```bash
pagedigest verify-live https://example.com --sample-size 25
```

It exits:

- `0` when there are no sampled mismatches;
- `1` for manifest fetch/validation or argument errors;
- `2` when one or more sampled digests mismatch.

Redirects, temporary network failures, non-success page statuses, and response
body size caps are reported as inconclusive rather than as digest failures.

## Sending `PageDigest-State`

After a successful manifest observation, a consumer may send the optional
`PageDigest-State` request header on subsequent page requests:

```python
from pagedigest import format_state_header

headers = {
    "PageDigest-State": format_state_header(
        decision["manifest"]["site_rev"],
        "/.well-known/pagedigest.json",
    )
}
```

This is a corroborating signal for the publisher. It lets the publisher see
that the client knows a manifest revision and should be skipping unchanged
covered pages. It is not authentication and should not be used for access
control. See [cooperative automation](./cooperative-automation.md) for
publisher-side logging and classification patterns.

## Integration checklist

- [ ] Manifest fetch is origin-rooted, not page-path relative.
- [ ] Invalid manifests trigger normal crawl fallback.
- [ ] `site_rev` and per-URL `rev` decreases are treated as anomalies.
- [ ] Removed URLs are applied only under complete coverage.
- [ ] `ETag` and `Last-Modified` are persisted for conditional manifest fetches.
- [ ] Digest audits are sampled and size-capped.
- [ ] `PageDigest-State` is emitted only after a valid manifest observation.
- [ ] Metrics track skipped fetches, manifest failures, anomalies, audit
      mismatches, and inconclusive audit results.
