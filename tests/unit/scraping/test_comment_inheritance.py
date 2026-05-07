"""Tests for `apply_comment_inheritance`.

Covers the post-ingest fallback that gives unattributed reddit_comments
SECONDARY attribution by inheriting from their parent reddit_post — used
in tandem with `fetch_reddit_comments(emit_all_comments=True)` for the
Reddit-deepen path.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from pulse_check.scraping.comment_inheritance import (
    _post_id_from_post_mention_id,
    apply_comment_inheritance,
)
from pulse_check.storage.enums import AttributionMethod, AttributionType, SourceType
from pulse_check.storage.models import Mention, MentionAttribution, Product

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _seed_post(
    session: Session,
    *,
    post_id: str,
    anchor_id: str,
) -> str:
    """Seed a reddit_post Mention + a PRIMARY MentionAttribution. Returns mention_id."""
    mention_id = f"reddit_post_{post_id}_{anchor_id}"
    session.add(
        Mention(
            mention_id=mention_id,
            source_type=SourceType.REDDIT_POST,
            source_url=f"https://www.reddit.com/comments/{post_id}/",
            raw_text=f"post text {post_id}",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    session.add(
        MentionAttribution(
            mention_id=mention_id,
            product_id=anchor_id,
            attribution_type=AttributionType.PRIMARY,
            attribution_method=AttributionMethod.REGEX,
        )
    )
    return mention_id


def _seed_comment(
    session: Session,
    *,
    comment_id: str,
    parent_post_id: str | None,
) -> str:
    """Seed a reddit_comment Mention. parent_post_id=None means metadata
    has no parent_id (simulates a malformed/missing-link case)."""
    mention_id = f"reddit_comment_{comment_id}"
    metadata: dict[str, object] = {}
    if parent_post_id is not None:
        metadata["parent_id"] = f"t3_{parent_post_id}"
    session.add(
        Mention(
            mention_id=mention_id,
            source_type=SourceType.REDDIT_COMMENT,
            source_url=f"https://www.reddit.com/comments/{parent_post_id or 'x'}/_/{comment_id}",
            raw_text=f"comment text {comment_id}",
            published_at=datetime(2026, 1, 2, tzinfo=UTC),
            metadata_=metadata,
        )
    )
    return mention_id


# ---------------------------------------------------------------------------
# `_post_id_from_post_mention_id` helper
# ---------------------------------------------------------------------------


def test_post_id_helper_single_anchor_id() -> None:
    assert (
        _post_id_from_post_mention_id("reddit_post_1t3vw6v_alienware_16_aurora")
        == "1t3vw6v"
    )


def test_post_id_helper_no_anchor_suffix() -> None:
    # Defensive: if a post somehow lacks the anchor suffix, still return the post_id.
    assert _post_id_from_post_mention_id("reddit_post_1t3vw6v") == "1t3vw6v"


def test_post_id_helper_rejects_non_reddit_post() -> None:
    assert _post_id_from_post_mention_id("reddit_comment_xyz") is None
    assert _post_id_from_post_mention_id("amazon_review_42") is None


def test_post_id_helper_rejects_empty() -> None:
    assert _post_id_from_post_mention_id("reddit_post_") is None


# ---------------------------------------------------------------------------
# `apply_comment_inheritance`
# ---------------------------------------------------------------------------


def test_inherits_single_product_from_parent_post(session: Session) -> None:
    _seed_product(session, "alienware_16_aurora")
    _seed_post(session, post_id="aaa", anchor_id="alienware_16_aurora")
    comment_id = _seed_comment(session, comment_id="c1", parent_post_id="aaa")
    session.commit()

    stats = apply_comment_inheritance(session)
    session.commit()

    assert stats.new_attributions == 1
    assert stats.comments_scanned == 1
    rows = session.query(MentionAttribution).filter_by(mention_id=comment_id).all()
    assert len(rows) == 1
    assert rows[0].product_id == "alienware_16_aurora"
    assert rows[0].attribution_type == AttributionType.SECONDARY
    assert rows[0].attribution_method == AttributionMethod.REGEX


def test_inherits_all_products_from_multi_attributed_parent(session: Session) -> None:
    _seed_product(session, "alienware_16_aurora")
    _seed_product(session, "rog_strix_g16")
    # Same Reddit post primary-attributed to both products via dual fan-out.
    _seed_post(session, post_id="bbb", anchor_id="alienware_16_aurora")
    _seed_post(session, post_id="bbb", anchor_id="rog_strix_g16")
    comment_id = _seed_comment(session, comment_id="c2", parent_post_id="bbb")
    session.commit()

    stats = apply_comment_inheritance(session)
    session.commit()

    assert stats.new_attributions == 2
    rows = session.query(MentionAttribution).filter_by(mention_id=comment_id).all()
    products = sorted(r.product_id for r in rows)
    assert products == ["alienware_16_aurora", "rog_strix_g16"]
    assert all(r.attribution_type == AttributionType.SECONDARY for r in rows)


def test_skips_comment_with_missing_parent_id(session: Session) -> None:
    _seed_product(session, "alienware_16_aurora")
    _seed_post(session, post_id="aaa", anchor_id="alienware_16_aurora")
    _seed_comment(session, comment_id="orphan", parent_post_id=None)
    session.commit()

    stats = apply_comment_inheritance(session)

    assert stats.new_attributions == 0
    assert stats.skipped_no_parent == 1


def test_skips_comment_when_parent_not_in_db(session: Session) -> None:
    _seed_product(session, "alienware_16_aurora")
    _seed_comment(session, comment_id="lonely", parent_post_id="not_in_db")
    session.commit()

    stats = apply_comment_inheritance(session)

    assert stats.new_attributions == 0
    assert stats.skipped_parent_not_attributed == 1


def test_skips_comment_already_attributed(session: Session) -> None:
    _seed_product(session, "alienware_16_aurora")
    _seed_post(session, post_id="aaa", anchor_id="alienware_16_aurora")
    comment_id = _seed_comment(session, comment_id="c3", parent_post_id="aaa")
    # Pre-existing PRIMARY attribution (e.g. comment text matched anchor regex).
    session.add(
        MentionAttribution(
            mention_id=comment_id,
            product_id="alienware_16_aurora",
            attribution_type=AttributionType.PRIMARY,
            attribution_method=AttributionMethod.REGEX,
        )
    )
    session.commit()

    stats = apply_comment_inheritance(session)

    assert stats.new_attributions == 0
    assert stats.skipped_already_attributed == 0  # filtered before scan
    rows = session.query(MentionAttribution).filter_by(mention_id=comment_id).all()
    assert len(rows) == 1  # still just the original primary, no inherited row
    assert rows[0].attribution_type == AttributionType.PRIMARY


def test_idempotent_on_rerun(session: Session) -> None:
    _seed_product(session, "alienware_16_aurora")
    _seed_post(session, post_id="aaa", anchor_id="alienware_16_aurora")
    _seed_comment(session, comment_id="c4", parent_post_id="aaa")
    session.commit()

    apply_comment_inheritance(session)
    session.commit()
    second = apply_comment_inheritance(session)
    session.commit()

    assert second.new_attributions == 0
    assert second.comments_scanned == 0  # comment now has an attribution → filtered
    assert session.query(MentionAttribution).count() == 2  # 1 post primary + 1 comment secondary


def test_only_touches_reddit_comments(session: Session) -> None:
    _seed_product(session, "alienware_16_aurora")
    _seed_post(session, post_id="aaa", anchor_id="alienware_16_aurora")
    # A non-comment mention (BestBuy review) with NO attribution and a parent_id
    # in metadata — must not be touched by the inheritance pass.
    session.add(
        Mention(
            mention_id="bestbuy_review_x",
            source_type=SourceType.BESTBUY_REVIEW,
            source_url="https://www.bestbuy.com/site/r/x.p",
            raw_text="bestbuy review",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
            metadata_={"parent_id": "t3_aaa"},
        )
    )
    session.commit()

    stats = apply_comment_inheritance(session)

    assert stats.comments_scanned == 0
    assert stats.new_attributions == 0
    assert (
        session.query(MentionAttribution).filter_by(mention_id="bestbuy_review_x").count()
        == 0
    )
