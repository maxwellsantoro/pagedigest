"""A Scrapy consumer for the pagedigest v1 protocol.

Skips re-fetching covered URLs whose manifest `rev` is unchanged since the last
crawl, sends the optional cooperation header, and audits a fraction of skips
against the publisher's sha256 digests. Cardinal rule from the spec: a missing,
malformed, stale, or dishonest manifest must never make crawling worse than it
would be with no manifest at all.
"""

from .middleware import PageDigestMiddleware  # noqa: F401
