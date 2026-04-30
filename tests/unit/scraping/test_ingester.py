"""Ingester tests: upsert-mention + append-attribution pattern, dedup, ProductSnapshot skip."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from scrapers_lib import ProductSnapshot, RawMention
from scrapers_lib.core.schemas import Attribution
from sqlalchemy.orm import Session

from pulse_check.scraping.ingester import ingest_batch
from pulse_check.storage.models import Mention, MentionAttribution, Product


def _make_product(session: Session, product_id: str) -> None:
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


def _rm(
    *,
    mention_id: str = "reddit_post_abc",
    anchor_id: str | None = "alienware_16_aurora",
    raw_text: str = "The Alienware 16 Aurora runs hot.",
) -> RawMention:
    attribution = (
        Attribution(anchor_id=anchor_id, confidence=1.0, method="regex")
        if anchor_id is not None
        else None
    )
    return RawMention(
        mention_id=mention_id,
        source="reddit",
        source_type="post",
        source_url="https://reddit.com/r/GamingLaptops/comments/abc",
        raw_text=raw_text,
        published_at=datetime(2026, 1, 15, tzinfo=UTC),
        attribution=attribution,
    )


def test_new_mention_inserts_row_and_primary_attribution(session: Session) -> None:
    _make_product(session, "alienware_16_aurora")
    session.commit()

    stats = ingest_batch(session, [_rm()])

    assert stats.new_mentions == 1
    assert stats.new_attributions == 1
    assert stats.existing_mentions == 0

    rows = session.query(Mention).all()
    assert len(rows) == 1
    assert rows[0].mention_id == "reddit_post_abc"

    attrs = session.query(MentionAttribution).all()
    assert len(attrs) == 1
    assert attrs[0].product_id == "alienware_16_aurora"


def test_two_mentions_same_id_different_anchors_dedup_mention_add_attrs(
    session: Session,
) -> None:
    _make_product(session, "alienware_16_aurora")
    _make_product(session, "rog_strix_g16")
    session.commit()

    batch = [
        _rm(mention_id="reddit_post_same", anchor_id="alienware_16_aurora"),
        _rm(mention_id="reddit_post_same", anchor_id="rog_strix_g16"),
    ]
    stats = ingest_batch(session, batch)

    assert stats.new_mentions == 1
    assert stats.existing_mentions == 1
    assert stats.new_attributions == 2

    assert session.query(Mention).count() == 1
    attrs = session.query(MentionAttribution).order_by(MentionAttribution.product_id).all()
    assert [a.product_id for a in attrs] == ["alienware_16_aurora", "rog_strix_g16"]


def test_reingest_is_idempotent(session: Session) -> None:
    _make_product(session, "alienware_16_aurora")
    session.commit()

    ingest_batch(session, [_rm()])
    session.commit()
    stats = ingest_batch(session, [_rm()])  # identical payload

    assert stats.new_mentions == 0
    assert stats.existing_mentions == 1
    assert stats.new_attributions == 0
    assert stats.existing_attributions == 1
    assert session.query(MentionAttribution).count() == 1


def test_mention_without_attribution_still_persists(session: Session) -> None:
    stats = ingest_batch(session, [_rm(anchor_id=None)])

    assert stats.new_mentions == 1
    assert stats.new_attributions == 0
    assert stats.skipped_without_attribution == 1
    assert session.query(Mention).count() == 1
    assert session.query(MentionAttribution).count() == 0


def test_product_snapshot_is_skipped_with_counter(session: Session) -> None:
    snapshot = ProductSnapshot(
        source="amazon",
        source_id="B0AW16A",
        anchor_id="alienware_16_aurora",
        url="https://www.amazon.com/dp/B0AW16A",
        title="Alienware 16 Aurora",
        price=Decimal("2499.99"),
    )
    stats = ingest_batch(session, [snapshot])

    assert stats.skipped_snapshots == 1
    assert stats.new_mentions == 0
    assert session.query(Mention).count() == 0
