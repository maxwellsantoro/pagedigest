# Link Relation Registration Request: `pagedigest`

Filed as:
[protocol-registries/link-relations#73](https://github.com/protocol-registries/link-relations/issues/73).

Issue title:

```text
Registration request: pagedigest
```

Issue body:

````markdown
## Relation Name

`pagedigest`

## Description

Refers to a PageDigest manifest resource for the link context's origin.

## Reference

- PageDigest v1 specification:
  https://raw.githubusercontent.com/maxwellsantoro/pagedigest/main/SPEC.md
- Project site:
  https://pagedigest.org/

## Notes

The target IRI is usually `/.well-known/pagedigest.json`.

During the v1 release-candidate period, PageDigest uses the URI-form extension
relation:

```http
Link: </.well-known/pagedigest.json>; rel="https://pagedigest.org/rel"
````

If `pagedigest` is accepted as a registered relation type, the project will
update examples to prefer:

```http
Link: </.well-known/pagedigest.json>; rel="pagedigest"
```

## Additional information

PageDigest is a site-level change-detection manifest for automated consumers
such as crawlers, indexers, mirrors, and agents. The manifest lets a stateful
consumer compare a publisher's monotonic `site_rev` and per-URL `rev` values
before re-fetching unchanged pages.

Deployment and stability notes:

- `pagedigest.org` publishes a live manifest at:
  https://pagedigest.org/.well-known/pagedigest.json
- `dotrepo.org` is a measured dogfood producer:
  https://github.com/maxwellsantoro/pagedigest/blob/main/docs/case-studies/dotrepo.md
- The repository includes a reference generator, reference consumer,
  conformance vectors, and release checklist:
  https://github.com/maxwellsantoro/pagedigest

I understand that single-owner repositories are weak references for permanent
registration. This request is intended as an early provisional-style expert
review request while the project gathers broader deployment feedback.
```
