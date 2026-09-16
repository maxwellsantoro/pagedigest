from __future__ import annotations

import copy
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from test_core import load_tool


def manifest_fixture():
    return {
        "version": 1,
        "generated": "2026-09-16T00:00:00Z",
        "site_rev": 4,
        "coverage": {"mode": "complete"},
        "entries": {"/": {"rev": 2, "digest": "sha256:" + "a" * 64}},
    }


def state_fixture(astro=False):
    return {
        "site_rev": 4,
        "coverage": {"mode": "complete"},
        "entries": {"/": {"rev": 2, "content_hash" if astro else "digest": "a" * 64}},
        "retired": {"/old": {"rev": 7, "content_hash" if astro else "digest": "c" * 64}},
    }


class ReconcileStateTests(unittest.TestCase):
    def run_reconcile(self, root, *, with_state=True):
        argv = [
            "reconcile",
            str(root / "manifest.json"),
            "--base-url",
            "https://example.com",
            "--apply",
            "--bump-site-rev",
        ]
        if with_state:
            argv += ["--state", str(root / "state.json")]
        tool = self.tool
        outcome = tool.Reconciliation("/", "stable-transform", "test", "sha256:" + "b" * 64)
        with (
            patch("sys.argv", argv),
            patch.object(tool, "reconcile_entry", return_value=outcome),
            redirect_stdout(io.StringIO()),
        ):
            return tool.main()

    def setUp(self):
        self.tool = load_tool("reconcile_served_digests")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "manifest.json").write_text(json.dumps(manifest_fixture()))
        (self.root / "state.json").write_text(json.dumps(state_fixture()))

    def test_bump_preserves_rust_and_astro_content_state(self):
        for astro in (False, True):
            with self.subTest(astro=astro):
                original = state_fixture(astro)
                (self.root / "state.json").write_text(json.dumps(original))
                (self.root / "manifest.json").write_text(json.dumps(manifest_fixture()))
                self.assertEqual(self.run_reconcile(self.root), 0)
                state = json.loads((self.root / "state.json").read_text())
                manifest = json.loads((self.root / "manifest.json").read_text())
                self.assertEqual(state, {**original, "site_rev": 5})
                self.assertEqual(manifest["site_rev"], 5)
                self.assertEqual(manifest["entries"]["/"]["rev"], 2)
                self.assertEqual(manifest["entries"]["/"]["digest"], "sha256:" + "b" * 64)

    def test_bump_requires_state_before_any_write(self):
        before = (self.root / "manifest.json").read_bytes()
        with self.assertRaisesRegex(SystemExit, "requires --state"):
            self.run_reconcile(self.root, with_state=False)
        self.assertEqual((self.root / "manifest.json").read_bytes(), before)

    @unittest.skipIf(os.name == "nt", "POSIX file modes")
    def test_atomic_replacement_preserves_file_permissions(self):
        manifest_path = self.root / "manifest.json"
        state_path = self.root / "state.json"
        manifest_path.chmod(0o644)
        state_path.chmod(0o600)
        self.run_reconcile(self.root)
        self.assertEqual(stat.S_IMODE(manifest_path.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(state_path.stat().st_mode), 0o600)

    def test_mismatched_state_is_rejected_without_writes(self):
        for field, value in (("site_rev", 3), ("coverage", None), ("entries", {})):
            state = state_fixture()
            state[field] = value
            (self.root / "state.json").write_text(json.dumps(state))
            before = (self.root / "manifest.json").read_bytes()
            with self.subTest(field=field), self.assertRaisesRegex(SystemExit, "does not match"):
                self.run_reconcile(self.root)
            self.assertEqual((self.root / "manifest.json").read_bytes(), before)
            self.assertEqual(json.loads((self.root / "state.json").read_text()), state)

    def test_manifest_write_failure_does_not_lose_high_water_mark(self):
        write = self.tool.write_json_atomic

        def fail_manifest(path, value):
            if path.name == "manifest.json":
                raise OSError("simulated write failure")
            write(path, value)

        with patch.object(self.tool, "write_json_atomic", side_effect=fail_manifest):
            with self.assertRaises(OSError):
                self.run_reconcile(self.root)
        self.assertEqual(json.loads((self.root / "state.json").read_text())["site_rev"], 5)
        self.assertEqual(json.loads((self.root / "manifest.json").read_text())["site_rev"], 4)

    def test_state_write_failure_does_not_publish_new_revision(self):
        with patch.object(self.tool, "write_json_atomic", side_effect=OSError("state write failed")):
            with self.assertRaises(OSError):
                self.run_reconcile(self.root)
        self.assertEqual(json.loads((self.root / "manifest.json").read_text())["site_rev"], 4)


class DogfoodGuardTests(unittest.TestCase):
    def run_guard(self, committed, fresh_state=None, fresh_manifest=None):
        tool = load_tool("check_dogfood_manifest")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            manifest_path = root / "manifest.json"
            state_path.write_text(json.dumps(state_fixture()))
            manifest_path.write_text(json.dumps(committed))

            def generate(site, output, state):
                output.write_text(json.dumps(fresh_manifest or manifest_fixture()))
                state.write_text(json.dumps(fresh_state or state_fixture()))

            with (
                patch.object(tool, "COMMITTED_STATE", state_path),
                patch.object(tool, "COMMITTED_MANIFEST", manifest_path),
                patch.object(tool, "run_generator", side_effect=generate),
                redirect_stdout(io.StringIO()),
            ):
                return tool.main()

    def test_reconciled_or_removed_digest_is_allowed(self):
        for digest in (None, "sha256:" + "b" * 64):
            manifest = manifest_fixture()
            if digest is None:
                del manifest["entries"]["/"]["digest"]
            else:
                manifest["entries"]["/"]["digest"] = digest
            self.assertEqual(self.run_guard(manifest), 0)

    def test_source_hash_drift_is_detected_even_when_revisions_match(self):
        state = state_fixture()
        state["entries"]["/"]["digest"] = "d" * 64
        with self.assertRaisesRegex(SystemExit, "dogfood manifest drift"):
            self.run_guard(manifest_fixture(), fresh_state=state)

    def test_manifest_revision_coverage_and_url_drift_are_rejected(self):
        original = manifest_fixture()
        variants = []
        for field, value in (
            ("site_rev", 5),
            ("coverage", {"mode": "prefixes", "prefixes": ["/blog/"]}),
            ("entries", {}),
        ):
            variants.append({**original, field: value})
        changed_rev = copy.deepcopy(original)
        changed_rev["entries"]["/"]["rev"] = 3
        variants.append(changed_rev)
        for manifest in variants:
            with self.subTest(manifest=manifest), self.assertRaisesRegex(SystemExit, "dogfood manifest drift"):
                self.run_guard(manifest)

    def test_invalid_served_digest_is_rejected(self):
        manifest = manifest_fixture()
        manifest["entries"]["/"]["digest"] = "not a digest"
        with self.assertRaisesRegex(SystemExit, "invalid dogfood manifest"):
            self.run_guard(manifest)


if __name__ == "__main__":
    unittest.main()
