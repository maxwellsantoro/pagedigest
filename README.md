# pagedigest

**One JSON file that tells automated clients which of your pages changed. Both sides stop wasting bandwidth.**

---

Right now, an AI crawler hitting a blog and the webmaster running that blog are having the same argument from opposite sides.

The webmaster: *"If you would stop hammering my server for pages that haven't changed, I wouldn't have to rate-limit or ban you."*

The crawler: *"If you would stop hiding behind bot detection, I wouldn't have to hammer your server — I just need to know what's new."*

They're describing the same waste. They just have no way to coordinate.

`pagedigest` is the coordination.

## What it is

A single static JSON file at `/.well-known/pagedigest.json`. Each URL on the site gets a monotonic integer version number and, optionally, a cryptographic hash. A consumer — an AI crawler, search indexer, archival system, feed mirror, or any other automated client — fetches the manifest, compares integers against its cache, and fetches only the URLs where the integer moved.

For a 10,000-page docs site that changes 20 pages a week, a consumer using `pagedigest` makes one manifest request plus twenty page fetches per cycle, instead of ten thousand per-URL checks.

```json
{
  "version": 1,
  "generated": "2025-10-16T10:00:00Z",
  "site_rev": 18293,
  "entries": {
    "/": { "rev": 47 },
    "/about": { "rev": 12 },
    "/blog/hello-world": {
      "rev": 3,
      "digest": "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
      "modified": "2025-10-15T18:22:00Z"
    }
  }
}
```

- **`site_rev`** — site-wide integer; increments on any covered content change, or when covered URLs are added/removed. Crawlers that see no change skip the rest.
- **`rev`** — per-URL integer; increments when that URL's content changes.
- **`digest`** — optional SHA-256 of the page; lets crawlers spot-audit publisher claims.
- **`modified`** — optional timestamp for human inspection.

## Why not sitemap.xml or ETag?

- `site_rev` gives a one-request, site-level fast path before touching per-URL state.
- Monotonic integers avoid timestamp ambiguity, clock skew, and timezone edge cases.
- `sitemap.xml` `<lastmod>` is timestamp-based and often coarse or inconsistently maintained; monotonic `rev`/`site_rev` are explicit protocol state.
- Optional `digest` adds auditability when publishers and consumers need trust checks.
- `ETag`/`If-None-Match` still costs one request per URL; `pagedigest` is one manifest request plus only changed pages.

## Where this fits in the stack

- `robots.txt`: permission and crawl policy.
- `pagedigest`: change detection and fetch efficiency.
- licensing/pay-per-crawl systems: economic terms.

These layers are complementary and can be deployed independently.

## Best-fit consumers

`pagedigest` is best for stateful, periodic consumers that retain crawl state: search indexers, archives, mirrors, enterprise sync pipelines, and agent caches.

It is less useful for stateless one-shot fetchers unless they persist per-site or per-URL cache state across sessions.

## Implementation status (RC)

Version 1 is in release-candidate status and the wire format is intended to be stable.

In-repo minimal reference implementations (Rust generator and Python consumer) are available now for RC validation and early integration.

Package-manager distribution, polished install paths, and plugin ecosystem coverage are still in active development. Install commands and APIs shown below represent planned public distribution targets and may evolve until those packages are fully shipped.

## How to use it

### If you publish content

Planned install targets for the reference generator (Rust binary):

```bash
# npm wrapper around the prebuilt binary
npx pagedigest ./dist

# Cargo
cargo install pagedigest
pagedigest ./dist

# Prebuilt binaries
# Download for your platform from GitHub Releases
```

All three install paths produce the same binary output, just through different package managers. Pick whichever matches your workflow.

If you use a static site generator, a plugin wires this into your build:

```bash
# Astro
npm install @pagedigest/astro

# Hugo, Jekyll, Eleventy: see plugins/
```

Your build now emits `/.well-known/pagedigest.json`. You're done.

### If you build crawlers

Python:

```python
from pagedigest import check_site

decision = check_site(
    "https://example.com",
    cached_site_rev=18292,
    cached_revs={"/": 46, "/about": 12}
)
# Returns a decision object with changed/new/unchanged URL lists and fallback metadata
# Example: decision["changed"] could be ["/"] when only the homepage moved
```

Planned API shape: convenience wrapper `check_site`; lower-level API `fetch`, `diff`, `audit`. Approximate implementation size is ~100 lines with a single runtime dependency: `requests`.

## What's in this repo

- [**SPEC.md**](./SPEC.md) — The technical specification. File format, field semantics, consumer behavior.
- [**CONTRACT.md**](./CONTRACT.md) — The social and operational bargain around the protocol.
- [`pagedigest.schema.json`](./pagedigest.schema.json) — Machine-readable schema for validators and tooling.

In-repo minimal reference implementations now include:

- a Rust generator CLI
- a Python consumer library

See:

- `implementations/rust-generator/`
- `implementations/python-consumer/`
- `test-vectors/`

Planned ecosystem integrations still include static-site-generator plugins and package-manager distribution.

If you are reading a packed review snapshot or docs-only bundle, the implementation directories may not be included here even though they exist in the broader project or release plan.

## The bargain

`pagedigest` is a coordination protocol, not a defense mechanism.

**Publishers commit** to maintaining an honest manifest: the integers reflect real content changes; the digests are accurate hashes; the manifest covers what it claims to cover.

**Consumers commit** to respecting the manifest: fetch it first, compare integers, skip unchanged URLs, and periodically audit digests to catch publishers who lie.

**Both sides benefit** because the waste was never in either of their interests. The protocol doesn't create the alignment — the alignment was always there. The protocol just makes it actionable.

A publisher who maintains the manifest honestly has strong justification to rate-limit consumers that ignore it, because those consumers are imposing real cost that the publisher has done real work to make unnecessary. A publisher who doesn't maintain the manifest honestly does not have that justification, and consumers are encouraged to treat such sites as maintaining an unreliable manifest or not participating reliably in the protocol. See [CONTRACT.md](./CONTRACT.md) for the full obligations and the recommended 429 pattern.

## What this is not

- **Not a new transport protocol.** It is a JSON manifest published over ordinary HTTP. Discovery identifiers use existing Web registration mechanisms.
- **Not middleware.** Static sites generate it at build time. Dynamic sites can generate it however they want, but there's no required serving logic.
- **Not a payment protocol.** There is no paid tier, no micropayment rail, no access control.
- **Not a licensing mechanism.** The manifest signals what changed, not what's permitted. Copyright and terms of service are separate.
- **Not a replacement for `robots.txt`.** A crawler should respect both. `robots.txt` says what's allowed; `pagedigest` says what's changed.

## Scope

This version is for **public, primarily static HTML and Markdown content** — blogs, documentation, news archives, marketing sites, product catalogs. Sites with pervasive personalization, authentication requirements, or client-side JavaScript rendering are explicitly out of scope for version 1. Future versions may address them.

Partial manifests are supported. A publisher can cover only the parts of their site that are in scope. URLs not listed are not described by the manifest; consumers should apply their default behavior to anything outside manifest coverage.

Publishers with unlinked-but-public URLs they do not want enumerated should use partial manifests and review coverage carefully before publishing.

## Interoperability notes

- Partial manifests are allowed.
- Consumers must ignore unknown fields.
- Publishers should expect some consumers to use manifests without using the 429 pattern.
- Publishers should advertise discovery via `Link: </.well-known/pagedigest.json>; rel="https://pagedigest.org/rel"` on ordinary 200 responses, not only on 429 responses.
- On managed static hosting where custom 429 headers/bodies are limited, prioritize discovery on ordinary 200 responses and publish a stable operator-facing usage note.
- Digest auditing is optional but recommended.

## Content hygiene

Publisher-side byte stability is the biggest practical adoption risk for trustworthy `digest` values.

See [CONTENT_HYGIENE.md](./CONTENT_HYGIENE.md) for a short implementation guide and deployment checklist.

## Status

Version 1 release candidate. MIT licensed.

The wire format is intended to be stable. Implementation feedback may refine wording and edge cases before v1 is finalized, but publishers and consumers who build against the current spec should not expect breaking changes to field names, semantics, or file location.

The manifest format is stable for v1 RC; registration of discovery identifiers may still be finalized before 1.0.

### RC compatibility note for adopters

- v1 RC manifests are expected to remain valid for v1.0.
- Field names, semantics, and the canonical location `/.well-known/pagedigest.json` are not expected to break.
- Before 1.0, only clarifications and optional extensions are expected.

Early adopters who want to participate in refining the ecosystem should open an issue or reach out directly.

## Conformance and CI

The repository includes a conformance-oriented vector bundle plus automated checks:

- `test-vectors/` for valid/invalid/anomalous manifest fixtures
- `tools/validate_vectors.py` for fixture integrity checks
- `tools/smoke_generator_progression.py` for end-to-end generator revision progression checks
- `tools/verify_over_wire_digests.py` for live dogfood digest sampling against identity-encoded responses
- `.github/workflows/ci.yml` for CI execution on push and pull requests

Run all local checks with one command:

```bash
./tools/run_checks.sh
```

## Contributing

- **Crawler authors:** The most useful contribution is integrating the Python client (or porting it to your language) and reporting what you find. Does the protocol work in your pipeline? What's missing? What would stop you from adopting it?

- **Publishers:** Install it, measure your bot traffic before and after, publish the numbers. Real adoption data is the most persuasive thing this project can have.

- **SSG maintainers:** Plugins for other static site generators are welcome. See `plugins/` for the existing ones as a template.
