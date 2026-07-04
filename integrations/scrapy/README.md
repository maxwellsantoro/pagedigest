# pagedigest-scrapy

A [Scrapy](https://scrapy.org) downloader middleware that **consumes** a
[pagedigest v1](https://pagedigest.org) manifest: it skips re-fetching covered
URLs whose `rev` hasn't changed since the last crawl, sends the optional
cooperation header, and audits a fraction of skips against publisher digests.

pagedigest has a publishing side and a spec, but no consumer — so nothing yet
demonstrates the request reduction the protocol promises, or exercises the
publisher-honesty side of the trust model. This is that missing half, against a
real crawler.

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
  fields, unknown `version`, non-integer or **decreasing** `site_rev`/`rev`, or an
  oversized (>10 MB) manifest all resolve to normal crawling. The middleware can
  make a crawl slower-by-a-manifest-fetch, but never *wrong*.

## Status

This is an experimental consumer integration, not a published package yet. It is
kept in-tree to make the consumer-side adoption path concrete and testable.

## Install & enable

From this directory, use an isolated environment and install the local package:

```bash
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

Seven reactor-free tests cover: no-manifest fallback, first-contact-then-skip,
rev-bump refetch, `site_rev` monotonicity fallback, out-of-coverage passthrough,
digest-mismatch detection, and site-distrust escalation.

## Notes & limits

- The manifest is fetched with a short synchronous `requests` call and cached per
  origin (TTL `PAGEDIGEST_MANIFEST_TTL`, default 300s). A high-throughput consumer
  would prefetch manifests through the scheduler; the decision logic is unchanged.
- `bytes_saved_est` is the body size recorded when each URL was last fetched, so
  it's an estimate of avoided transfer, not a live measurement.
- Trust state is per-origin and local. Cross-consumer / federated reputation is
  out of scope here (and deferred in the spec).
