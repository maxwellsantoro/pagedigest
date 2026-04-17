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

## How to use it

### If you publish content

The reference generator is written in Rust and distributed three ways:

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

changed = check_site(
    "https://example.com",
    cached_site_rev=18292,
    cached_revs={"/": 46, "/about": 12}
)
# Returns ["/"] — only the homepage changed since last crawl
```

Convenience wrapper: `check_site`. Lower-level API: `fetch`, `diff`, `audit`. ~100 lines. Zero dependencies beyond `requests`.

## What's in this repo

- [**SPEC.md**](./SPEC.md) — The technical specification. File format, field semantics, consumer behavior.
- [**CONTRACT.md**](./CONTRACT.md) — The social and operational bargain around the protocol.
- [`pagedigest.schema.json`](./pagedigest.schema.json) — Machine-readable schema for validators and tooling.

Reference implementations currently include:
- a Rust generator CLI
- a Python consumer library
- static-site-generator integrations

If you are reading a packed review snapshot or docs-only bundle, the implementation directories may not be included here even though they exist in the broader project or release plan.

## The bargain

`pagedigest` is a coordination protocol, not a defense mechanism.

**Publishers commit** to maintaining an honest manifest: the integers reflect real content changes; the digests are accurate hashes; the manifest covers what it claims to cover.

**Consumers commit** to respecting the manifest: fetch it first, compare integers, skip unchanged URLs, and periodically audit digests to catch publishers who lie.

**Both sides benefit** because the waste was never in either of their interests. The protocol doesn't create the alignment — the alignment was always there. The protocol just makes it actionable.

A publisher who maintains the manifest honestly has strong justification to rate-limit consumers that ignore it, because those consumers are imposing real cost that the publisher has done real work to make unnecessary. A publisher who doesn't maintain the manifest honestly does not have that justification, and consumers are encouraged to treat such sites as operating in bad faith. See [CONTRACT.md](./CONTRACT.md) for the full obligations and the recommended 429 pattern.

## What this is not

- **Not a new transport protocol.** It is a JSON manifest published over ordinary HTTP. Discovery identifiers use existing Web registration mechanisms.
- **Not middleware.** Static sites generate it at build time. Dynamic sites can generate it however they want, but there's no required serving logic.
- **Not a payment protocol.** There is no paid tier, no micropayment rail, no access control.
- **Not a licensing mechanism.** The manifest signals what changed, not what's permitted. Copyright and terms of service are separate.
- **Not a replacement for `robots.txt`.** A crawler should respect both. `robots.txt` says what's allowed; `pagedigest` says what's changed.

## Scope

This version is for **public, primarily static HTML and Markdown content** — blogs, documentation, news archives, marketing sites, product catalogs. Sites with pervasive personalization, authentication requirements, or client-side JavaScript rendering are explicitly out of scope for version 1. Future versions may address them.

Partial manifests are supported. A publisher can cover only the parts of their site that are in scope. URLs not listed are not described by the manifest; consumers should apply their default behavior to anything outside manifest coverage.

## Interoperability notes

- Partial manifests are allowed.
- Consumers must ignore unknown fields.
- Publishers should expect some consumers to use manifests without using the 429 pattern.
- Digest auditing is optional but recommended.

## Status

Version 1 release candidate. MIT licensed.

The wire format is intended to be stable. Implementation feedback may refine wording and edge cases before v1 is finalized, but publishers and consumers who build against the current spec should not expect breaking changes to field names, semantics, or file location.

The manifest format is stable for v1 RC; registration of discovery identifiers may still be finalized before 1.0.

The reference implementations are in active development. Early adopters who want to participate in refining the ecosystem should open an issue or reach out directly.

## Contributing

- **Crawler authors:** The most useful contribution is integrating the Python client (or porting it to your language) and reporting what you find. Does the protocol work in your pipeline? What's missing? What would stop you from adopting it?

- **Publishers:** Install it, measure your bot traffic before and after, publish the numbers. Real adoption data is the most persuasive thing this project can have.

- **SSG maintainers:** Plugins for other static site generators are welcome. See `plugins/` for the existing ones as a template.
