#!/usr/bin/env python3
"""Generate the dogfood collection, excluding Cloudflare's error template.

404.html remains deployed to render errors; it is not a successful resource at
that URL. Stage the collection before generation so removals advance revisions
and retire keys normally. Never filter an already-generated manifest afterward.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_generator(site: Path, output: Path, state: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="pagedigest-collection-") as tmp:
        collection = Path(tmp) / "site"
        shutil.copytree(site, collection)
        (collection / "404.html").unlink(missing_ok=True)
        subprocess.run(
            [
                "cargo",
                "run",
                "--quiet",
                "--locked",
                "--",
                str(collection),
                "--output",
                str(output.resolve()),
                "--state",
                str(state.resolve()),
                "--with-digest",
            ],
            cwd=ROOT / "implementations/rust-generator",
            check=True,
            capture_output=True,
            text=True,
        )


if __name__ == "__main__":
    run_generator(
        ROOT / "site",
        ROOT / "site/.well-known/pagedigest.json",
        ROOT / "site-state/state.json",
    )
    print("generated dogfood collection; 404.html excluded as an error template")
