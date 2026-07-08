#!/usr/bin/env python3
"""Validate pagedigest test-vectors for basic consistency and expected outcomes.

This tool does not replace full protocol conformance tests, but it ensures the
fixture bundle remains internally coherent and usable by implementations.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
VECTORS = ROOT / "test-vectors"
SCHEMA_PATH = ROOT / "pagedigest.schema.json"


def load_consumer_core() -> Any:
    path = ROOT / "implementations" / "python-consumer" / "pagedigest" / "core.py"
    spec = importlib.util.spec_from_file_location("pagedigest_vector_core", path)
    if spec is None or spec.loader is None:
        raise ValueError("could not load Python consumer core")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    # The schema declares `format: date-time` on `generated` and `modified`.
    # jsonschema does not enforce format keywords unless a FormatChecker is
    # supplied AND a backend library for the format is importable. To keep this
    # tool dependency-free, register a stdlib-only date-time check so the
    # keyword is actually meaningful rather than silently vacuous. This is still
    # looser than the consumer's UTC-only validator (the normative boundary),
    # which is exercised by the unittest suite.
    format_checker = FormatChecker()

    @format_checker.checks("date-time", raises=ValueError)
    def _is_date_time(value: object) -> bool:
        if not isinstance(value, str):
            return True
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True

    return Draft202012Validator(schema, format_checker=format_checker)


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


def assert_invalid_key_scheme_relative(path: Path) -> None:
    data = read_json(path)
    keys = (data.get("entries") or {}).keys()
    if not any(k.startswith("//") for k in keys):
        raise ValueError(
            f"{path.name}: expected a scheme-relative key starting with //"
        )
    core = load_consumer_core()
    err = core.validate_manifest(data)
    if err is None:
        raise ValueError(
            f"{path.name}: consumer should reject scheme-relative URL keys"
        )


def assert_invalid_digest_shape(path: Path) -> None:
    data = read_json(path)
    core = load_consumer_core()
    err = core.validate_manifest(data)
    if err != "invalid-digest":
        raise ValueError(f"{path.name}: expected invalid-digest, got {err!r}")


def assert_site_rev_equal_short_circuit(prev_path: Path, next_path: Path) -> None:
    prev = read_json(prev_path)
    nxt = read_json(next_path)
    if prev["site_rev"] != nxt["site_rev"]:
        raise ValueError("expected equal site_rev for short-circuit pair")
    core = load_consumer_core()
    decisions = core.diff(
        nxt, prev["site_rev"], {k: e["rev"] for k, e in prev["entries"].items()}
    )
    if decisions.get("site_changed"):
        raise ValueError("equal site_rev must report site_changed=False")
    if (
        decisions.get("changed")
        or decisions.get("new")
        or decisions.get("fallback_urls")
    ):
        raise ValueError("equal site_rev short-circuit must not schedule fetches")
    if sorted(decisions.get("unchanged", [])) != sorted(nxt["entries"].keys()):
        raise ValueError(
            "equal site_rev short-circuit should list all keys as unchanged"
        )


def assert_complete_removal(prev_path: Path, next_path: Path) -> None:
    prev = read_json(prev_path)
    nxt = read_json(next_path)
    if (prev.get("coverage") or {}).get("mode") != "complete":
        raise ValueError("expected complete coverage on prev")
    if (nxt.get("coverage") or {}).get("mode") != "complete":
        raise ValueError("expected complete coverage on next")
    if nxt["site_rev"] <= prev["site_rev"]:
        raise ValueError("expected site_rev increase when entries are removed")
    core = load_consumer_core()
    decisions = core.diff(
        nxt,
        prev["site_rev"],
        {k: e["rev"] for k, e in prev["entries"].items()},
    )
    if "/about" not in decisions.get("removed", []):
        raise ValueError("complete coverage should surface removed keys")


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


def assert_coverage_mode_change_bumps_site_rev(
    prev_path: Path, next_path: Path
) -> None:
    prev = read_json(prev_path)
    nxt = read_json(next_path)

    prev_mode = (prev.get("coverage") or {}).get("mode")
    next_mode = (nxt.get("coverage") or {}).get("mode")
    if prev_mode == next_mode:
        raise ValueError("expected coverage mode to change between fixtures")

    if nxt["site_rev"] <= prev["site_rev"]:
        raise ValueError("expected site_rev to increase when coverage semantics change")


def assert_coverage_prefixes_change_bumps_site_rev(
    prev_path: Path, next_path: Path
) -> None:
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


def assert_rollback_increments_revs(prev_path: Path, next_path: Path) -> None:
    prev = read_json(prev_path)
    nxt = read_json(next_path)

    if nxt["site_rev"] <= prev["site_rev"]:
        raise ValueError("expected site_rev to increase after content rollback")

    prev_entries = prev["entries"]
    nxt_entries = nxt["entries"]
    bumped = False
    for key, prev_entry in prev_entries.items():
        if key not in nxt_entries:
            continue
        next_rev = nxt_entries[key]["rev"]
        if next_rev <= prev_entry["rev"]:
            raise ValueError(f"expected rev to increase for rolled-back URL {key}")
        bumped = True
    if not bumped:
        raise ValueError("expected at least one entry rev to increase in rollback pair")


def assert_url_key_variants(path: Path) -> None:
    data = read_json(path)
    entries = data.get("entries") or {}
    for required in ("/about", "/about/", "/pricing?region=us", "/posts/hello%20world"):
        if required not in entries:
            raise ValueError(
                f"expected key missing from url-key-variants fixture: {required}"
            )


def assert_header_formats(path: Path) -> None:
    core = load_consumer_core()
    data = read_json(path)
    for case in data.get("cases", []):
        value = case["value"]
        try:
            parsed = core.parse_state_header(value)
        except ValueError:
            if case.get("valid"):
                raise ValueError(
                    f"expected valid PageDigest-State value: {value}"
                ) from None
        else:
            if not case.get("valid"):
                raise ValueError(f"expected invalid PageDigest-State value: {value}")
            if parsed != case.get("parsed"):
                raise ValueError(f"unexpected parsed PageDigest-State value: {value}")


def main() -> int:
    validator = load_schema_validator()

    # Guard against a silent no-op: if the date-time format check stops
    # enforcing, schema validation would accept invalid timestamps.
    if not any(
        True
        for _ in validator.iter_errors(
            {
                "version": 1,
                "generated": "2026-13-45T00:00:00Z",
                "site_rev": 1,
                "entries": {},
            }
        )
    ):
        raise ValueError(
            "date-time format checker is not enforcing; schema would accept invalid timestamps"
        )

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
        "invalid-url-key-scheme-relative",
        "invalid-digest-shape",
        "violation-monotonicity",
        "rollback-content",
        "site-rev-equal-short-circuit",
        "complete-removal",
        "audit-match",
        "audit-mismatch",
        "header-formats",
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
        VECTORS / "rollback-content-prev.json",
        VECTORS / "rollback-content-next.json",
        VECTORS / "site-rev-equal-short-circuit-prev.json",
        VECTORS / "site-rev-equal-short-circuit-next.json",
        VECTORS / "complete-removal-prev.json",
        VECTORS / "complete-removal-next.json",
        VECTORS / "audit-match" / "manifest.json",
        VECTORS / "audit-mismatch" / "manifest.json",
    ]
    for path in valid_fixtures:
        assert_schema_valid(validator, path)

    invalid_fixtures = [
        VECTORS / "invalid-missing-required.json",
        VECTORS / "invalid-url-key-fragment.json",
        VECTORS / "invalid-digest-shape.json",
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
    assert_invalid_key_scheme_relative(VECTORS / "invalid-url-key-scheme-relative.json")
    assert_invalid_digest_shape(VECTORS / "invalid-digest-shape.json")
    assert_monotonicity_violation(
        VECTORS / "violation-monotonicity-prev.json",
        VECTORS / "violation-monotonicity-next.json",
    )
    assert_rollback_increments_revs(
        VECTORS / "rollback-content-prev.json",
        VECTORS / "rollback-content-next.json",
    )
    assert_coverage_mode_change_bumps_site_rev(
        VECTORS / "coverage-mode-change-prev.json",
        VECTORS / "coverage-mode-change-next.json",
    )
    assert_coverage_prefixes_change_bumps_site_rev(
        VECTORS / "coverage-prefixes-change-prev.json",
        VECTORS / "coverage-prefixes-change-next.json",
    )
    assert_site_rev_equal_short_circuit(
        VECTORS / "site-rev-equal-short-circuit-prev.json",
        VECTORS / "site-rev-equal-short-circuit-next.json",
    )
    assert_complete_removal(
        VECTORS / "complete-removal-prev.json",
        VECTORS / "complete-removal-next.json",
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
    assert_header_formats(VECTORS / "header-formats.json")

    print("test-vectors validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
