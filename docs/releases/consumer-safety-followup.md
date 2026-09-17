# Consumer safety follow-up

The updated review's two correctness findings are addressed in the experimental
Scrapy adapter and dogfood collection. Published implementation versions are
unchanged: these changes affect the in-tree adapter, examples, tooling, and site.

## Replay policy

The adapter bypasses and revokes replay on explicit request cache/validation
instructions. It conservatively declines response policies requiring HTTP
freshness or validation it does not implement. An observed ineligible network
response invalidates the prior body while retaining the revision high-water mark;
legacy stored responses are checked before reuse. See the
[adapter policy and limits](../../integrations/scrapy/README.md#cached-response-replay-and-scope).

Sixteen real middleware scenarios cover request bypass, response no-cache,
multiple header fields, qualified no-cache, policy transitions with unchanged
bodies/revisions, legacy entries, and restrictive responses encountered during
forced audits. These run through the Scrapy downloader and a local HTTP server.
The source suite now has 20 gates; isolated wheel-install checks also exercise
the in-tree adapter's policy and traversal tests.

## Whole-collection synchronization

Cloudflare's error template stays deployed but is excluded before manifest
generation. Its former `/404.html` entry is retired through the normal generator
state transition. The digest is not replaced with a redirect target's hash.
The generation helper and operational commands are documented in
[site-state/README.md](../../site-state/README.md).

The new deployment gate requires cold and warm complete snapshots of the exact
published revision, including audits of all reused digest-bearing resources.
Its first run caught an edge still serving revision 11 immediately after revision
12 was uploaded. Bounded retries use separate consumer state on each attempt;
previous revisions and incomplete snapshots never count as deployment success.

Live checks on September 17, 2026 UTC completed against `https://pagedigest.org`:

| Cycle | Site revision | Required page downloads | Audits | Completed resources |
|---|---:|---:|---:|---:|
| Cold | 12 | 3 | 0 | 3 |
| Warm (manifest HTTP 304) | 12 | 0 | 3 | 3 |
| Controlled homepage update | 13 | 1 (`/`) | 2 | 3 |

Every cycle also made one manifest request. The final live digest audit matched
all three entries, with zero mismatches and zero inconclusive results. The
[raw live-consumer report](../benchmarks/dogfood-sync-2026-09-17.json) records
request URLs/statuses, completed snapshots, local integrity reads, and timings.
The homepage evidence update was the controlled content change. Its revision and
cached body hash were required to advance before the changed cycle could pass.
[CI and deployment including whole-collection checks](https://github.com/maxwellsantoro/pagedigest/actions/runs/35165342997)
passed for that update.

## Comparative evidence and messaging

The [refined benchmark](../benchmarks/README.md) has seven strategies across six
scenarios, including equal audit policies, conditional sitemap fetching, and the
actual disk-backed consumer. All 42 combinations require equivalent resource
sets and bytes. The unchanged persistent cycle read and hashed 100 cached bodies;
local CPU, elapsed time, integrity reads, and network traffic are reported
separately. Scrapy callback/indexing/model processing still needs measurement in
the external operator's actual pipeline.

The homepage and README now lead their evidence sections with the comparative
benchmark. The GitHub repository description identifies the stable version 1 wire
format, replacing the stale RC description. No headline or protocol expansion was
needed.

The independently operated recurring-consumer trial remains open. This project's
live checks are dogfood evidence, not independent adoption. Its
[acceptance criteria](../benchmarks/README.md#independent-adoption-acceptance)
continue to require comparable alternatives, equivalent results and freshness,
and network, processing, audit, fallback, and operational costs.
