# The pagedigest Contract

> *This document is explanatory, not legal. It describes the social and technical bargain that makes the protocol work, the obligations each side accepts by participating, and the conditions under which enforcement is legitimate. It is not a contract in the legal sense, creates no rights or obligations enforceable in court, and is not a license. The MIT license governs use of the reference implementations; the technical spec governs the wire format.*

## What this document is

This document describes what `pagedigest` is *for*. It is the social framework around the technical specification. Publishers and consumers who want to understand the intent of the protocol — and the conditions under which each side earns the cooperation of the other — should read this alongside the technical spec.

The technical spec defines the wire format. This document defines the bargain.

## The symmetry

Right now, publishers and crawlers are having the same argument from opposite sides.

A publisher running a docs site or a blog looks at their logs and sees the same AI crawlers fetching the same URLs hundreds of times for content that hasn't changed in months. They see the bandwidth bill, the origin load, the wasted CPU. They feel justified in blocking, rate-limiting, or deploying increasingly aggressive bot detection.

An engineer running a crawler at an AI lab looks at their compute logs and sees headless browsers spinning up thousands of times to re-render pages that are byte-identical to the version they fetched yesterday. They see the compute bill, the IP rotation overhead, the rendering tax. They feel justified in routing around bot detection because they're just trying to get the job done.

Both sides are describing the same waste. Neither side benefits from it. The problem is not that the two sides have opposed interests. The problem is that the two sides have no cheap way to coordinate.

`pagedigest` is the coordination.

This is the structural test the protocol passes that `robots.txt` fails: both sides can sincerely advocate for it using the same argument. A publisher can say to a crawler *"if you would just use the manifest, I wouldn't have to rate-limit you."* A crawler can say to a publisher *"if you would just publish the manifest, I wouldn't have to hammer your server."* The sentences are symmetric. Both sides are describing a cooperation that is in their own interest, not a concession to the other side.

## Why the alignment exists but hasn't been actionable

The alignment between publishers and crawlers around redundant fetching is real but has been structurally inaccessible for three reasons.

First, publishers don't trust crawlers to respect soft signals. `Last-Modified` is easy to ignore because it's just a claim, and a crawler that trusts it risks missing updates. So crawlers rationally ignore it and fetch anyway.

Second, crawlers don't have a cheap way to know what changed across a site. Even `ETag` with `304 Not Modified` requires one HEAD request per URL, which for a large site means thousands of requests per cycle regardless of how little actually changed.

Third, neither side has a way to verify the other's cooperation. A publisher claiming to have efficient caching has no way to demonstrate it. A crawler claiming to respect efficiency hints has no way to prove it.

`pagedigest` addresses all three simultaneously. One file per site lists every URL with a monotonic integer version. A crawler fetches that one file, compares integers, and fetches only pages whose integer moved. Optional cryptographic hashes let crawlers spot-audit publisher claims. The audit is falsifiable — publishers who lie get caught, publishers who cooperate in good faith accumulate trust.

## The contract

The protocol functions as a contract between publishers and consumers. Each side has obligations. Each side has earned rights. The contract only holds when both sides meet their obligations.

### Publisher obligations

A publisher who publishes a `pagedigest` manifest is committing to the following:

The manifest will be reachable at `/.well-known/pagedigest.json` and will be a valid document conforming to the specification.

The `site_rev` integer will increment when any URL covered by the manifest has its content changed, or when covered URLs are added to or removed from the manifest, and will not increment for unrelated reasons — cache invalidations, deploys that don't change content, tracking-pixel updates, A/B bucket reshuffling, or any other operational churn that doesn't represent actual content change.

Per-URL `rev` integers will increment only when the content of that specific URL has changed. A publisher whose `rev` increments without content change has broken the protocol, even if the increment was accidental.

Where `digest` values are provided, they will be accurate cryptographic hashes of the identity-encoded bytes served for the corresponding URL.

The publisher will treat reported manifest errors in good faith and repair them promptly. The protocol relies on the manifest being accurate; a publisher who knowingly maintains inaccurate manifests forfeits the cooperation of crawlers.

### Consumer obligations

A consumer that chooses to consume `pagedigest` manifests is committing to the following:

The consumer will fetch the manifest before fetching individual URLs on the site, at whatever frequency is consistent with the consumer's own freshness requirements.

The consumer will compare `site_rev` against its cached value and, when unchanged, will refrain from fetching individual URLs.

When `site_rev` has changed, the consumer will compare per-URL `rev` values against cached values and fetch only URLs whose `rev` has incremented.

The consumer will periodically audit `digest` values where present, by fetching the URL with `Accept-Encoding: identity`, computing the hash of the response body, and comparing to the manifest's `digest` field. A reasonable audit rate is approximately 1% of manifest-derived skips, though consumers are free to choose their own rate.

Where audit mismatches exceed a consumer-defined threshold, the consumer is expected to downgrade trust in that publisher's manifest and may fall back to unconditional fetching.

Different consumers will choose different thresholds based on risk tolerance and crawl cost. A consumer may begin with a conservative default and tighten or relax it based on observed publisher reliability over time.

### Earned enforcement

A publisher who meets their obligations has strong justification to rate-limit or block consumers that ignore the manifest. This is the protocol's intended escalation path when a valid manifest is ignored. A consumer that continues to fetch a site redundantly after being shown a valid manifest is imposing real cost on a publisher who has done real work to make that cost unnecessary, and the publisher is justified in responding.

Conversely, a publisher who does not meet their obligations does not have this justification. Citing `pagedigest` in a rate-limit response while maintaining a stale, dishonest, or absent manifest is a violation of the contract, and consumers are encouraged to treat such sites as maintaining an unreliable manifest or not participating reliably in the protocol.

The legitimacy of escalation depends on the manifest being valid, current, and specific to the traffic being limited. Without that grounding, the enforcement is just another bot-war escalation. With it, the publisher's response is connected to measurable evidence of waste.

## The 429 pattern

When a publisher with a valid, honestly maintained manifest rate-limits a consumer for redundant fetching, the recommended response carries information through several channels at once, because no single channel reaches every consumer reliably.

### The Link header (primary programmatic channel)

Every rate-limit response from a publisher who maintains a valid manifest SHOULD include:

```
Link: </.well-known/pagedigest.json>; rel="https://pagedigest.org/rel"
```

This header is the most reliable channel for reaching automated systems. Crawler frameworks can be configured to inspect `Link` headers on error responses without any human in the loop. Adopting this convention across the ecosystem allows a crawler library to detect manifest availability programmatically and adjust behavior automatically — which is the right level for this signal to operate at long-term.

When this relation is expressed as a URI in `Link`, clients should treat it as an identifier for relation semantics, not as a URL they are expected to dereference during ordinary operation.

### The response body (secondary, human channel)

The recommended response body cites specific evidence of waste and points to the manifest:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 3600
Link: </.well-known/pagedigest.json>; rel="https://pagedigest.org/rel"
Content-Type: text/plain

You fetched /blog/hello-world 47 times in the last 24 hours.
According to our manifest, this URL has rev: 3 and has not
changed since 2026-02-08.

The manifest is at /.well-known/pagedigest.json. If your
crawler respected it, you would have fetched this page once,
compared the integer on subsequent visits, and not made the
other 46 requests.

We are not trying to ban you. We are asking you to use the
manifest so we can both stop wasting bandwidth.
```

This message is for the human engineer who eventually investigates why a crawler's success rate against a particular site has dropped. Many automated crawler fleets silently drop 429 response bodies and surface only the status code; the body is read when an engineer looks into the failure pattern, not on every request. That investigation often happens because compute or rate-limit metrics surface the problem internally — which is itself one of the design's intended outcomes.

The body's value is in being precise enough to immediately diagnose: a crawler engineer reading this in their logs has a specific URL, a specific count, and a specific manifest path. There's nothing to argue with and a clear next step.

Publishers MAY include specific request counts, last-change dates, or other measured evidence when their infrastructure tracks it. Publishers without that telemetry MAY use a simpler message that still cites the manifest:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 3600
Link: </.well-known/pagedigest.json>; rel="https://pagedigest.org/rel"
Content-Type: text/plain

You've been rate-limited for repeated requests to URLs that
haven't changed.

This site publishes a pagedigest manifest at
/.well-known/pagedigest.json. If your crawler respected it,
you would skip unchanged pages and avoid this rate limit.
```

The important properties are that the message cite the manifest, set the `Link` header, and avoid the adversarial frame.

### Pattern detection (tertiary, behavioral channel)

The third channel is pattern: as adoption grows, crawler engineers will encounter the pagedigest relation in `Link` headers across many sites. That cross-site pattern is itself a signal — it tells a consumer operator that a recognizable convention exists and that integrating it would resolve a class of failures, not just one site's complaints.

This is the slowest channel but the most durable. It's how `robots.txt` and `sitemap.xml` actually got adopted: not because a single message convinced a single engineer, but because the convention became visible enough that ignoring it became operationally expensive.

### Realistic expectations

The 429 channel is not a guarantee that a crawler will adopt the manifest. Some crawlers will continue to ignore it, either because they're poorly maintained, because they're operated by parties indifferent to publisher costs, or because their architecture doesn't surface the signal in a way an engineer can act on. The pattern is designed to catch the consumers who are reachable, not all of them.

For consumers it doesn't reach, the publisher still has rate-limiting and blocking as a fallback — the same tools they had before `pagedigest` existed. The protocol doesn't make those tools less effective. It just adds a path for the cooperative outcome to happen first.

### Managed static-host fallback

Some managed static hosting platforms do not allow full control over 429 responses, custom response headers, or error bodies.

When full 429 customization is unavailable, publishers SHOULD still surface the manifest relation on ordinary successful responses (for example, HTTP 200 responses) using the same `Link` relation guidance. Publishers MAY also publish a stable explanatory resource (for example `/.well-known/pagedigest-usage.txt` or equivalent) that points automated operators to the manifest location and expected behavior.

This fallback is weaker than a fully instrumented 429 response, but it preserves discoverability and reduces integration friction for static-host deployments.

## Escalation

When a consumer continues to fetch redundantly after receiving a Level 1 message, a publisher may tighten rate limits and update the response:

```
You have continued to fetch /blog/hello-world redundantly after
being shown the pagedigest manifest. Your request rate is now
limited to 10 requests per hour. This will remain in effect
until your crawler begins respecting the manifest.
```

If non-compliance continues, a publisher may block the crawler:

```
This crawler has been blocked from this site for sustained
redundant fetching. The pagedigest manifest at
/.well-known/pagedigest.json was offered and ignored. When your
crawler begins respecting the manifest, contact the webmaster
to have this block lifted.
```

The escalation is gradient, not binary. At each level, the cooperative path is still available to the crawler. Nothing here prevents the crawler from adopting the manifest and resuming normal access. The block is always reversible through compliance.

## Making cooperation observable

A consumer may send `PageDigest-State` after checking the manifest. The header
makes its observed revision log-visible, but it does not prove identity or good
behavior. Publishers should corroborate it with manifest access and a low
unchanged-page overfetch ratio before changing treatment. The specification
defines the reserved syntax; the [cooperative automation
guide](./docs/cooperative-automation.md) provides the classification table and
nginx/Cloudflare recipes.

## What the protocol is not

`pagedigest` is not an anti-scraping protocol. A consumer that fetches the same URL once per day, respects the manifest's `rev` integer, and only re-fetches when content actually changes is not being restricted. That is the intended use.

`pagedigest` is not a licensing mechanism. The protocol makes no statement about whether a consumer is permitted to use the content it fetches. That is a separate question governed by copyright, terms of service, and law. The manifest is a technical signal about whether fetching is redundant, not a legal signal about whether fetching is authorized.

`pagedigest` is not a replacement for `robots.txt`. The two serve different purposes. `robots.txt` tells a consumer what it is allowed to fetch. `pagedigest` tells a consumer what has changed since last time. A consumer should read both.

`pagedigest` is not neutral infrastructure. The protocol takes a position: both sides have been wasting resources, and both sides have an interest in stopping. That position is baked into the design. Participants are expected to act in good faith toward the shared interest in efficiency.

## On good faith

Every functioning protocol on the internet depends on good faith at some layer. TCP depends on hosts implementing congestion control honestly. TLS depends on certificate authorities issuing certificates carefully. BGP depends on operators announcing routes accurately. When participants act in bad faith, the protocol degrades — not catastrophically, but measurably.

`pagedigest` is no different. The protocol is designed so that bad faith is detectable and costly. Publishers who lie about their manifests lose consumer trust, measured through audit mismatches. Consumers who ignore manifests face rate limits and blocks from publishers who are justified in imposing them. The enforcement mechanisms are not the core of the protocol — the core is the cooperation. But the enforcement mechanisms are what make the cooperation robust.

A publisher who adopts `pagedigest` is saying: *I will do the work to make my site cheap for you to crawl. I expect you to do the work to crawl it cheaply.*

A consumer who adopts `pagedigest` is saying: *I will respect your manifest. I expect you to maintain it honestly.*

Both statements are in the self-interest of the speaker. That is the protocol's strongest property. The cooperation it asks for is not a sacrifice on either side; it is the version of the existing relationship where both sides waste less.
