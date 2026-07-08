# `pagedigest`

Thin npm launcher for the PageDigest manifest generator.

```bash
npx pagedigest ./site-dist
```

The launcher downloads the matching generator binary from the pinned GitHub
release on first use, verifies its SHA-256 digest, and caches the verified
binary. Supported platforms: `linux-x64`, `darwin-arm64`, `darwin-x64`, and
`win32-x64`. Other architectures (for example `linux-arm64`) fail with a clear
error. Windows archives are `.zip` files extracted with the system `tar`
(`tar.exe` on modern Windows).

Generator options:

```bash
npx pagedigest --help
```

Requires Node.js 20 or newer. The generator and launcher are MIT licensed.
