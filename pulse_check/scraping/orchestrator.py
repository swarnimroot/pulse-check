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

from scrapers_lib import ProductSnapshot, RawMention, Scheduler

# Import fetcher modules for their @register side effects.
# Without these, scrapers-lib's Scheduler has an empty fetcher registry and
# every enqueued job fails with "no fetcher for source ...".
from scrapers_lib.tier1 import article, reddit, rss, youtube  # noqa: F401
from scrapers_lib.tier3 import amazon, bestbuy  # noqa: F401
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.config.models import ProductConfig, ProductSet, RunConfig
from pulse_check.scraping.anchors import to_anchor, to_anchors
from pulse_check.scraping.attribution import (
    SecondaryAttributionStats,
    apply_secondary_attribution,
)
from pulse_check.scraping.comment_inheritance import (
    CommentInheritanceStats,
    apply_comment_inheritance,
)
from pulse_check.scraping.ingester import IngestStats, ingest_batch
from pulse_check.settings import get_settings
from pulse_check.storage.enums import AttributionType, SourceType
from pulse_check.storage.models import Mention, MentionAttribution, Product

log = logging.getLogger(__name__)


def run_scrape(
    session: Session,
    run_config: RunConfig,
    product_set: ProductSet,
    *,
    state_file: str | Path | None = None,
) -> tuple[IngestStats, SecondaryAttributionStats, CommentInheritanceStats]:
    """Drain a full scrape for the given run config and persist to `session`.

    The caller owns the session's transaction lifetime. A fresh Scheduler is
    constructed at `state_file` (default: `settings.scheduler_db_path`).
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
        _enqueue_all_sources(scheduler, run_config, product_set)
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
            # /new — recent posts (catches breaking discussions, fresh reviews).
            scheduler.enqueue(
                url=_reddit_url(subreddit),
                source="reddit",
                anchors=all_anchors,
            )
            # /top?t=year — substantive year-over-year posts; far higher
            # product-mention density than /new on low-volume subs.
            scheduler.enqueue(
                url=_reddit_url(subreddit),
                source="reddit",
                anchors=all_anchors,
                sort="top",
                time_filter="year",
            )
            count += 2

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


def _enqueue_reddit_comment_followups(
    scheduler: Scheduler, session: Session, product_set: ProductSet
) -> int:
    """Enqueue `fetch_reddit_comments` for every distinct source_url of
    primary-attributed reddit_post mentions in the DB. Returns the job count.

    Anchors are passed identical to the listing pass so each comment runs
    through scrapers-lib's per-item regex attribution (`_fan_out`); a comment
    discussing a different product than the parent post lands attributed
    correctly on its own merit. Idempotent at the ingest layer (mention_id
    upsert), so re-running is safe.
    """
    all_anchors = to_anchors(product_set)
    if not all_anchors:
        return 0

    rows = session.execute(
        select(Mention.source_url)
        .join(MentionAttribution, MentionAttribution.mention_id == Mention.mention_id)
        .where(
            Mention.source_type == SourceType.REDDIT_POST,
            MentionAttribution.attribution_type == AttributionType.PRIMARY,
        )
        .distinct()
    ).all()

    count = 0
    for (url,) in rows:
        scheduler.enqueue(
            url=url,
            source="reddit_comments",
            anchors=all_anchors,
            # Bypass per-comment regex; pulse-check inherits parent-post
            # primary attribution as SECONDARY via apply_comment_inheritance.
            emit_all_comments=True,
        )
        count += 1

    log.info("enqueued %d reddit comment-fetch followups", count)
    return count
