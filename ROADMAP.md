# Roadmap

**Now:** v1 RC — stable wire format, in-repo reference implementations, dogfood on [pagedigest.org](https://pagedigest.org).

**Next:** v1.0 — distribution, integrations, IANA filings. Gates: [RELEASE_CHECKLIST.md](./RELEASE_CHECKLIST.md).

The cross-project execution order is trust hygiene first, then the v1 spec
clarifications (`PageDigest-State`, prior-art, and audit economics), measured
dotrepo dogfood, agent consumption, and only then broad distribution.

## Phase 1 — Public RC

| Task | Status |
|------|--------|
| Pre-public docs/tests polish | done |
| Tag `v1.0.0-rc.1` | done — released 2026-07-02 |
| Adopter feedback channel (Issues/Discussions) | done — [v1 RC feedback issue](https://github.com/maxwellsantoro/pagedigest/issues/1) |
| RC announcement | draft ready — [docs/announcements/v1-rc.md](./docs/announcements/v1-rc.md) |
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
| Hugo / Eleventy / Jekyll plugins | P2 — copy Astro retired-rev + URL-key encoding + conformance smoke pattern |

Publisher pipeline: build → generate manifest → deploy → `reconcile_served_digests.py --apply` → verify. Details: [CONTENT_HYGIENE.md](./CONTENT_HYGIENE.md). Generators remind on `--with-digest` / default Astro digests.

## Phase 4 — Consumer path

| Task | Priority |
|------|----------|
| Consumer integration write-up | done |
| Reference sample (cache persistence) | done — atomic state and bounded body cache with failure tests |
| Live digest verification CLI (`pagedigest verify-live`) | done |
| Scrapy consumer middleware | experimental — [integrations/scrapy](./integrations/scrapy/); uses reference `pagedigest` validate/header; offline tests gated in CI; not published to PyPI |

## Phase 5 — Standards registration

Requests filed from [docs/registrations/](./docs/registrations/):
[well-known URI](https://github.com/protocol-registries/well-known-uris/issues/98)
and [link relation](https://github.com/protocol-registries/link-relations/issues/73).
Update docs when the short-form `rel` is accepted.

## Phase 6 — v1.0

All [1.0 Gate](./RELEASE_CHECKLIST.md#10-gate) items checked → tag `v1.0.0`, update README status.
Short-form IANA `rel` is **not** a hard blocker: v1.0 may ship with the
extension relation URI if registration is still pending (update docs when the
short token lands).

## Post-1.0 (reserved)

The v1.1 extension will finalize `PageDigest-State` intermediary semantics using
lessons from measured consumers. Manifest sharding, content extracts, DNS
discovery, and additional hash algorithms remain reserved; see [SPEC.md](./SPEC.md) §6.

### Explicitly deferred engineering

| Item | Why deferred |
|------|----------------|
| mypy/pyright in CI | Consumer is annotated and unit-tested; static typing is optional polish |
| Atomic Worker observation counters | KV get-then-put is best-effort metrics only (documented in `site/_worker.js`) |
| Pure-JS Windows unzip | System `tar.exe` is standard on modern Windows; documented in `packages/cli` |

## Contribute

Open an issue referencing a phase. Highest leverage now: **adopter feedback**, **additional producer case studies**, and **additional SSG integrations**.
