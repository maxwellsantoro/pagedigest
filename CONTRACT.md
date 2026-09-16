# Cooperation between publishers and consumers

This document explains the operational bargain around PageDigest. It is not a
legal contract, an access-control mechanism, or a content license. The
[specification](./SPEC.md) defines protocol behavior; the MIT license governs
reference implementation code.

A publisher maintains a change manifest. A recurring consumer uses it to reuse
results it already holds. Both can benefit when the cost of maintaining and
checking the manifest is lower than their existing refresh strategy.

## Publisher responsibilities

Maintain accurate revisions, retain durable revision history, and publish a
manifest that describes the applicable resources. Deploy page representations
before or atomically with the manifest. If digests are emitted, check them against
served identity-encoded bytes. [Publisher operations](./CONTENT_HYGIENE.md)
cover state recovery, byte churn, and reconciliation.

The reference generators compare full bytes. A publisher supplying semantic
revisions should document that choice so exact-byte mirrors can select an
appropriate validation policy.

## Consumer responsibilities

Retain usable results associated with cached revisions. Observing a manifest is
not completing a sync. Download or process missing results even if `site_rev`
matches, and retain normal discovery outside the manifest's scope. Link-following
crawlers need cached-response replay or a persistent discovery frontier.

Use audits according to the application's freshness and cost requirements.
A sampled digest match checks one representation; it does not prove correct
revision history or all skipped content. Preserve historical evidence where
available, retry inconclusive outcomes, and fall back when the manifest is
unreliable. See [the consumer guide](./docs/consumer-integration.md).

## Observable behavior

A consumer may send `PageDigest-State` to report a manifest observation. It is
not authentication, proof of a complete cache, or proof that a later fetch is
redundant. Missing caches, independent users, audits, different representations,
and reprocessing can all produce legitimate repeated requests.

Publisher telemetry should describe measured requests and costs, not infer
intent from a header or revision alone. The [cooperation logging guide](./docs/cooperative-automation.md)
explains the optional signal and its limits.

## Discovery and rate limiting

Advertise the manifest on ordinary successful responses:

```http
Link: </.well-known/pagedigest.json>; rel="https://pagedigest.org/rel"
```

Publishers may also include that discovery link in an existing rate-limit
response, together with `Retry-After` and a helpful explanation:

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 3600
Link: </.well-known/pagedigest.json>; rel="https://pagedigest.org/rel"
Content-Type: text/plain

This origin is rate-limiting requests. It also publishes a PageDigest manifest.
If your consumer retains previous results, the manifest may help reduce
refresh requests. Continue ordinary validation for uncovered or missing results.
```

Rate limits remain publisher policy. Publishing a manifest does not establish
that every client can use it, that repeated requests are wasteful, or that the
publisher has earned a protocol-defined entitlement to compliance. PageDigest
adds an optimization path; adopting it alone does not make unrelated bots change
behavior. It complements existing crawling policies and says nothing about
permission to use the fetched content.

## Evidence of value

Evaluate cooperation through equivalent results and freshness, followed by total
requests, transferred bytes, elapsed time, and processing cost. Include discovery,
manifest checks, audits, retries, and fallback. Avoid claiming model-token savings
unless the actual inference pipeline was measured.
