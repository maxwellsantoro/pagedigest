# Rust Generator (Minimal Reference)

Binary name: `pagedigest-generator` (`pagedigest` reserved for packaged distribution).

## Behavior

- Scans an input directory for allowlisted content files (`.html`, `.htm`, `.md` by default).
- Persists durable revision state (default: `<input_dir_parent>/.pagedigest/state.json`).
- Increments per-URL `rev` on content changes; `site_rev` on any add/remove/change; never decreases.
- Maps `index.html` to `/` or `/section/` (`--index-style trailing-slash|file`).
- Emits `coverage: {"mode": "complete"}` by default for full-directory static-site scans.

**Not emitted:** per-entry `modified`. Add in downstream integrations if needed.

## Digests

Optional (`--with-digest`). Hashes on-disk file bytes, not served HTTP bytes. For audit-ready digests, follow the post-deploy pipeline in [CONTENT_HYGIENE.md](../../CONTENT_HYGIENE.md).

## Revision state

Durable protocol state — keep private, outside ephemeral CI. See [site-state/README.md](../../site-state/README.md) for dogfood notes.

## Run

```bash
cargo run -- ./site-dist
cargo run -- ./site-dist --output ./site-dist/.well-known/pagedigest.json --state ./state.json --with-digest
```

Flags: `--index-style`, `--include-ext`, `--output`, `--state`, `--with-digest`, `--coverage complete|none`.
