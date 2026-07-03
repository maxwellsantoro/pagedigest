# Release Checklist

Objective gates for v1 RC and v1.0. Execution order and priorities: [ROADMAP.md](./ROADMAP.md).

## Pre-Freeze Clarifications (v1 RC Text)

- [x] URL-key comparison rule is explicit: pre-redirect request URL, byte-exact key matching.
- [x] Coverage metadata changes (`complete`/`prefixes` and prefix-list edits) require `site_rev` increment.
- [x] Rollback semantics are explicit: rollback is still a content change; revisions never decrease.
- [x] `rev` content scope explicitly includes important HTTP-level metadata (title/meta/canonical/OG/structured data).
- [x] Manifest conditional requests guidance is explicit (`ETag`/`Last-Modified` with `If-None-Match`/`If-Modified-Since`).
- [x] Digest-free trust note is explicit (no cryptographic audit path; soft evidence handling guidance).
- [x] Consumer class scope is explicit (stateful periodic consumers are primary target; stateless one-shot caveat).
- [x] Existing mechanisms are compared directly with primary references.
- [x] Audit guidance defines failure scope, recovery, and trust-building ranges.
- [x] `PageDigest-State` is reserved as optional version 1 client behavior with strict syntax and spoofing limits.

## RC Deliverables

- [x] Publish `test-vectors/` conformance bundle.
- [x] Publish minimal generator reference implementation.
- [x] Publish minimal consumer reference implementation.
- [x] Dogfood on `pagedigest.org` with documented manifest cache policy (`site/_headers`).
- [x] Publish content-hygiene guidance and post-deploy reconcile tooling.
- [x] Document static-hosting-friendly discovery fallback.
- [x] README marks unshipped distribution paths as planned; in-repo usage documented.

## RC Gate (wire format)

- [x] Manifest location fixed at `/.well-known/pagedigest.json`.
- [x] Core semantics defined: monotonic `site_rev`, monotonic per-URL `rev`, optional `digest`/`modified`, required `generated`.
- [x] `site_rev` includes content changes and URL additions/removals in `entries`.
- [x] Timestamps UTC; digest over identity-encoded bytes.
- [x] Consumer fallback for unreadable/malformed manifests.
- [x] Partial-manifest omission semantics explicit.
- [x] Unknown-field handling explicit.
- [x] Discovery via URI extension relation in `Link` headers (pending IANA).
- [x] Deployment consistency and transient audit-mismatch guidance documented.
- [x] Cooperation header syntax has conformance vectors and reference helpers.

## 1.0 Gate

- [ ] Well-known URI suffix registration filed and reflected in docs.
- [ ] Link relation registration filed and reflected in docs.
- [ ] If short-form `rel` is registered, update examples across docs.
- [ ] README install sections match shipped packages (PyPI, Releases, etc.).
- [ ] At least one producer integration publicly documented ([template](./docs/DOGFOOD_TEMPLATE.md)).
- [ ] At least one consumer integration publicly documented.
- [ ] Hygiene checker utility shipped (or explicitly deferred with issue).
- [ ] At least one SSG plugin shipped (Astro first).

## Discovery (RC guidance)

```http
Link: </.well-known/pagedigest.json>; rel="https://pagedigest.org/rel"
```

Valid as an RFC 8288 extension relation until a short token is registered. Drafts: [docs/registrations/](./docs/registrations/).
