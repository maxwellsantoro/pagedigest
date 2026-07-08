# Well-Known URI Registration Request: `pagedigest.json`

Filed as:
[protocol-registries/well-known-uris#98](https://github.com/protocol-registries/well-known-uris/issues/98).

Issue title:

```text
Registration request: pagedigest.json
```

Issue body:

````markdown
## URI suffix

`pagedigest.json`

## Change controller

PageDigest project / Maxwell Santoro

## Specification document(s)

- PageDigest v1 specification:
  https://raw.githubusercontent.com/maxwellsantoro/pagedigest/main/SPEC.md
- Project site:
  https://pagedigest.org/

## Status requested

Provisional.

The PageDigest wire format is final at version 1 (v1.0). The project
would like expert review before v1.0 and before claiming permanent status.

## Purpose

`/.well-known/pagedigest.json` identifies a site-level change-detection
manifest for automated consumers such as crawlers, indexers, mirrors, and
agents. The manifest lets a stateful consumer compare a publisher's monotonic
`site_rev` and per-URL `rev` values before re-fetching pages that have not
changed.

## Media type

`application/json`

## Security and privacy considerations

- Manifest integrity relies on HTTPS transport and the publisher's origin
  controls.
- A manifest can reveal a covered URL set. The specification supports partial
  coverage and cautions publishers against overclaiming complete coverage.
- Consumers are required to validate the manifest and apply normal resource
  limits before trusting it as an optimization signal.
- Consumers fall back to their normal crawl behavior when the manifest is
  missing, invalid, unavailable, or internally inconsistent.
- Optional `digest` values are SHA-256 hashes over identity-encoded response
  bytes and can be sampled by consumers to audit publisher correctness.

## Deployment and stability notes

- `pagedigest.org` publishes a live manifest at:
  https://pagedigest.org/.well-known/pagedigest.json
- `dotrepo.org` is a measured dogfood producer:
  https://github.com/maxwellsantoro/pagedigest/blob/main/docs/case-studies/dotrepo.md
- The repository includes a reference generator, reference consumer,
  conformance vectors, and release checklist:
  https://github.com/maxwellsantoro/pagedigest

Additional information: I understand that single-owner repositories are weak
references for permanent registration. This request is intended as an early
provisional registration / expert review request while the project gathers
broader deployment feedback.
````
