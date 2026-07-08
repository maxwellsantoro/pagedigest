# pagedigest-scrapy

A [Scrapy](https://scrapy.org) downloader middleware that **consumes** a
[pagedigest v1](https://pagedigest.org) manifest: it skips re-fetching covered
URLs whose `rev` hasn't changed since the last crawl, sends the optional
cooperation header, and audits a fraction of skips against publisher digests.

This is an experimental Scrapy adapter on top of the published consumer
library. Manifest validation and `PageDigest-State` header encode/decode are
**delegated to** [`pagedigest`](https://pypi.org/project/pagedigest/)
(`validate_manifest`, `format_state_header`, `parse_state_header`) so this
adapter cannot drift from the reference implementation. Integration notes live
in [`docs/consumer-integration.md`](../../docs/consumer-integration.md).

## What it does, mapped to the spec

- **site_rev fast path + per-URL `rev` compare (§3.1, §3.2).** A URL whose
  manifest `rev` equals the value cached from the last crawl is skipped via
  `IgnoreRequest`.
- **Cooperation header (§5.4).** Attaches `PageDigest-State: site_rev=N;
  manifest="/.well-known/pagedigest.json"` to page requests after reading the
  manifest, built to the ABNF (no leading zeros, path-safe). Only ever sends a
  `site_rev` it actually observed.
- **Digest audit (§5.2).** With probability `PAGEDIGEST_AUDIT_RATE` (default 1%),
  a skip-eligible URL is fetched instead with `Accept-Encoding: identity`, hashed,
  and compared to the manifest `digest`. A mismatch marks the URL suspect.
- **Containment ladder (§5.2).** Repeated mismatches across enough URLs escalate
  from URL-level suspicion to a site-level trust downgrade, after which the origin
  is no longer trusted for skipping until it re-earns it.
- **Cold-start hardening.** For the first hour with a new origin the audit rate
  is raised (`PAGEDIGEST_BOOTSTRAP_AUDIT_RATE`, default 25%), so a publisher earns
  trust by passing audits before you rely on its claims — addressing the
  first-contact gap the spec leaves to the consumer.
- **Fallback is the default (§5.3, §4.1).** Missing manifest, bad JSON, missing
  fields, unknown `version`, non-integer or **decreasing** `site_rev`, malformed
  coverage, or an oversized (>10 MB) manifest all resolve to normal crawling.
  A per-URL `rev` decrease is treated as anomalous for that URL: the page is
  fetched conventionally and the stored high-water `rev` is not lowered.
  The middleware can make a crawl slower-by-a-manifest-fetch, but never *wrong*.

## Status

This is an experimental consumer integration, not a published package yet. It is
kept in-tree to make the Scrapy adoption path concrete and testable.
Offline decision-logic tests (`tests/test_offline.py`) run in
`./tools/run_checks.sh` / CI; end-to-end Scrapy reactor demos stay manual.

## Install & enable

From this directory, use an isolated environment and install the local package
(pulls `pagedigest>=0.1.0` from PyPI, or point at the in-tree consumer):

```bash
python -m pip install -e ../../implementations/python-consumer
python -m pip install -e .
```

```python
# settings.py
DOWNLOADER_MIDDLEWARES = {
    "pagedigest_scrapy.middleware.PageDigestMiddleware": 585,
}
PAGEDIGEST_STORE = "pagedigest_state.db"   # SQLite crawl state (persist across runs)
PAGEDIGEST_AUDIT_RATE = 0.01               # steady-state digest audit fraction
# optional: PAGEDIGEST_BOOTSTRAP_AUDIT_RATE, PAGEDIGEST_MANIFEST_TTL,
#           PAGEDIGEST_SITE_DISTRUST_THRESHOLD, PAGEDIGEST_SEND_HEADER
```

Priority `585` places it just before Scrapy's `HttpCompressionMiddleware` (590)
so audit requests keep `Accept-Encoding: identity` intact.

It only helps **stateful** crawls: point `PAGEDIGEST_STORE` at a durable path and
reuse it across runs. The savings appear on the *second and later* crawls — the
first establishes the baseline.

## See it work

```bash
python examples/run_demo.py --store /tmp/pd.db --port 8760   # run 1: cold
python examples/run_demo.py --store /tmp/pd.db --port 8760   # run 2: warm
```

Observed on run 2 against the bundled 5-page localhost publisher:

```
pagedigest/skipped            5
pagedigest/bytes_saved_est    72
downloader/request_count      0     # every page skipped; manifest said nothing changed
```

## Tests

```bash
python tests/test_offline.py
```

Reactor-free tests cover: no-manifest fallback, first-contact-then-skip,
rev-bump refetch, per-URL rev-decrease high-water retention, `site_rev`
monotonicity fallback, out-of-coverage passthrough, digest-mismatch detection,
and site-distrust escalation.

## Notes & limits

- The manifest is fetched with a short synchronous `requests` call (no redirects)
  and cached per origin (TTL `PAGEDIGEST_MANIFEST_TTL`, default 300s). A
  high-throughput consumer would prefetch manifests through the scheduler; the
  decision logic is unchanged.
- Absent coverage metadata is treated as **unspecified** (not `complete`):
  omission is not "removed" and not "implicitly unchanged".
- Prefix coverage uses ordinary string-prefix matching; publishers should list
  trailing-slash prefixes (e.g. `/blog/`) to avoid sibling-path traps.
- `bytes_saved_est` is the body size recorded when each URL was last fetched, so
  it's an estimate of avoided transfer, not a live measurement.
- Trust state is per-origin and local. Cross-consumer / federated reputation is
  out of scope here (and deferred in the spec).
