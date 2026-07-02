# pagedigest Roadmap

**Current posture:** v1 RC — wire format stable, reference implementations in-repo, dogfood live on [pagedigest.org](https://pagedigest.org).

**Target:** v1.0 — packaged distribution, real integrations documented, discovery identifiers filed, README reflects shipped reality.

Objective gates live in [RELEASE_CHECKLIST.md](./RELEASE_CHECKLIST.md). This document is the execution plan.

---

## Done (RC + pre-public)

- [x] Specification, contract, schema, and conformance vectors
- [x] Rust generator and Python consumer reference implementations
- [x] CI quality gates (`./tools/run_checks.sh`)
- [x] Dogfood site with discovery header and manifest cache policy
- [x] Content-hygiene guide and post-deploy digest reconciliation tooling
- [x] Consumer tests against the vector bundle; rollback semantic fixture
- [x] Generator/state documentation for adopters

---

## Phase 1 — Public repo (now)

Ship the repository as a credible RC adopters can build against today.

| Task | Owner | Notes |
|------|-------|-------|
| Commit pre-public polish | maintainer | Docs, vectors, tests |
| Tag `v1.0.0-rc.1` (or similar) | maintainer | Marks wire-format freeze point |
| Enable GitHub Discussions or Issues template for adopter feedback | maintainer | Crawler + publisher channels |
| Announce RC status | maintainer | Point to SPEC + implementations; set expectations that packages are not yet on registries |

**Exit criteria:** Public repo with passing CI, clear RC labeling, feedback channel open.

---

## Phase 2 — Distribution

Make install paths real. Update README section-by-section as each lands.

| Task | Priority | Deliverable |
|------|----------|-------------|
| GitHub Releases for `pagedigest-generator` binary | P0 | Prebuilt macOS/Linux/Windows artifacts |
| PyPI publish (`pagedigest` consumer) | P0 | `pip install pagedigest` |
| `cargo install` for generator | P1 | Crate name aligned with README (`pagedigest` or `pagedigest-generator`) |
| npm wrapper (`npx pagedigest`) | P2 | Thin wrapper over release binary |
| Versioning policy | P0 | Semver for implementations; spec version stays `1` until a breaking wire change |

**Exit criteria:** README install blocks work without clone-and-build; each path tested in CI or release workflow.

---

## Phase 3 — Publisher integrations

Reduce friction for the primary audience: static-site publishers.

| Task | Priority | Deliverable |
|------|----------|-------------|
| Astro plugin (`@pagedigest/astro`) | P0 | Emits manifest + persists state in build output |
| Generator: optional `coverage` + `modified` | P1 | Match spec fields SSG users expect |
| Hygiene checker utility | P1 | Report manifest churn, missing reconcile, audit-readiness |
| Hugo / Eleventy / Jekyll plugins | P2 | Follow Astro contract |
| Producer case study | P0 | Before/after request counts on a real site (dogfood or partner) |

**Recommended publisher pipeline** (document in plugin READMEs):

1. Build site → generate manifest (`--with-digest` optional)
2. Deploy pages + manifest
3. `reconcile_served_digests.py --apply` → redeploy manifest
4. Verify with `verify_over_wire_digests.py`

**Exit criteria:** One SSG plugin shipped; one producer write-up with measured or simulated savings.

---

## Phase 4 — Consumer integrations

Prove the protocol works in real crawl pipelines.

| Task | Priority | Deliverable |
|------|----------|-------------|
| Consumer integration write-up | P0 | Stateful crawler using `check_site`, fallback on malformed manifests |
| Reference integration sample | P1 | Minimal script or notebook showing cache persistence |
| Port consumer to second language (optional) | P3 | Go or Rust if a partner needs it |

**Exit criteria:** One publicly documented consumer integration with graceful fallback behavior demonstrated.

---

## Phase 5 — Standards registration

Wire format does not block on this; 1.0 marketing and discovery ergonomics do.

| Task | Priority | Deliverable |
|------|----------|-------------|
| File well-known URI (`pagedigest.json`) | P0 | Draft in `docs/registrations/well-known-uri-registration-draft.md` |
| File link relation | P0 | Draft in `docs/registrations/link-relation-registration-draft.md` |
| Update docs if short-form `rel` is registered | P1 | Replace `https://pagedigest.org/rel` examples consistently |

**Exit criteria:** Registrations submitted; docs reflect submitted or accepted status.

---

## Phase 6 — v1.0 declaration

| Gate | Source |
|------|--------|
| Discovery registration filed (or accepted) | RELEASE_CHECKLIST §1.0 |
| README matches shipped packages | RELEASE_CHECKLIST §1.0 |
| Producer + consumer integrations published | RELEASE_CHECKLIST §1.0 |
| RC compatibility note for early adopters | README §RC compatibility (already drafted) |

**Action:** Tag `v1.0.0`, update README implementation-status section, close RC.

---

## Backlog (post-1.0)

Not required for v1.0. Reserved in [SPEC.md](./SPEC.md) §6.

- Manifest sharding for large sites
- Clean content extracts alongside manifest
- DNS-based `site_rev` discovery
- Additional digest algorithms

---

## Suggested timeline

| Phase | Rough target |
|-------|----------------|
| 1 — Public repo | Immediate |
| 2 — Distribution | 2–4 weeks |
| 3 — Publisher integrations | 4–8 weeks (Astro P0) |
| 4 — Consumer integrations | parallel with Phase 3 |
| 5 — Registrations | submit during Phase 2–3 |
| 6 — v1.0 | when Phases 2–5 exit criteria met |

Timelines are estimates; v1.0 ships on gates, not dates.

---

## How to contribute

Pick an unowned row, open an issue referencing this roadmap phase, and link a PR. Highest impact right now:

1. **GitHub Releases + PyPI** — unblocks adopters without cloning
2. **Astro plugin** — highest-leverage publisher path
3. **Producer case study** — strongest adoption argument
4. **Consumer integration write-up** — proves crawler-side value