from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

EXAMPLE = Path(__file__).parents[1] / "examples" / "cache_persistence.py"
SPEC = importlib.util.spec_from_file_location("cache_persistence", EXAMPLE)
assert SPEC is not None and SPEC.loader is not None
cache_persistence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cache_persistence)


class CachePersistenceTests(unittest.TestCase):
    def test_complete_coverage_replaces_revisions(self) -> None:
        manifest = {"coverage": {"mode": "complete"}, "entries": {"/new": {"rev": 3}}}
        self.assertEqual(cache_persistence.next_revs({"/old": 2}, manifest), {"/new": 3})

    def test_partial_coverage_preserves_unlisted_revisions(self) -> None:
        manifest = {"coverage": {"mode": "prefixes"}, "entries": {"/new": {"rev": 3}}}
        self.assertEqual(cache_persistence.next_revs({"/old": 2}, manifest), {"/old": 2, "/new": 3})

    def test_load_state_rejects_unsafe_page_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state_path.write_text(
                json.dumps({**cache_persistence.empty_state(), "pages": {"/": "../escape.body"}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "invalid page map"):
                cache_persistence.load_state(state_path)

    def test_failed_page_fetch_does_not_advance_state(self) -> None:
        decision = {
            "fallback": False,
            "not_modified": False,
            "new": ["/new"],
            "changed": [],
            "removed": [],
            "site_rev": 2,
            "etag": '"two"',
            "last_modified": None,
            "manifest": {
                "site_rev": 2,
                "coverage": {"mode": "complete"},
                "entries": {"/new": {"rev": 1}},
            },
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            cache_persistence.save_state(state_path, cache_persistence.empty_state())
            original = state_path.read_bytes()
            with (
                patch.object(cache_persistence, "check_site", return_value=decision),
                patch.object(cache_persistence, "fetch_page", side_effect=RuntimeError("offline")),
            ):
                result = cache_persistence.run_cycle("https://example.com", state_path, root / "pages")
            self.assertEqual(result, 1)
            self.assertEqual(state_path.read_bytes(), original)

    def test_successful_cycle_persists_only_after_body_fetch(self) -> None:
        decision = {
            "fallback": False,
            "not_modified": False,
            "new": ["/new"],
            "changed": [],
            "removed": [],
            "site_rev": 2,
            "etag": '"two"',
            "last_modified": "Fri, 03 Jul 2026 00:00:00 GMT",
            "manifest": {
                "site_rev": 2,
                "coverage": {"mode": "complete"},
                "entries": {"/new": {"rev": 1}},
            },
        }

        def fake_fetch(_session, _url, destination, **_kwargs):
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"new body")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            with (
                patch.object(cache_persistence, "check_site", return_value=decision),
                patch.object(cache_persistence, "fetch_page", side_effect=fake_fetch),
            ):
                result = cache_persistence.run_cycle("https://example.com", state_path, root / "pages")
            state = cache_persistence.load_state(state_path)
            self.assertEqual(result, 0)
            self.assertEqual(state["site_rev"], 2)
            self.assertEqual(state["revs"], {"/new": 1})
            self.assertTrue((root / "pages" / state["pages"]["/new"]).is_file())


if __name__ == "__main__":
    unittest.main()
