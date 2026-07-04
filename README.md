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

## Why not existing mechanisms?

Sitemaps tell you what exists. ETags tell you, one request at a time, what
changed. `pagedigest` tells you—in one request—what did not.

| Mechanism | Its job | The remaining gap |
|---|---|---|
| Sitemap + `lastmod` | Discovery and advisory timestamps | No monotonic site-wide fast path or audit model |
| ETag / 304 | Per-resource validation | Still one request per URL |
| RSS / Atom | Recent-entry feed | Does not establish that older or omitted pages stayed unchanged |
| IndexNow | Publisher push to participating search engines | Not a pullable manifest for arbitrary consumers |
| WebSub | Hub-mediated push | Requires subscription and callback state |
| CDN / cache | Make repeated serving cheaper | Still serves or validates the read |

The full non-normative comparison and primary references are in
[SPEC.md §8](./SPEC.md#8-relationship-to-existing-mechanisms-non-normative).

## Observable cooperation

After checking a manifest, a consumer may make that observation visible in
ordinary publisher logs:

```http
PageDigest-State: site_rev=18294
```

The optional version 1 header is a corroborating signal, not authentication.
Publishers combine it with manifest access and unchanged-page overfetch; see
[the syntax and spoofing analysis](./SPEC.md#54-optional-cooperation-request-header)
and [deployment recipes](./docs/cooperative-automation.md).

## Status

**v1 release candidate** — wire format stable at `/.well-known/pagedigest.json`. Discovery uses `Link: </.well-known/pagedigest.json>; rel="https://pagedigest.org/rel"` until IANA registration completes. Version 1 reserves `PageDigest-State` as optional client behavior; full intermediary semantics remain a planned v1.1 extension.

Reference implementations ship in this repo, and the Astro integration is
available from npm. Generator binaries ship through GitHub Releases, and the
generator is installable through Cargo or `npx`; the consumer ships on PyPI.
See [ROADMAP.md](./ROADMAP.md). RC adopters should not expect breaking field or
semantics changes before v1.0.

Live dogfood: [pagedigest.org](https://pagedigest.org). Source: [github.com/maxwellsantoro/pagedigest](https://github.com/maxwellsantoro/pagedigest). Sibling project: [dotrepo](https://dotrepo.org) ([ecosystem notes](./docs/ecosystem.md), [measured dogfood case study](./docs/case-studies/dotrepo.md)).

## Install and use

### Publisher — release binary

Download the archive for Linux, macOS, or Windows from the
[pagedigest-generator v0.1.0 release](https://github.com/maxwellsantoro/pagedigest/releases/tag/generator-v0.1.0),
extract it, then run:

```bash
./pagedigest-generator ./site-dist
```

The generator writes `site-dist/.well-known/pagedigest.json` and persists
revision state between builds.

### Publisher — npm

```bash
npx pagedigest ./site-dist
```

The launcher verifies the released generator archive against a pinned SHA-256
digest before caching and executing it.

### Publisher — Cargo

```bash
cargo install pagedigest
pagedigest-generator ./site-dist
```

### Publisher — run from source

```bash
cargo run --manifest-path implementations/rust-generator/Cargo.toml -- ./site-dist
```

Writes `site-dist/.well-known/pagedigest.json` and persists revision state. See [implementations/rust-generator/README.md](./implementations/rust-generator/README.md) for flags (`--with-digest`, `--index-style`, state path).

Publishers using digests should follow the post-deploy pipeline in [CONTENT_HYGIENE.md](./CONTENT_HYGIENE.md).

### Consumer — PyPI

```bash
python -m pip install pagedigest
pagedigest verify-live https://example.com
```

The installed Python API exports `fetch`, `diff`, `audit`, and `check_site`.

### Consumer — run from source

```bash
cd implementations/python-consumer
uv sync
uv run python -c "
from pagedigest import check_site
print(check_site('https://example.com', cached_site_rev=1, cached_revs={'/': 1}))
"
```

API: `fetch`, `diff`, `audit`, `check_site`. See [implementations/python-consumer/README.md](./implementations/python-consumer/README.md).

### Astro integration

```bash
npm install @pagedigest/astro
```

Configuration and options: [packages/astro](./packages/astro/).

## Quality gates

```bash
./tools/run_checks.sh
```

Includes conformance vectors (`test-vectors/`), consumer unit tests, generator tests, and revision-progression smoke test. CI mirrors this workflow.

Publisher tooling also includes `tools/check_content_hygiene.py` (pre-generate churn scan), `tools/reconcile_served_digests.py` (post-deploy digest convergence), and `pagedigest verify-live` (live audit sampling; `tools/verify_over_wire_digests.py` remains as a compatibility wrapper). Consumer guidance lives in [docs/consumer-integration.md](./docs/consumer-integration.md).

## Contributing

See [ROADMAP.md](./ROADMAP.md) for prioritized work. Highest impact: more producer case studies ([template](./docs/DOGFOOD_TEMPLATE.md)), adopter feedback, and the persistent-cache consumer sample.

MIT licensed.
