import json
import unittest
from pathlib import Path

from pagedigest.core import diff, validate_manifest

ROOT = Path(__file__).resolve().parents[3]
VECTORS = ROOT / "test-vectors"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def manifest_path(case: dict) -> Path:
    if "manifest" in case:
        return VECTORS / case["manifest"]
    if "file" in case:
        return VECTORS / case["file"]
    raise KeyError(f"case {case.get('id')} has no manifest path")


class VectorBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.index = read_json(VECTORS / "index.json")

    def test_valid_fixtures_pass_consumer_validation(self) -> None:
        for case in self.index["cases"]:
            if case["kind"] != "valid":
                continue
            manifest = read_json(manifest_path(case))
            self.assertIsNone(
                validate_manifest(manifest),
                msg=f"{case['id']} should pass validate_manifest",
            )

    def test_semantic_fixture_pairs_pass_consumer_validation(self) -> None:
        semantic_kinds = {"semantic-site-rev-bump", "semantic-rev-bump", "anomalous-sequence"}
        for case in self.index["cases"]:
            if case["kind"] not in semantic_kinds:
                continue
            for rel_path in case["files"]:
                manifest = read_json(VECTORS / rel_path)
                self.assertIsNone(
                    validate_manifest(manifest),
                    msg=f"{case['id']} fixture {rel_path} should pass validate_manifest",
                )

    def test_audit_fixtures_pass_consumer_validation(self) -> None:
        for case in self.index["cases"]:
            if case["kind"] not in {"audit-match", "audit-mismatch"}:
                continue
            manifest = read_json(manifest_path(case))
            self.assertIsNone(validate_manifest(manifest), msg=case["id"])

    def test_invalid_missing_required_fails_validation(self) -> None:
        manifest = read_json(VECTORS / "invalid-missing-required.json")
        self.assertEqual(validate_manifest(manifest), "missing-entries")

    def test_invalid_fragment_key_fails_validation(self) -> None:
        manifest = read_json(VECTORS / "invalid-url-key-fragment.json")
        self.assertEqual(validate_manifest(manifest), "invalid-url-key-pattern")

    def test_monotonicity_violation_surfaces_as_site_anomaly(self) -> None:
        prev = read_json(VECTORS / "violation-monotonicity-prev.json")
        nxt = read_json(VECTORS / "violation-monotonicity-next.json")

        result = diff(
            nxt, cached_site_rev=prev["site_rev"], cached_revs={k: v["rev"] for k, v in prev["entries"].items()}
        )
        self.assertEqual(result.get("site_anomaly"), "site-rev-decrease")

    def test_entry_rev_decrease_surfaces_as_anomaly(self) -> None:
        prev = read_json(VECTORS / "violation-monotonicity-prev.json")
        manifest = {
            **prev,
            "site_rev": prev["site_rev"] + 1,
            "entries": {
                **prev["entries"],
                "/docs/start": {"rev": prev["entries"]["/docs/start"]["rev"] - 1},
            },
        }

        result = diff(
            manifest,
            cached_site_rev=prev["site_rev"],
            cached_revs={k: v["rev"] for k, v in prev["entries"].items()},
        )
        self.assertIsNone(result.get("site_anomaly"))
        self.assertTrue(any(a.get("reason") == "rev-decrease" for a in result.get("anomalies", [])))

    def test_rollback_content_surfaces_as_changed(self) -> None:
        prev = read_json(VECTORS / "rollback-content-prev.json")
        nxt = read_json(VECTORS / "rollback-content-next.json")

        result = diff(
            nxt, cached_site_rev=prev["site_rev"], cached_revs={k: v["rev"] for k, v in prev["entries"].items()}
        )
        self.assertEqual(result["changed"], ["/article"])
        self.assertEqual(result["anomalies"], [])
        self.assertTrue(result["site_changed"])


if __name__ == "__main__":
    unittest.main()
