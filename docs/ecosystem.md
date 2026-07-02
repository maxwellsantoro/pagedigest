# Ecosystem and shared direction

`pagedigest` is one layer of a broader goal shared with its sibling project
[dotrepo](https://dotrepo.org): a cooperation layer that lets automated
consumers stop re-deriving what a publisher — or a trustworthy third party —
can declare once.

The layering:

- **`pagedigest` answers "what changed?"** for any published URL set: one
  manifest request, monotonic revisions, optional auditable digests.
- **dotrepo answers "what is this and how do I use it?"** for software
  repositories: a trust-aware semantic record covering build, test, license,
  ownership, security, docs, and relationships, with provenance and honest
  absence.

They target the same waste from adjacent angles. AI crawlers and agents today
re-fetch unchanged pages and re-read entire repositories to recover facts that
have not changed and could have been declared. `pagedigest` removes the
redundant *fetch*; dotrepo removes the redundant *interpretation*. Both pitch
measured waste reduction to the same audience — crawler operators and
agent-framework authors — so positioning and distribution effort are
coordinated across the two projects rather than duplicated.

## dotrepo as a production publisher

dotrepo's static public export already emits a per-file digest manifest
(`v0/files.json` plus a snapshot digest) in a bespoke shape — the pagedigest
pattern before pagedigest existed. The planned integration is for that export
to also emit `/.well-known/pagedigest.json`, making dotrepo:

- pagedigest's first production publisher with real, continuously refreshed
  content and real automated consumers (mirrors and agent caches), and
- a live demonstration that the manifest lets a consumer sync a
  many-thousand-file corpus with one request plus only the changed files.

Each project becomes the other's proof: pagedigest gets a working publisher
with measurable savings; dotrepo gets standard change detection instead of a
project-specific manifest format.

dotrepo's crawler is also a natural pagedigest *consumer*: where an evidence
source publishes a manifest, the crawler's work-avoidance ladder can honor it
before materializing anything, the same way it honors cached repository heads.

## Design note: third-party observed-revision manifests

This is a possible future direction, not part of version 1. The v1 wire format
and publisher/consumer contract are unaffected.

As specified, `pagedigest` is publisher-gated: a site gets a manifest only if
its operator publishes one. dotrepo faced the same two-sided-adoption problem
and escaped it with autonomous overlays — records generated on the
repository's behalf, clearly marked as non-authoritative, useful before any
maintainer participates, and designed to be superseded by a native record
without losing provenance.

The analogous unilateral bootstrap for pagedigest is a **third-party
observed-revision manifest**: a party that already crawls a site (a search
indexer, an archive, a CDN, a mirror network) publishes, under its own origin,
a manifest of the revisions and digests *it observed* for that site's URLs.
Other consumers could then use the observer's manifest for change detection
against sites that have not adopted pagedigest.

Key properties any future design would need to preserve:

- **Clear non-authority.** An observed manifest describes what an observer saw
  and when, never what the publisher declares. It must be impossible to
  confuse the two; the publisher's own `/.well-known/pagedigest.json` always
  supersedes any observation.
- **Honest staleness.** Observed revisions are only as fresh as the observer's
  last crawl; the manifest must carry that observation time so consumers can
  reason about it.
- **No enforcement rights.** The CONTRACT's earned-enforcement bargain (the
  429 pattern) belongs exclusively to publishers who do the work of
  maintaining an honest manifest. Observers earn none of it.
- **Provenance survives handoff.** When a publisher later adopts pagedigest
  natively, consumers switch to the authoritative manifest without ambiguity.

The payoff is the same one dotrepo demonstrated: usefulness stops depending on
publisher adoption, while native adoption remains the authority upgrade.
