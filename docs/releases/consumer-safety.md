# Consumer safety release

Generator/launcher 0.3.0, Python consumer 0.2.0, and Astro integration 0.2.0 make reuse
conditional on usable local results and durable publisher history. The version 1
wire format remains unchanged. The npm launcher pins all four generator archives
by SHA-256.

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

## Verification

Verified September 16, 2026. Source release: `4ff9961`; launcher pins: `82bc620`.

- All 18 repository gates pass, including conformance, publisher recovery,
  interrupted/incomplete consumer syncs, real Scrapy traversal, isolated artifact
  installations, and 30 equivalent-result benchmark cycles.
- [Python 0.2.0 publishing](https://github.com/maxwellsantoro/pagedigest/actions/runs/35149000186)
  tests the exact built wheel before publishing. The wheel downloaded from PyPI
  then passed all 100 consumer tests and the real Scrapy traversal test in a new
  environment using the installed package. Its SHA-256 is
  `b1cd55d5ea98a47502d76084d527425d4702dc3582eeb83a2c84c0c5f3c9e311`.
- [Generator binaries](https://github.com/maxwellsantoro/pagedigest/releases/tag/generator-v0.3.0)
  built on Linux x64, macOS Intel/ARM, and Windows x64. Downloaded archive hashes
  match GitHub's asset digests and the launcher pins. The macOS ARM binary was
  exercised locally; this is not a claim of runtime testing on every platform.
- A fresh `cargo install pagedigest --version 0.3.0 --locked` and a fresh
  `npx pagedigest@0.3.0` installation each passed initialization, unchanged-run,
  missing-state rejection, and recovery-floor checks. The npx check used empty
  npm and binary caches, exercising the public download and digest verification.
- [Astro publishing](https://github.com/maxwellsantoro/pagedigest/actions/runs/35149002818)
  installs and tests the exact tarball before publication. A fresh npm download
  matched the published integrity and passed the same initialization, unchanged-run,
  changed-content, missing-state, and recovery checks outside the source tree.

The live dogfood audit after the safety changes returned three digest matches,
zero mismatches, and one inconclusive redirect (`/404.html`, HTTP 308). Redirects
are not silently counted as matches. No served-byte reconciliation was needed.
This deployment is operated by this project and does not satisfy the
[independent adoption criteria](../benchmarks/README.md#independent-adoption-acceptance).
