# Rust Generator (Minimal Reference)

This is the minimal reference generator implementation. The binary is named `pagedigest-generator`; a shorter `pagedigest` name is reserved for packaged distribution.

## Behavior

- Scans an input directory for allowlisted content files.
- Persists durable revision state (default: `<input_dir_parent>/.pagedigest/state.json`).
- Increments per-URL `rev` on content changes and additions.
- Increments `site_rev` on any add/remove/change.
- Never decreases revision counters.
- Normalizes `index.html` routes to request-style keys (`/` and `/section/`) by default.

## Not emitted (v1 minimal scope)

- `coverage` metadata (`complete` / `prefixes`)
- per-entry `modified` timestamps

Add these in your own integration if your deployment needs them.

## Digests

Digests are optional and off by default. Pass `--with-digest` to include per-entry `sha256:` values.

This minimal reference hashes **source file bytes on disk**, not identity-encoded HTTP response bytes. That is accurate when served bytes match build output, but breaks when:

- a CDN or edge feature rewrites HTML (minification, email obfuscation, script injection)
- the served representation differs from the scanned file (for example `.md` source served as rendered HTML)
- trailing-slash redirects change which bytes a consumer receives

**Recommended digest pipeline:**

1. Generate the manifest from final deployable artifacts (`--with-digest` if you want digests).
2. Deploy pages and manifest.
3. Run `tools/reconcile_served_digests.py --apply` against the live origin so digests converge to identity-encoded served bytes (or are removed when the host cannot produce stable bytes).
4. Redeploy the reconciled manifest.

See [CONTENT_HYGIENE.md](../../CONTENT_HYGIENE.md) for the Cloudflare email-obfuscation case study.

## Revision state

Revision counters are durable protocol state. Keep the state file private and outside ephemeral CI storage. After a backup restore or environment reseed, advance to a value strictly greater than any value previously published — never reset to zero. The dogfood setup in `site-state/` commits state intentionally for reproducible builds; most publishers should not.

## Run

```bash
cargo run -- ./site-dist
```

Optional flags:

```bash
cargo run -- ./site-dist \
  --output ./site-dist/.well-known/pagedigest.json \
  --state ./state/pagedigest-state.json \
  --with-digest
```

Additional options:

- `--index-style trailing-slash|file` controls index route mapping.
- `--include-ext html,htm,md,markdown` controls file extension allowlist.