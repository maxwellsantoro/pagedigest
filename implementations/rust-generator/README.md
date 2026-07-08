# Rust Generator (Minimal Reference)

Crate name: `pagedigest`. Installed binary: `pagedigest-generator`.

## Behavior

- Scans an input directory for allowlisted content files (`.html`, `.htm`, `.md` by default).
- Persists durable revision state (default: `<input_dir_parent>/.pagedigest/state.json`).
- Increments per-URL `rev` on content changes; `site_rev` on any add/remove/change; never decreases.
- Retains per-URL `rev` high-water marks in state `retired` when a URL leaves the
  scan set so a later re-add cannot emit a lower `rev` (SPEC §4.1.1).
- Maps `index.html` to `/` or `/section/` (`--index-style trailing-slash|file`).
- Emits coverage metadata (see [Coverage](#coverage)).
- Optionally emits stable per-entry `modified` timestamps (`--with-modified`).

## Coverage

The generator scans the input directory and emits one of:

- `--coverage complete` (default): `{"mode": "complete"}`. Use **only** when the
  input directory is the entire covered URL set for the origin — `complete`
  tells consumers that any URL they know which is absent from the manifest has
  been removed. Pointing the generator at a subdirectory while keeping
  `complete` would overclaim coverage.
- `--coverage prefixes --prefix /blog/ [--prefix /docs/]`:
  `{"mode": "prefixes", "prefixes": [...]}`. Only entries whose URL key starts
  with one of the given prefixes are listed; URLs outside them receive default
  crawler behavior. Use this for partial manifests. Prefixes must begin with `/`
  and are normalized (sorted, de-duplicated) so re-runs do not churn `site_rev`.
- `--coverage none`: omits the field, so omission is ambiguous rather than a
  completeness claim.

Changing coverage semantics (mode or prefix list) increments `site_rev`, per
[SPEC.md §3.1](../../SPEC.md#31-top-level-fields).

## Digests

Optional (`--with-digest`). Hashes on-disk file bytes, not served HTTP bytes. For audit-ready digests, follow the post-deploy pipeline in [CONTENT_HYGIENE.md](../../CONTENT_HYGIENE.md).

## Modified timestamps

Optional (`--with-modified`). The generator records when it first observes each
content digest and persists that UTC timestamp in durable state. Unchanged
content keeps the same timestamp across rebuilds; changed content receives the
current generation timestamp. This deliberately avoids filesystem mtimes,
which often churn when otherwise identical build artifacts are copied.

## Revision state

Durable protocol state — keep private, outside ephemeral CI. See [site-state/README.md](../../site-state/README.md) for dogfood notes.

## Run

```bash
cargo run -- ./site-dist
cargo run -- ./site-dist --output ./site-dist/.well-known/pagedigest.json --state ./state.json --with-digest
```

Or install the released crate:

```bash
cargo install pagedigest
pagedigest-generator ./site-dist
```

Flags: `--index-style`, `--include-ext`, `--output`, `--state`,
`--with-digest`, `--with-modified`, `--coverage complete|prefixes|none`,
`--prefix` (repeatable; requires `--coverage prefixes`).
