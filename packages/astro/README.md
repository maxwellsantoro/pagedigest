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

## Scope vs Rust generator

This package covers the **static HTML subset** of the publisher path:

| Behavior | `@pagedigest/astro` | `pagedigest-generator` |
|----------|---------------------|------------------------|
| Default extensions | `.html`, `.htm` | `.html`, `.htm`, `.md`, `.markdown` |
| Index URL keys | Trailing-slash (`about/index.html` → `/about/`) | Same default (`--index-style trailing-slash`) |
| Path percent-encoding | Encodes spaces and selected reserved characters | Same practical encode set |
| `.well-known` tree | Skipped entirely | Skipped entirely |
| URL-key collisions | Hard error | Hard error |
| State / manifest writes | Atomic temp + rename | Atomic temp + sync + rename |
| Per-URL rev high-water | Retained in `retired` after removal | Retained in `retired` after removal |
| State field for content | `content_hash` | `digest` (hex, no `sha256:` prefix) |
| Per-entry `modified` | Not supported | `--with-modified` |
| Default digests | On (`withDigest: true`) | Off (`--with-digest`) |

Use the Rust generator (or `npx pagedigest`) when you need Markdown entries,
file-style index keys, or `--with-modified`. CI runs
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
  coverage: { mode: "complete" },
});
```

- `output`: manifest path inside Astro's output directory.
- `state`: persistent revision-state file, relative to project root unless
  absolute.
- `includeExtensions`: generated output file extensions to include.
- `withDigest`: emit SHA-256 digests of generated identity bytes.
- `coverage`: `complete`, `prefixes`, or `false` to omit coverage metadata.

For digest reliability, run the post-deploy reconciliation flow described in
[`CONTENT_HYGIENE.md`](../../CONTENT_HYGIENE.md) if your host or CDN mutates
HTML after Astro builds it.
