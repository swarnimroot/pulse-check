"""Tests for the deterministic A1 verbatim selector.

Selector queries `aspect_tags` directly, so each test inserts the rows it
needs into the in-memory DB via the shared `session` fixture.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from pulse_check.storage.enums import (
    Aspect,
    AttributionType,
    Intensity,
    Polarity,
    SourceType,
)
from pulse_check.storage.models import AspectTag, Mention, Product
from pulse_check.synthesis.selector import (
    SELECTOR_PER_BUCKET_CAP,
    AspectSelection,
    select_a1_verbatims,
)

_PRODUCT_ID = "alienware_16"


def _add_product(session: Session) -> None:
    session.add(Product(product_id=_PRODUCT_ID, display_name="Alienware 16", brand="dell"))
    session.flush()


def _add_mention(session: Session, mid: str) -> None:
    session.add(
        Mention(
            mention_id=mid,
            source_type=SourceType.REDDIT_POST,
            source_url="https://example.com",
            raw_text=f"text-{mid}",
        )
    )


def _add_tag(
    session: Session,
    *,
    mention_id: str,
    aspect: Aspect,
    polarity: Polarity,
    intensity: Intensity,
) -> None:
    session.add(
        AspectTag(
            mention_id=mention_id,
            product_id=_PRODUCT_ID,
            aspect=aspect,
            polarity=polarity,
            intensity=intensity,
            taxonomy_version="v0",
            prompt_version="aspect_v1",
            model="qwen",
            temperature=0.0,
        )
    )


def test_empty_pools_return_empty_selection(session: Session) -> None:
    _add_product(session)
    session.commit()

    out = select_a1_verbatims(
        session,
        product_id=_PRODUCT_ID,
        aspect=Aspect.BATTERY,
        primary_mention_pool=[],
        secondary_mention_pool=[],
    )

    assert out == AspectSelection(Aspect.BATTERY, (), (), (), ())


def test_primary_positive_picks_high_intensity_first(session: Session) -> None:
    _add_product(session)
    for mid, intensity in [
        ("m1", Intensity.LOW),
        ("m2", Intensity.HIGH),
        ("m3", Intensity.MEDIUM),
    ]:
        _add_mention(session, mid)
        _add_tag(
            session,
            mention_id=mid,
            aspect=Aspect.PERFORMANCE,
            polarity=Polarity.POSITIVE,
            intensity=intensity,
        )
    session.commit()

    out = select_a1_verbatims(
        session,
        product_id=_PRODUCT_ID,
        aspect=Aspect.PERFORMANCE,
        primary_mention_pool=["m1", "m2", "m3"],
        secondary_mention_pool=[],
    )

    assert [v.mention_id for v in out.primary_positive] == ["m2", "m3", "m1"]
    assert out.primary_negative == ()
    assert out.secondary_positive == ()
    assert out.secondary_negative == ()


def test_caps_at_three_per_polarity(session: Session) -> None:
    _add_product(session)
    for i in range(5):
        mid = f"m{i}"
        _add_mention(session, mid)
        _add_tag(
            session,
            mention_id=mid,
            aspect=Aspect.DISPLAY,
            polarity=Polarity.POSITIVE,
            intensity=Intensity.HIGH,
        )
    session.commit()

    out = select_a1_verbatims(
        session,
        product_id=_PRODUCT_ID,
        aspect=Aspect.DISPLAY,
        primary_mention_pool=[f"m{i}" for i in range(5)],
        secondary_mention_pool=[],
    )

    assert len(out.primary_positive) == SELECTOR_PER_BUCKET_CAP
    # Tied on intensity → mention_id asc tiebreak
    assert [v.mention_id for v in out.primary_positive] == ["m0", "m1", "m2"]


def test_secondary_pool_routed_to_secondary_bucket(session: Session) -> None:
    _add_product(session)
    _add_mention(session, "m1")
    _add_tag(
        session,
        mention_id="m1",
        aspect=Aspect.KEYBOARD,
        polarity=Polarity.NEGATIVE,
        intensity=Intensity.MEDIUM,
    )
    session.commit()

    out = select_a1_verbatims(
        session,
        product_id=_PRODUCT_ID,
        aspect=Aspect.KEYBOARD,
        primary_mention_pool=[],
        secondary_mention_pool=["m1"],
    )

    assert len(out.secondary_negative) == 1
    sv = out.secondary_negative[0]
    assert sv.bucket == AttributionType.SECONDARY
    assert sv.polarity == Polarity.NEGATIVE
    assert out.primary_positive == ()


def test_dedup_collapses_cluster_to_one(session: Session) -> None:
    _add_product(session)
    for mid in ["m1", "m2", "m3"]:
        _add_mention(session, mid)
        _add_tag(
            session,
            mention_id=mid,
            aspect=Aspect.THERMALS,
            polarity=Polarity.NEGATIVE,
            intensity=Intensity.HIGH,
        )
    session.commit()

    out = select_a1_verbatims(
        session,
        product_id=_PRODUCT_ID,
        aspect=Aspect.THERMALS,
        primary_mention_pool=["m1", "m2", "m3"],
        secondary_mention_pool=[],
        clusters={"m1": "c0", "m2": "c0", "m3": "c1"},
    )

    picked_ids = [v.mention_id for v in out.primary_negative]
    assert len(picked_ids) == 2
    assert "m3" in picked_ids
    # Either m1 or m2 — both share cluster c0; mention_id asc tiebreak picks m1
    assert "m1" in picked_ids
    assert "m2" not in picked_ids


def test_neutral_polarity_never_cited(session: Session) -> None:
    _add_product(session)
    _add_mention(session, "m1")
    _add_tag(
        session,
        mention_id="m1",
        aspect=Aspect.AESTHETICS,
        polarity=Polarity.NEUTRAL,
        intensity=Intensity.HIGH,
    )
    session.commit()

    out = select_a1_verbatims(
        session,
        product_id=_PRODUCT_ID,
        aspect=Aspect.AESTHETICS,
        primary_mention_pool=["m1"],
        secondary_mention_pool=[],
    )

    assert out.primary_positive == ()
    assert out.primary_negative == ()


def test_pool_member_without_aspect_tag_silently_skipped(session: Session) -> None:
    _add_product(session)
    _add_mention(session, "m1")  # no aspect_tag row
    session.commit()

    out = select_a1_verbatims(
        session,
        product_id=_PRODUCT_ID,
        aspect=Aspect.PORTABILITY,
        primary_mention_pool=["m1"],
        secondary_mention_pool=[],
    )

    assert out.primary_positive == ()


def test_clusters_none_means_no_dedup(session: Session) -> None:
    _add_product(session)
    for mid in ["m1", "m2"]:
        _add_mention(session, mid)
        _add_tag(
            session,
            mention_id=mid,
            aspect=Aspect.BATTERY,
            polarity=Polarity.POSITIVE,
            intensity=Intensity.MEDIUM,
        )
    session.commit()

    out = select_a1_verbatims(
        session,
        product_id=_PRODUCT_ID,
        aspect=Aspect.BATTERY,
        primary_mention_pool=["m1", "m2"],
        secondary_mention_pool=[],
        clusters=None,
    )

    assert len(out.primary_positive) == 2


def test_polarity_split_within_aspect(session: Session) -> None:
    _add_product(session)
    _add_mention(session, "p1")
    _add_mention(session, "n1")
    _add_tag(
        session,
        mention_id="p1",
        aspect=Aspect.PRICE_VALUE,
        polarity=Polarity.POSITIVE,
        intensity=Intensity.HIGH,
    )
    _add_tag(
        session,
        mention_id="n1",
        aspect=Aspect.PRICE_VALUE,
        polarity=Polarity.NEGATIVE,
        intensity=Intensity.LOW,
    )
    session.commit()

    out = select_a1_verbatims(
        session,
        product_id=_PRODUCT_ID,
        aspect=Aspect.PRICE_VALUE,
        primary_mention_pool=["p1", "n1"],
        secondary_mention_pool=[],
    )

    assert [v.mention_id for v in out.primary_positive] == ["p1"]
    assert [v.mention_id for v in out.primary_negative] == ["n1"]
