"""CLI entry point: dry-run RSS discovery — poll operator-supplied RSS feeds
and report per-source admitted/rejected counts + sample titles.

No DB writes, no LLM, no Article/YouTube body-fetcher invocation. RSS HTTP
only. Wraps `pulse_check.scraping.rss_discovery.discover()` with a capturing
`feed_fetcher` so raw entries are recorded per URL; the rejected sample set
is then derived as `raw − admitted` by URL membership, without duplicating
`discover()`'s filter logic.

Usage:
    python scripts/dry_run_rss_discovery.py \\
        --rss-sources configs/wave5_rss_sources.yaml \\
        --backfill-months 3
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from pulse_check.config.loader import load_rss_sources
from pulse_check.config.models import RSSWindow
from pulse_check.logging_config import configure_logging
from pulse_check.scraping.rss_discovery import (
    DiscoveredItem,
    FeedFetcher,
    _RSSEntry,
    discover,
)

log = logging.getLogger("pulse_check.scripts.dry_run_rss_discovery")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pulse-check dry-run-rss-discovery",
        description=(
            "Poll operator-supplied RSS feeds and report per-source "
            "admitted/rejected counts + sample titles. No ingest, no LLM."
        ),
    )
    parser.add_argument(
        "--rss-sources",
        type=Path,
        default=Path("configs/wave5_rss_sources.yaml"),
        help="Path to RSS sources YAML (default: configs/wave5_rss_sources.yaml).",
    )
    parser.add_argument(
        "--backfill-months",
        type=int,
        default=3,
        help="published_at window in months (default: 3).",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path("data/dry_run"),
        help="Directory for the per-session log file (default: data/dry_run/).",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=5,
        help="Sample admitted/rejected titles per source (default: 5).",
    )
    return parser.parse_args(argv)


def _attach_session_log(log_path: Path) -> None:
    """Add a per-session file handler to the root logger so the dry-run
    transcript is captured to its own file in addition to the rotating
    `data/pulse_check.log` set up by `configure_logging()`.
    """
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    logging.getLogger().addHandler(handler)


def _make_capturing_fetcher(
    raw_capture: dict[str, list[_RSSEntry]],
    *,
    base_fetcher: FeedFetcher | None = None,
) -> FeedFetcher:
    """Wrap a feed fetcher so every URL → entries pair is recorded in
    `raw_capture` before being returned. Captures both primary feed fetches
    and HTML-fallback secondary fetches (both flow through this callable).
    """
    if base_fetcher is None:
        from scrapers_lib.tier1.rss import fetch_rss_feed

        def _default(url: str) -> Sequence[_RSSEntry]:
            return list(fetch_rss_feed(url, anchors=None))

        base: FeedFetcher = _default
    else:
        base = base_fetcher

    def capturing(url: str) -> Sequence[_RSSEntry]:
        entries: list[_RSSEntry] = list(base(url))
        raw_capture[url] = entries
        return entries

    return capturing


def _fmt_published(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d") if dt is not None else "(no date)"


def _sort_rejected_recent_first(entries: list[_RSSEntry]) -> list[_RSSEntry]:
    """Sort rejected entries with most-recent published_at first; None last.
    Keeps title-rejections (typically recent) visually separated from
    window-rejections (typically older) so the operator can tune keywords
    on the head of the list.
    """

    def key(e: _RSSEntry) -> tuple[int, float]:
        dt = e.published_at
        if dt is None:
            return (1, 0.0)
        return (0, -dt.timestamp())

    return sorted(entries, key=key)


def _report_source(
    *,
    label: str,
    feed_url: str,
    raw_entries: list[_RSSEntry],
    admitted_items: list[DiscoveredItem],
    samples: int,
) -> None:
    admitted_urls = {item.url for item in admitted_items}
    rejected = [e for e in raw_entries if e.source_url not in admitted_urls]
    raw_count = len(raw_entries)
    log.info("%s", label)
    log.info("  feed: %s", feed_url)
    log.info(
        "  raw=%d  admitted=%d  rejected=%d",
        raw_count,
        len(admitted_items),
        len(rejected),
    )
    if raw_count == 0:
        log.info("  (feed returned zero entries — HTML fallback may have run)")
    if admitted_items:
        log.info("  admitted samples (up to %d):", samples)
        for item in admitted_items[:samples]:
            log.info(
                "    [%s] %s", _fmt_published(item.published_at), item.title
            )
    if rejected:
        log.info("  rejected samples (up to %d, recent-first):", samples)
        for entry in _sort_rejected_recent_first(rejected)[:samples]:
            title = entry.source_title or "(no title)"
            log.info("    [%s] %s", _fmt_published(entry.published_at), title)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    configure_logging()

    args.log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    log_path: Path = args.log_dir / f"session26_{ts}.log"
    _attach_session_log(log_path)

    log.info("=== DRY-RUN RSS DISCOVERY ===")
    log.info("sources: %s", args.rss_sources)
    log.info("backfill_months: %d", args.backfill_months)
    log.info("samples_per_source: %d", args.samples)
    log.info("output_log: %s", log_path)

    sources = load_rss_sources(args.rss_sources)
    window = RSSWindow(enabled=True, backfill_months=args.backfill_months)
    log.info("title_keywords: %s", sources.title_keywords)
    log.info(
        "configured: youtube_channels=%d  article_feeds=%d (enabled=%d)",
        len(sources.youtube_channels),
        len(sources.article_rss_feeds),
        sum(1 for f in sources.article_rss_feeds if f.enabled),
    )

    raw_capture: dict[str, list[_RSSEntry]] = {}
    fetcher = _make_capturing_fetcher(raw_capture)
    items, stats = discover(sources, window, feed_fetcher=fetcher)

    admitted_by_feed: dict[str, list[DiscoveredItem]] = {}
    for item in items:
        admitted_by_feed.setdefault(item.origin_feed, []).append(item)

    log.info("")
    log.info("--- YouTube channels (%d) ---", len(sources.youtube_channels))
    for i, ch in enumerate(sources.youtube_channels, 1):
        label = (
            f"[{i}/{len(sources.youtube_channels)}] "
            f"{ch.handle} ({ch.display_name})"
        )
        _report_source(
            label=label,
            feed_url=ch.rss_url,
            raw_entries=raw_capture.get(ch.rss_url, []),
            admitted_items=admitted_by_feed.get(ch.rss_url, []),
            samples=args.samples,
        )

    enabled_articles = sum(1 for f in sources.article_rss_feeds if f.enabled)
    log.info("")
    log.info(
        "--- Article RSS feeds (%d total, %d enabled) ---",
        len(sources.article_rss_feeds),
        enabled_articles,
    )
    for i, site in enumerate(sources.article_rss_feeds, 1):
        if not site.enabled:
            log.info(
                "[%d/%d] %s (disabled) — skipped",
                i,
                len(sources.article_rss_feeds),
                site.site,
            )
            continue
        status_tag = f" status={site.status}" if site.status else ""
        label = f"[{i}/{len(sources.article_rss_feeds)}] {site.site}{status_tag}"
        _report_source(
            label=label,
            feed_url=site.rss_url,
            raw_entries=raw_capture.get(site.rss_url, []),
            admitted_items=admitted_by_feed.get(site.rss_url, []),
            samples=args.samples,
        )

    operator_urls = {ch.rss_url for ch in sources.youtube_channels} | {
        f.rss_url for f in sources.article_rss_feeds
    }
    fallback_urls = sorted(set(raw_capture) - operator_urls)
    log.info("")
    log.info("--- HTML-fallback discoveries (%d) ---", len(fallback_urls))
    if not fallback_urls:
        log.info("  (none)")
    for i, url in enumerate(fallback_urls, 1):
        label = f"[fallback {i}/{len(fallback_urls)}]"
        _report_source(
            label=label,
            feed_url=url,
            raw_entries=raw_capture.get(url, []),
            admitted_items=admitted_by_feed.get(url, []),
            samples=args.samples,
        )

    log.info("")
    log.info("--- AGGREGATE ---")
    log.info("  feeds_polled: %d", stats.feeds_polled)
    log.info("  feeds_with_zero_entries: %d", stats.feeds_with_zero_entries)
    log.info(
        "  feeds_recovered_by_html_fallback: %d",
        stats.feeds_recovered_by_html_fallback,
    )
    log.info("  items_seen: %d", stats.items_seen)
    log.info("  items_after_title_filter: %d", stats.items_after_title_filter)
    log.info("  items_after_window_filter: %d", stats.items_after_window_filter)
    log.info("  final admitted: %d", len(items))
    log.info("")
    log.info("log written to: %s", log_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
