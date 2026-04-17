# Rust Generator (Minimal Reference)

This is the minimal reference generator implementation.

## Behavior

- Scans an input directory for files.
- Computes deterministic SHA-256 digests over file bytes.
- Persists durable revision state in `pagedigest-state.json`.
- Increments per-URL `rev` on content changes and additions.
- Increments `site_rev` on any add/remove/change.
- Never decrements revision counters.

## Run

```bash
cargo run -- ./site-dist
```

Optional flags:

```bash
cargo run -- ./site-dist --output ./site-dist/.well-known/pagedigest.json --state ./state/pagedigest-state.json
```
