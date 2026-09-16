"""Deterministic, reactor-free tests of the consumer decision logic.

Drives process_request / process_response directly with in-memory manifests, so
every protocol branch is checked without network or Scrapy's reactor.
"""

import hashlib
import json
import os
import sys
import tempfile

from scrapy.http import Request, Response
from scrapy.settings import Settings
from scrapy.exceptions import IgnoreRequest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pagedigest_scrapy import middleware as mw  # noqa: E402
from pagedigest_scrapy.middleware import PageDigestMiddleware  # noqa: E402

ORIGIN = "http://ex.test"


class Stats:
    def __init__(self):
        self.d = {}

    def inc_value(self, k, n=1):
        self.d[k] = self.d.get(k, 0) + n

    def get_value(self, k, default=0):
        return self.d.get(k, default)


def manifest_bytes(site_rev, entries, coverage=None):
    doc = {
        "version": 1,
        "generated": "2025-10-16T10:00:00Z",
        "site_rev": site_rev,
        "entries": entries,
    }
    if coverage:
        doc["coverage"] = coverage
    return json.dumps(doc).encode()


def make_mw(tmp, **over):
    s = Settings(
        {
            "PAGEDIGEST_STORE": tmp,
            "PAGEDIGEST_MANIFEST_TTL": 0.0,
            "PAGEDIGEST_AUDIT_RATE": 0.0,
            "PAGEDIGEST_BOOTSTRAP_AUDIT_RATE": 0.0,
        }
    )
    for k, v in over.items():
        s.set(k.upper(), v)
    return PageDigestMiddleware(s, Stats())


def req(path="/a"):
    return Request(ORIGIN + path)


def resp(request, body=b"hello"):
    return Response(request.url, body=body, request=request)


def set_manifest(raw):
    mw.M.fetch = lambda *a, **k: raw


def run(check):
    with tempfile.TemporaryDirectory() as d:
        check(os.path.join(d, "s.db"))


def test_fallback_no_manifest():
    def c(db):
        set_manifest(None)
        m = make_mw(db)
        assert m.process_request(req(), None) is None
        assert m.stats.get_value("pagedigest/manifest_unusable") == 1

    run(c)
    print("ok: fallback when no manifest")


def test_first_contact_then_skip():
    def c(db):
        set_manifest(manifest_bytes(10, {"/a": {"rev": 3}}))
        m = make_mw(db)
        r = req("/a")
        # first contact: no cached rev -> must fetch (None)
        assert m.process_request(r, None) is None
        # cooperation header present and correct
        assert (
            r.headers.get("PageDigest-State")
            == b'site_rev=10; manifest="/.well-known/pagedigest.json"'
        )
        m.process_response(r, resp(r), None)  # records rev 3
        # second run, unchanged -> skip
        r2 = req("/a")
        try:
            m.process_request(r2, None)
            assert False, "expected IgnoreRequest"
        except IgnoreRequest:
            pass
        assert m.stats.get_value("pagedigest/skipped") == 1

    run(c)
    print("ok: first contact fetches, unchanged run skips")


def test_changed_refetch():
    def c(db):
        set_manifest(manifest_bytes(10, {"/a": {"rev": 3}}))
        m = make_mw(db)
        r = req("/a")
        m.process_request(r, None)
        m.process_response(r, resp(r), None)
        # publisher bumps rev -> must refetch
        set_manifest(manifest_bytes(11, {"/a": {"rev": 4}}))
        assert m.process_request(req("/a"), None) is None
        assert m.stats.get_value("pagedigest/skipped", 0) == 0

    run(c)
    print("ok: bumped rev forces refetch")


def test_rev_decrease_keeps_high_water():
    def c(db):
        set_manifest(manifest_bytes(10, {"/a": {"rev": 3}}))
        m = make_mw(db)
        r = req("/a")
        m.process_request(r, None)
        m.process_response(r, resp(r), None)
        cached_rev, _ = m.store.get_rev(ORIGIN, "/a")
        assert cached_rev == 3
        # publisher lowers rev -> fetch, but do not store the lower value
        set_manifest(manifest_bytes(11, {"/a": {"rev": 1}}))
        r2 = req("/a")
        assert m.process_request(r2, None) is None
        assert r2.meta["pagedigest"].get("rev_anomaly") is True
        m.process_response(r2, resp(r2), None)
        cached_after, _ = m.store.get_rev(ORIGIN, "/a")
        assert cached_after == 3
        assert m.stats.get_value("pagedigest/rev_decrease") == 1

    run(c)
    print("ok: rev decrease keeps high-water mark")


def test_monotonicity_fallback():
    def c(db):
        set_manifest(manifest_bytes(10, {"/a": {"rev": 3}}))
        m = make_mw(db)
        r = req("/a")
        m.process_request(r, None)
        m.process_response(r, resp(r), None)
        # site_rev decreases -> anomalous -> whole-site fallback
        set_manifest(manifest_bytes(9, {"/a": {"rev": 3}}))
        assert m.process_request(req("/a"), None) is None
        assert m.stats.get_value("pagedigest/manifest_unusable") >= 1

    run(c)
    print("ok: site_rev decrease triggers fallback")


def test_coverage_prefixes():
    def c(db):
        raw = manifest_bytes(
            10,
            {"/blog/x": {"rev": 1}},
            coverage={"mode": "prefixes", "prefixes": ["/blog/"]},
        )
        set_manifest(raw)
        m = make_mw(db)
        # /about is outside coverage -> no protocol treatment (fetch normally)
        assert m.process_request(req("/about"), None) is None

    run(c)
    print("ok: out-of-coverage URL is left alone")


def test_audit_detects_dishonest_digest():
    def c(db):
        body = b"the real content"
        honest = "sha256:" + hashlib.sha256(body).hexdigest()
        wrong = "sha256:" + "0" * 64
        # publisher lies: claims a digest that won't match the served bytes
        set_manifest(manifest_bytes(10, {"/a": {"rev": 3, "digest": wrong}}))
        m = make_mw(
            db, pagedigest_bootstrap_audit_rate=1.0
        )  # audit every skip-eligible hit
        r = req("/a")
        m.process_request(r, None)
        m.process_response(r, resp(r, body), None)
        # unchanged -> would skip, but audit forces a real fetch instead
        r2 = req("/a")
        assert m.process_request(r2, None) is None
        assert r2.meta.get("pagedigest_audit") is True
        assert r2.headers.get("Accept-Encoding") == b"identity"
        m.process_response(r2, resp(r2, body), None)
        assert m.stats.get_value("pagedigest/audit_mismatch") == 1
        assert m.store.is_url_suspect(ORIGIN, "/a")

    run(c)
    print("ok: digest audit catches a dishonest manifest")


def test_site_distrust_escalation():
    def c(db):
        wrong = "sha256:" + "0" * 64
        entries = {f"/p{i}": {"rev": 1, "digest": wrong} for i in range(3)}
        set_manifest(manifest_bytes(10, entries))
        m = make_mw(
            db,
            pagedigest_bootstrap_audit_rate=1.0,
            pagedigest_site_distrust_threshold=3,
        )
        for i in range(3):
            p = f"/p{i}"
            r = req(p)
            m.process_request(r, None)
            m.process_response(r, resp(r, b"x"), None)
            r2 = req(p)
            m.process_request(r2, None)
            m.process_response(r2, resp(r2, b"x"), None)
        assert m.store.trust_state(ORIGIN) == "site_distrusted"
        # once distrusted, an unchanged URL is no longer skipped
        set_manifest(manifest_bytes(10, {"/p0": {"rev": 1}}))
        assert m.process_request(req("/p0"), None) is None

    run(c)
    print("ok: repeated mismatches escalate to site distrust + fallback")


def test_http_errors_do_not_cache_revisions_or_block_retries():
    for status in (301, 404, 429, 500, 503):
        for previous_rev in (None, 2):
            m = make_mw(":memory:")
            set_manifest(manifest_bytes(10, {"/a": {"rev": 3}}))
            if previous_rev is not None:
                m.store.set_rev(ORIGIN, "/a", previous_rev)
            r = req()
            m.process_request(r, None)
            m.process_response(
                r, Response(r.url, status=status, body=b"error", request=r), None
            )
            assert m.store.get_rev(ORIGIN, "/a")[0] == previous_rev
            retry = r.copy()
            assert m.process_request(retry, None) is None
            m.process_response(retry, resp(retry), None)
            assert m.store.get_rev(ORIGIN, "/a")[0] == 3
            try:
                m.process_request(req(), None)
                assert False, "successful retry should establish revision"
            except IgnoreRequest:
                pass
            m.store.close()
    print("ok: HTTP failures leave revisions unchanged and retries fetch")


def test_audit_http_errors_are_inconclusive():
    for status in (301, 404, 429, 500):
        m = make_mw(":memory:", pagedigest_bootstrap_audit_rate=1.0)
        set_manifest(
            manifest_bytes(10, {"/a": {"rev": 3, "digest": "sha256:" + "0" * 64}})
        )
        m.store.set_rev(ORIGIN, "/a", 3, 100)
        r = req()
        m.process_request(r, None)
        assert r.meta["dont_redirect"]
        m.process_response(
            r, Response(r.url, status=status, body=b"error", request=r), None
        )
        assert m.stats.get_value("pagedigest/audit_inconclusive") == 1
        assert m.stats.get_value("pagedigest/audit_mismatch", 0) == 0
        assert not m.store.is_url_suspect(ORIGIN, "/a")
        assert m.store.get_rev(ORIGIN, "/a") == (3, 100)
        m.store.close()
    print("ok: audit redirects and errors are inconclusive")


def test_suspect_url_recovers_from_clean_forced_fetch():
    m = make_mw(":memory:", pagedigest_bootstrap_audit_rate=1.0)
    digest = "sha256:" + hashlib.sha256(b"good").hexdigest()
    set_manifest(manifest_bytes(10, {"/a": {"rev": 3, "digest": digest}}))
    m.store.set_rev(ORIGIN, "/a", 3)
    r = req()
    m.process_request(r, None)
    m.process_response(r, resp(r, b"bad"), None)
    assert m.store.is_url_suspect(ORIGIN, "/a")
    m.bootstrap_rate = 0.0
    r = req()
    m.process_request(r, None)
    assert r.meta["pagedigest_audit"]  # recovery does not depend on sample rate
    m.process_response(r, resp(r, b"good"), None)
    assert not m.store.is_url_suspect(ORIGIN, "/a")
    try:
        m.process_request(req(), None)
        assert False, "recovered URL should skip"
    except IgnoreRequest:
        pass
    m.store.close()
    print("ok: suspect URL recovers through a clean forced fetch")


def test_site_recovers_only_after_all_suspect_urls_pass():
    m = make_mw(
        ":memory:",
        pagedigest_bootstrap_audit_rate=1.0,
        pagedigest_site_distrust_threshold=2,
    )
    digest = "sha256:" + hashlib.sha256(b"good").hexdigest()
    set_manifest(
        manifest_bytes(10, {p: {"rev": 3, "digest": digest} for p in ("/a", "/b")})
    )
    for p in ("/a", "/b"):
        m.store.set_rev(ORIGIN, p, 3)
        r = req(p)
        m.process_request(r, None)
        m.process_response(r, resp(r, b"bad"), None)
    assert m.store.trust_state(ORIGIN) == "site_distrusted"
    m.bootstrap_rate = 0.0
    for p in ("/a", "/b"):
        r = req(p)
        m.process_request(r, None)
        assert r.meta["pagedigest_audit"]
        m.process_response(r, resp(r, b"good"), None)
        assert m.store.trust_state(ORIGIN) == (
            "site_distrusted" if p == "/a" else "trusted"
        )
    assert m.stats.get_value("pagedigest/site_recovered") == 1
    m.store.close()
    print("ok: site recovers after every suspect URL passes an audit")


def test_recovery_without_digest_keeps_fetching():
    m = make_mw(":memory:")
    set_manifest(manifest_bytes(10, {"/a": {"rev": 3}}))
    m.store.set_rev(ORIGIN, "/a", 3)
    m.store.mark_url_suspect(ORIGIN, "/a")
    for _ in range(2):
        r = req()
        assert m.process_request(r, None) is None
        m.process_response(r, resp(r), None)
        assert m.store.is_url_suspect(ORIGIN, "/a")
    m.store.close()
    print("ok: missing digest cannot clear suspicion")


def test_redirect_metadata_does_not_record_original_revision():
    m = make_mw(":memory:")
    set_manifest(manifest_bytes(10, {"/a": {"rev": 3}}))
    r = req()
    m.process_request(r, None)
    redirected = r.replace(url=ORIGIN + "/unlisted")
    m.process_request(redirected, None)
    m.process_response(redirected, resp(redirected), None)
    assert m.store.get_rev(ORIGIN, "/a")[0] is None
    m.store.close()
    print("ok: redirects do not carry stale revision metadata")


def test_unlisted_redirect_clears_cooperation_header():
    m = make_mw(":memory:")
    set_manifest(manifest_bytes(17, {}))
    r = req("/unlisted")
    m.process_request(r, None)
    assert r.headers.get("PageDigest-State")
    assert "pagedigest" not in r.meta
    set_manifest(None)
    redirected = r.replace(url="https://other.test/unlisted")
    m.process_request(redirected, None)
    assert "PageDigest-State" not in redirected.headers
    assert "pagedigest_state_header" not in redirected.meta
    m.store.close()
    print("ok: unlisted redirects clear origin-specific cooperation headers")


def test_large_revisions_and_deep_json_fall_back():
    for raw in (
        manifest_bytes(2**63, {"/a": {"rev": 1}}),
        manifest_bytes(1, {"/a": {"rev": 2**63}}),
        b"[" * 100_000 + b"0" + b"]" * 100_000,
    ):
        m = make_mw(":memory:")
        set_manifest(raw)
        r = req()
        assert m.process_request(r, None) is None
        m.process_response(r, resp(r), None)
        assert "PageDigest-State" not in r.headers
        assert m.store.get_site(ORIGIN)[0] is None
        assert m.store.get_rev(ORIGIN, "/a")[0] is None
        assert m.stats.get_value("pagedigest/manifest_unusable") == 1
        m.store.close()
    # The largest supported value must still persist and skip correctly.
    m = make_mw(":memory:")
    set_manifest(manifest_bytes(2**63 - 1, {"/a": {"rev": 2**63 - 1}}))
    r = req()
    m.process_request(r, None)
    m.process_response(r, resp(r), None)
    assert m.store.get_site(ORIGIN)[0] == 2**63 - 1
    assert m.store.get_rev(ORIGIN, "/a")[0] == 2**63 - 1
    try:
        m.process_request(req(), None)
    except IgnoreRequest:
        pass
    else:
        raise AssertionError("unchanged maximum revision should skip")
    m.store.close()
    print("ok: unsupported revisions and decoder depth fall back safely")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nall offline tests passed")
