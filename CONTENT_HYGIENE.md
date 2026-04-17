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
