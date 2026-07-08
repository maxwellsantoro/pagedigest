# Roadmap

**Now:** v1.0 — stable wire format, shipped reference implementations and packages, dogfood on [pagedigest.org](https://pagedigest.org). Gates: [RELEASE_CHECKLIST.md](./RELEASE_CHECKLIST.md).

**Next:** Post-1.0 reserved work and adoption (additional SSGs, measured consumers, IANA short-form `rel` when assigned). See [Post-1.0](#post-10-reserved).

The cross-project execution order that got us here was trust hygiene first, then the v1 spec clarifications (`PageDigest-State`, prior-art, and audit economics), measured dotrepo dogfood, agent consumption, and then broad distribution.

## Phase 1 — Public RC

| Task | Status |
|------|--------|
| Pre-public docs/tests polish | done |
| Tag `v1.0.0-rc.1` | done — released 2026-07-02 |
| Adopter feedback channel (Issues/Discussions) | done — [v1 RC feedback issue](https://github.com/maxwellsantoro/pagedigest/issues/1) |
| RC announcement | done — [docs/announcements/v1-rc.md](./docs/announcements/v1-rc.md) published on site at [/announcements/v1-rc/](https://pagedigest.org/announcements/v1-rc/) |
| Prior-art comparison on README/site/spec | done |
| Reserve optional `PageDigest-State` + vectors | done |
| Audit-economics failure-scope guidance | done |
| pagedigest.org `PageDigest-State` observer | done — Worker shipped; `PAGEDIGEST_OBSERVATIONS` KV bound and live counts confirmed 2026-07-04 |

## Phase 2 — Distribution

| Task | Priority / status |
|------|-------------------|
| GitHub Releases (`pagedigest-generator` binaries) | done — `v0.2.0` published for Linux, macOS, and Windows |
| PyPI (`pagedigest` consumer) | done — `0.1.0` published with Trusted Publishing |
| `cargo install` | done — `pagedigest 0.2.0` published to crates.io |
| npm wrapper (`npx pagedigest`) | done — `pagedigest 0.2.0` published with verified binary downloads and Trusted Publishing |

Update README install blocks as each ships. Semver for implementations; spec `version` stays `1`.
Canonical matrix: [README.md § Version matrix](./README.md#version-matrix).

## Phase 3 — Publisher path

| Task | Priority |
|------|----------|
| Astro plugin (`@pagedigest/astro`) | done — `0.1.0` published to npm; OIDC releases configured |
| Astro `withModified` + pipeline/docs parity | done — matches generator observation timestamps; HTML subset documented |
| Producer case study ([dotrepo](./docs/case-studies/dotrepo.md), [template](./docs/DOGFOOD_TEMPLATE.md)) | done — first measured case study |
| Hygiene checker utility | done — `tools/check_content_hygiene.py` |
| Generator: per-entry `modified` fields | done — stable observed-content timestamps via `--with-modified` |
| Hugo / Eleventy / Jekyll plugins | deferred — Post-1.0; copy Astro retired-rev + URL-key encoding + conformance smoke pattern |

Publisher pipeline: build → generate manifest → deploy → `reconcile_served_digests.py --apply` → verify. Details: [CONTENT_HYGIENE.md](./CONTENT_HYGIENE.md). Generators remind on `--with-digest` / default Astro digests.

## Phase 4 — Consumer path

| Task | Priority |
|------|----------|
| Consumer integration write-up | done |
| Reference sample (cache persistence) | done — atomic state and bounded body cache with failure tests |
| Live digest verification CLI (`pagedigest verify-live`) | done |
| Scrapy consumer middleware | done (experimental in-tree) — [integrations/scrapy](./integrations/scrapy/); uses reference `pagedigest` validate/header; offline tests gated in CI; PyPI publish deferred to Post-1.0 |

## Phase 5 — Standards registration

| Task | Status |
|------|--------|
| Well-known URI suffix registration | done — filed ([issue #98](https://github.com/protocol-registries/well-known-uris/issues/98)); docs reflect extension-URI discovery |
| Link relation registration | done — filed ([issue #73](https://github.com/protocol-registries/link-relations/issues/73)); v1.0 ships with `rel="https://pagedigest.org/rel"` |
| Short-form IANA `rel` token | deferred — update examples when assigned (not a v1.0 blocker; see [RELEASE_CHECKLIST.md](./RELEASE_CHECKLIST.md)) |

Drafts remain in [docs/registrations/](./docs/registrations/).

## Phase 6 — v1.0

| Task | Status |
|------|--------|
| All hard [1.0 Gate](./RELEASE_CHECKLIST.md#10-gate) items | done |
| README / ROADMAP / SPEC primary status → v1.0 | done |
| Tag `v1.0.0` | done — local annotated tag on the status-ship commit (implementation package semver stays 0.x until a separate package release) |

Short-form IANA `rel` remains optional follow-up, not a v1.0 blocker.

## Post-1.0 (reserved)

The v1.1 extension will finalize `PageDigest-State` intermediary semantics using
lessons from measured consumers. Manifest sharding, content extracts, DNS
discovery, and additional hash algorithms remain reserved; see [SPEC.md](./SPEC.md) §6.

| Item | Disposition |
|------|-------------|
| Hugo / Eleventy / Jekyll plugins | P2 publisher path; reuse Astro conformance pattern |
| Scrapy middleware on PyPI | Graduate from experimental when a maintainer is ready |
| Short-form IANA `rel` examples | Flip docs when the token is assigned |
| mypy/pyright in CI | Optional polish; consumer is annotated and unit-tested |
| Atomic Worker observation counters | KV get-then-put is best-effort metrics only (`site/_worker.js`) |
| Pure-JS Windows unzip | System `tar.exe` is standard on modern Windows (`packages/cli`) |

## Contribute

Open an issue referencing a phase. Highest leverage now: **adopter feedback**, **additional producer case studies**, and **additional SSG integrations**.
