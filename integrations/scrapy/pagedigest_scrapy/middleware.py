"""pagedigest consumer as a Scrapy downloader middleware.

Behavior per request to an origin that publishes a manifest:
  1. Ensure the origin's manifest is loaded (cached, TTL'd, size-capped).
  2. Attach the `PageDigest-State` cooperation header (we observed site_rev).
  3. If the URL is covered and its `rev` is unchanged since our last crawl,
     either skip it (IgnoreRequest) or -- with audit probability -- fetch it
     anyway and verify the publisher's digest.
  4. Anything unusable (no manifest / malformed / stale / distrusted origin)
     falls straight through to normal crawling. Never worse than no manifest.

The manifest is fetched with a short synchronous `requests` call and cached, to
keep this reference implementation legible. A high-throughput consumer would
prefetch manifests through the scheduler instead; the decision logic here is
unchanged by that.
"""
from __future__ import annotations

import hashlib
import random
import time
from urllib.parse import urlsplit

import requests
from scrapy import signals
from scrapy.exceptions import IgnoreRequest, NotConfigured

from . import header, manifest as M
from .store import Store, TRUSTED, SITE_DISTRUSTED

BOOTSTRAP_WINDOW_S = 3600  # first hour with an origin: audit harder (cold-start trust)


class PageDigestMiddleware:
    def __init__(self, settings, stats):
        if not settings.getbool("PAGEDIGEST_ENABLED", True):
            raise NotConfigured
        self.stats = stats
        self.store = Store(settings.get("PAGEDIGEST_STORE", "pagedigest_state.db"))
        self.audit_rate = settings.getfloat("PAGEDIGEST_AUDIT_RATE", 0.01)
        self.bootstrap_rate = settings.getfloat("PAGEDIGEST_BOOTSTRAP_AUDIT_RATE", 0.25)
        self.manifest_ttl = settings.getfloat("PAGEDIGEST_MANIFEST_TTL", 300.0)
        self.max_bytes = settings.getint("PAGEDIGEST_MAX_MANIFEST_BYTES", M.MAX_BYTES)
        self.send_header = settings.getbool("PAGEDIGEST_SEND_HEADER", True)
        self.site_distrust_threshold = settings.getint("PAGEDIGEST_SITE_DISTRUST_THRESHOLD", 3)
        self._session = requests.Session()
        self._cache = {}   # origin -> (Manifest|None, fetched_at)
        self._rng = random.Random(settings.getint("PAGEDIGEST_SEED", 0) or None)

    @classmethod
    def from_crawler(cls, crawler):
        mw = cls(crawler.settings, crawler.stats)
        crawler.signals.connect(mw.spider_closed, signal=signals.spider_closed)
        return mw

    # ---- request path ----
    def process_request(self, request, spider):
        if request.method != "GET" or request.meta.get("pagedigest_audit"):
            return None  # never intercept our own audit fetches
        parts = urlsplit(request.url)
        origin = f"{parts.scheme}://{parts.netloc}"
        path = parts.path or "/"
        if parts.query:
            path += "?" + parts.query

        man = self._manifest(origin)
        if man is None:
            return None  # fallback: no usable manifest

        if self.send_header:
            try:
                request.headers["PageDigest-State"] = header.build(man.site_rev, man.manifest_path)
            except ValueError:
                pass

        if not man.covers(path):
            return None
        entry = man.entry_for(path)
        if entry is None:
            return None  # covered prefix but not listed -> no protocol treatment

        if self.store.trust_state(origin) == SITE_DISTRUSTED:
            self.stats.inc_value("pagedigest/fallback_distrusted")
            return None  # earn trust back before we skip anything again

        cached_rev, cached_size = self.store.get_rev(origin, path)
        # stash for process_response regardless of branch
        request.meta["pagedigest"] = {"origin": origin, "path": path,
                                       "rev": entry.rev, "digest": entry.digest}

        changed = cached_rev is None or entry.rev != cached_rev
        if changed or self.store.is_url_suspect(origin, path):
            return None  # must fetch: new, changed, or under suspicion

        # unchanged & trusted -> skip, unless selected for audit
        if entry.digest and self._audit_now(origin):
            request.meta["pagedigest_audit"] = True
            request.headers["Accept-Encoding"] = "identity"  # spec 3.2: hash identity bytes
            self.stats.inc_value("pagedigest/audits")
            return None  # deliberately spend this request to verify honesty

        self._record_skip(origin, path, cached_size)
        raise IgnoreRequest(f"pagedigest: {path} unchanged at rev {entry.rev}")

    # ---- response path ----
    def process_response(self, request, response, spider):
        meta = request.meta.get("pagedigest")
        if not meta:
            return response

        if request.meta.get("pagedigest_audit") and meta["digest"]:
            got = "sha256:" + hashlib.sha256(response.body).hexdigest()
            if got != meta["digest"]:
                self._on_mismatch(meta["origin"], meta["path"])
            else:
                self.stats.inc_value("pagedigest/audit_ok")
                self.store.clear_url_suspect(meta["origin"], meta["path"])

        # record the freshly observed rev + size for next run's comparison
        self.store.set_rev(meta["origin"], meta["path"], meta["rev"], len(response.body))
        return response

    # ---- helpers ----
    def _manifest(self, origin):
        hit = self._cache.get(origin)
        if hit and (time.time() - hit[1]) < self.manifest_ttl:
            return hit[0]
        prev = self.store.get_site(origin)[0]
        raw = M.fetch(origin, session=self._session, max_bytes=self.max_bytes)
        man = M.parse(raw, prev) if raw is not None else None
        if man is not None:
            # a usable manifest with a decreased site_rev was already rejected in
            # parse(); persist the accepted site_rev for the next monotonic check.
            self.store.set_site(origin, man.site_rev)
            self.stats.inc_value("pagedigest/manifests_loaded")
        else:
            self.stats.inc_value("pagedigest/manifest_unusable")
        self._cache[origin] = (man, time.time())
        return man

    def _audit_now(self, origin) -> bool:
        first_seen = self.store.get_site(origin)[1] or time.time()
        rate = self.bootstrap_rate if (time.time() - first_seen) < BOOTSTRAP_WINDOW_S else self.audit_rate
        return self._rng.random() < rate

    def _on_mismatch(self, origin, path):
        # containment ladder (spec 5.2): URL-level first; escalate to site-level
        # only when mismatches span enough URLs.
        self.stats.inc_value("pagedigest/audit_mismatch")
        self.store.mark_url_suspect(origin, path)
        if self.store.count_url_suspects(origin) >= self.site_distrust_threshold:
            self.store.set_trust(origin, SITE_DISTRUSTED)
            self.stats.inc_value("pagedigest/site_distrusted")

    def spider_closed(self, spider):
        skipped = self.stats.get_value("pagedigest/skipped", 0)
        saved = self.stats.get_value("pagedigest/bytes_saved_est", 0)
        spider.logger.info(
            f"[pagedigest] skipped {skipped} unchanged fetches "
            f"(~{saved} bytes saved), audits={self.stats.get_value('pagedigest/audits',0)}, "
            f"mismatches={self.stats.get_value('pagedigest/audit_mismatch',0)}")
        self.store.close()

    # bytes-saved accounting lives here so IgnoreRequest stays a one-liner
    def _record_skip(self, origin, path, size):
        self.stats.inc_value("pagedigest/skipped")
        self.stats.inc_value("pagedigest/bytes_saved_est", size)
