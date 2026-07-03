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
| Tag `v1.0.0-rc.1` | pending |
| Adopter feedback channel (Issues/Discussions) | pending |
| RC announcement | pending |
| Prior-art comparison on README/site/spec | done |
| Reserve optional `PageDigest-State` + vectors | done |
| Audit-economics failure-scope guidance | done |
| pagedigest.org `PageDigest-State` observer | in progress — Worker shipped; bind KV for persisted counts |

## Phase 2 — Distribution

| Task | Priority |
|------|----------|
| GitHub Releases (`pagedigest-generator` binaries) | P0 |
| PyPI (`pagedigest` consumer) | P0 |
| `cargo install` | P1 |
| npm wrapper (`npx pagedigest`) | P2 |

Update README install blocks as each ships. Semver for implementations; spec `version` stays `1`.

## Phase 3 — Publisher path

| Task | Priority |
|------|----------|
| Astro plugin (`@pagedigest/astro`) | P0 |
| Producer case study ([template](./docs/DOGFOOD_TEMPLATE.md)) | P0 |
| Hygiene checker utility | P1 |
| Generator: per-entry `modified` fields | P1 |
| Hugo / Eleventy / Jekyll plugins | P2 |

Publisher pipeline: build → generate manifest → deploy → `reconcile_served_digests.py --apply` → verify. Details: [CONTENT_HYGIENE.md](./CONTENT_HYGIENE.md).

## Phase 4 — Consumer path

| Task | Priority |
|------|----------|
| Consumer integration write-up | P0 |
| Reference sample (cache persistence) | P1 |

## Phase 5 — Standards registration

Submit drafts in [docs/registrations/](./docs/registrations/). Update docs when short-form `rel` is accepted.

## Phase 6 — v1.0

All [1.0 Gate](./RELEASE_CHECKLIST.md#10-gate) items checked → tag `v1.0.0`, update README status.

## Post-1.0 (reserved)

The v1.1 extension will finalize `PageDigest-State` intermediary semantics using
lessons from measured consumers. Manifest sharding, content extracts, DNS
discovery, and additional hash algorithms remain reserved; see [SPEC.md](./SPEC.md) §6.

## Contribute

Open an issue referencing a phase. Highest leverage now: **GitHub Releases + PyPI**, **Astro plugin**, **producer case study**, **consumer write-up**.
