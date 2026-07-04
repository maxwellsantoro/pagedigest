# PageDigest v1 release candidate

PageDigest v1 is now in release-candidate status.

PageDigest is a one-file change-detection protocol for public websites. A
publisher serves a manifest at `/.well-known/pagedigest.json` with a monotonic
site revision and per-URL revisions. Stateful consumers fetch that manifest,
compare it with their cache, and skip page fetches for URLs that provably have
not changed.

For a 10,000-page site that changes 20 pages in a week, a consumer can make one
manifest request plus 20 page fetches instead of 10,000 per-URL checks.

The v1 RC includes:

- A stable wire format with `site_rev`, per-URL `rev`, optional `digest`, and
  optional `modified` fields.
- Digest audit guidance for consumers that want to verify publisher claims.
- Optional `PageDigest-State` request headers so cooperative consumers can make
  manifest observations visible in ordinary publisher logs.
- Reference publisher and consumer implementations.
- Distribution through GitHub Releases, Cargo, `npx`, PyPI, and an Astro
  integration.
- Production dogfood on `pagedigest.org` and a measured producer case study for
  `dotrepo.org`.

Install paths:

```bash
npx pagedigest ./site-dist
cargo install pagedigest
python -m pip install pagedigest
npm install @pagedigest/astro
```

Useful links:

- Project: https://github.com/maxwellsantoro/pagedigest
- Spec: https://github.com/maxwellsantoro/pagedigest/blob/main/SPEC.md
- Contract: https://github.com/maxwellsantoro/pagedigest/blob/main/CONTRACT.md
- Roadmap: https://github.com/maxwellsantoro/pagedigest/blob/main/ROADMAP.md
- Live dogfood: https://pagedigest.org/.well-known/pagedigest.json
- RC feedback: https://github.com/maxwellsantoro/pagedigest/issues/1

What feedback would help before v1.0:

- Publisher integration reports from static-site generators, custom build
  systems, CMS exports, and CDN/edge deployments.
- Consumer integration reports from crawlers, caches, monitors, archive
  systems, agents, and search/indexing pipelines.
- Any cases where URL keys, redirects, digest audits, deployment races, or
  partial coverage semantics are surprising in practice.

The main remaining v1.0 dependency outside the repo is registry review for the
well-known URI and link relation requests. The v1 field semantics are expected
to remain stable through final v1.0.
