"""Orchestrator tests: product upsert idempotency + Reddit comment-fetch followups.

Covers two slices:

1. `_upsert_products` — session-5 deferred patch. Verifies insert / idempotent
   rerun / display_name update against the same `ProductSet` shape the gold-set
   sampler depends on (Patch 1 was production code, Patch 2 was these tests).

2. `_enqueue_reddit_comment_followups` — bite 6.2-revised. Verifies that the
   helper enqueues one `reddit_comments` job per distinct source_url of
   primary-attributed reddit_post mentions in the DB, dedups multi-product
   URLs, ignores secondary attributions and non-reddit-post mentions, and
   no-ops when the product set has no buildable anchors or the DB has no
   primary-attributed Reddit posts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from pulse_check.config.models import (
    ArticleRSSFeedSource,
    AttributionPatterns,
    ProductConfig,
    ProductSet,
    ProductUrls,
    RSSSources,
    RSSWindow,
    YouTubeChannelSource,
)
from pulse_check.scraping.orchestrator import (
    _enqueue_reddit_comment_followups,
    _enqueue_rss_discovered,
    _upsert_products,
)
from pulse_check.storage.enums import AttributionMethod, AttributionType, SourceType
from pulse_check.storage.models import Mention, MentionAttribution, Product

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pc(
    product_id: str,
    *,
    display_name: str | None = None,
    primary: list[str] | None = None,
) -> ProductConfig:
    return ProductConfig(
        product_id=product_id,
        display_name=display_name or product_id,
        brand="x",
        aliases=[],
        attribution_patterns=AttributionPatterns(
            primary=primary if primary is not None else [rf"\b{product_id}\b"],
        ),
        urls=ProductUrls(),
    )


def _ps(*products: ProductConfig) -> ProductSet:
    return ProductSet(products=list(products))


def _seed_product(session: Session, product_id: str) -> None:
    session.add(
        Product(
            product_id=product_id,
            display_name=product_id,
            brand="x",
            aliases=[],
            attribution_patterns={},
            urls={},
        )
    )


def _seed_mention(
    session: Session,
    *,
    mention_id: str,
    source_type: SourceType,
    source_url: str,
) -> None:
    session.add(
        Mention(
            mention_id=mention_id,
            source_type=source_type,
            source_url=source_url,
            raw_text=f"text for {mention_id}",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )


def _seed_attr(
    session: Session,
    *,
    mention_id: str,
    product_id: str,
    attribution_type: AttributionType,
) -> None:
    session.add(
        MentionAttribution(
            mention_id=mention_id,
            product_id=product_id,
            attribution_type=attribution_type,
            attribution_method=AttributionMethod.REGEX,
        )
    )


# ---------------------------------------------------------------------------
# `_upsert_products` (session-5 deferred Patch 2)
# ---------------------------------------------------------------------------


def test_upsert_inserts_new_products(session: Session) -> None:
    ps = _ps(_pc("alienware_16_aurora"), _pc("rog_strix_g16"))

    _upsert_products(session, ps)
    session.commit()

    rows = session.query(Product).order_by(Product.product_id).all()
    assert [r.product_id for r in rows] == ["alienware_16_aurora", "rog_strix_g16"]
    assert rows[0].display_name == "alienware_16_aurora"
    assert rows[0].brand == "x"


def test_upsert_is_idempotent_on_rerun(session: Session) -> None:
    ps = _ps(_pc("alienware_16_aurora"))

    _upsert_products(session, ps)
    session.commit()
    _upsert_products(session, ps)  # identical second call
    session.commit()

    assert session.query(Product).count() == 1


def test_upsert_updates_display_name_on_existing_row(session: Session) -> None:
    ps_v1 = _ps(_pc("alienware_16_aurora", display_name="Alienware 16 Aurora"))
    ps_v2 = _ps(_pc("alienware_16_aurora", display_name="Alienware 16 Aurora R2"))

    _upsert_products(session, ps_v1)
    session.commit()
    _upsert_products(session, ps_v2)
    session.commit()

    row = session.get(Product, "alienware_16_aurora")
    assert row is not None
    assert row.display_name == "Alienware 16 Aurora R2"
    assert session.query(Product).count() == 1


# ---------------------------------------------------------------------------
# `_enqueue_reddit_comment_followups` (bite 6.2-revised)
# ---------------------------------------------------------------------------


@pytest.fixture
def scheduler() -> MagicMock:
    return MagicMock()


def test_enqueues_one_job_per_distinct_primary_reddit_post_url(
    session: Session, scheduler: MagicMock
) -> None:
    _seed_product(session, "alienware_16_aurora")
    _seed_mention(
        session,
        mention_id="reddit_post_a",
        source_type=SourceType.REDDIT_POST,
        source_url="https://www.reddit.com/r/Alienware/comments/aaa/",
    )
    _seed_mention(
        session,
        mention_id="reddit_post_b",
        source_type=SourceType.REDDIT_POST,
        source_url="https://www.reddit.com/r/Alienware/comments/bbb/",
    )
    _seed_attr(
        session,
        mention_id="reddit_post_a",
        product_id="alienware_16_aurora",
        attribution_type=AttributionType.PRIMARY,
    )
    _seed_attr(
        session,
        mention_id="reddit_post_b",
        product_id="alienware_16_aurora",
        attribution_type=AttributionType.PRIMARY,
    )
    session.commit()

    count = _enqueue_reddit_comment_followups(
        scheduler, session, _ps(_pc("alienware_16_aurora"))
    )

    assert count == 2
    assert scheduler.enqueue.call_count == 2
    enqueued_urls = {c.kwargs["url"] for c in scheduler.enqueue.call_args_list}
    assert enqueued_urls == {
        "https://www.reddit.com/r/Alienware/comments/aaa/",
        "https://www.reddit.com/r/Alienware/comments/bbb/",
    }
    for c in scheduler.enqueue.call_args_list:
        assert c.kwargs["source"] == "reddit_comments"
        assert len(c.kwargs["anchors"]) == 1
        assert c.kwargs["anchors"][0].anchor_id == "alienware_16_aurora"


def test_returns_zero_when_no_primary_reddit_posts(
    session: Session, scheduler: MagicMock
) -> None:
    _seed_product(session, "alienware_16_aurora")
    session.commit()

    count = _enqueue_reddit_comment_followups(
        scheduler, session, _ps(_pc("alienware_16_aurora"))
    )

    assert count == 0
    scheduler.enqueue.assert_not_called()


def test_deduplicates_url_across_multi_product_attribution(
    session: Session, scheduler: MagicMock
) -> None:
    _seed_product(session, "alienware_16_aurora")
    _seed_product(session, "rog_strix_g16")
    _seed_mention(
        session,
        mention_id="reddit_post_shared",
        source_type=SourceType.REDDIT_POST,
        source_url="https://www.reddit.com/r/GamingLaptops/comments/shared/",
    )
    _seed_attr(
        session,
        mention_id="reddit_post_shared",
        product_id="alienware_16_aurora",
        attribution_type=AttributionType.PRIMARY,
    )
    _seed_attr(
        session,
        mention_id="reddit_post_shared",
        product_id="rog_strix_g16",
        attribution_type=AttributionType.PRIMARY,
    )
    session.commit()

    count = _enqueue_reddit_comment_followups(
        scheduler, session, _ps(_pc("alienware_16_aurora"), _pc("rog_strix_g16"))
    )

    assert count == 1
    assert scheduler.enqueue.call_count == 1
    # Both anchors are passed so a comment about either product attributes correctly.
    anchor_ids = {a.anchor_id for a in scheduler.enqueue.call_args.kwargs["anchors"]}
    assert anchor_ids == {"alienware_16_aurora", "rog_strix_g16"}


def test_ignores_secondary_attributions_and_non_reddit_post_sources(
    session: Session, scheduler: MagicMock
) -> None:
    _seed_product(session, "alienware_16_aurora")
    # Reddit post with PRIMARY — should be enqueued.
    _seed_mention(
        session,
        mention_id="reddit_post_primary",
        source_type=SourceType.REDDIT_POST,
        source_url="https://www.reddit.com/r/Alienware/comments/primary/",
    )
    _seed_attr(
        session,
        mention_id="reddit_post_primary",
        product_id="alienware_16_aurora",
        attribution_type=AttributionType.PRIMARY,
    )
    # Reddit post with only SECONDARY — must be excluded.
    _seed_mention(
        session,
        mention_id="reddit_post_secondary_only",
        source_type=SourceType.REDDIT_POST,
        source_url="https://www.reddit.com/r/Alienware/comments/secondary/",
    )
    _seed_attr(
        session,
        mention_id="reddit_post_secondary_only",
        product_id="alienware_16_aurora",
        attribution_type=AttributionType.SECONDARY,
    )
    # Non-reddit-post primary attribution — must be excluded.
    _seed_mention(
        session,
        mention_id="bestbuy_review_x",
        source_type=SourceType.BESTBUY_REVIEW,
        source_url="https://www.bestbuy.com/site/r/x.p",
    )
    _seed_attr(
        session,
        mention_id="bestbuy_review_x",
        product_id="alienware_16_aurora",
        attribution_type=AttributionType.PRIMARY,
    )
    session.commit()

    count = _enqueue_reddit_comment_followups(
        scheduler, session, _ps(_pc("alienware_16_aurora"))
    )

    assert count == 1
    enqueued_urls = [c.kwargs["url"] for c in scheduler.enqueue.call_args_list]
    assert enqueued_urls == ["https://www.reddit.com/r/Alienware/comments/primary/"]


def test_returns_zero_when_no_buildable_anchors(
    session: Session, scheduler: MagicMock
) -> None:
    # Product with empty primary patterns → to_anchors returns [] → no-op.
    _seed_product(session, "alienware_16_aurora")
    _seed_mention(
        session,
        mention_id="reddit_post_a",
        source_type=SourceType.REDDIT_POST,
        source_url="https://www.reddit.com/r/Alienware/comments/aaa/",
    )
    _seed_attr(
        session,
        mention_id="reddit_post_a",
        product_id="alienware_16_aurora",
        attribution_type=AttributionType.PRIMARY,
    )
    session.commit()

    count = _enqueue_reddit_comment_followups(
        scheduler,
        session,
        _ps(_pc("alienware_16_aurora", primary=[])),
    )

    assert count == 0
    scheduler.enqueue.assert_not_called()


# ---------------------------------------------------------------------------
# `_enqueue_rss_discovered` (bite: rss_discovery)
# ---------------------------------------------------------------------------


def _rss_sources_for_orch_test() -> RSSSources:
    return RSSSources(
        title_keywords=["review"],
        youtube_channels=[
            YouTubeChannelSource(
                handle="@x",
                display_name="x",
                channel_id="UCx",
                rss_url="https://yt.example/feed",
            )
        ],
        article_rss_feeds=[
            ArticleRSSFeedSource(site="ex", rss_url="https://art.example/feed")
        ],
    )


def test_enqueue_rss_discovered_enqueues_with_all_product_anchors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler = MagicMock()
    ps = _ps(_pc("alienware_16_aurora"), _pc("rog_strix_g16"))

    # Stub the discover() call inside orchestrator to a deterministic 2-item list.
    from pulse_check.scraping import orchestrator as orch
    from pulse_check.scraping.rss_discovery import DiscoveredItem, DiscoveryStats

    fake_items = [
        DiscoveredItem(
            url="https://yt.example/v/1",
            title="review yay",
            published_at=None,
            target_source="youtube",
            origin_feed="https://yt.example/feed",
        ),
        DiscoveredItem(
            url="https://art.example/a/1",
            title="review nay",
            published_at=None,
            target_source="article",
            origin_feed="https://art.example/feed",
        ),
    ]
    fake_stats = DiscoveryStats(
        feeds_polled=2,
        feeds_with_zero_entries=0,
        feeds_recovered_by_html_fallback=0,
        items_seen=2,
        items_after_title_filter=2,
        items_after_window_filter=2,
    )
    monkeypatch.setattr(
        orch, "discover", lambda *_args, **_kwargs: (fake_items, fake_stats)
    )

    count = _enqueue_rss_discovered(
        scheduler, ps, _rss_sources_for_orch_test(), RSSWindow(enabled=True)
    )

    assert count == 2
    assert scheduler.enqueue.call_count == 2
    # Each call gets all-product anchors and the target source.
    calls = scheduler.enqueue.call_args_list
    sources = [c.kwargs["source"] for c in calls]
    assert sources == ["youtube", "article"]
    for c in calls:
        anchors = c.kwargs["anchors"]
        assert {a.anchor_id for a in anchors} == {
            "alienware_16_aurora",
            "rog_strix_g16",
        }


def test_enqueue_rss_discovered_noop_when_no_buildable_anchors() -> None:
    scheduler = MagicMock()
    ps = _ps(_pc("alienware_16_aurora", primary=[]))  # no patterns → no anchor

    count = _enqueue_rss_discovered(
        scheduler, ps, _rss_sources_for_orch_test(), RSSWindow(enabled=True)
    )

    assert count == 0
    scheduler.enqueue.assert_not_called()
