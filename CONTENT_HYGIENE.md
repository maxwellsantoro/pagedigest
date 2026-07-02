# Content Hygiene Guide (RC)

This guide helps publishers avoid false churn in `rev` and `digest` values.

## Why this matters

If non-content bytes change on every build or request, `pagedigest` becomes noisy:

- Consumers re-fetch unchanged pages.
- Audit mismatch rates increase.
- Trust in the manifest decreases.

## Common churn sources

- Build timestamps in rendered pages.
- Randomized cache-busting query strings injected at build time.
- Session IDs / CSRF tokens embedded into static output.
- Analytics snippets that change per build.
- Dynamic aggregates in static templates (view counts, comment counts).
- CDN and edge features that rewrite HTML after deploy (see below).

## Case study: CDN feature injection

Observed on pagedigest.org's own first production day (2026-07-02):
Cloudflare's **Email Address Obfuscation** rewrote a `mailto:` link into a
`/cdn-cgi/l/email-protection` URL and injected a decode script before
`</body>`, so the served bytes for `/` no longer matched the manifest's
`digest` — an honest publisher failing its own audit because of host
middleware. Pages without an email address on the same host audited clean.

Any edge feature that mutates HTML bytes has the same effect. Known
offenders include email obfuscation, auto-minification, script injectors
(RUM/analytics beacons, Rocket Loader-style optimizers), and bot-management
snippets. Before publishing digests, either:

- disable HTML-mutating edge features for the origin, or
- audit each covered URL over the wire after deploy
  (`tools/verify_over_wire_digests.py`) and omit `digest` for URLs the host
  refuses to serve byte-stable.

`rev` integers remain valid either way — this failure mode only poisons
`digest` audits, but a poisoned audit reads as publisher dishonesty to
consumers, which is worse than omitting the digest.

## Practical pipeline pattern

Recommended order:

1. Render site to final deployable artifacts.
2. Ensure final output is deterministic for content-bearing pages.
3. Generate `pagedigest` from rendered output.
4. Deploy pages and manifest atomically (or pages first, then manifest).

## Digest reliability note

The current minimal Rust generator hashes source file bytes from the selected input directory.

Use it against final rendered output whenever possible. If CDN/edge layers transform HTML bytes (for example minification or script injection), digest audits may fail even when publisher intent is honest.

## Quick checklist before publishing

- [ ] Input directory is final rendered output (not source templates).
- [ ] Output excludes non-content artifacts (maps/temp files).
- [ ] Global template timestamp/churn is removed or stabilized.
- [ ] Manifest and pages are deployed in a consistent order.
- [ ] Initial audit sample confirms low mismatch/inconclusive rates.

## If you cannot make bytes stable

For URLs with unavoidable non-content churn:

- omit `digest` for those URLs,
- keep `rev` monotonic and content-driven,
- document the limitation in publisher notes.

## Dogfood verification helper

Use `tools/verify_over_wire_digests.py` against a live deployment to sample digest-bearing entries and compare manifest hashes to identity-encoded responses over the wire.

Example:

```bash
python tools/verify_over_wire_digests.py https://example.com --sample-size 25
```
