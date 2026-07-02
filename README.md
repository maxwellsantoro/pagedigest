# pagedigest

**One JSON file that tells automated clients which of your pages changed. Both sides stop wasting bandwidth.**

Publishers and crawlers waste the same bandwidth re-fetching unchanged pages. `pagedigest` coordinates them with a single manifest at `/.well-known/pagedigest.json`: monotonic `site_rev` and per-URL `rev` integers, plus optional SHA-256 digests consumers can audit.

For a 10,000-page site that changes 20 pages a week, a consumer makes **one manifest request plus twenty page fetches** per cycle instead of ten thousand per-URL checks.

```json
{
  "version": 1,
  "generated": "2025-10-16T10:00:00Z",
  "site_rev": 18293,
  "entries": {
    "/": { "rev": 47 },
    "/blog/hello-world": {
      "rev": 3,
      "digest": "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    }
  }
}
```

| Field | Role |
|-------|------|
| `site_rev` | Site-wide integer; bumps on any covered change. Equal cache → skip all URL fetches. |
| `rev` | Per-URL integer; bumps on content change. |
| `digest` | Optional SHA-256 of identity-encoded response bytes for audit. |
| `modified` | Optional UTC timestamp for humans; not used in protocol logic. |

**Normative details:** [SPEC.md](./SPEC.md). **Social bargain:** [CONTRACT.md](./CONTRACT.md). **Full doc index:** [docs/README.md](./docs/README.md).

## Why not sitemap.xml or ETag?

- `site_rev` is a one-request site-level fast path.
- Monotonic integers avoid timestamp ambiguity and clock skew.
- `sitemap.xml` `<lastmod>` is often coarse or stale; `rev`/`site_rev` are explicit protocol state.
- `ETag`/`If-None-Match` still costs one request per URL; `pagedigest` is one manifest plus only changed pages.

## Status

**v1 release candidate** — wire format stable at `/.well-known/pagedigest.json`. Discovery uses `Link: </.well-known/pagedigest.json>; rel="https://pagedigest.org/rel"` until IANA registration completes.

Reference implementations ship in this repo. Package registries and SSG plugins are **planned** — see [ROADMAP.md](./ROADMAP.md). RC adopters should not expect breaking field or semantics changes before v1.0.

Live dogfood: [pagedigest.org](https://pagedigest.org). Source: [github.com/maxwellsantoro/pagedigest](https://github.com/maxwellsantoro/pagedigest). Sibling project: [dotrepo](https://dotrepo.org) ([ecosystem notes](./docs/ecosystem.md)).

## Use from this repo (today)

### Publisher — generate a manifest

```bash
cargo run --manifest-path implementations/rust-generator/Cargo.toml -- ./site-dist
```

Writes `site-dist/.well-known/pagedigest.json` and persists revision state. See [implementations/rust-generator/README.md](./implementations/rust-generator/README.md) for flags (`--with-digest`, `--index-style`, state path).

Publishers using digests should follow the post-deploy pipeline in [CONTENT_HYGIENE.md](./CONTENT_HYGIENE.md).

### Consumer — fetch, diff, audit

```bash
cd implementations/python-consumer
uv sync
uv run python -c "
from pagedigest import check_site
print(check_site('https://example.com', cached_site_rev=1, cached_revs={'/': 1}))
"
```

API: `fetch`, `diff`, `audit`, `check_site`. See [implementations/python-consumer/README.md](./implementations/python-consumer/README.md).

### Planned distribution (not yet shipped)

```bash
# Generator — future targets
npx pagedigest ./dist          # npm wrapper over release binary
cargo install pagedigest       # crates.io
# Consumer — future target
pip install pagedigest         # PyPI

# SSG — future target
npm install @pagedigest/astro
```

## Quality gates

```bash
./tools/run_checks.sh
```

Includes conformance vectors (`test-vectors/`), consumer unit tests, generator tests, and revision-progression smoke test. CI mirrors this workflow.

Publisher tooling also includes `tools/reconcile_served_digests.py` (post-deploy digest convergence) and `tools/verify_over_wire_digests.py` (live audit sampling).

## Contributing

See [ROADMAP.md](./ROADMAP.md) for prioritized work. Highest impact: distribution (GitHub Releases + PyPI), Astro plugin, producer case study ([template](./docs/DOGFOOD_TEMPLATE.md)), consumer integration write-up.

MIT licensed.