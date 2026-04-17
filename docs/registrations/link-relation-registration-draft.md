# Link Relation Registration Draft

## Template Basis

RFC 8288 and IANA Link Relation Types Registry.

## Registration Request (Draft)

- Relation name: `pagedigest` (draft target)
- Description: identifies the pagedigest manifest for an origin.
- Reference: pagedigest v1 specification
- Notes:
  - During RC, URI-form extension relation remains valid:
    - `rel="https://pagedigest.org/rel"`
  - Target resource is usually `/.well-known/pagedigest.json`.

## Semantics Summary

- The relation identifies a change-detection manifest resource.
- Clients should treat relation identifiers as semantics labels, not dereference targets.
- Consumers may fetch the linked manifest and apply protocol rules for site/URL revision comparisons.

## Open Items Before Filing

- Confirm final short relation token availability.
- Confirm publication status and permanent reference URL.
- Align final examples across README, SPEC, CONTRACT, and release checklist after registration.
