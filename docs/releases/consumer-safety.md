# Consumer safety release

Generator 0.3.0, Python consumer 0.2.0, and Astro integration 0.2.0 make reuse
conditional on usable local results and durable publisher history. The version 1
wire format remains unchanged. The npm launcher update follows verified generator
release archives.

## Migration

- **Rust generator 0.3.0 / Astro 0.2.0:** existing state remains readable. Missing
  state fails instead of silently resetting revisions. Use `--init` or
  `initialize: true` once for a first publication, then remove it. Recover missing
  history only with a trustworthy high-water bound using `--recover-floor` or
  `recoverFloor`. See [publisher operations](../../CONTENT_HYGIENE.md#durable-publisher-state).
- **Python consumer 0.2.0:** supply `cached_manifest` with HTTP validators to enable
  conditional requests. Process returned downloads and audit candidates even if
  `not_modified` is true. `cached_revs` must describe results still available.
  The persistent example validates body integrity, performs audits on 304 cycles,
  and preserves completed snapshots through interrupted downloads.
- **Experimental Scrapy adapter:** unchanged requests now replay cached responses
  instead of raising `IgnoreRequest`. Callbacks continue to run so an unchanged
  parent cannot hide changed descendants. Old stores without response bodies
  refill from the network. This adapter remains an in-tree integration.

Release checks include conformance fixtures, publisher recovery, failed syncs,
real Scrapy traversal, isolated artifact installations, and a controlled HTTP
benchmark that requires equivalent content and resource sets before counting
savings. [Benchmark scope and results](../benchmarks/README.md).

Independent production-consumer evidence remains an open adoption milestone.
Registry availability and exact versions are recorded in the
[version matrix](../../README.md#version-matrix).
