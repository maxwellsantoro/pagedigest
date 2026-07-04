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
