#!/usr/bin/env python3
"""Integration smoke test for the Rust generator.

This script verifies durable state behavior across repeated generator runs:
1) Initial generation creates entries with rev=1 and site_rev=1.
2) No content change keeps revision counters stable.
3) Content update increments the file rev and site_rev.
4) File removal increments site_rev and removes the entry.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR_DIR = ROOT / "implementations" / "rust-generator"


def run_generator(
    site_dir: Path,
    manifest_path: Path,
    state_path: Path,
    extra_args: list[str] | None = None,
) -> None:
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
    ]
    if extra_args:
        cmd.extend(extra_args)
    subprocess.run(cmd, cwd=GENERATOR_DIR, check=True)


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pagedigest-smoke-") as tmp:
        tmp_path = Path(tmp)
        site_dir = tmp_path / "site"
        site_dir.mkdir(parents=True, exist_ok=True)

        file_path = site_dir / "index.html"
        file_path.write_text("hello v1\n", encoding="utf-8")

        manifest_path = tmp_path / "out" / "pagedigest.json"
        state_path = tmp_path / "state" / "pagedigest-state.json"

        # First run: seed revisions.
        run_generator(site_dir, manifest_path, state_path)
        m1 = load_manifest(manifest_path)
        assert_equal(m1["site_rev"], 1, "site_rev after first run")
        assert_equal(m1["coverage"], {"mode": "complete"}, "coverage after first run")
        assert_equal(m1["entries"]["/"]["rev"], 1, "rev after first run")

        # Second run: no change.
        run_generator(site_dir, manifest_path, state_path)
        m2 = load_manifest(manifest_path)
        assert_equal(m2["site_rev"], 1, "site_rev after no-change run")
        assert_equal(
            m2["coverage"], {"mode": "complete"}, "coverage after no-change run"
        )
        assert_equal(m2["entries"]["/"]["rev"], 1, "rev after no-change run")

        # Third run: content change.
        file_path.write_text("hello v2\n", encoding="utf-8")
        run_generator(site_dir, manifest_path, state_path)
        m3 = load_manifest(manifest_path)
        assert_equal(m3["site_rev"], 2, "site_rev after content change")
        assert_equal(m3["entries"]["/"]["rev"], 2, "rev after content change")

        # Fourth run: file removal.
        file_path.unlink()
        run_generator(site_dir, manifest_path, state_path)
        m4 = load_manifest(manifest_path)
        assert_equal(m4["site_rev"], 3, "site_rev after file removal")
        if "/" in m4["entries"]:
            raise AssertionError(
                "removed file key should not exist in manifest entries"
            )

        # Fifth run: coverage semantics change, so site_rev bumps even without content changes.
        run_generator(
            site_dir, manifest_path, state_path, extra_args=["--coverage", "none"]
        )
        m5 = load_manifest(manifest_path)
        assert_equal(m5["site_rev"], 4, "site_rev after coverage change")
        if "coverage" in m5:
            raise AssertionError(
                "coverage should be omitted when --coverage none is used"
            )

        # Sixth run: same coverage semantics, no content change.
        run_generator(
            site_dir, manifest_path, state_path, extra_args=["--coverage", "none"]
        )
        m6 = load_manifest(manifest_path)
        assert_equal(m6["site_rev"], 4, "site_rev after no-change coverage-none run")

    print("generator smoke progression passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
