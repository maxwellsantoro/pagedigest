import hashlib
import importlib.util
import json
import random
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from pagedigest.core import audit, check_site, diff, fetch, manifest_url, resolve_url_key, validate_manifest

ROOT = Path(__file__).resolve().parents[3]


def load_tool(name: str) -> Any:
    path = ROOT / "tools" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class StubResponse:
    def __init__(
        self,
        status_code: int,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
        json_data: Any | None = None,
        json_error: Exception | None = None,
    ):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self._json_data = json_data
        self._json_error = json_error
        self.closed = False

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._json_data

    def iter_content(self, chunk_size: int = 65536) -> Any:
        del chunk_size
        if self.content:
            yield self.content

    def close(self) -> None:
        self.closed = True


class StubSession:
    def __init__(self, response: StubResponse):
        self._response = response
        self.last_url: str | None = None

    def get(self, *args: Any, **kwargs: Any) -> StubResponse:
        if args:
            self.last_url = args[0]
        return self._response


def valid_manifest(**overrides: Any) -> dict[str, Any]:
    manifest = {
        "version": 1,
        "generated": "2026-04-17T12:00:00Z",
        "site_rev": 1,
        "entries": {
            "/": {"rev": 1},
        },
    }
    manifest.update(overrides)
    return manifest


class CoreTests(unittest.TestCase):
    def test_fetch_rejects_unsupported_version(self) -> None:
        response = StubResponse(
            status_code=200,
            content=json.dumps(valid_manifest(version=2)).encode("utf-8"),
        )
        out = fetch("https://example.com", session=StubSession(response))
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "unsupported-version")

    def test_manifest_url_uses_origin_root_for_pathful_base_url(self) -> None:
        self.assertEqual(
            manifest_url("https://example.com/blog/page"),
            "https://example.com/.well-known/pagedigest.json",
        )

    def test_fetch_uses_origin_root_for_pathful_base_url(self) -> None:
        response = StubResponse(
            status_code=200,
            content=json.dumps(valid_manifest()).encode("utf-8"),
        )
        session = StubSession(response)
        out = fetch("https://example.com/blog/page", session=session)
        self.assertTrue(out.ok)
        self.assertEqual(session.last_url, "https://example.com/.well-known/pagedigest.json")

    def test_fetch_rejects_invalid_base_url(self) -> None:
        out = fetch("not-a-url")
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "invalid-base-url")

    def test_fetch_handles_invalid_json(self) -> None:
        response = StubResponse(status_code=200, content=b"not-json")
        out = fetch("https://example.com", session=StubSession(response))
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "invalid-json")

    def test_fetch_handles_invalid_site_rev(self) -> None:
        response = StubResponse(
            status_code=200,
            content=json.dumps(valid_manifest(site_rev="one")).encode("utf-8"),
        )
        out = fetch("https://example.com", session=StubSession(response))
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "invalid-site-rev")

    def test_fetch_rejects_boolean_site_rev(self) -> None:
        response = StubResponse(
            status_code=200,
            content=json.dumps(valid_manifest(site_rev=True)).encode("utf-8"),
        )
        out = fetch("https://example.com", session=StubSession(response))
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "invalid-site-rev")

    def test_validate_manifest_accepts_fractional_utc_timestamp(self) -> None:
        manifest = valid_manifest(generated="2026-04-17T12:00:00.123456Z")
        self.assertIsNone(validate_manifest(manifest))

    def test_validate_manifest_accepts_explicit_utc_offset(self) -> None:
        manifest = valid_manifest(generated="2026-04-17T12:00:00+00:00")
        self.assertIsNone(validate_manifest(manifest))

    def test_validate_manifest_rejects_invalid_calendar_timestamp(self) -> None:
        manifest = valid_manifest(generated="2026-02-30T12:00:00Z")
        self.assertEqual(validate_manifest(manifest), "invalid-generated")

    def test_fetch_handles_missing_required_field(self) -> None:
        response = StubResponse(
            status_code=200,
            content=json.dumps(
                {
                    "version": 1,
                    "generated": "2026-04-17T12:00:00Z",
                    "site_rev": 1,
                }
            ).encode("utf-8"),
        )
        out = fetch("https://example.com", session=StubSession(response))
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "missing-entries")

    def test_fetch_rejects_fragment_url_key(self) -> None:
        response = StubResponse(
            status_code=200,
            content=json.dumps(valid_manifest(entries={"/docs#section": {"rev": 1}})).encode("utf-8"),
        )
        out = fetch("https://example.com", session=StubSession(response))
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "invalid-url-key-pattern")

    def test_fetch_rejects_unencoded_space_in_url_key(self) -> None:
        response = StubResponse(
            status_code=200,
            content=json.dumps(valid_manifest(entries={"/posts/hello world": {"rev": 1}})).encode("utf-8"),
        )
        out = fetch("https://example.com", session=StubSession(response))
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "invalid-url-key-space")

    def test_fetch_rejects_invalid_entry_rev(self) -> None:
        response = StubResponse(
            status_code=200,
            content=json.dumps(valid_manifest(entries={"/": {"rev": "1"}})).encode("utf-8"),
        )
        out = fetch("https://example.com", session=StubSession(response))
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "invalid-rev")

    def test_fetch_rejects_boolean_entry_rev(self) -> None:
        response = StubResponse(
            status_code=200,
            content=json.dumps(valid_manifest(entries={"/": {"rev": True}})).encode("utf-8"),
        )
        out = fetch("https://example.com", session=StubSession(response))
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "invalid-rev")

    def test_fetch_rejects_invalid_digest(self) -> None:
        response = StubResponse(
            status_code=200,
            content=json.dumps(valid_manifest(entries={"/": {"rev": 1, "digest": "sha256:deadbeef"}})).encode("utf-8"),
        )
        out = fetch("https://example.com", session=StubSession(response))
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "invalid-digest")

    def test_fetch_rejects_invalid_coverage_mode(self) -> None:
        response = StubResponse(
            status_code=200,
            content=json.dumps(valid_manifest(coverage={"mode": "everything"})).encode("utf-8"),
        )
        out = fetch("https://example.com", session=StubSession(response))
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "invalid-coverage-mode")

    def test_fetch_rejects_oversized_manifest(self) -> None:
        response = StubResponse(
            status_code=200,
            content=b"x" * 32,
            headers={"Content-Length": "64"},
        )
        out = fetch("https://example.com", session=StubSession(response), max_bytes=32)
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "manifest-too-large")

    def test_fetch_rejects_manifest_body_exceeding_limit(self) -> None:
        response = StubResponse(status_code=200, content=b"x" * 40)
        out = fetch("https://example.com", session=StubSession(response), max_bytes=32)
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "manifest-too-large")
        self.assertTrue(response.closed)

    def test_fetch_returns_not_modified_signal(self) -> None:
        response = StubResponse(status_code=304, headers={"ETag": "abc"})
        out = fetch("https://example.com", session=StubSession(response))
        self.assertTrue(out.ok)
        self.assertEqual(out.status_code, 304)
        self.assertEqual(out.etag, "abc")

    def test_validate_manifest_accepts_url_key_variants(self) -> None:
        manifest = valid_manifest(
            entries={
                "/about": {"rev": 1},
                "/about/": {"rev": 1},
                "/pricing?region=us": {"rev": 1},
                "/posts/hello%20world": {"rev": 1},
            }
        )
        self.assertIsNone(validate_manifest(manifest))

    def test_resolve_url_key_keeps_valid_key_on_origin(self) -> None:
        self.assertEqual(
            resolve_url_key("https://example.com/base", "/pricing?region=us"),
            "https://example.com/pricing?region=us",
        )

    def test_resolve_url_key_rejects_origin_escape(self) -> None:
        with self.assertRaisesRegex(ValueError, "url-key-origin-escape"):
            resolve_url_key("https://example.com", "//127.0.0.1/admin")

    def test_audit_does_not_request_embedded_absolute_url(self) -> None:
        session = StubSession(StubResponse(status_code=200, content=b"internal"))
        out = audit(
            "https://example.com",
            "/http://127.0.0.1:8000/admin",
            "sha256:" + "0" * 64,
            session=session,
        )
        self.assertEqual(session.last_url, "https://example.com/http://127.0.0.1:8000/admin")
        self.assertEqual(out["result"], "mismatch")

    def test_verifier_keeps_embedded_absolute_url_on_origin(self) -> None:
        verifier = load_tool("verify_over_wire_digests")
        response = StubResponse(status_code=200, content=b"publisher path")
        with patch.object(verifier.requests, "get", return_value=response) as request:
            verifier.audit_entry("https://example.com", "/http://127.0.0.1/admin", "sha256:" + "0" * 64, 10)
        self.assertEqual(request.call_args.args[0], "https://example.com/http://127.0.0.1/admin")

    def test_verifier_manifest_url_uses_origin_root_for_pathful_base_url(self) -> None:
        verifier = load_tool("verify_over_wire_digests")
        self.assertEqual(
            verifier.build_manifest_url("https://example.com/blog/page", None),
            "https://example.com/.well-known/pagedigest.json",
        )

    def test_reconciler_rejects_scheme_relative_origin_escape(self) -> None:
        reconciler = load_tool("reconcile_served_digests")
        with patch.object(reconciler.requests, "get") as request:
            digest, error = reconciler.fetch_identity_digest("https://example.com", "//127.0.0.1/admin", 10)
        self.assertIsNone(digest)
        self.assertEqual(error, "url-key-origin-escape")
        request.assert_not_called()

    def test_diff_detects_changed_and_new_urls(self) -> None:
        manifest = {
            "version": 1,
            "generated": "2026-04-17T12:00:00Z",
            "site_rev": 11,
            "entries": {
                "/": {"rev": 3},
                "/new": {"rev": 1},
                "/same": {"rev": 2},
            },
            "coverage": {"mode": "complete"},
        }

        result = diff(manifest, cached_site_rev=10, cached_revs={"/": 2, "/same": 2, "/old": 1})
        self.assertEqual(result["changed"], ["/"])
        self.assertEqual(result["new"], ["/new"])
        self.assertEqual(result["unchanged"], ["/same"])
        self.assertEqual(result["removed"], ["/old"])

    def test_diff_flags_site_rev_decrease(self) -> None:
        manifest = {
            "version": 1,
            "generated": "2026-04-17T12:00:00Z",
            "site_rev": 9,
            "entries": {
                "/": {"rev": 3},
            },
        }

        result = diff(manifest, cached_site_rev=10, cached_revs={"/": 3})
        self.assertEqual(result.get("site_anomaly"), "site-rev-decrease")
        self.assertEqual(result["changed"], [])

    def test_check_site_falls_back_on_site_rev_decrease(self) -> None:
        response = StubResponse(
            status_code=200,
            content=json.dumps(
                {
                    "version": 1,
                    "generated": "2026-04-17T12:00:00Z",
                    "site_rev": 9,
                    "entries": {"/": {"rev": 3}},
                }
            ).encode("utf-8"),
        )

        out = check_site(
            "https://example.com",
            cached_site_rev=10,
            cached_revs={"/": 3},
            session=StubSession(response),
        )
        self.assertTrue(out["fallback"])
        self.assertEqual(out["error"], "site-rev-decrease")

    def test_check_site_falls_back_on_entry_rev_decrease(self) -> None:
        response = StubResponse(
            status_code=200,
            content=json.dumps(
                {
                    "version": 1,
                    "generated": "2026-04-17T12:00:00Z",
                    "site_rev": 11,
                    "entries": {"/": {"rev": 2}},
                }
            ).encode("utf-8"),
        )

        out = check_site(
            "https://example.com",
            cached_site_rev=10,
            cached_revs={"/": 3},
            session=StubSession(response),
        )
        self.assertTrue(out["fallback"])
        self.assertEqual(out["error"], "manifest-anomaly")
        self.assertEqual(out["anomalies"][0]["reason"], "rev-decrease")

    def test_check_site_samples_audit_candidates_from_unchanged_entries(self) -> None:
        digest = "sha256:" + ("a" * 64)
        response = StubResponse(
            status_code=200,
            content=json.dumps(
                {
                    "version": 1,
                    "generated": "2026-04-17T12:00:00Z",
                    "site_rev": 11,
                    "entries": {
                        "/changed": {"rev": 2},
                        "/unchanged": {"rev": 3, "digest": digest},
                    },
                }
            ).encode("utf-8"),
        )

        out = check_site(
            "https://example.com",
            cached_site_rev=10,
            cached_revs={"/changed": 1, "/unchanged": 3},
            sample_audit_rate=1.0,
            session=StubSession(response),
            rng=random.Random(0),
        )
        self.assertFalse(out["fallback"])
        self.assertEqual(out["changed"], ["/changed"])
        self.assertEqual(out["audit_candidates"], [{"url": "/unchanged", "digest": digest}])

    def test_audit_match(self) -> None:
        body = b"audit match body\n"
        expected = "sha256:" + hashlib.sha256(body).hexdigest()
        response = StubResponse(status_code=200, content=body)

        out = audit("https://example.com", "/audit", expected, session=StubSession(response))
        self.assertEqual(out["result"], "match")

    def test_audit_redirect_is_inconclusive(self) -> None:
        response = StubResponse(status_code=302, content=b"redirect")
        out = audit(
            "https://example.com",
            "/audit",
            "sha256:deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
            session=StubSession(response),
        )
        self.assertEqual(out["result"], "inconclusive")
        self.assertEqual(out["reason"], "redirect")


if __name__ == "__main__":
    unittest.main()
