#!/usr/bin/env python3
"""Cross-implementation smoke: Rust generator vs @pagedigest/astro on a shared tree.

Compares URL keys, revs, digests, and coverage for the overlapping static-HTML
subset, including Unicode and escaped filename characters with trailing-slash
index style. Both generated manifests must pass reference consumer validation.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tempfile
from pathlib import Path

from pagedigest import validate_manifest


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
    for name in [
        "café.html",
        "100%.html",
        "a[b].html",
        "hello world.html",
        "hello%20world.html",
        "😀.html",
    ]:
        (site_dir / name).write_text(f"<h1>{name}</h1>\n", encoding="utf-8")
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
    if not state_path.exists():
        cmd.append("--init")
    subprocess.run(cmd, cwd=GENERATOR_DIR, check=True)
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def run_astro(site_dir: Path, state_path: Path) -> dict:
    script = f"""
import {{ generateManifest }} from {json.dumps(ASTRO_SRC.resolve().as_uri())};
const result = await generateManifest({{
  outputDir: {json.dumps(str(site_dir))},
  statePath: {json.dumps(str(state_path))},
  output: "astro-manifest.json",
  initialize: {str(not state_path.exists()).lower()},
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


class ServedTransformHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"deterministic served transform"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


def check_reconcile_progression(
    site: Path, manifest_path: Path, state_path: Path, generate, base_url: str
) -> None:
    before = json.loads(manifest_path.read_text(encoding="utf-8"))
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "reconcile_served_digests.py"),
            str(manifest_path),
            "--base-url",
            base_url,
            "--apply",
            "--bump-site-rev",
            "--state",
            str(state_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    reconciled = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert reconciled["site_rev"] == before["site_rev"] + 1
    unchanged = generate()
    assert unchanged["site_rev"] == reconciled["site_rev"], (
        "rebuild lost reconciled site_rev"
    )
    assert unchanged["entries"] == before["entries"], (
        "reconciliation changed content revision state"
    )
    (site / "index.html").write_text(
        "<h1>Changed after reconciliation</h1>\n", encoding="utf-8"
    )
    changed = generate()
    assert changed["site_rev"] == reconciled["site_rev"] + 1, (
        "content change reused reconciled site_rev"
    )
    assert changed["entries"]["/"]["rev"] == before["entries"]["/"]["rev"] + 1


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

        for manifest in (rust, astro):
            error = validate_manifest(manifest)
            if error:
                raise AssertionError(f"generated manifest is invalid: {error}")
        left = comparable(rust)
        right = comparable(astro)
        if left != right:
            raise AssertionError(
                "generator/astro divergence:\n"
                f"rust={json.dumps(left, indent=2)}\n"
                f"astro={json.dumps(right, indent=2)}"
            )

        expected_keys = {
            "/",
            "/about.html",
            "/blog/",
            "/docs/",
            "/caf%C3%A9.html",
            "/100%25.html",
            "/a%5Bb%5D.html",
            "/hello%20world.html",
            "/hello%2520world.html",
            "/%F0%9F%98%80.html",
        }
        if set(left["entries"]) != expected_keys:
            raise AssertionError(f"unexpected keys: {sorted(left['entries'])}")

        server = ThreadingHTTPServer(("127.0.0.1", 0), ServedTransformHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}"
            check_reconcile_progression(
                site_rust,
                tmp_path / "rust-manifest.json",
                tmp_path / "rust-state.json",
                lambda: run_rust(
                    site_rust,
                    tmp_path / "rust-manifest.json",
                    tmp_path / "rust-state.json",
                ),
                base_url,
            )
            check_reconcile_progression(
                site_astro,
                site_astro / "astro-manifest.json",
                tmp_path / "astro-state.json",
                lambda: run_astro(site_astro, tmp_path / "astro-state.json"),
                base_url,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    print("generator↔astro conformance and reconciliation progression passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
