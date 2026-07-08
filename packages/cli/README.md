# `pagedigest`

Thin npm launcher for the PageDigest manifest generator.

```bash
npx pagedigest ./site-dist
npx pagedigest ./site-dist --with-digest
```

The launcher downloads the matching generator binary from the pinned GitHub
release on first use, verifies its SHA-256 digest against a hard-coded pin,
enforces a 10 MB archive size cap, and caches the verified binary.

## Supported platforms

| Platform key | Archive |
|--------------|---------|
| `linux-x64` | `.tar.gz` |
| `darwin-arm64` | `.tar.gz` |
| `darwin-x64` | `.tar.gz` |
| `win32-x64` | `.zip` |

Other architectures (for example `linux-arm64`) fail with a clear error.

### Windows extraction

Windows releases ship as `.zip`. The launcher extracts them with the system
`tar` (`tar.exe` on modern Windows 10/11 and Windows Server 2019+). If `tar`
is missing from `PATH`, installation fails with an extract error — install a
recent Windows build or use the [GitHub release binary](https://github.com/maxwellsantoro/pagedigest/releases)
directly / `cargo install pagedigest` instead.

## Digests and deploy hygiene

`--with-digest` hashes **on-disk** build output. After a successful run that
includes digests, the launcher prints a short reminder. Full pipeline:

1. Generate the manifest from final static output.
2. Deploy pages + manifest.
3. `python tools/reconcile_served_digests.py … --apply` when the CDN rewrites HTML.
4. `pagedigest verify-live https://example.com` to sample live audits.

See [CONTENT_HYGIENE.md](../../CONTENT_HYGIENE.md).

## Generator options

```bash
npx pagedigest --help
```

Requires Node.js 20 or newer (for global `fetch`). The generator and launcher
are MIT licensed.

## Version matrix

| Component | Version |
|-----------|---------|
| Spec wire `version` | `1` (RC) |
| This launcher / generator | `0.2.0` |
| Python consumer (PyPI) | `0.1.0` |
| `@pagedigest/astro` | `0.1.0` |

Semver tracks **implementations**. Spec field `version` stays `1` until a
breaking protocol revision.
