# Rust Generator (Minimal Reference)

This is the minimal reference generator implementation.

## Behavior

- Scans an input directory for allowlisted content files.
- Computes deterministic SHA-256 digests over source file bytes.
- Persists durable revision state in `.pagedigest/state.json` next to the input directory's parent by default.
- Increments per-URL `rev` on content changes and additions.
- Increments `site_rev` on any add/remove/change.
- Never decrements revision counters.
- Normalizes `index.html` routes to request-style keys (`/` and `/section/`) by default.

## Current digest limitation

This minimal reference computes digests from source file bytes. It is most accurate when served bytes match source bytes (no transform/minify/injection at CDN or runtime).

## Run

```bash
cargo run -- ./site-dist
```

Optional flags:

```bash
cargo run -- ./site-dist --output ./site-dist/.well-known/pagedigest.json --state ./state/pagedigest-state.json
```

Additional options:

- `--index-style trailing-slash|file` controls index route mapping.
- `--include-ext html,htm,md,markdown` controls file extension allowlist.
