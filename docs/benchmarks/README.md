# Controlled consumer benchmark

This is a **local HTTP experiment**, not an independently operated production
consumer. The [refined report](./refined-2026-09-16.json) records seven strategies
across six scenarios on September 16, 2026: **42 consumer/scenario combinations**
on 100 repetitive HTML documents with gzip enabled. Every combination reproduced
the exact current resource set and bytes. Each cycle sees one coherent fixture
version. The [original five-strategy report](./local-2026-09-16.json) remains
available as historical evidence; it contained 30 combinations.

```bash
uv run --project implementations/python-consumer --locked python \
  tools/benchmark_consumers.py --pages 100 --output /tmp/pagedigest-benchmark.json
```

Request counts include discovery, manifests, conditional page requests, and audits.
Payload bytes are actual compressed response-body bytes counted by the local
server, except identity audit responses. HTTP response-header bytes and elapsed
time are separate fields. TLS, TCP, request headers, rendering, and model inference
are not measured. Timings depend on the machine and are not performance claims.
All sitemap-based strategies conditionally fetch an accurate sitemap using ETags
after the cold cycle, just as the two manifest formats do. The full and conditional
crawlers use that sitemap for discovery;
the fingerprint and PageDigest manifests also describe additions and removals.

| Scenario | Full | Conditional HTTP | Accurate sitemap | Fingerprint | Fingerprint + audits | PageDigest + audits | Persistent PageDigest |
|---|---:|---:|---:|---:|---:|---:|---:|
| cold | 101 | 101 | 101 | 101 | 101 | 101 | 101 |
| no-change | 101 | 101 | 1 | 1 | 2 | 2 | 2 |
| sparse-change | 101 | 101 | 3 | 3 | 4 | 4 | 4 |
| template-change | 101 | 101 | 101 | 101 | 101 | 101 | 101 |
| add-remove | 101 | 101 | 2 | 2 | 3 | 3 | 3 |
| cache-eviction | 101 | 101 | 2 | 2 | 3 | 3 | 3 |

Both audited manifest strategies sample 1% of reusable bodies (rounded down,
minimum one when the pool is nonempty), fetch identity bytes, and compare both
the declared digest and cached representation. The fingerprint mode without audits
remains a configured-workflow comparison; the added audited mode separates
verification traffic from format overhead. For example, the unchanged audited
fingerprint and PageDigest cycles each transferred 2,120 body bytes in two requests.
After a sparse edit they used four requests each, with 6,525 versus 6,692 body bytes.
Those are fixture observations, not a claim of a general performance advantage.

The accurate sitemap and fingerprint baselines can match or outperform PageDigest
on this cooperative fixture. This is expected: batching accurate metadata supplies
most of the request savings. Counters add ordered change signals and permit a
semantic revision independent of a byte digest, but require durable history.
The fingerprint baseline has no counter history to recover. Audits add requests
for either format; those costs are included, not hidden.

The benchmark does not establish useful scale beyond this fixture. Version 1's
single manifest and the reference 10 MiB limit bound practical coverage; larger
sites need measured partial-coverage strategies. No claim of token savings follows
from bytes divided by four.

## Local consumer work

The `pagedigest-persistent` strategy runs the actual persistent example against
real disk state and content-addressed bodies. Its elapsed time includes state
loading, hashing existing cached bodies, HTTP planning/audits/downloads, and
snapshot persistence. `consumer_thread_cpu_seconds` measures the consumer thread,
excluding the local HTTP server's threads. `cache_integrity_bytes`,
`cache_integrity_bodies`, and `cache_integrity_seconds` isolate its existing-body
integrity pass. The final independent byte-equivalence assertion is outside the
measured cycle for every strategy.

In the refined 100-document unchanged cycle, this consumer read and hashed all
100 cached bodies (211,990 bytes). It used two network requests, about 7.4 ms elapsed
and 5.5 ms consumer-thread CPU on this machine; about 2.2 ms was the integrity pass.
The in-memory PageDigest strategy took about 2.3 ms elapsed. These single local
samples demonstrate work the planning-only comparison omitted; they are not
production latency forecasts or statistically established speed differences.

The persistent example requests identity bodies for required downloads, so its
wire bytes can exceed the gzip-enabled in-memory strategies. The report retains
that real behavior instead of silently normalizing it away. This mode does not
measure Scrapy callback parsing or an indexer's/model's downstream work. An
external trial must instrument whichever integration and processing pipeline it
actually deploys, including replay callbacks and operational maintenance.

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
