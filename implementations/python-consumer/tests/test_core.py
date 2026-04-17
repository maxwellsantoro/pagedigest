import hashlib
import unittest
from typing import Any

from pagedigest.core import audit, check_site, diff, fetch


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

    def json(self) -> Any:
        if self._json_error is not None:
            raise self._json_error
        return self._json_data


class StubSession:
    def __init__(self, response: StubResponse):
        self._response = response

    def get(self, *args: Any, **kwargs: Any) -> StubResponse:
        return self._response


class CoreTests(unittest.TestCase):
    def test_fetch_rejects_unsupported_version(self) -> None:
        response = StubResponse(
            status_code=200,
            json_data={
                "version": 2,
                "generated": "2026-04-17T12:00:00Z",
                "site_rev": 1,
                "entries": {},
            },
        )
        out = fetch("https://example.com", session=StubSession(response))
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "unsupported-version")

    def test_fetch_handles_invalid_json(self) -> None:
        response = StubResponse(status_code=200, json_error=ValueError("bad json"))
        out = fetch("https://example.com", session=StubSession(response))
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "invalid-json")

    def test_fetch_handles_invalid_site_rev(self) -> None:
        response = StubResponse(
            status_code=200,
            json_data={
                "version": 1,
                "generated": "2026-04-17T12:00:00Z",
                "site_rev": "one",
                "entries": {},
            },
        )
        out = fetch("https://example.com", session=StubSession(response))
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "invalid-site-rev")

    def test_fetch_handles_missing_required_field(self) -> None:
        response = StubResponse(
            status_code=200,
            json_data={
                "version": 1,
                "generated": "2026-04-17T12:00:00Z",
                "site_rev": 1,
            },
        )
        out = fetch("https://example.com", session=StubSession(response))
        self.assertFalse(out.ok)
        self.assertEqual(out.error, "missing-entries")

    def test_fetch_returns_not_modified_signal(self) -> None:
        response = StubResponse(status_code=304, headers={"ETag": "abc"})
        out = fetch("https://example.com", session=StubSession(response))
        self.assertTrue(out.ok)
        self.assertEqual(out.status_code, 304)
        self.assertEqual(out.etag, "abc")

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
            json_data={
                "version": 1,
                "generated": "2026-04-17T12:00:00Z",
                "site_rev": 9,
                "entries": {
                    "/": {"rev": 3}
                },
            },
        )

        out = check_site(
            "https://example.com",
            cached_site_rev=10,
            cached_revs={"/": 3},
            session=StubSession(response),
        )
        self.assertTrue(out["fallback"])
        self.assertEqual(out["error"], "site-rev-decrease")

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
