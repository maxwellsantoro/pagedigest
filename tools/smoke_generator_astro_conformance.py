#!/usr/bin/env python3
"""Cross-implementation smoke: Rust generator vs @pagedigest/astro on a shared tree.

Compares URL keys, revs, digests, and coverage for the overlapping static-HTML
subset (plain ASCII paths, trailing-slash index style). Astro does not implement
the generator's full percent-encoding or Markdown allowlist; those stay
generator-only by design.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_DIR = ROOT / "implementations" / "rust-generator"
ASTRO_SRC = ROOT / "packages" / "astro" / "src" / "index.js"


def write_fixture(site_dir: Path) -> None:
    (site_dir / "blog").mkdir(parents=True, exist_ok=True)
    (site_dir / "docs").mkdir(parents=True, exist_ok=True)
    (site_dir / "index.html").write_text("<h1>Home</h1>\n", encoding="utf-8")
    (site_dir / "about.html").write_text("<h1>About</h1>\n", encoding="utf-8")
    (site_dir / "blog" / "index.html").write_text("<h1>Blog</h1>\n", encoding="utf-8")
    (site_dir / "docs" / "index.htm").write_text("<h1>Docs</h1>\n", encoding="utf-8")
    well_known = site_dir / ".well-known"
    well_known.mkdir(parents=True, exist_ok=True)
    (well_known / "pagedigest.json").write_text("{}\n", encoding="utf-8")


def run_rust(site_dir: Path, manifest_path: Path, state_path: Path) -> dict:
    cmd = [
        "cargo",
        "run",
        "--quiet",
        "--",
        str(site_dir),
        "--output",
        str(manifest_path),
        "--state",
        str(state_path),
        "--with-digest",
        "--include-ext",
        "html,htm",
        "--index-style",
        "trailing-slash",
        "--coverage",
        "complete",
    ]
    subprocess.run(cmd, cwd=GENERATOR_DIR, check=True)
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def run_astro(site_dir: Path, state_path: Path) -> dict:
    script = f"""
import {{ generateManifest }} from {json.dumps(ASTRO_SRC.resolve().as_uri())};
const result = await generateManifest({{
  outputDir: {json.dumps(str(site_dir))},
  statePath: {json.dumps(str(state_path))},
  output: ".well-known/pagedigest.json",
  includeExtensions: [".html", ".htm"],
  withDigest: true,
  coverage: {{ mode: "complete" }},
  generated: "2026-07-08T00:00:00Z",
}});
process.stdout.write(JSON.stringify(result.manifest));
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def comparable(manifest: dict) -> dict:
    return {
        "coverage": manifest.get("coverage"),
        "site_rev": manifest["site_rev"],
        "entries": {
            key: {
                "rev": entry["rev"],
                "digest": entry.get("digest"),
            }
            for key, entry in sorted(manifest["entries"].items())
        },
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pagedigest-astro-conf-") as tmp:
        tmp_path = Path(tmp)

        site_rust = tmp_path / "site-rust"
        site_rust.mkdir()
        write_fixture(site_rust)
        rust = run_rust(
            site_rust,
            tmp_path / "rust-manifest.json",
            tmp_path / "rust-state.json",
        )

        site_astro = tmp_path / "site-astro"
        site_astro.mkdir()
        write_fixture(site_astro)
        astro = run_astro(site_astro, tmp_path / "astro-state.json")

        left = comparable(rust)
        right = comparable(astro)
        if left != right:
            raise AssertionError(
                "generator/astro divergence:\n"
                f"rust={json.dumps(left, indent=2)}\n"
                f"astro={json.dumps(right, indent=2)}"
            )

        expected_keys = {"/", "/about.html", "/blog/", "/docs/"}
        if set(left["entries"]) != expected_keys:
            raise AssertionError(f"unexpected keys: {sorted(left['entries'])}")

    print("generator↔astro conformance passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
