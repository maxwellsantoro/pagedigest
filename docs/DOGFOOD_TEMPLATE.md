# Dogfood Deployment Template

Use this template for the producer case study ([ROADMAP](../ROADMAP.md) Phase 3).

## Site

- Domain:
- Content profile (docs/blog/etc):
- Coverage mode (`complete` or `prefixes`):

## Generation Method

- Generator version:
- Generation trigger (build, webhook, schedule):
- Revision-state persistence mechanism:
- Manifest generated from rendered output directory (not source templates):

## Edge/CDN Byte Controls

- HTML/asset transforms disabled on covered paths (minify/injection/rewrites):
- Edge worker/script injections disabled on covered paths:
- Any unavoidable transformations documented:
- Preflight digest verification run (`tools/verify_over_wire_digests.py`) and result:

## Manifest Caching Policy

- `Cache-Control`:
- Conditional-request support (`ETag` / `Last-Modified`):
- Rationale for chosen freshness window:

## Example Manifest

- Manifest URL:
- Snapshot timestamp:
- Sample entries:

## Before/After Crawl Behavior

- Baseline request volume:
- With `pagedigest` request volume:
- Estimated skipped fetches:
- Observed bandwidth/compute delta:

Suggested concrete metrics:

- `manifest_requests_per_cycle`:
- `page_requests_per_cycle`:
- `skipped_fetch_percentage`:
- `audit_runs_per_cycle`:
- `audit_success_rate`:
- `audit_inconclusive_rate`:
- `estimated_origin_bandwidth_delta`:
- `estimated_consumer_compute_delta`:

## Audit Notes

- Audit sample rate:
- Match rate:
- Mismatch/inconclusive cases:

## Hygiene Footgun Found and Fixed

- Symptom:
- Root cause:
- Fix:
- Outcome:
