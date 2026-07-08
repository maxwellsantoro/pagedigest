#!/usr/bin/env python3
"""Reconcile a pagedigest manifest with the bytes a host actually serves.

CDN and edge features (email obfuscation, minification, script injectors)
can rewrite HTML after deploy, so digests computed from build output fail
over-the-wire audits even though the publisher is honest. This tool runs
after deploy and makes the manifest converge to served reality without
requiring the publisher to disable any edge feature:

- each digest-bearing URL is fetched twice with `Accept-Encoding: identity`
- **match**: both fetches hash to the manifest digest — nothing to do
- **stable-transform**: the fetches agree with each other but not the
  manifest (deterministic edge rewrite, e.g. minification) — with
  `--apply`, the digest is adopted from the served bytes
- **unstable**: the two fetches differ from each other (per-response
  rewrite, e.g. randomized email obfuscation) — no digest can ever verify;
  with `--apply`, the digest is removed for that URL, which the spec
  defines as the honest state (`rev` stays monotonic and content-driven)

Intended pipeline: generate manifest -> deploy site -> reconcile --apply
-> deploy the corrected manifest. Run it on every publish so a rebuild
that reintroduces an unverifiable digest is corrected in the same cycle.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from pagedigest import identity_digest, resolve_url_key, validate_manifest

MAX_AUDIT_BYTES = 10 * 1024 * 1024


@dataclass
class Reconciliation:
    path: str
    status: str  # match | stable-transform | unstable | inconclusive
    detail: str
    served_digest: str | None = None


def fetch_identity_digest(
    base_url: str, path: str, timeout: int, max_bytes: int = MAX_AUDIT_BYTES
) -> tuple[str | None, str]:
    try:
        url = resolve_url_key(base_url, path)
    except ValueError as exc:
        return None, str(exc)
    try:
        r = requests.get(
            url,
            headers={"Accept-Encoding": "identity"},
            allow_redirects=False,
            timeout=timeout,
            stream=True,
        )
    except requests.RequestException as exc:
        return None, f"network-error: {exc}"
    try:
        if 300 <= r.status_code < 400:
            return None, f"redirect:{r.status_code}"
        if r.status_code < 200 or r.status_code >= 300:
            return None, f"non-success:{r.status_code}"
        digest, error = identity_digest(r, max_bytes)
        return digest, error if error else "ok"
    finally:
        r.close()


def reconcile_entry(
    base_url: str,
    path: str,
    expected_digest: str,
    timeout: int,
    max_bytes: int = MAX_AUDIT_BYTES,
) -> Reconciliation:
    first, first_detail = fetch_identity_digest(base_url, path, timeout, max_bytes)
    if first is None:
        return Reconciliation(path, "inconclusive", first_detail)
    if first == expected_digest:
        # One matching fetch is sufficient: the digest verifies over the wire.
        return Reconciliation(path, "match", "ok")

    second, second_detail = fetch_identity_digest(base_url, path, timeout, max_bytes)
    if second is None:
        return Reconciliation(path, "inconclusive", second_detail)
    if second == expected_digest:
        # Alternating between the published digest and something else means
        # the bytes are not stable; treat as unstable rather than a match.
        return Reconciliation(
            path, "unstable", f"served bytes alternate: {first} vs {expected_digest}"
        )
    if first == second:
        return Reconciliation(
            path,
            "stable-transform",
            f"served bytes are stable but differ from manifest: {first}",
            served_digest=first,
        )
    return Reconciliation(
        path, "unstable", f"served bytes vary per request: {first} vs {second}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile pagedigest digests with served bytes after deploy"
    )
    parser.add_argument("manifest", help="Path to the local manifest to reconcile")
    parser.add_argument("--base-url", required=True, help="Deployed site base URL")
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Rewrite the manifest: adopt digests for stable transforms, remove "
            "digests for unstable URLs. Without this flag the tool only reports."
        ),
    )
    parser.add_argument(
        "--bump-site-rev",
        action="store_true",
        help=(
            "When rewriting with --apply, also increment site_rev so consumers "
            "that short-circuit on equal site_rev re-process entry digests. "
            "Digest-only corrections do not require a site_rev bump under the "
            "SPEC, but some audit caches only refresh when site_rev moves."
        ),
    )
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=MAX_AUDIT_BYTES,
        help="Abort identity fetches larger than this many bytes",
    )
    args = parser.parse_args()
    if args.bump_site_rev and not args.apply:
        raise SystemExit("--bump-site-rev requires --apply")

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise SystemExit(f"{manifest_path} must contain a JSON object")
    if (validation_error := validate_manifest(manifest)) is not None:
        raise SystemExit(f"{manifest_path} is invalid: {validation_error}")
    entries = manifest.get("entries")
    if not isinstance(entries, dict):
        raise SystemExit(f"{manifest_path} has no entries object")

    results: list[Reconciliation] = []
    for path, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        digest = entry.get("digest")
        if isinstance(digest, str):
            results.append(
                reconcile_entry(
                    args.base_url, path, digest, args.timeout, args.max_bytes
                )
            )

    changed = False
    for result in results:
        print(f"- {result.status}: {result.path} ({result.detail})")
        if not args.apply:
            continue
        entry = entries[result.path]
        if result.status == "stable-transform" and result.served_digest:
            entry["digest"] = result.served_digest
            changed = True
        elif result.status == "unstable":
            del entry["digest"]
            changed = True

    problem_count = sum(r.status in ("stable-transform", "unstable") for r in results)
    inconclusive_count = sum(r.status == "inconclusive" for r in results)
    print(
        f"checked: {len(results)}  match: {sum(r.status == 'match' for r in results)}  "
        f"reconciled: {problem_count if args.apply else 0}  "
        f"outstanding: {0 if args.apply else problem_count}  "
        f"inconclusive: {inconclusive_count}"
    )

    if changed:
        manifest["generated"] = (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        if args.bump_site_rev:
            site_rev = manifest.get("site_rev")
            if not isinstance(site_rev, int) or isinstance(site_rev, bool):
                raise SystemExit(f"{manifest_path} has invalid site_rev")
            manifest["site_rev"] = site_rev + 1
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        note = " (site_rev bumped)" if args.bump_site_rev else ""
        print(
            f"rewrote {manifest_path}{note} (redeploy the manifest to publish the corrections)"
        )

    # Non-zero when problems remain unapplied, so this can gate a deploy.
    if problem_count > 0 and not args.apply:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
