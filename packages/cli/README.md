# `pagedigest`

Thin npm launcher for the PageDigest manifest generator.

```bash
npx pagedigest ./site-dist
```

The launcher downloads the matching generator binary from the pinned GitHub
release on first use, verifies its SHA-256 digest, and caches the verified
binary. It supports x64 Linux and Windows plus x64 and Apple Silicon macOS.

Generator options:

```bash
npx pagedigest --help
```

Requires Node.js 20 or newer. The generator and launcher are MIT licensed.
