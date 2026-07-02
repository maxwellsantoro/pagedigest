#!/usr/bin/env python3
"""Validate pagedigest test-vectors for basic consistency and expected outcomes.

This tool does not replace full protocol conformance tests, but it ensures the
fixture bundle remains internally coherent and usable by implementations.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "test-vectors"
SCHEMA_PATH = ROOT / "pagedigest.schema.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def assert_schema_valid(validator: Draft202012Validator, path: Path) -> None:
    data = read_json(path)
    errors = sorted(validator.iter_errors(data), key=lambda err: list(err.path))
    if errors:
        details = "; ".join(f"{err.message} at {list(err.path)}" for err in errors)
        raise ValueError(f"{path.name}: schema validation failed: {details}")


def assert_schema_invalid(validator: Draft202012Validator, path: Path) -> None:
    data = read_json(path)
    if not any(True for _ in validator.iter_errors(data)):
        raise ValueError(f"{path.name}: expected schema validation to fail")


def validate_required_fields(path: Path) -> None:
    data = read_json(path)
    for key in ("version", "generated", "site_rev", "entries"):
        if key not in data:
            raise ValueError(f"{path.name}: missing required field {key}")


def assert_invalid_missing_required(path: Path) -> None:
    data = read_json(path)
    if "entries" in data:
        raise ValueError(f"{path.name}: expected missing entries field")


def assert_invalid_key_fragment(path: Path) -> None:
    data = read_json(path)
    keys = (data.get("entries") or {}).keys()
    if not any("#" in k for k in keys):
        raise ValueError(f"{path.name}: expected a key containing fragment marker #")


def assert_monotonicity_violation(prev_path: Path, next_path: Path) -> None:
    prev = read_json(prev_path)
    nxt = read_json(next_path)
    if nxt["site_rev"] >= prev["site_rev"]:
        raise ValueError("expected site_rev decrease in monotonicity violation pair")

    prev_entries = prev["entries"]
    nxt_entries = nxt["entries"]
    violated = False
    for key, prev_entry in prev_entries.items():
        if key in nxt_entries and nxt_entries[key]["rev"] < prev_entry["rev"]:
            violated = True
            break
    if not violated:
        raise ValueError("expected at least one per-entry rev decrease")


def assert_audit_case(manifest_path: Path, body_path: Path, expect_match: bool) -> None:
    manifest = read_json(manifest_path)
    digest = manifest["entries"]["/audit"]["digest"]
    body = body_path.read_bytes()
    computed = "sha256:" + hashlib.sha256(body).hexdigest()
    if expect_match and computed != digest:
        raise ValueError("expected digest match but got mismatch")
    if not expect_match and computed == digest:
        raise ValueError("expected digest mismatch but got match")


def assert_coverage_mode_change_bumps_site_rev(prev_path: Path, next_path: Path) -> None:
    prev = read_json(prev_path)
    nxt = read_json(next_path)

    prev_mode = (prev.get("coverage") or {}).get("mode")
    next_mode = (nxt.get("coverage") or {}).get("mode")
    if prev_mode == next_mode:
        raise ValueError("expected coverage mode to change between fixtures")

    if nxt["site_rev"] <= prev["site_rev"]:
        raise ValueError("expected site_rev to increase when coverage semantics change")


def assert_coverage_prefixes_change_bumps_site_rev(prev_path: Path, next_path: Path) -> None:
    prev = read_json(prev_path)
    nxt = read_json(next_path)

    prev_cov = prev.get("coverage") or {}
    next_cov = nxt.get("coverage") or {}
    if prev_cov.get("mode") != "prefixes" or next_cov.get("mode") != "prefixes":
        raise ValueError("expected both fixtures to use coverage.mode=prefixes")

    if prev_cov.get("prefixes") == next_cov.get("prefixes"):
        raise ValueError("expected coverage prefixes list to change between fixtures")

    if nxt["site_rev"] <= prev["site_rev"]:
        raise ValueError("expected site_rev to increase when coverage.prefixes changes")


def assert_url_key_variants(path: Path) -> None:
    data = read_json(path)
    entries = data.get("entries") or {}
    for required in ("/about", "/about/", "/pricing?region=us", "/posts/hello%20world"):
        if required not in entries:
            raise ValueError(f"expected key missing from url-key-variants fixture: {required}")


def main() -> int:
    validator = load_schema_validator()

    index = read_json(VECTORS / "index.json")
    case_ids = {c["id"] for c in index["cases"]}
    expected_ids = {
        "valid-minimal",
        "valid-with-digest",
        "valid-partial-prefix",
        "valid-with-coverage-complete",
        "coverage-mode-change",
        "coverage-prefixes-change",
        "url-key-variants",
        "invalid-missing-required",
        "invalid-url-key-fragment",
        "violation-monotonicity",
        "audit-match",
        "audit-mismatch",
    }
    missing = expected_ids - case_ids
    if missing:
        raise ValueError(f"index missing expected cases: {sorted(missing)}")

    valid_fixtures = [
        VECTORS / "valid-minimal.json",
        VECTORS / "valid-with-digest.json",
        VECTORS / "valid-partial-prefix.json",
        VECTORS / "valid-with-coverage-complete.json",
        VECTORS / "url-key-variants.json",
        VECTORS / "coverage-mode-change-prev.json",
        VECTORS / "coverage-mode-change-next.json",
        VECTORS / "coverage-prefixes-change-prev.json",
        VECTORS / "coverage-prefixes-change-next.json",
        VECTORS / "violation-monotonicity-prev.json",
        VECTORS / "violation-monotonicity-next.json",
        VECTORS / "audit-match" / "manifest.json",
        VECTORS / "audit-mismatch" / "manifest.json",
    ]
    for path in valid_fixtures:
        assert_schema_valid(validator, path)

    invalid_fixtures = [
        VECTORS / "invalid-missing-required.json",
        VECTORS / "invalid-url-key-fragment.json",
    ]
    for path in invalid_fixtures:
        assert_schema_invalid(validator, path)

    validate_required_fields(VECTORS / "valid-minimal.json")
    validate_required_fields(VECTORS / "valid-with-digest.json")
    validate_required_fields(VECTORS / "valid-partial-prefix.json")
    validate_required_fields(VECTORS / "valid-with-coverage-complete.json")
    validate_required_fields(VECTORS / "url-key-variants.json")

    assert_invalid_missing_required(VECTORS / "invalid-missing-required.json")
    assert_invalid_key_fragment(VECTORS / "invalid-url-key-fragment.json")
    assert_monotonicity_violation(
        VECTORS / "violation-monotonicity-prev.json",
        VECTORS / "violation-monotonicity-next.json",
    )
    assert_coverage_mode_change_bumps_site_rev(
        VECTORS / "coverage-mode-change-prev.json",
        VECTORS / "coverage-mode-change-next.json",
    )
    assert_coverage_prefixes_change_bumps_site_rev(
        VECTORS / "coverage-prefixes-change-prev.json",
        VECTORS / "coverage-prefixes-change-next.json",
    )
    assert_url_key_variants(VECTORS / "url-key-variants.json")
    assert_audit_case(
        VECTORS / "audit-match" / "manifest.json",
        VECTORS / "audit-match" / "page-body.bin",
        expect_match=True,
    )
    assert_audit_case(
        VECTORS / "audit-mismatch" / "manifest.json",
        VECTORS / "audit-mismatch" / "page-body.bin",
        expect_match=False,
    )

    print("test-vectors validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())