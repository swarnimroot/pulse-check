"""RSS-discovery pass: pull operator-supplied RSS feeds, title-filter the
entries, and surface the surviving URLs for downstream `fetch_article` /
`fetch_youtube_transcript` enqueues.

The discovery pass is the v5 alternative to per-product `youtube_seeds` and
`article_seeds`. The operator supplies a small set of *publishers* (YouTube
review channels + review-site RSS feeds); this module polls each feed and
returns titles/URLs that survive a case-insensitive substring keyword filter
+ a `backfill_months` window.

Each returned URL is intended for the existing fetcher path:
- `target_source == "youtube"` → `scrapers_lib.tier1.youtube.fetch_youtube_transcript`
- `target_source == "article"` → `scrapers_lib.tier1.article.fetch_article`

The orchestrator enqueues those URLs with all-product anchors, so per-product
attribution happens at the body / transcript level (chunk anchor regex) — the
title filter is only a cheap pre-skip for obviously-irrelevant content.

Auto-discovery fallback: when a configured `rss_url` returns zero entries
when parsed as a feed (e.g. RTINGS's `/rss-feeds` page is an HTML index, not
a feed), the module fetches the URL as HTML once and looks for a feed-ish
link containing the keyword "laptop" — either `<link rel="alternate"
type="application/rss+xml" href="...">` or `<a href="...">` whose href/text
mentions both "laptop" and one of rss/feed/xml. The first match wins; the
auto-discovered URL is then re-fetched as a feed (single retry, no
recursion).

All external IO sits behind injection seams (`feed_fetcher`, `html_fetcher`,
`now`) so unit tests run offline.
"""

from __future__ import annotations

import html.parser
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from urllib.parse import urljoin

from pulse_check.config.models import RSSSources, RSSWindow

log = logging.getLogger(__name__)

TargetSource = Literal["article", "youtube"]

# RTINGS-style index-page fallback keyword. v1 hard-codes "laptop" since every
# product in the v1 universe is a gaming laptop; promote to a config field if
# we ever add non-laptop categories.
_INDEX_PAGE_KEYWORD = "laptop"


@dataclass(frozen=True)
class DiscoveredItem:
    """One title-filtered RSS entry ready to enqueue for body fetching."""

    url: str
    title: str
    published_at: datetime | None
    target_source: TargetSource
    origin_feed: str


@dataclass(frozen=True)
class DiscoveryStats:
    """Counters for logging / observability."""

    feeds_polled: int
    feeds_with_zero_entries: int
    feeds_recovered_by_html_fallback: int
    items_seen: int
    items_after_title_filter: int
    items_after_window_filter: int


# ---------------------------------------------------------------------------
# RawMention surface used here. We deliberately import the type only for
# typing — at runtime the feed_fetcher returns whatever scrapers-lib hands
# back. Tests inject a stub that returns objects with the same attribute
# surface.
# ---------------------------------------------------------------------------


class _RSSEntry(Protocol):
    """Structural type for what feed_fetcher returns per RSS entry.

    `scrapers_lib.RawMention` satisfies this — `source_url` is always
    populated; `source_title` and `published_at` are `str | None` and
    `datetime | None` respectively. Declared as a `Protocol` so test stubs
    (plain dataclasses) duck-type without an inheritance dependency on
    scrapers-lib's pydantic model.
    """

    @property
    def source_url(self) -> str: ...
    @property
    def source_title(self) -> str | None: ...
    @property
    def published_at(self) -> datetime | None: ...


FeedFetcher = Callable[[str], Sequence[_RSSEntry]]
HTMLFetcher = Callable[[str], str]


def discover(
    sources: RSSSources,
    window: RSSWindow,
    *,
    feed_fetcher: FeedFetcher | None = None,
    html_fetcher: HTMLFetcher | None = None,
    now: datetime | None = None,
) -> tuple[list[DiscoveredItem], DiscoveryStats]:
    """Run discovery across all youtube_channels + article_rss_feeds.

    Returns the title-filtered + window-filtered items plus aggregate stats.
    Disabled article feeds are skipped before fetching; YouTube channels do
    not have an `enabled` flag in v1.
    """
    fetch_feed = feed_fetcher if feed_fetcher is not None else _default_feed_fetcher
    fetch_html = html_fetcher if html_fetcher is not None else _default_html_fetcher
    clock = now if now is not None else datetime.now(UTC)

    cutoff: datetime | None = None
    if window.backfill_months is not None:
        # 30-day month approximation matches `YouTubeWindow` / `ArticleWindow`
        # semantics elsewhere in the orchestrator.
        cutoff = clock - timedelta(days=window.backfill_months * 30)

    keywords_lower = [k.lower() for k in sources.title_keywords]

    out: list[DiscoveredItem] = []
    feeds_polled = 0
    feeds_zero = 0
    feeds_recovered = 0
    items_seen = 0
    items_after_title = 0
    items_after_window = 0

    def _process(rss_url: str, target: TargetSource) -> None:
        nonlocal feeds_polled, feeds_zero, feeds_recovered
        nonlocal items_seen, items_after_title, items_after_window

        feeds_polled += 1
        entries, recovered = _fetch_with_fallback(rss_url, fetch_feed, fetch_html)
        if recovered:
            feeds_recovered += 1
        if not entries:
            feeds_zero += 1
            return

        for entry in entries:
            items_seen += 1
            title = entry.source_title or ""
            if not _passes_title_filter(title, keywords_lower):
                continue
            items_after_title += 1
            if not _passes_window_filter(entry.published_at, cutoff):
                continue
            items_after_window += 1
            out.append(
                DiscoveredItem(
                    url=entry.source_url,
                    title=title,
                    published_at=entry.published_at,
                    target_source=target,
                    origin_feed=rss_url,
                )
            )

    for ch in sources.youtube_channels:
        _process(ch.rss_url, "youtube")

    for site in sources.article_rss_feeds:
        if not site.enabled:
            log.info("rss_discovery: skipping disabled feed %s (%s)", site.site, site.rss_url)
            continue
        _process(site.rss_url, "article")

    stats = DiscoveryStats(
        feeds_polled=feeds_polled,
        feeds_with_zero_entries=feeds_zero,
        feeds_recovered_by_html_fallback=feeds_recovered,
        items_seen=items_seen,
        items_after_title_filter=items_after_title,
        items_after_window_filter=items_after_window,
    )
    log.info(
        "rss_discovery: feeds=%d zero=%d recovered=%d seen=%d "
        "title_pass=%d window_pass=%d",
        feeds_polled,
        feeds_zero,
        feeds_recovered,
        items_seen,
        items_after_title,
        items_after_window,
    )
    return out, stats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fetch_with_fallback(
    rss_url: str,
    feed_fetcher: FeedFetcher,
    html_fetcher: HTMLFetcher,
) -> tuple[Sequence[_RSSEntry], bool]:
    """Fetch `rss_url` as a feed. On zero entries / fetch failure, try once
    to scrape the URL as HTML for an auto-discoverable feed link.

    Returns (entries, recovered) where `recovered=True` indicates the HTML
    fallback path produced entries.
    """
    entries = _safe_feed_fetch(rss_url, feed_fetcher)
    if entries:
        return entries, False

    html_text = _safe_html_fetch(rss_url, html_fetcher)
    if html_text is None:
        return [], False
    discovered = _discover_feed_from_html(html_text, base_url=rss_url, keyword=_INDEX_PAGE_KEYWORD)
    if discovered is None:
        log.info("rss_discovery: no feed link auto-discovered from %s", rss_url)
        return [], False
    log.info("rss_discovery: auto-discovered feed %s from index page %s", discovered, rss_url)
    fallback_entries = _safe_feed_fetch(discovered, feed_fetcher)
    return fallback_entries, bool(fallback_entries)


def _safe_feed_fetch(url: str, fetcher: FeedFetcher) -> Sequence[_RSSEntry]:
    try:
        return fetcher(url)
    except Exception:
        log.warning("rss_discovery: feed fetch failed: %s", url, exc_info=True)
        return []


def _safe_html_fetch(url: str, fetcher: HTMLFetcher) -> str | None:
    try:
        return fetcher(url)
    except Exception:
        log.warning("rss_discovery: html fallback fetch failed: %s", url, exc_info=True)
        return None


def _passes_title_filter(title: str, keywords_lower: list[str]) -> bool:
    if not title:
        return False
    title_lower = title.lower()
    return any(kw in title_lower for kw in keywords_lower)


def _passes_window_filter(published_at: datetime | None, cutoff: datetime | None) -> bool:
    if cutoff is None or published_at is None:
        return True
    return published_at >= cutoff


def _default_feed_fetcher(url: str) -> Sequence[_RSSEntry]:
    """Production feed fetcher: thin wrapper around scrapers-lib.

    scrapers-lib's `RawMention` exposes `source_url`, `source_title`, and
    `published_at` — the structural surface this module relies on.
    """
    from scrapers_lib.tier1.rss import fetch_rss_feed

    raw_mentions = fetch_rss_feed(url, anchors=None)
    return list(raw_mentions)


def _default_html_fetcher(url: str) -> str:
    """Production HTML fetcher for the auto-discovery fallback."""
    import httpx

    response = httpx.get(url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    return response.text


# ---------------------------------------------------------------------------
# HTML auto-discovery (RTINGS-style fallback)
# ---------------------------------------------------------------------------


def _discover_feed_from_html(
    html_text: str, *, base_url: str, keyword: str
) -> str | None:
    """Scan HTML for the first feed-ish link whose href or anchor text
    contains `keyword` (case-insensitive).

    Order of preference (first match wins):
    1. `<link rel="alternate" type="application/rss+xml|atom+xml" href="..."`
       where the href contains the keyword.
    2. `<a href="...rss|feed|xml..." >text<...` where href OR text contains
       the keyword.

    Returns the discovered URL (absolutized against `base_url`) or None.
    """
    finder = _FeedLinkFinder(keyword.lower())
    finder.feed(html_text)
    if finder.best is None:
        return None
    return urljoin(base_url, finder.best)


class _FeedLinkFinder(html.parser.HTMLParser):
    """Stdlib-only HTML parser that captures the first matching feed link.

    Stops at first match (no continuation past discovery).
    """

    def __init__(self, keyword_lower: str) -> None:
        super().__init__()
        self.keyword = keyword_lower
        self.best: str | None = None
        self._anchor_href: str | None = None
        self._anchor_text_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.best is not None:
            return
        a = {k: (v or "") for k, v in attrs}
        if tag == "link":
            rel = a.get("rel", "").lower()
            type_ = a.get("type", "").lower()
            href = a.get("href", "")
            is_alt_feed = "alternate" in rel and ("rss" in type_ or "atom" in type_)
            if is_alt_feed and self.keyword in href.lower():
                self.best = href
        elif tag == "a":
            self._anchor_href = a.get("href", "")
            self._anchor_text_buf = []

    def handle_data(self, data: str) -> None:
        if self.best is not None or self._anchor_href is None:
            return
        self._anchor_text_buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self.best is not None or self._anchor_href is None:
            if tag == "a":
                self._anchor_href = None
                self._anchor_text_buf = []
            return
        href = self._anchor_href
        text = "".join(self._anchor_text_buf)
        href_lower = href.lower()
        text_lower = text.lower()
        is_feedish = any(s in href_lower for s in ("rss", "feed", "xml"))
        if is_feedish and (self.keyword in href_lower or self.keyword in text_lower):
            self.best = href
        self._anchor_href = None
        self._anchor_text_buf = []
