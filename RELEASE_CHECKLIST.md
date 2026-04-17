# pagedigest Release Checklist

This checklist separates release-candidate readiness from final 1.0 readiness so implementation work can proceed without ambiguity.

## Pre-Freeze Clarifications (v1 RC Text)

- [x] URL-key comparison rule is explicit: pre-redirect request URL, byte-exact key matching.
- [x] Coverage metadata changes (`complete`/`prefixes` and prefix-list edits) require `site_rev` increment.
- [x] Rollback semantics are explicit: rollback is still a content change; revisions never decrease.
- [x] `rev` content scope explicitly includes important HTTP-level metadata (title/meta/canonical/OG/structured data).
- [x] Manifest conditional requests guidance is explicit (`ETag`/`Last-Modified` with `If-None-Match`/`If-Modified-Since`).
- [x] Digest-free trust note is explicit (no cryptographic audit path; soft evidence handling guidance).
- [x] Consumer class scope is explicit (stateful periodic consumers are primary target; stateless one-shot caveat).

## Launch Now (No More Bikeshedding)

- [x] Publish `test-vectors/` conformance bundle (valid, invalid, monotonicity, and audit match/mismatch cases).
- [x] Publish minimal generator reference implementation (emits `/.well-known/pagedigest.json`).
- [x] Publish minimal consumer reference implementation (fetch, diff `site_rev`/`rev`, optional `digest` audit).
- [ ] Dogfood on one real publisher-controlled site (ideally `pagedigest.org`) and document generation method.
- [ ] Document manifest cache policy choice (`Cache-Control` and rationale) from dogfood deployment.
- [x] Publish content-hygiene implementation guidance for publishers.
- [x] Document static-hosting-friendly discovery fallback when custom 429 behavior is unavailable.
- [ ] Publish one producer case study with before/after crawl behavior or simulated savings.
- [ ] Publish one real consumer integration that handles malformed manifests gracefully and skips unchanged URLs.
- [ ] Ship one polished SSG plugin (Astro first), then expand to additional SSGs.
- [ ] Publish a hygiene checker utility/report to detect manifest churn and audit-readiness issues.
- [ ] Update README language to reflect shipped reality for each package as it goes live.
- [ ] Keep not-yet-shipped pieces explicitly marked as planned in README.
- [ ] File well-known URI suffix registration.
- [ ] File link relation registration.

### Practical Order

1. Ship generator.
2. Ship consumer.
3. Dogfood on one real site.
4. Update README to reflect shipped reality.
5. Publish producer + consumer write-ups.
6. File registrations.
7. Declare 1.0 when done.

## RC Gate (v1 RC)

- [x] Manifest location is fixed at `/.well-known/pagedigest.json`.
- [x] Core semantics are defined: monotonic `site_rev`, monotonic per-URL `rev`, optional `digest`, optional `modified`, required `generated`.
- [x] `site_rev` semantics include content changes and URL additions/removals in `entries`.
- [x] Timestamp requirement is explicit: UTC for `generated` and `modified`.
- [x] Digest input is explicit: identity-encoded bytes (`Accept-Encoding: identity`).
- [x] Consumer fallback is explicit for unreadable/malformed manifests.
- [x] Partial-manifest omission semantics are explicit (omission is not implicitly unchanged).
- [x] Unknown-field handling is explicit (consumers ignore unrecognized fields).
- [x] Discovery language is standards-clean pending registration: URI extension relation in `Link` headers.
- [x] Deployment consistency and transient audit mismatch guidance are documented.

## 1.0 Gate (Final)

- [ ] Well-known URI suffix registration status is finalized and reflected in docs.
- [ ] Link relation registration status is finalized and reflected in docs.
- [ ] If short-form relation becomes registered, examples are updated consistently across docs.
- [ ] README implementation-status language matches shipped reality.
- [ ] README explicitly compares `pagedigest` with `sitemap.xml` `<lastmod>` and `ETag` / `If-None-Match`.
- [ ] At least one real producer integration is publicly documented.
- [ ] At least one real consumer integration is publicly documented.
- [ ] Compatibility note is published for early RC adopters (expected non-breaking path).

## Discovery Registration Notes

Current RC guidance uses:

```http
Link: </.well-known/pagedigest.json>; rel="https://pagedigest.org/rel"
```

This remains valid as an extension relation type under RFC 8288.

If and when a short relation token is registered, examples MAY switch to the registered short form.

## Suggested PR Description (Copy/Paste)

```markdown
## Release checklist update

This PR updates release posture tracking for pagedigest v1.

### What changed
- Added explicit RC gate and 1.0 gate checklist.
- Captured discovery registration dependencies separately from wire-format stability.
- Documented current URI-based Link relation guidance used during RC.

### Why
- Keeps implementers unblocked while standards registrations finalize.
- Makes go/no-go criteria visible and objective.
- Reduces ambiguity between protocol integrity work and ecosystem rollout work.

### Release posture
- v1 RC: ready
- v1.0 final: pending discovery-identifier registration status and at least one producer+consumer integration write-up
```
