#!/usr/bin/env python3
"""Build and exercise distributable artifacts outside the source import path."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, cwd, **kwargs):
    return subprocess.run(args, cwd=cwd, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheel", type=Path, help="Test this exact built wheel instead of rebuilding"
    )
    parser.add_argument("--python-only", action="store_true")
    args = parser.parse_args()
    supplied_wheel = args.wheel.resolve() if args.wheel else None
    with tempfile.TemporaryDirectory(prefix="pagedigest-artifacts-") as tmp:
        root = Path(tmp)
        wheel = supplied_wheel
        if wheel is None:
            source = root / "consumer-source"
            shutil.copytree(
                ROOT / "implementations/python-consumer",
                source,
                ignore=shutil.ignore_patterns(
                    ".venv", "build", "dist", "*.egg-info", "__pycache__", ".ruff_cache"
                ),
            )
            run(["uv", "build", "--wheel", "--out-dir", str(root), str(source)], root)
            wheel = next(root.glob("*.whl"))
        run(["uv", "venv", str(root / "venv")], root)
        python = (
            root / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        )
        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                str(wheel),
                "Scrapy>=2.11",
            ],
            root,
        )
        run(
            [
                str(python),
                "-I",
                "-c",
                "import pagedigest; assert 'site-packages' in pagedigest.__file__; print(pagedigest.__file__)",
            ],
            root,
        )
        run(
            [
                str(python),
                "-I",
                "-m",
                "unittest",
                "discover",
                "-s",
                str(ROOT / "implementations/python-consumer/tests"),
            ],
            root,
        )
        run(
            [str(python), str(ROOT / "integrations/scrapy/tests/test_traversal.py")],
            root,
        )
        run(
            [str(python), str(ROOT / "integrations/scrapy/tests/test_cache_policy.py")],
            root,
        )
        run([str(python), "-I", "-m", "pagedigest.cli", "--help"], root)
        if args.python_only:
            print("exact wheel installation checks passed")
            return 0
        packed = run(
            ["npm", "pack", "--json", "--pack-destination", str(root)],
            ROOT / "packages/astro",
            capture_output=True,
            text=True,
        )
        archive = root / json.loads(packed.stdout)[0]["filename"]
        run(
            [
                "npm",
                "install",
                "--prefix",
                str(root),
                "--ignore-scripts",
                "--legacy-peer-deps",
                str(archive),
            ],
            root,
        )
        script = """import { generateManifest } from '@pagedigest/astro';
import { mkdir, writeFile } from 'node:fs/promises';
await mkdir('site'); await writeFile('site/index.html', 'artifact smoke');
await generateManifest({ outputDir:'site', statePath:'state.json', initialize:true });
const next = await generateManifest({ outputDir:'site', statePath:'state.json' });
if (next.manifest.site_rev !== 1) throw Error('unstable packaged generator');"""
        run(["node", "--input-type=module", "-e", script], root)
    print(
        "built wheel and npm tarball installation checks passed (not a published-release verification)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
