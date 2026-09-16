# Controlled consumer benchmark

This is a **local HTTP experiment**, not an independently operated production
consumer. The checked-in [raw report](./local-2026-09-16.json) records a run on
September 16, 2026 with 100 repetitive HTML documents and gzip enabled.
All 30 completed consumer/scenario combinations reproduced the exact current
resource set and bytes. Each cycle sees one coherent fixture version.

```bash
uv run --project implementations/python-consumer --locked python \
  tools/benchmark_consumers.py --pages 100 --output /tmp/pagedigest-benchmark.json
```

Request counts include discovery, manifests, conditional page requests, and audits.
Payload bytes are actual compressed response-body bytes counted by the local
server, except identity audit responses. HTTP response-header bytes and elapsed
time are separate fields. TLS, TCP, request headers, rendering, and model inference
are not measured. Timings depend on the machine and are not performance claims.
The baseline full and conditional crawlers fetch an accurate sitemap for discovery;
the fingerprint and PageDigest manifests also describe additions and removals.

| Scenario | Full | Conditional HTTP | Accurate sitemap | Fingerprint manifest | PageDigest (1% audits) |
|---|---:|---:|---:|---:|---:|
| cold | 101 | 101 | 101 | 101 | 101 |
| no-change | 101 | 101 | 1 | 1 | 2 |
| sparse-change | 101 | 101 | 3 | 3 | 4 |
| template-change | 101 | 101 | 101 | 101 | 101 |
| add-remove | 101 | 101 | 2 | 2 | 3 |
| cache-eviction | 101 | 101 | 2 | 2 | 3 |

The accurate sitemap and fingerprint baselines can match or outperform PageDigest
on this cooperative fixture. This is expected: batching accurate metadata supplies
most of the request savings. Counters add ordered change signals and permit a
semantic revision independent of a byte digest, but require durable history.
The fingerprint baseline has no counter history to recover. PageDigest spends
additional requests on audits; those costs are included, not hidden.

The benchmark does not establish useful scale beyond this fixture. Version 1's
single manifest and the reference 10 MiB limit bound practical coverage; larger
sites need measured partial-coverage strategies. No claim of token savings follows
from bytes divided by four.

## Safety evidence outside the performance fixture

The repository suite separately exercises publisher state loss/recovery, local
body loss/corruption, equal-revision incomplete caches, interrupted downloads,
audit mismatch/inconclusive recovery, partial coverage semantics, and real Scrapy
parent/child traversal. Deployment skew is handled conservatively through audit
failure/retry tests; no multi-edge production experiment is claimed.

## Independent adoption acceptance

The next adoption milestone requires an independent operator using a recurring
consumer against a separately operated publisher. Record the software/artifact
versions, collection scope, observation dates, and freshness requirements.

Compare conditional HTTP, accurate sitemap, fingerprint manifest, and PageDigest
where applicable. ResourceSync should be included when already supported or when
its richer synchronization capabilities are part of the workload. Require equal
resource sets and required content/processing results before counting savings.

Exercise cold and unchanged runs, sparse and broad edits, additions/removals,
cache eviction, interrupted processing, publisher recovery, partial coverage,
and deployment skew. Report total requests, compressed bytes, latency, fallback
and audit rates, missed/delayed updates, and actual processing cost. Measure model
tokens only if unchanged content actually enters the original inference pipeline.
This milestone remains open; the local report does not substitute for it.
