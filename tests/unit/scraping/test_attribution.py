"""Secondary attribution pass tests."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from pulse_check.config.models import (
    AttributionPatterns,
    ProductConfig,
    ProductSet,
    ProductUrls,
)
from pulse_check.scraping.attribution import apply_secondary_attribution
from pulse_check.storage.enums import (
    AttributionMethod,
    AttributionType,
    SourceType,
)
from pulse_check.storage.models import Mention, MentionAttribution, Product


def _seed_products(session: Session) -> None:
    for pid, display in [
        ("alienware_16_aurora", "Alienware 16 Aurora"),
        ("rog_strix_g16", "ROG Strix G16"),
    ]:
        session.add(
            Product(
                product_id=pid,
                display_name=display,
                brand="x",
                aliases=[],
                attribution_patterns={},
                urls={},
            )
        )


def _mention(mention_id: str, text: str) -> Mention:
    return Mention(
        mention_id=mention_id,
        source_type=SourceType.REDDIT_POST,
        source_url=f"https://reddit.com/{mention_id}",
        raw_text=text,
        published_at=datetime(2026, 1, 15, tzinfo=UTC),
        metadata_={},
    )


def _product_set() -> ProductSet:
    return ProductSet(
        products=[
            ProductConfig(
                product_id="alienware_16_aurora",
                display_name="Alienware 16 Aurora",
                brand="Alienware",
                attribution_patterns=AttributionPatterns(
                    primary=[r"\balienware\s+16\s+aurora\b"],
                    secondary=[r"\balienware\s+aurora\b"],
                ),
                urls=ProductUrls(),
            ),
            ProductConfig(
                product_id="rog_strix_g16",
                display_name="ROG Strix G16",
                brand="ASUS ROG",
                attribution_patterns=AttributionPatterns(
                    primary=[r"\brog\s+strix\s+g16\b"],
                    secondary=[r"\bstrix\b"],
                ),
                urls=ProductUrls(),
            ),
        ]
    )


def test_secondary_adds_rows_where_regex_matches(session: Session) -> None:
    _seed_products(session)
    session.add(_mention("m_1", "Considered the Strix too but went with the ROG."))
    session.commit()

    stats = apply_secondary_attribution(session, _product_set())
    session.commit()

    assert stats.mentions_scanned == 1
    assert stats.new_attributions == 1

    attrs = session.query(MentionAttribution).all()
    assert len(attrs) == 1
    assert attrs[0].product_id == "rog_strix_g16"
    assert attrs[0].attribution_type is AttributionType.SECONDARY
    assert attrs[0].attribution_method is AttributionMethod.REGEX


def test_secondary_skipped_when_primary_already_exists(session: Session) -> None:
    _seed_products(session)
    session.add(_mention("m_1", "The Alienware 16 Aurora is great."))
    session.add(
        MentionAttribution(
            mention_id="m_1",
            product_id="alienware_16_aurora",
            attribution_type=AttributionType.PRIMARY,
            attribution_method=AttributionMethod.REGEX,
        )
    )
    session.commit()

    stats = apply_secondary_attribution(session, _product_set())

    assert stats.already_primary == 1
    assert stats.new_attributions == 0
    assert session.query(MentionAttribution).count() == 1  # only the original primary


def test_secondary_pass_is_idempotent(session: Session) -> None:
    _seed_products(session)
    session.add(_mention("m_1", "Considered the Strix too."))
    session.commit()

    first = apply_secondary_attribution(session, _product_set())
    session.commit()
    second = apply_secondary_attribution(session, _product_set())
    session.commit()

    assert first.new_attributions == 1
    assert second.new_attributions == 0
    assert second.already_secondary == 1
    assert session.query(MentionAttribution).count() == 1


def test_no_buildable_anchors_short_circuits(session: Session) -> None:
    _seed_products(session)
    session.add(_mention("m_1", "Some text."))
    session.commit()

    empty_set = ProductSet(
        products=[
            ProductConfig(
                product_id="alienware_16_aurora",
                display_name="Alienware 16 Aurora",
                brand="Alienware",
                attribution_patterns=AttributionPatterns(primary=[], secondary=[]),
                urls=ProductUrls(),
            ),
        ]
    )
    stats = apply_secondary_attribution(session, empty_set)

    assert stats.mentions_scanned == 0
    assert stats.new_attributions == 0


def test_mention_matching_multiple_products_gets_multiple_secondaries(
    session: Session,
) -> None:
    _seed_products(session)
    session.add(
        _mention(
            "m_1",
            "Torn between the Alienware 16 Aurora and the ROG Strix G16.",
        )
    )
    session.commit()

    stats = apply_secondary_attribution(session, _product_set())
    session.commit()

    assert stats.new_attributions == 2
    attrs = session.query(MentionAttribution).order_by(MentionAttribution.product_id).all()
    assert [a.product_id for a in attrs] == [
        "alienware_16_aurora",
        "rog_strix_g16",
    ]
    for a in attrs:
        assert a.attribution_type is AttributionType.SECONDARY
