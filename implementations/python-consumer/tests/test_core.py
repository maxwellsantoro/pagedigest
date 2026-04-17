import hashlib
import unittest
from typing import Any

from pagedigest.core import audit, diff


class StubResponse:
    def __init__(self, status_code: int, content: bytes = b"", headers: dict[str, str] | None = None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


class StubSession:
    def __init__(self, response: StubResponse):
        self._response = response

    def get(self, *args: Any, **kwargs: Any) -> StubResponse:
        return self._response


class CoreTests(unittest.TestCase):
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
