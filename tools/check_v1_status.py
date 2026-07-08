#!/usr/bin/env python3
"""Structural gate: protocol docs present as v1.0 with hard 1.0 gates closed.

Drives the real checked-in files (ROADMAP, README, SPEC, RELEASE_CHECKLIST).
Fails if primary status regresses to RC-only or a hard 1.0 checkbox is reopened.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    print(f"check_v1_status: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    if not re.search(r"^\*\*Now:\*\*\s+v1\.0\b", roadmap, re.MULTILINE):
        fail("ROADMAP.md **Now:** must state v1.0")
    if re.search(r"^\*\*Now:\*\*\s+v1 RC\b", roadmap, re.MULTILINE):
        fail("ROADMAP.md **Now:** still says v1 RC")
    # Phase 1–6 must not leave bare unfinished work as P2/draft in the phase tables.
    phase_blocks = re.findall(
        r"## Phase [1-6].*?(?=## |\Z)",
        roadmap,
        re.DOTALL,
    )
    if len(phase_blocks) < 6:
        fail(f"expected 6 Phase sections, found {len(phase_blocks)}")
    for block in phase_blocks:
        for line in block.splitlines():
            if (
                "|" not in line
                or line.strip().startswith("|---")
                or "Task" in line
                and "Status" in line
            ):
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 2:
                continue
            status = cells[-1].lower()
            if (
                status in {"p2", "draft ready"}
                or status.startswith("p2 ")
                or status.startswith("draft ")
            ):
                fail(f"Phase row still unfinished: {line.strip()}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # Primary status line under ## Status
    status_section = re.search(r"## Status\n+(.*?)(?:\n## |\Z)", readme, re.DOTALL)
    if status_section is None:
        fail("README.md missing ## Status section")
    status_lead = status_section.group(1).lstrip()
    first_line = status_lead.splitlines()[0] if status_lead else ""
    if not first_line.startswith("**v1.0**"):
        fail(f"README.md Status lead must start with **v1.0**, got: {first_line!r}")

    spec = (ROOT / "SPEC.md").read_text(encoding="utf-8")
    if not re.search(r"^\*\*Status:\*\*\s+Final \(v1\.0\)\s*$", spec, re.MULTILINE):
        fail("SPEC.md **Status:** must be Final (v1.0)")

    checklist = (ROOT / "RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
    gate = re.search(r"## 1\.0 Gate\n(.*?)(?:\n## |\Z)", checklist, re.DOTALL)
    if gate is None:
        fail("RELEASE_CHECKLIST.md missing ## 1.0 Gate")
    gate_body = gate.group(1)
    # Hard items are checked boxes; the short-form rel may remain open with non-blocker wording.
    open_items = re.findall(r"^- \[ \] (.+)$", gate_body, re.MULTILINE)
    for item in open_items:
        if "short-form" not in item.lower() and "short form" not in item.lower():
            fail(f"hard 1.0 Gate item still open: {item}")
        if (
            "not a hard blocker" not in item.lower()
            and "not a v1.0 blocker" not in item.lower()
        ):
            fail("open short-form rel item must state it is not a hard/v1.0 blocker")
    if (
        "Protocol status:** v1.0" not in checklist
        and "Protocol status: v1.0" not in checklist
    ):
        # Accept either markdown bold form used in the checklist header note.
        if "**Protocol status:** v1.0" not in checklist:
            fail("RELEASE_CHECKLIST.md must state Protocol status: v1.0")

    print("check_v1_status: ok (docs present v1.0; hard 1.0 gates closed)")


if __name__ == "__main__":
    main()
