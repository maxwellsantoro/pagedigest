"""pagedigest consumer as a Scrapy downloader middleware.

Behavior per request to an origin that publishes a manifest:
  1. Ensure the origin's manifest is loaded (cached, TTL'd, size-capped).
  2. Attach the `PageDigest-State` cooperation header (we observed site_rev).
  3. If the URL is covered and its `rev` is unchanged since our last crawl,
     either replay its cached response or -- with audit probability -- fetch it
     anyway and verify the publisher's digest.
  4. Anything unusable (no manifest / malformed / stale / distrusted origin)
     falls straight through to normal crawling. Cached responses preserve ordinary spider callbacks and traversal.

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
from scrapy.exceptions import NotConfigured
from scrapy.http import Headers
from scrapy.responsetypes import responsetypes

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
        self.max_cache_bytes = settings.getint("PAGEDIGEST_MAX_CACHE_BYTES", 10 * 1024 * 1024)
        self.send_header = settings.getbool("PAGEDIGEST_SEND_HEADER", True)
        self.site_distrust_threshold = settings.getint(
            "PAGEDIGEST_SITE_DISTRUST_THRESHOLD", 3
        )
        self._session = requests.Session()
        self._cache = {}  # origin -> (Manifest|None, fetched_at)
        self._rng = random.Random(settings.getint("PAGEDIGEST_SEED", 0) or None)

    @classmethod
    def from_crawler(cls, crawler):
        mw = cls(crawler.settings, crawler.stats)
        crawler.signals.connect(mw.spider_closed, signal=signals.spider_closed)
        return mw

    # ---- request path ----
    def process_request(self, request, spider):
        # Redirects and retries copy metadata; decide again for this request URL.
        request.meta.pop("pagedigest", None)
        if request.meta.pop("pagedigest_state_header", False):
            request.headers.pop("PageDigest-State", None)
        request.meta.pop("pagedigest_audit", None)
        if request.method != "GET" or request.headers.get("Authorization") or request.headers.get("Cookie"):
            return None
        if request.headers.get("Range"):
            return None
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
                request.headers["PageDigest-State"] = header.build(
                    man.site_rev, man.manifest_path
                )
                request.meta["pagedigest_state_header"] = True
            except ValueError:
                pass

        if not man.covers(path):
            return None
        entry = man.entry_for(path)
        if entry is None:
            return None  # covered prefix but not listed -> no protocol treatment

        distrusted = self.store.trust_state(origin) == SITE_DISTRUSTED
        if distrusted:
            self.stats.inc_value("pagedigest/fallback_distrusted")

        cached_rev, cached_size = self.store.get_rev(origin, path)
        # stash for process_response regardless of branch
        request.meta["pagedigest"] = {
            "origin": origin,
            "path": path,
            "rev": entry.rev,
            "digest": entry.digest,
        }

        # SPEC §5.1: per-URL rev decrease is anomalous — fetch conventionally
        # and do not rewrite the stored high-water mark downward.
        if cached_rev is not None and entry.rev < cached_rev:
            request.meta["pagedigest"]["rev_anomaly"] = True
            self.stats.inc_value("pagedigest/rev_decrease")
            return None

        changed = cached_rev is None or entry.rev > cached_rev
        recovering = distrusted or self.store.is_url_suspect(origin, path)
        if changed and not recovering:
            return None  # must fetch new or changed content

        # unchanged & trusted -> skip, unless selected for audit
        if entry.digest and (recovering or self._audit_now(origin)):
            request.meta["pagedigest_audit"] = True
            # Audit the listed URL, never a redirect target's body.
            request.meta["dont_redirect"] = True
            request.headers["Accept-Encoding"] = (
                "identity"  # spec 3.2: hash identity bytes
            )
            self.stats.inc_value("pagedigest/audits")
            return None  # deliberately spend this request to verify honesty

        if recovering:
            return None  # no digest available to re-establish trust

        cached = self.store.get_response(origin, path)
        if cached is None or (entry.digest and entry.digest != cached[2]):
            return None  # metadata without usable matching bytes never permits reuse
        body, headers, _ = cached
        headers = Headers(headers)
        response_type = responsetypes.from_args(headers=headers, url=request.url, body=body)
        self._record_skip(origin, path, cached_size)
        return response_type(request.url, status=200, headers=headers, body=body,
                             request=request, flags=["pagedigest_cached"])


    # ---- response path ----
    def process_response(self, request, response, spider):
        if "pagedigest_cached" in response.flags:
            return response
        meta = request.meta.get("pagedigest")
        if not meta:
            return response

        if response.status < 200 or response.status >= 300:
            if request.meta.get("pagedigest_audit"):
                self.stats.inc_value("pagedigest/audit_inconclusive")
            return response  # failed fetches cannot establish a cached revision

        if request.meta.get("pagedigest_audit") and meta["digest"]:
            got = "sha256:" + hashlib.sha256(response.body).hexdigest()
            if got != meta["digest"]:
                self._on_mismatch(meta["origin"], meta["path"])
                return response
            else:
                self.stats.inc_value("pagedigest/audit_ok")
                self.store.clear_url_suspect(meta["origin"], meta["path"])
                if (
                    self.store.trust_state(meta["origin"]) == SITE_DISTRUSTED
                    and self.store.count_url_suspects(meta["origin"]) == 0
                ):
                    self.store.set_trust(meta["origin"], TRUSTED)
                    self.stats.inc_value("pagedigest/site_recovered")

        # Never lower a stored per-URL rev (SPEC §4.1 / §5.1 anomaly path).
        if meta.get("rev_anomaly"):
            return response

        # Cache only full public representations within the configured limit.
        vary = response.headers.get(b"Vary", b"").lower().split(b",")
        policy = response.headers.get(b"Cache-Control", b"").lower()
        if (response.status != 200 or len(response.body) > self.max_cache_bytes
                or any(value.strip() not in (b"", b"accept-encoding") for value in vary)
                or b"private" in policy or b"no-store" in policy or response.headers.get(b"Set-Cookie")):
            return response
        self.store.set_response(meta["origin"], meta["path"], response)
        # record the freshly observed rev + size for next run's comparison
        self.store.set_rev(
            meta["origin"], meta["path"], meta["rev"], len(response.body)
        )
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
        rate = (
            self.bootstrap_rate
            if (time.time() - first_seen) < BOOTSTRAP_WINDOW_S
            else self.audit_rate
        )
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
            f"(~{saved} bytes saved), audits={self.stats.get_value('pagedigest/audits', 0)}, "
            f"mismatches={self.stats.get_value('pagedigest/audit_mismatch', 0)}"
        )
        self.store.close()

    # Count avoided network downloads, not avoided callback processing.
    def _record_skip(self, origin, path, size):
        self.stats.inc_value("pagedigest/skipped")
        self.stats.inc_value("pagedigest/bytes_saved_est", size)
