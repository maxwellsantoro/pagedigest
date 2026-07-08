#!/usr/bin/env python3
"""Check rendered output for common PageDigest content-hygiene hazards.

The checker is intentionally conservative: findings are warnings unless a file
is unreadable. Use ``--fail-on warning`` to turn warnings into a deployment gate.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

TEXT_EXTENSIONS = {
    ".css",
    ".htm",
    ".html",
    ".js",
    ".json",
    ".md",
    ".svg",
    ".txt",
    ".xml",
}

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "target",
    "__pycache__",
}

VOLATILE_TIMESTAMP = re.compile(
    r"\b\d{4}-\d{2}-\d{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
)
GENERATED_PHRASE = re.compile(
    r"\b(?:generated|built|rendered|compiled)\s+(?:at|on)\b", re.IGNORECASE
)
CACHE_BUST_QUERY = re.compile(
    r"[?&](?:v|ver|version|t|ts|time|cb|cache[-_]?bust)=([0-9]{8,}|[a-fA-F0-9]{12,})\b"
)
SESSION_TOKEN = re.compile(
    r"\b(?:csrf|xsrf|session)[-_ ]?(?:token|id)?\b\s*[:=]", re.IGNORECASE
)


@dataclass(frozen=True)
class Finding:
    severity: str
    rule: str
    path: str
    line: int | None
    detail: str


def iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def check_path_shape(root: Path, path: Path) -> list[Finding]:
    rel = relative_path(root, path)
    name = path.name.lower()
    findings: list[Finding] = []
    if name.endswith((".bak", ".tmp", ".temp", ".orig", "~")) or name in {
        ".ds_store",
        "thumbs.db",
    }:
        findings.append(
            Finding(
                "warning",
                "non-content-artifact",
                rel,
                None,
                "Temporary/editor artifact appears in rendered output; exclude it before generating a manifest.",
            )
        )
    if name.endswith(".map"):
        findings.append(
            Finding(
                "warning",
                "source-map-artifact",
                rel,
                None,
                "Source map appears in rendered output; include it only if it is intentional content.",
            )
        )
    return findings


def is_protocol_manifest(rel: str) -> bool:
    """Manifest ``generated`` is required protocol metadata, not page-content churn."""
    return rel == ".well-known/pagedigest.json" or rel.endswith(
        "/.well-known/pagedigest.json"
    )


def check_text(root: Path, path: Path, text: str) -> list[Finding]:
    rel = relative_path(root, path)
    findings: list[Finding] = []
    skip_volatile_timestamps = is_protocol_manifest(rel)
    for line_number, line in enumerate(text.splitlines(), start=1):
        if "mailto:" in line:
            findings.append(
                Finding(
                    "warning",
                    "edge-email-obfuscation-risk",
                    rel,
                    line_number,
                    "mailto link can be rewritten by CDN email-obfuscation features; reconcile served digests after deploy.",
                )
            )
        if "/cdn-cgi/" in line:
            findings.append(
                Finding(
                    "warning",
                    "edge-injected-cloudflare-path",
                    rel,
                    line_number,
                    "Cloudflare /cdn-cgi/ marker appears in output; verify this is not host-injected churn.",
                )
            )
        if not skip_volatile_timestamps and (
            GENERATED_PHRASE.search(line) or VOLATILE_TIMESTAMP.search(line)
        ):
            findings.append(
                Finding(
                    "warning",
                    "volatile-build-timestamp",
                    rel,
                    line_number,
                    "Timestamp-like generated content can cause false rev/digest churn across builds.",
                )
            )
        if CACHE_BUST_QUERY.search(line):
            findings.append(
                Finding(
                    "warning",
                    "volatile-cache-busting-query",
                    rel,
                    line_number,
                    "Timestamp/hash-like cache-busting query can churn even when page semantics are unchanged.",
                )
            )
        if SESSION_TOKEN.search(line):
            findings.append(
                Finding(
                    "warning",
                    "embedded-session-token",
                    rel,
                    line_number,
                    "Session/CSRF-looking token in static output may be per-build or per-request churn.",
                )
            )
    return findings


def check_tree(root: Path) -> list[Finding]:
    root = root.resolve()
    if not root.exists():
        return [
            Finding(
                "error",
                "input-missing",
                str(root),
                None,
                "Input directory does not exist.",
            )
        ]
    if not root.is_dir():
        return [
            Finding(
                "error",
                "input-not-directory",
                str(root),
                None,
                "Input path must be a directory.",
            )
        ]

    findings: list[Finding] = []
    for path in iter_files(root):
        findings.extend(check_path_shape(root, path))
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(
                Finding(
                    "warning",
                    "non-utf8-text-candidate",
                    relative_path(root, path),
                    None,
                    "File extension is usually text, but the file is not UTF-8 decodable.",
                )
            )
            continue
        except OSError as exc:
            findings.append(
                Finding(
                    "error",
                    "unreadable-file",
                    relative_path(root, path),
                    None,
                    str(exc),
                )
            )
            continue
        findings.extend(check_text(root, path, text))
    return findings


def should_fail(findings: list[Finding], fail_on: str) -> bool:
    if fail_on == "none":
        return False
    if fail_on == "warning":
        return any(f.severity in {"warning", "error"} for f in findings)
    return any(f.severity == "error" for f in findings)


def print_text(findings: list[Finding]) -> None:
    if not findings:
        print("content hygiene: no findings")
        return
    for finding in findings:
        location = (
            finding.path if finding.line is None else f"{finding.path}:{finding.line}"
        )
        print(f"- {finding.severity}: {location}: {finding.rule}: {finding.detail}")
    warning_count = sum(f.severity == "warning" for f in findings)
    error_count = sum(f.severity == "error" for f in findings)
    print(f"content hygiene: {warning_count} warning(s), {error_count} error(s)")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check rendered output for PageDigest content-hygiene hazards"
    )
    parser.add_argument("input_dir", help="Rendered output directory to inspect")
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON"
    )
    parser.add_argument(
        "--fail-on",
        choices=("none", "warning", "error"),
        default="error",
        help="Exit non-zero at this severity threshold (default: error)",
    )
    args = parser.parse_args(argv)

    findings = check_tree(Path(args.input_dir))
    if args.json:
        print(
            json.dumps(
                {"findings": [asdict(f) for f in findings]}, indent=2, sort_keys=True
            )
        )
    else:
        print_text(findings)
    return 1 if should_fail(findings, args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
