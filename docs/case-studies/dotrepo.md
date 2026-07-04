# dotrepo.org dogfood case study

`dotrepo.org` is PageDigest's first production-style publisher: a static public
index of trust-aware repository metadata for automated clients. The site is a
good dogfood target because it publishes thousands of small JSON records whose
unchanged state is valuable to mirrors, agent caches, and search/indexing tools.

This report is based on the checked-in dotrepo public export generated on
2026-07-03 at 12:00:00 UTC, snapshot
`36f920af151bc66dfa0a93144857c004f08db1962d55991a70bfd0a1c44216b1`.

## Site

- Domain: `https://dotrepo.org`
- Content profile: static homepage and repository-index JSON API
- Coverage mode: `prefixes`, covering repository JSON records under `v0/repos/`
- Repository count in export: 613
- Covered PageDigest entries: 2,453

## Generation method

- Generator: dotrepo's Rust public exporter emits a PageDigest v1 manifest as
  part of the public export.
- Generation trigger: release/public-export build.
- Revision-state persistence: previous `/.well-known/pagedigest.json` is read
  back into the exporter so unchanged records retain their `rev` values.
- Manifest generated from rendered output directory: yes; entries are generated
  from the static JSON payloads that are published.

## Manifest caching policy

- Manifest URL: `https://dotrepo.org/.well-known/pagedigest.json`
- Manifest `site_rev`: 2
- Manifest generated: `2026-07-03T12:00:00Z`
- Manifest size: 674,421 bytes
- Covered records: 2,453

## Before/after crawl behavior

The export compares the current manifest to the previously published manifest.
For this snapshot:

| Metric | Value |
| --- | ---: |
| Baseline record fetches | 2,453 |
| PageDigest-aware record fetches | 135 |
| Manifest requests per cycle | 1 |
| Skipped unchanged record fetches | 2,318 |
| Skipped fetch percentage | 94.5% |
| Covered JSON bytes | 4,874,442 |
| Covered JSON bytes avoided | 4,127,371 |
| Covered-byte avoidance | 84.7% |
| Estimated tokens avoided | 1,031,842 |

Including the manifest download, a PageDigest-aware sync would fetch about
1,421,492 bytes for this cycle: 674,421 bytes of manifest plus 747,071 bytes of
changed covered records. Against a naive full covered-record fetch
(4,874,442 bytes), that is still about 70.8% less transferred data for the
covered record set.

## Example manifest

```bash
curl -s https://dotrepo.org/.well-known/pagedigest.json | jq '{site_rev, generated, entries: (.entries | length)}'
```

Expected shape for this snapshot:

```json
{
  "site_rev": 2,
  "generated": "2026-07-03T12:00:00Z",
  "entries": 2453
}
```

## Audit notes

- Digest mode: enabled for covered records.
- Local generation audit: the public export records every covered path's content
  digest and computes PageDigest economics from generated static payload bytes.
- Live over-wire audit: still required after deployment. Run
  `pagedigest verify-live https://dotrepo.org` to confirm CDN-served identity
  bytes match the generated digests.
- Known caveat: byte savings above are generated-export economics, not a claim
  that every deployed edge has already converged.

## Hygiene footgun found and fixed

- Symptom: public paths could tell different freshness stories; the homepage,
  `/v0/meta.json`, `/v0/stats.json`, immutable snapshot paths, and PageDigest
  manifest needed an explicit coherence contract.
- Root cause: public-origin coherence was implicit in the export process and
  smoke tests, not exposed as a single machine-checkable health artifact.
- Fix: dotrepo now emits `/v0/health.json`, validates homepage/meta/stats/repos
  counts and digests in the release gate, and requires the same route in its
  live edge canary.
- Outcome: the dogfood publisher now has a concrete health endpoint that helps
  distinguish a coherent deployment from cache or route split-brain.

## Why this matters

PageDigest prevents redundant fetching; dotrepo prevents redundant repository
interpretation. The dotrepo public index is therefore the sibling-stack proof:
one manifest lets clients skip unchanged repository records, and each fetched
record preserves trust, provenance, and conflict context.
