"""End-to-end scrape orchestration.

`run_scrape(session, run_config, product_set)` wires scrapers-lib's Scheduler
to our ingester and drives a full scrape for all enabled sources in the run
config. The result_sink callback persists each fetcher batch + commits
incrementally so a crashed scrape leaves a usable partial corpus. After the
Scheduler drains, the secondary attribution pass runs over the DB.

Source-specific job enqueueing:
- Reddit: one job per subreddit (listing sweep), anchors = all products.
- BestBuy reviews / Amazon reviews: one job per (product, URL). Anchors must
  include the target product because scrapers-lib's URL-map attribution
  requires exact-URL match on the anchor.
- YouTube: one job per seeded video URL per product.
- Article: one job per seeded article URL per product.

Products without a URL for a given source are skipped with a log line rather
than failing the scrape.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scrapers_lib import ProductSnapshot, RawMention, Scheduler

# Import fetcher modules for their @register side effects.
# Without these, scrapers-lib's Scheduler has an empty fetcher registry and
# every enqueued job fails with "no fetcher for source ...".
from scrapers_lib.tier1 import article, reddit, rss, youtube  # noqa: F401
from scrapers_lib.tier3 import amazon, bestbuy  # noqa: F401
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.config.models import (
    ProductConfig,
    ProductSet,
    RSSSources,
    RSSWindow,
    RunConfig,
)
from pulse_check.scraping.anchors import to_anchor, to_anchors
from pulse_check.scraping.attribution import (
    SecondaryAttributionStats,
    apply_secondary_attribution,
)
from pulse_check.scraping.comment_inheritance import (
    CommentInheritanceStats,
    apply_comment_inheritance,
)
from pulse_check.scraping.discovered_urls import DiscoveredUrlEntry
from pulse_check.scraping.ingester import IngestStats, ingest_batch
from pulse_check.scraping.rss_discovery import discover
from pulse_check.settings import get_settings
from pulse_check.storage.enums import AttributionType, SourceType
from pulse_check.storage.models import Mention, MentionAttribution, Product

log = logging.getLogger(__name__)

# Max reddit comment-followups (per-post `.rss` fetches) per run. Reddit
# rate-limits its public `.rss` endpoint with a 429 after ~100 requests/run, so
# the per-run reddit budget (≈12 listing feeds + this) must stay under that.
# Deepening only the newest posts keeps daily fresh-discussion capture while
# leaving full historical deepening to the occasional quarterly pass. Tune via
# the `cap` arg if Reddit's tolerance changes.
REDDIT_COMMENT_FOLLOWUP_CAP = 50


def run_scrape(
    session: Session,
    run_config: RunConfig,
    product_set: ProductSet,
    *,
    rss_sources: RSSSources | None = None,
    discovered_urls: list[DiscoveredUrlEntry] | None = None,
    state_file: str | Path | None = None,
) -> tuple[IngestStats, SecondaryAttributionStats, CommentInheritanceStats]:
    """Drain a full scrape for the given run config and persist to `session`.

    The caller owns the session's transaction lifetime. A fresh Scheduler is
    constructed at `state_file` (default: `settings.scheduler_db_path`).

    When `run_config.source_windows.rss.enabled` is true and `rss_sources` is
    supplied, the RSS-discovery pass runs at orchestrator startup before the
    per-product enqueues. Discovered URLs are enqueued with all-product
    anchors against the `youtube` / `article` fetchers; per-product seed
    URLs (`youtube_seeds` / `article_seeds`) still fire alongside if their
    own windows are enabled (coexist; no de-dup at this layer).

    When `discovered_urls` is supplied (operator-curated catalog-discovery
    output), each entry is enqueued with its product's single anchor against
    the `article` fetcher — mirroring per-product `article_seeds` rather than
    RSS broadcast, since each entry is already product-anchored at the YAML
    level. Gated on `source_windows.article.enabled` so the operator can
    disable the article path globally without clearing this list.
    """
    ingest_stats = IngestStats()

    def _sink(results: Sequence[RawMention | ProductSnapshot]) -> None:
        ingest_batch(session, list(results), stats=ingest_stats)
        session.commit()

    if state_file is None:
        state_file = get_settings().scheduler_db_path
    Path(state_file).parent.mkdir(parents=True, exist_ok=True)

    _upsert_products(session, product_set)
    session.commit()

    scheduler = Scheduler(state_file=state_file, result_sink=_sink)
    try:
        sw = run_config.source_windows
        if sw.rss is not None and sw.rss.enabled and rss_sources is not None:
            _enqueue_rss_discovered(
                scheduler, session, product_set, rss_sources, sw.rss
            )
        _enqueue_all_sources(scheduler, run_config, product_set)
        if (
            sw.article is not None
            and sw.article.enabled
            and discovered_urls is not None
        ):
            _enqueue_discovered_urls(scheduler, product_set, discovered_urls)
        scheduler.run_worker(mode="until_empty")

        # Reddit-deepen pass: pull comment trees on every primary-attributed
        # reddit_post already in the DB (including ones just ingested above).
        # Operates DB-side so re-runs deepen the corpus from prior scrapes too.
        reddit_window = run_config.source_windows.reddit
        if reddit_window is not None and reddit_window.enabled:
            followups = _enqueue_reddit_comment_followups(
                scheduler, session, product_set
            )
            if followups > 0:
                scheduler.run_worker(mode="until_empty")
    finally:
        scheduler.close()

    secondary_stats = apply_secondary_attribution(session, product_set)
    session.commit()

    inheritance_stats = apply_comment_inheritance(session)
    session.commit()

    log.info(
        "scrape complete: mentions new=%d existing=%d; "
        "attributions primary=%d secondary=%d inherited=%d",
        ingest_stats.new_mentions,
        ingest_stats.existing_mentions,
        ingest_stats.new_attributions,
        secondary_stats.new_attributions,
        inheritance_stats.new_attributions,
    )
    return ingest_stats, secondary_stats, inheritance_stats


def _upsert_products(session: Session, product_set: ProductSet) -> None:
    """Idempotent upsert of products from config into the DB.

    Existing rows (matched on `product_id`) are updated with current values
    of `display_name`, `brand`, `aliases`, `attribution_patterns`, `urls`.
    Missing rows are inserted. No row is ever deleted by this function.

    Run before scraping so the `products` table is populated when the
    gold-set sampler joins on it (a previously missing prereq).
    """
    for pc in product_set.products:
        existing = session.get(Product, pc.product_id)
        if existing is not None:
            existing.display_name = pc.display_name
            existing.brand = pc.brand
            existing.aliases = list(pc.aliases)
            existing.attribution_patterns = pc.attribution_patterns.model_dump()
            existing.urls = pc.urls.model_dump()
        else:
            session.add(
                Product(
                    product_id=pc.product_id,
                    display_name=pc.display_name,
                    brand=pc.brand,
                    aliases=list(pc.aliases),
                    attribution_patterns=pc.attribution_patterns.model_dump(),
                    urls=pc.urls.model_dump(),
                )
            )
    session.flush()


def _enqueue_all_sources(
    scheduler: Scheduler, run_config: RunConfig, product_set: ProductSet
) -> int:
    """Enqueue jobs for every enabled source. Returns the job count."""
    sw = run_config.source_windows
    all_anchors = to_anchors(product_set)
    count = 0

    if sw.reddit is not None and sw.reddit.enabled and all_anchors:
        for subreddit in sw.reddit.subreddits:
            # Reddit 403-blocks the .json API for our IP; the .rss listing feed
            # is the live path (recent posts; RSS has no sort/time_filter).
            # Historical depth is already in the corpus from the backfill — the
            # daily cadence only needs fresh posts. See scrapers_lib.tier1.reddit.
            scheduler.enqueue(
                url=_reddit_url(subreddit),
                source="reddit_rss",
                anchors=all_anchors,
            )
            count += 1

    if sw.bestbuy_reviews is not None and sw.bestbuy_reviews.enabled:
        for product in product_set.products:
            url = product.urls.bestbuy
            if url is None:
                log.info(
                    "skipping bestbuy_reviews for %s: no bestbuy URL in config",
                    product.product_id,
                )
                continue
            anchor = _single_anchor(product)
            if anchor is None:
                continue
            scheduler.enqueue(
                url=url,
                source="bestbuy_reviews",
                anchors=[anchor],
                paginate=sw.bestbuy_reviews.paginate,
            )
            count += 1

    if sw.amazon_reviews is not None and sw.amazon_reviews.enabled:
        for product in product_set.products:
            url = product.urls.amazon
            if url is None:
                log.info(
                    "skipping amazon_reviews for %s: no amazon URL in config",
                    product.product_id,
                )
                continue
            anchor = _single_anchor(product)
            if anchor is None:
                continue
            scheduler.enqueue(
                url=url,
                source="amazon_reviews",
                anchors=[anchor],
            )
            count += 1

    if sw.youtube is not None and sw.youtube.enabled:
        for product in product_set.products:
            anchor = _single_anchor(product)
            if anchor is None:
                continue
            for video_url in product.urls.youtube_seeds:
                scheduler.enqueue(
                    url=video_url,
                    source="youtube",
                    anchors=[anchor],
                    # YouTube captions are PoToken-gated for ~half of videos;
                    # enable the yt-dlp + faster-whisper (CPU) audio fallback so
                    # caption-less videos still yield a transcript instead of
                    # being silently dropped.
                    audio_fallback=True,
                )
                count += 1

    if sw.article is not None and sw.article.enabled:
        for product in product_set.products:
            anchor = _single_anchor(product)
            if anchor is None:
                continue
            for article_url in product.urls.article_seeds:
                scheduler.enqueue(
                    url=article_url,
                    source="article",
                    anchors=[anchor],
                )
                count += 1

    log.info("enqueued %d scrape jobs", count)
    return count


def _single_anchor(product: ProductConfig) -> object | None:
    """Build the anchor for a single targeted source (BestBuy/Amazon/seed URL)."""
    return to_anchor(product)


def _reddit_url(subreddit: str) -> str:
    sub = subreddit.removeprefix("r/").removeprefix("/r/")
    return f"https://www.reddit.com/r/{sub}/"


def _enqueue_discovered_urls(
    scheduler: Scheduler,
    product_set: ProductSet,
    entries: list[DiscoveredUrlEntry],
) -> int:
    """Enqueue operator-approved discovered URLs as single-anchor article jobs.

    Each `DiscoveredUrlEntry` carries the product_id it was discovered for;
    that product's anchor is the only one passed to the scheduler, so the
    resulting mention is PRIMARY-attributed to the source product. Mentions
    of other tracked products in the article body are picked up by the
    post-fetch `apply_secondary_attribution` sweep.

    Entries whose `product_id` is not present in `product_set` are skipped
    with a log line — defensive against drift between curated YAMLs and the
    active run's product set.
    """
    product_by_id = {p.product_id: p for p in product_set.products}
    count = 0
    skipped_unknown = 0
    skipped_no_anchor = 0
    for entry in entries:
        product = product_by_id.get(entry.product_id)
        if product is None:
            skipped_unknown += 1
            continue
        anchor = to_anchor(product)
        if anchor is None:
            skipped_no_anchor += 1
            continue
        scheduler.enqueue(
            url=entry.url,
            source="article",
            anchors=[anchor],
        )
        count += 1
    log.info(
        "discovered_urls: enqueued %d article jobs "
        "(skipped %d unknown product_id, %d no-anchor)",
        count,
        skipped_unknown,
        skipped_no_anchor,
    )
    return count


def _youtube_video_id(url: str) -> str | None:
    """Best-effort 11-char video id from a watch / youtu.be / embed / shorts URL.

    Returns ``None`` when the URL isn't a recognizable YouTube video link.
    """
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if host in ("youtu.be", "www.youtu.be"):
        vid = p.path.strip("/").split("/")[0] if p.path else ""
        return vid or None
    if "youtube" in host:
        qs = parse_qs(p.query)
        if qs.get("v"):
            return qs["v"][0]
        parts = p.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] in ("embed", "shorts", "v"):
            return parts[1]
    return None


def _video_id_from_chunk_mention_id(mention_id: str) -> str:
    """Recover the video id from a ``youtube_<vid>_chunk_<n>`` mention id.

    Mirrors ``scrapers_lib.core.attribution.youtube_chunk_id``. Dialect-free
    (string ops) so it works without JSON-extract on ``metadata_``.
    """
    return mention_id.removeprefix("youtube_").rsplit("_chunk_", 1)[0]


def _transcribed_youtube_video_ids(session: Session) -> set[str]:
    """Video ids already transcribed into the corpus (``youtube_chunk`` mentions)."""
    return {
        _video_id_from_chunk_mention_id(mid)
        for mid in session.execute(
            select(Mention.mention_id).where(
                Mention.source_type == SourceType.YOUTUBE_CHUNK
            )
        ).scalars()
    }


def _enqueue_rss_discovered(
    scheduler: Scheduler,
    session: Session,
    product_set: ProductSet,
    rss_sources: RSSSources,
    rss_window: RSSWindow,
) -> int:
    """Run RSS discovery and enqueue surviving URLs with all-product anchors.

    Each `DiscoveredItem` becomes one scheduler job; `target_source`
    determines the fetcher (`youtube` for channel-feed video URLs,
    `article` for review-site article URLs). Returns the job count.

    **YouTube pre-fetch dedup.** Transcription is expensive (yt-dlp download +
    faster-whisper on CPU, ~30 s-3 min/video), and the corpus dedups only at
    *ingest* — after the fetch. Re-sweeping the same recent videos every day
    would re-run whisper on already-transcribed videos for nothing. So a
    discovered YouTube video whose id is already in the corpus is skipped before
    enqueue. Articles are cheap HTTP re-fetches, so they aren't deduped here.
    """
    all_anchors = to_anchors(product_set)
    if not all_anchors:
        log.info("rss_discovery: no anchors built; skipping")
        return 0

    transcribed = _transcribed_youtube_video_ids(session)
    items, _stats = discover(rss_sources, rss_window)
    enqueued = 0
    skipped_seen = 0
    for item in items:
        if item.target_source == "youtube":
            vid = _youtube_video_id(item.url)
            if vid is not None and vid in transcribed:
                skipped_seen += 1
                continue
            # Enable the yt-dlp + faster-whisper (CPU) audio fallback so
            # caption-less / PoToken-gated videos still yield a transcript
            # instead of being silently dropped.
            extra: dict[str, object] = {"audio_fallback": True}
        else:
            extra = {}
        scheduler.enqueue(
            url=item.url,
            source=item.target_source,
            anchors=all_anchors,
            **extra,
        )
        enqueued += 1
    log.info(
        "rss_discovery: enqueued %d jobs (skipped %d already-transcribed youtube videos)",
        enqueued,
        skipped_seen,
    )
    return enqueued


def _enqueue_reddit_comment_followups(
    scheduler: Scheduler,
    session: Session,
    product_set: ProductSet,
    *,
    cap: int = REDDIT_COMMENT_FOLLOWUP_CAP,
) -> int:
    """Enqueue `fetch_reddit_comments_rss` for the most-recent primary-attributed
    reddit_post source_urls in the DB (newest first, capped). Returns the count.

    Anchors are passed identical to the listing pass so each comment runs
    through scrapers-lib's per-item regex attribution (`_fan_out`); a comment
    discussing a different product than the parent post lands attributed
    correctly on its own merit. Idempotent at the ingest layer (mention_id
    upsert), so re-running is safe.

    **Capped + recency-ordered (daily-cadence fix).** Reddit rate-limits its
    public `.rss` endpoint (429 after ~100 requests/run), and deepening every
    historical post each day is both rate-fatal and wasteful — old posts'
    comments are already in the corpus. So we deepen only the `cap` newest
    posts (by `published_at`), which keeps the per-run reddit request budget
    under the 429 ceiling and prioritizes fresh discussion. Older posts are
    covered by the occasional full pass (quarterly refresh). The skip count is
    logged, never silent.
    """
    all_anchors = to_anchors(product_set)
    if not all_anchors:
        return 0

    rows = session.execute(
        select(Mention.source_url, Mention.published_at)
        .join(MentionAttribution, MentionAttribution.mention_id == Mention.mention_id)
        .where(
            Mention.source_type == SourceType.REDDIT_POST,
            MentionAttribution.attribution_type == AttributionType.PRIMARY,
        )
        .distinct()
    ).all()

    # Dedup by url (a multi-product post yields multiple attribution rows),
    # keeping newest first. `published_at` may be None → sort it oldest.
    seen: set[str] = set()
    ordered_urls: list[str] = []
    for url, _pub in sorted(
        rows,
        key=lambda r: r[1].timestamp() if r[1] else 0.0,
        reverse=True,
    ):
        if url in seen:
            continue
        seen.add(url)
        ordered_urls.append(url)

    capped = ordered_urls[:cap]
    for url in capped:
        scheduler.enqueue(
            url=url,
            source="reddit_comments_rss",
            anchors=all_anchors,
            # Bypass per-comment regex; pulse-check inherits parent-post
            # primary attribution as SECONDARY via apply_comment_inheritance.
            emit_all_comments=True,
        )

    log.info(
        "enqueued %d reddit comment-fetch followups (newest-first; %d eligible, "
        "%d skipped by cap=%d)",
        len(capped),
        len(ordered_urls),
        max(0, len(ordered_urls) - len(capped)),
        cap,
    )
    return len(capped)
