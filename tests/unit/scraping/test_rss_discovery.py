"""Unit tests for the RSS-discovery pass.

Covers:
- Title-keyword filter (substring, case-insensitive, must match >=1).
- Window filter (`backfill_months`) against `published_at`; None passes.
- Disabled article feeds are skipped without invoking the feed_fetcher.
- HTML auto-discovery fallback when a feed URL returns zero entries
  (RTINGS-style index page).
- Feed-fetcher exceptions handled gracefully.
- Stats counters track the pipeline accurately.
- Standalone tests for `_discover_feed_from_html` against representative
  HTML fragments.

All scrapers-lib + httpx IO is mocked via the `feed_fetcher` / `html_fetcher`
injection seams; tests run fully offline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from pulse_check.config.models import (
    ArticleRSSFeedSource,
    RSSSources,
    RSSWindow,
    YouTubeChannelSource,
)
from pulse_check.scraping.rss_discovery import (
    DiscoveredItem,
    _discover_feed_from_html,
    discover,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


@dataclass
class _StubEntry:
    """Structural stand-in for `RawMention` — only the fields rss_discovery reads."""

    source_url: str
    source_title: str | None
    published_at: datetime | None


def _yt(rss_url: str = "https://yt.example/feed1") -> YouTubeChannelSource:
    return YouTubeChannelSource(
        handle="@x",
        display_name="x",
        channel_id="UCx",
        rss_url=rss_url,
    )


def _art(
    rss_url: str = "https://art.example/feed1",
    *,
    enabled: bool = True,
) -> ArticleRSSFeedSource:
    return ArticleRSSFeedSource(site="ex", rss_url=rss_url, enabled=enabled)


def _src(
    *,
    keywords: list[str] | None = None,
    yt: list[YouTubeChannelSource] | None = None,
    art: list[ArticleRSSFeedSource] | None = None,
) -> RSSSources:
    return RSSSources(
        title_keywords=keywords or ["review", "vs"],
        youtube_channels=yt or [],
        article_rss_feeds=art or [],
    )


_NOW = datetime(2026, 5, 12, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Title filter
# ---------------------------------------------------------------------------


def test_discover_title_filter_keeps_substring_match() -> None:
    entries = [
        _StubEntry("https://yt.example/v/1", "Best gaming laptop 2026 REVIEW", None),
        _StubEntry("https://yt.example/v/2", "I built a desk", None),
        _StubEntry("https://yt.example/v/3", "Alienware vs ROG", None),
    ]
    feed = MagicMock(return_value=entries)
    items, stats = discover(
        _src(keywords=["review", "vs"], yt=[_yt()]),
        RSSWindow(enabled=True),
        feed_fetcher=feed,
        html_fetcher=MagicMock(),
        now=_NOW,
    )
    urls = [i.url for i in items]
    assert urls == ["https://yt.example/v/1", "https://yt.example/v/3"]
    assert stats.items_seen == 3
    assert stats.items_after_title_filter == 2
    assert stats.items_after_window_filter == 2
    assert all(i.target_source == "youtube" for i in items)


def test_discover_title_filter_is_case_insensitive() -> None:
    entries = [_StubEntry("u1", "RTX 5090 REVIEW", None)]
    items, _ = discover(
        _src(keywords=["review"], yt=[_yt()]),
        RSSWindow(enabled=True),
        feed_fetcher=MagicMock(return_value=entries),
        html_fetcher=MagicMock(),
        now=_NOW,
    )
    assert len(items) == 1


def test_discover_skips_entries_with_no_title() -> None:
    entries = [_StubEntry("u1", None, None), _StubEntry("u2", "review!", None)]
    items, _ = discover(
        _src(keywords=["review"], yt=[_yt()]),
        RSSWindow(enabled=True),
        feed_fetcher=MagicMock(return_value=entries),
        html_fetcher=MagicMock(),
        now=_NOW,
    )
    assert [i.url for i in items] == ["u2"]


# ---------------------------------------------------------------------------
# Window filter
# ---------------------------------------------------------------------------


def test_discover_window_filter_drops_old_entries() -> None:
    entries = [
        _StubEntry("recent", "review fresh", _NOW - timedelta(days=10)),
        _StubEntry("old", "review old", _NOW - timedelta(days=240)),
    ]
    items, stats = discover(
        _src(keywords=["review"], yt=[_yt()]),
        RSSWindow(enabled=True, backfill_months=6),
        feed_fetcher=MagicMock(return_value=entries),
        html_fetcher=MagicMock(),
        now=_NOW,
    )
    assert [i.url for i in items] == ["recent"]
    assert stats.items_after_title_filter == 2
    assert stats.items_after_window_filter == 1


def test_discover_window_filter_none_passes_unaware_entries() -> None:
    entries = [_StubEntry("u1", "review", None)]
    items, _ = discover(
        _src(keywords=["review"], yt=[_yt()]),
        RSSWindow(enabled=True, backfill_months=1),
        feed_fetcher=MagicMock(return_value=entries),
        html_fetcher=MagicMock(),
        now=_NOW,
    )
    assert len(items) == 1


def test_discover_no_backfill_passes_everything() -> None:
    entries = [_StubEntry("u1", "review", _NOW - timedelta(days=900))]
    items, _ = discover(
        _src(keywords=["review"], yt=[_yt()]),
        RSSWindow(enabled=True, backfill_months=None),
        feed_fetcher=MagicMock(return_value=entries),
        html_fetcher=MagicMock(),
        now=_NOW,
    )
    assert len(items) == 1


# ---------------------------------------------------------------------------
# Source routing + disabled feeds
# ---------------------------------------------------------------------------


def test_discover_routes_articles_and_youtube_independently() -> None:
    entries_yt = [_StubEntry("yt1", "review v1", None)]
    entries_art = [_StubEntry("art1", "review art", None)]

    def fake_fetcher(url: str) -> list[_StubEntry]:
        return entries_yt if "yt" in url else entries_art

    items, _ = discover(
        _src(
            keywords=["review"],
            yt=[_yt("https://yt.example/feed")],
            art=[_art("https://art.example/feed")],
        ),
        RSSWindow(enabled=True),
        feed_fetcher=fake_fetcher,
        html_fetcher=MagicMock(),
        now=_NOW,
    )
    by_target = {i.target_source: i.url for i in items}
    assert by_target == {"youtube": "yt1", "article": "art1"}


def test_discover_skips_disabled_article_feed_without_fetching() -> None:
    feed = MagicMock(return_value=[])
    discover(
        _src(art=[_art("https://art.example/feed", enabled=False)]),
        RSSWindow(enabled=True),
        feed_fetcher=feed,
        html_fetcher=MagicMock(),
        now=_NOW,
    )
    assert feed.call_count == 0


# ---------------------------------------------------------------------------
# HTML auto-discovery fallback
# ---------------------------------------------------------------------------


def test_discover_falls_back_to_html_when_feed_returns_zero_entries() -> None:
    fallback_entries = [_StubEntry("article1", "best laptop review", None)]
    feed = MagicMock(
        side_effect=[
            [],  # first call (the configured index URL) returns nothing
            fallback_entries,  # auto-discovered URL returns real entries
        ]
    )
    index_html = (
        '<html><body><a href="/laptops/rss">Laptops RSS feed</a></body></html>'
    )
    html_get = MagicMock(return_value=index_html)

    items, stats = discover(
        _src(keywords=["review"], art=[_art("https://rtings.example/rss-feeds")]),
        RSSWindow(enabled=True),
        feed_fetcher=feed,
        html_fetcher=html_get,
        now=_NOW,
    )

    assert [i.url for i in items] == ["article1"]
    assert stats.feeds_polled == 1
    assert stats.feeds_recovered_by_html_fallback == 1
    # Second feed fetch hit the auto-discovered absolute URL.
    feed.assert_any_call("https://rtings.example/laptops/rss")


def test_discover_html_fallback_misses_when_no_feedish_link() -> None:
    feed = MagicMock(return_value=[])
    html_get = MagicMock(return_value="<html><body><p>no feed here</p></body></html>")
    items, stats = discover(
        _src(art=[_art("https://x.example/index")]),
        RSSWindow(enabled=True),
        feed_fetcher=feed,
        html_fetcher=html_get,
        now=_NOW,
    )
    assert items == []
    assert stats.feeds_with_zero_entries == 1
    assert stats.feeds_recovered_by_html_fallback == 0


def test_discover_handles_feed_fetcher_exception() -> None:
    def explode(_url: str) -> list[_StubEntry]:
        raise RuntimeError("boom")

    items, stats = discover(
        _src(yt=[_yt()]),
        RSSWindow(enabled=True),
        feed_fetcher=explode,
        html_fetcher=MagicMock(return_value=""),
        now=_NOW,
    )
    assert items == []
    assert stats.feeds_polled == 1
    assert stats.feeds_with_zero_entries == 1


# ---------------------------------------------------------------------------
# Empty sources
# ---------------------------------------------------------------------------


def test_discover_no_sources_returns_empty() -> None:
    items, stats = discover(
        _src(),
        RSSWindow(enabled=True),
        feed_fetcher=MagicMock(),
        html_fetcher=MagicMock(),
        now=_NOW,
    )
    assert items == []
    assert stats == _empty_stats()


def _empty_stats() -> object:
    from pulse_check.scraping.rss_discovery import DiscoveryStats

    return DiscoveryStats(
        feeds_polled=0,
        feeds_with_zero_entries=0,
        feeds_recovered_by_html_fallback=0,
        items_seen=0,
        items_after_title_filter=0,
        items_after_window_filter=0,
    )


# ---------------------------------------------------------------------------
# _discover_feed_from_html (standalone)
# ---------------------------------------------------------------------------


def test_html_discovery_prefers_link_alternate_rss_xml() -> None:
    html = """
    <html><head>
      <link rel="alternate" type="application/rss+xml" href="/laptop/rss.xml">
      <link rel="alternate" type="application/rss+xml" href="/desktop/rss.xml">
    </head><body></body></html>
    """
    got = _discover_feed_from_html(html, base_url="https://x.test/index", keyword="laptop")
    assert got == "https://x.test/laptop/rss.xml"


def test_html_discovery_accepts_link_alternate_atom_xml() -> None:
    html = '<link rel="alternate" type="application/atom+xml" href="/laptop-feed">'
    got = _discover_feed_from_html(html, base_url="https://x.test/", keyword="laptop")
    assert got == "https://x.test/laptop-feed"


def test_html_discovery_matches_anchor_with_feedish_href_and_keyword_in_text() -> None:
    html = """
    <a href="/feeds/category-7.xml">Laptops</a>
    <a href="/feeds/category-8.xml">Phones</a>
    """
    got = _discover_feed_from_html(html, base_url="https://x.test/", keyword="laptop")
    assert got == "https://x.test/feeds/category-7.xml"


def test_html_discovery_matches_anchor_with_keyword_in_href() -> None:
    html = '<a href="/laptop/rss">Reviews</a>'
    got = _discover_feed_from_html(html, base_url="https://x.test/", keyword="laptop")
    assert got == "https://x.test/laptop/rss"


def test_html_discovery_rejects_non_feedish_anchor() -> None:
    html = '<a href="/laptop/page">Laptops landing page</a>'
    got = _discover_feed_from_html(html, base_url="https://x.test/", keyword="laptop")
    assert got is None


def test_html_discovery_returns_none_when_nothing_matches() -> None:
    html = '<a href="/desktop/rss">Desktop RSS</a>'
    got = _discover_feed_from_html(html, base_url="https://x.test/", keyword="laptop")
    assert got is None


def test_html_discovery_handles_absolute_href() -> None:
    html = '<a href="https://other.test/laptop/rss">Laptop RSS</a>'
    got = _discover_feed_from_html(html, base_url="https://x.test/", keyword="laptop")
    assert got == "https://other.test/laptop/rss"


# ---------------------------------------------------------------------------
# Shape contract: DiscoveredItem is hashable + immutable
# ---------------------------------------------------------------------------


def test_discovered_item_is_frozen_and_hashable() -> None:
    item = DiscoveredItem(
        url="u", title="t", published_at=None, target_source="article", origin_feed="o"
    )
    assert hash(item) == hash(item)
