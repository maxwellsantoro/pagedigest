# `@pagedigest/astro`

Astro integration for generating `/.well-known/pagedigest.json` after a static
Astro build.

```js
// astro.config.mjs
import { defineConfig } from "astro/config";
import pagedigest from "@pagedigest/astro";

export default defineConfig({
  integrations: [pagedigest()],
});
```

The integration writes `.well-known/pagedigest.json` inside Astro's output
directory during `astro:build:done`, and stores persistent revision state at
`.astro/pagedigest-state.json`.

## Publisher pipeline (required when digests are enabled)

Digests are over **served** identity-encoded bytes. This integration hashes
**build output**. After deploy, reconcile so CDN/edge rewrites do not poison
audits:

```bash
# 1) astro build  (writes dist/ + .well-known/pagedigest.json)
# 2) Deploy pages + manifest (atomic if possible; else pages first, then manifest)
# 3) Reconcile digests to live responses
python tools/reconcile_served_digests.py ./dist/.well-known/pagedigest.json \
  --base-url https://example.com --apply
# Redeploy the manifest if it changed.
# 4) Sample live audits
pagedigest verify-live https://example.com --sample-size 25
```

Full rationale: [`CONTENT_HYGIENE.md`](../../CONTENT_HYGIENE.md). If you cannot
reconcile, set `withDigest: false` and rely on `rev` only.

## Scope vs Rust generator

This package covers the **static HTML subset** of the publisher path:

| Behavior | `@pagedigest/astro` | `pagedigest-generator` |
|----------|---------------------|------------------------|
| Default extensions | `.html`, `.htm` | `.html`, `.htm`, `.md`, `.markdown` |
| Index URL keys | Trailing-slash only (`about/index.html` → `/about/`) | `--index-style trailing-slash\|file` |
| Path percent-encoding | Encodes spaces and selected reserved characters | Same practical encode set |
| `.well-known` tree | Skipped entirely | Skipped entirely |
| URL-key collisions | Hard error | Hard error |
| State / manifest writes | Atomic temp + rename | Atomic temp + sync + rename |
| Per-URL rev high-water | Retained in `retired` after removal | Retained in `retired` after removal |
| State field for content | `content_hash` | `digest` (hex, no `sha256:` prefix) |
| Per-entry `modified` | `withModified: true` | `--with-modified` |
| Default digests | On (`withDigest: true`) | Off (`--with-digest`) |

Use the Rust generator (or `npx pagedigest`) when you need Markdown entries or
file-style index keys (`--index-style file`). CI runs
`tools/smoke_generator_astro_conformance.py` on the shared ASCII HTML subset so
the two stay aligned for that matrix.

Keep the state file durable between builds. If it is deleted on every CI run,
PageDigest revisions will restart and consumers will correctly treat that as an
untrusted/fallback condition.

## Options

```js
pagedigest({
  output: ".well-known/pagedigest.json",
  state: ".astro/pagedigest-state.json",
  includeExtensions: [".html", ".htm"],
  withDigest: true,
  withModified: false,
  coverage: { mode: "complete" },
});
```

- `output`: manifest path inside Astro's output directory.
- `state`: persistent revision-state file, relative to project root unless
  absolute.
- `includeExtensions`: generated output file extensions to include.
- `withDigest`: emit SHA-256 digests of generated identity bytes (default
  `true`). Reconcile after deploy when the host rewrites HTML.
- `withModified`: emit stable per-entry content-observation timestamps
  (default `false`). Unchanged content keeps the prior timestamp.
- `coverage`: `complete`, `prefixes`, or `false` to omit coverage metadata.
