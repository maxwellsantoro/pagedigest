"""Exercise complete snapshots, conditional responses, audits and recovery."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from test_cache_persistence import cache_persistence as cache
from test_core import QueueSession, StubResponse

from pagedigest import check_site, diff


def digest(body):
    return "sha256:" + hashlib.sha256(body).hexdigest()


def manifest(entries=None, site_rev=7):
    return {
        "version": 1,
        "generated": "2026-09-16T12:00:00Z",
        "site_rev": site_rev,
        "coverage": {"mode": "complete"},
        "entries": entries or {"/a": {"rev": 3, "digest": digest(b"A")}},
    }


def response(doc):
    return StubResponse(200, json.dumps(doc).encode(), {"ETag": '"v7"'})


class ConsumerSafetyTests(unittest.TestCase):
    def test_equal_revision_missing_stale_and_decreased_local_entries(self):
        m = manifest({"/new": {"rev": 2}, "/stale": {"rev": 4}, "/backward": {"rev": 1}})
        d = diff(m, 7, {"/stale": 3, "/backward": 2})
        self.assertEqual(d["new"], ["/new"])
        self.assertEqual(d["changed"], ["/stale"])
        self.assertEqual(d["fallback_urls"], ["/backward"])

    def test_conditional_request_requires_manifest_and_304_plans_work(self):
        session = QueueSession([response(manifest())])
        check_site("https://example.com", 7, {}, etag='"v7"', session=session)
        self.assertNotIn("If-None-Match", session.requests[0][1]["headers"])
        session = QueueSession([StubResponse(304)])
        d = check_site("https://example.com", 7, {}, etag='"v7"', cached_manifest=manifest(), session=session)
        self.assertEqual(d["new"], ["/a"])
        self.assertTrue(d["not_modified"])
        session = QueueSession([StubResponse(304)])
        d = check_site("https://example.com", 7, {}, session=session)
        self.assertTrue(d["fallback"])

    def test_reused_revision_with_new_digest_refetches(self):
        old = manifest()
        new = manifest({"/a": {"rev": 3, "digest": digest(b"B")}})
        d = check_site("https://example.com", 7, {"/a": 3}, cached_manifest=old, session=QueueSession([response(new)]))
        self.assertEqual(d["changed"], ["/a"])

    def seed(self, root):
        state, pages = root / "state.json", root / "pages"
        session = QueueSession([response(manifest()), StubResponse(200, b"A")])
        self.assertEqual(cache.run_cycle("https://example.com", state, pages, session=session), 0)
        return state, pages

    def test_missing_or_corrupt_body_recovers_on_200_and_304(self):
        for status in (200, 304):
            for corrupt in (False, True):
                with self.subTest(status=status, corrupt=corrupt), tempfile.TemporaryDirectory() as tmp:
                    state, pages = self.seed(Path(tmp))
                    body = pages / cache.load_state(state)["pages"]["/a"]
                    if corrupt:
                        body.write_bytes(b"corrupted")
                    else:
                        body.unlink()
                    session = QueueSession(
                        [response(manifest()) if status == 200 else StubResponse(304), StubResponse(200, b"A")]
                    )
                    self.assertEqual(cache.run_cycle("https://example.com", state, pages, session=session), 0)
                    self.assertEqual(body.read_bytes(), b"A")
                    self.assertEqual(len(session.requests), 2)

    def test_audits_execute_after_304_and_mismatch_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            state, pages = self.seed(Path(tmp))
            session = QueueSession([StubResponse(304), StubResponse(200, b"wrong")])
            self.assertEqual(
                cache.run_cycle("https://example.com", state, pages, session=session, sample_audit_rate=1), 1
            )
            self.assertTrue(cache.load_state(state)["distrusted"])
            self.assertEqual(cache.load_state(state)["site_rev"], 7)
            session = QueueSession([StubResponse(304), StubResponse(200, b"A")])
            self.assertEqual(cache.run_cycle("https://example.com", state, pages, session=session), 0)
            self.assertFalse(cache.load_state(state)["distrusted"])
            session = QueueSession([StubResponse(304), StubResponse(200, b"A")])
            self.assertEqual(
                cache.run_cycle("https://example.com", state, pages, session=session, sample_audit_rate=1), 0
            )
            self.assertEqual(len(session.requests), 2)

    def test_inconclusive_audit_does_not_advance_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            state, pages = self.seed(Path(tmp))
            previous = state.read_bytes()
            session = QueueSession([StubResponse(304), StubResponse(503)])
            self.assertEqual(
                cache.run_cycle("https://example.com", state, pages, session=session, sample_audit_rate=1), 1
            )
            self.assertEqual(state.read_bytes(), previous)

    def test_failed_multi_page_cycle_preserves_previous_bodies(self):
        with tempfile.TemporaryDirectory() as tmp:
            state, pages = self.seed(Path(tmp))
            previous = state.read_bytes()
            old_body = pages / cache.load_state(state)["pages"]["/a"]
            m = manifest({"/a": {"rev": 4}, "/z": {"rev": 1}}, site_rev=8)
            session = QueueSession([response(m), StubResponse(200, b"B"), StubResponse(503)])
            self.assertEqual(cache.run_cycle("https://example.com", state, pages, session=session), 1)
            self.assertEqual(state.read_bytes(), previous)
            self.assertEqual(old_body.read_bytes(), b"A")

    def test_cache_cannot_be_reused_for_another_origin(self):
        with tempfile.TemporaryDirectory() as tmp:
            state, pages = self.seed(Path(tmp))
            with self.assertRaisesRegex(ValueError, "another origin"):
                cache.run_cycle("https://other.example", state, pages, session=QueueSession([]))
