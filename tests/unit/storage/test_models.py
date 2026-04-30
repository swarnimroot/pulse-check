"""Storage model tests.

Coverage priorities per TESTING §3:
- JSON column round-trip (lists + dicts)
- Timezone-aware datetime round-trip (SQLite stores as ISO strings; SQLAlchemy
  must hand them back with tzinfo)
- Unique constraint enforcement on aspect_tags + mention_attributions
- Nullable tombstone fields toggle correctly
- LlmCache keyed lookup + nullable parsed_output
- Brief narrative JSON preserves nested citation structure
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pulse_check.storage.enums import (
    Addressability,
    Aspect,
    AttributionMethod,
    AttributionType,
    Intensity,
    Polarity,
    ReasonBucket,
    ScopeType,
    SourceType,
)
from pulse_check.storage.models import (
    AggregateAspectSku,
    AggregatePairReason,
    AspectTag,
    Brief,
    DeliberationTag,
    LlmCache,
    Mention,
    MentionAttribution,
    PairWinRate,
    Product,
    ReasonTag,
    Run,
)


def _make_product(session: Session, product_id: str = "alienware_16_aurora") -> Product:
    product = Product(
        product_id=product_id,
        display_name="Alienware 16 Aurora",
        brand="Alienware",
        aliases=["16 Aurora", "Aurora 16"],
        attribution_patterns={"primary": [r"\balienware\s+16\s+aurora\b"]},
        urls={
            "bestbuy": "https://example.com/bb",
            "youtube_seeds": ["https://yt.example/1"],
        },
    )
    session.add(product)
    session.flush()
    return product


def _make_mention(session: Session, mention_id: str = "m_123") -> Mention:
    mention = Mention(
        mention_id=mention_id,
        source_type=SourceType.REDDIT_POST,
        source_url="https://reddit.com/r/GamingLaptops/comments/abc",
        published_at=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
        author="user123",
        raw_text="Great laptop, decent thermals but the fans are loud.",
        channel="GamingLaptops",
        metadata_={"upvotes": 42, "verified_purchase": True},
    )
    session.add(mention)
    session.flush()
    return mention


def _make_run(session: Session, run_id: str = "run_test_1") -> Run:
    run = Run(
        run_id=run_id,
        config_snapshot={"run_id": run_id},
        taxonomy_version="v0",
        prompt_versions={"aspect_tagging": "aspect_v1"},
    )
    session.add(run)
    session.flush()
    return run


# ---------------------------------------------------------------------------
# Product / Mention round-trips
# ---------------------------------------------------------------------------


def test_product_json_round_trip(session: Session) -> None:
    _make_product(session)
    session.commit()
    session.expire_all()

    fetched = session.get(Product, "alienware_16_aurora")
    assert fetched is not None
    assert fetched.aliases == ["16 Aurora", "Aurora 16"]
    assert fetched.urls["youtube_seeds"] == ["https://yt.example/1"]
    assert fetched.attribution_patterns["primary"] == [r"\balienware\s+16\s+aurora\b"]


def test_mention_timezone_round_trip(session: Session) -> None:
    _make_mention(session)
    session.commit()
    session.expire_all()

    fetched = session.get(Mention, "m_123")
    assert fetched is not None
    assert fetched.published_at is not None
    assert fetched.published_at.tzinfo is not None
    assert fetched.published_at == datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
    assert fetched.first_seen_at.tzinfo is not None
    assert fetched.metadata_ == {"upvotes": 42, "verified_purchase": True}


def test_mention_tombstone_fields_nullable_and_settable(session: Session) -> None:
    mention = _make_mention(session)
    session.commit()
    assert mention.tombstoned_at is None
    assert mention.tombstone_reason is None

    mention.tombstoned_at = datetime.now(UTC)
    mention.tombstone_reason = "reddit_404"
    session.commit()
    session.expire_all()

    fetched = session.get(Mention, "m_123")
    assert fetched is not None
    assert fetched.tombstoned_at is not None
    assert fetched.tombstone_reason == "reddit_404"


# ---------------------------------------------------------------------------
# Attribution unique constraint
# ---------------------------------------------------------------------------


def test_mention_attribution_unique_on_type(session: Session) -> None:
    _make_product(session)
    _make_mention(session)
    session.commit()

    session.add(
        MentionAttribution(
            mention_id="m_123",
            product_id="alienware_16_aurora",
            attribution_type=AttributionType.PRIMARY,
            attribution_method=AttributionMethod.URL,
        )
    )
    session.commit()

    # Second primary attribution for same (mention, product) violates uniqueness.
    session.add(
        MentionAttribution(
            mention_id="m_123",
            product_id="alienware_16_aurora",
            attribution_type=AttributionType.PRIMARY,
            attribution_method=AttributionMethod.REGEX,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    # Primary + secondary attributions for the same mention/product coexist.
    session.add(
        MentionAttribution(
            mention_id="m_123",
            product_id="alienware_16_aurora",
            attribution_type=AttributionType.SECONDARY,
            attribution_method=AttributionMethod.REGEX,
        )
    )
    session.commit()


# ---------------------------------------------------------------------------
# AspectTag unique constraint — the full taxonomy+prompt versioning key
# ---------------------------------------------------------------------------


def test_aspect_tag_unique_key_blocks_duplicate_and_permits_prompt_bump(
    session: Session,
) -> None:
    _make_product(session)
    _make_mention(session)
    session.commit()

    def _tag(prompt_version: str, polarity: Polarity) -> AspectTag:
        return AspectTag(
            mention_id="m_123",
            product_id="alienware_16_aurora",
            aspect=Aspect.THERMALS,
            polarity=polarity,
            intensity=Intensity.MEDIUM,
            taxonomy_version="v0",
            prompt_version=prompt_version,
            model="qwen2.5:7b-q4_K_M",
            temperature=0.0,
        )

    session.add(_tag("aspect_v1", Polarity.POSITIVE))
    session.commit()

    # Same tuple duplicates → IntegrityError.
    session.add(_tag("aspect_v1", Polarity.NEGATIVE))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    # Bumped prompt_version → new row permitted, reflecting re-tagging under v2 prompt.
    session.add(_tag("aspect_v2", Polarity.NEGATIVE))
    session.commit()

    rows = (
        session.query(AspectTag)
        .filter_by(mention_id="m_123", product_id="alienware_16_aurora")
        .order_by(AspectTag.prompt_version)
        .all()
    )
    assert [r.prompt_version for r in rows] == ["aspect_v1", "aspect_v2"]


# ---------------------------------------------------------------------------
# Deliberation + Reason + Aggregate + Brief round-trips
# ---------------------------------------------------------------------------


def test_deliberation_and_reason_tags_persist(session: Session) -> None:
    _make_product(session, "alienware_16_aurora")
    _make_product(session, "rog_strix_g16")
    thread = _make_mention(session, "m_thread")
    _make_mention(session, "m_comment")
    session.commit()

    session.add(
        DeliberationTag(
            thread_mention_id="m_thread",
            is_deliberation=True,
            is_resolved=True,
            products_discussed=["alienware_16_aurora", "rog_strix_g16"],
            chosen_product_id="rog_strix_g16",
            prompt_version="delib_v1",
            model="qwen2.5:7b-q4_K_M",
            temperature=0.0,
        )
    )
    session.add(
        ReasonTag(
            mention_id="m_comment",
            thread_mention_id="m_thread",
            winning_product_id="rog_strix_g16",
            reason_bucket=ReasonBucket.THERMALS,
            polarity=Polarity.POSITIVE,
            intensity=Intensity.HIGH,
            prompt_version="reason_v1",
            model="qwen2.5:7b-q4_K_M",
            temperature=0.0,
        )
    )
    session.commit()
    session.expire_all()

    delib = session.query(DeliberationTag).one()
    assert delib.is_resolved is True
    assert delib.products_discussed == ["alienware_16_aurora", "rog_strix_g16"]
    assert delib.chosen_product_id == "rog_strix_g16"

    reason = session.query(ReasonTag).one()
    assert reason.reason_bucket is ReasonBucket.THERMALS
    assert reason.intensity is Intensity.HIGH
    assert thread.mention_id == "m_thread"


def test_aggregate_aspect_sku_preserves_provenance(session: Session) -> None:
    _make_product(session)
    _make_run(session)
    session.commit()

    session.add(
        AggregateAspectSku(
            run_id="run_test_1",
            product_id="alienware_16_aurora",
            aspect=Aspect.THERMALS,
            total_mentions=3,
            polarity_counts={"negative": 2, "neutral": 0, "positive": 1},
            net_sentiment=-0.33,
            intensity_counts={
                "negative": {"low": 1, "medium": 1, "high": 0},
                "positive": {"low": 0, "medium": 1, "high": 0},
            },
            verified_share=0.67,
            by_source={"reddit_post": {"count": 2, "net_sentiment": -0.5}},
            by_recency={"last_30d": 1, "last_90d": 2, "older": 0},
            mention_ids=["m_1", "m_2", "m_3"],
        )
    )
    session.commit()
    session.expire_all()

    agg = session.query(AggregateAspectSku).one()
    assert agg.mention_ids == ["m_1", "m_2", "m_3"]
    assert agg.polarity_counts == {"negative": 2, "neutral": 0, "positive": 1}
    assert agg.intensity_counts["negative"]["medium"] == 1
    assert agg.computed_at.tzinfo is not None


def test_aggregate_pair_reason_and_win_rate(session: Session) -> None:
    _make_product(session, "alienware_16_aurora")
    _make_product(session, "rog_strix_g16")
    _make_run(session)
    session.commit()

    session.add(
        AggregatePairReason(
            run_id="run_test_1",
            pair_id="alienware_16_aurora_vs_rog_strix_g16",
            winning_product_id="rog_strix_g16",
            reason_bucket=ReasonBucket.THERMALS,
            total_mentions=12,
            intensity_counts={"low": 2, "medium": 6, "high": 4},
            addressability=Addressability.HARDWARE,
            addressability_rationale="Fan curve + chassis design cited.",
            representative_mention_ids=["m_1", "m_2"],
            mention_ids=["m_1", "m_2", "m_3"],
        )
    )
    session.add(
        PairWinRate(
            run_id="run_test_1",
            pair_id="alienware_16_aurora_vs_rog_strix_g16",
            product_a_id="alienware_16_aurora",
            product_b_id="rog_strix_g16",
            total_resolved_threads=20,
            a_wins=7,
            b_wins=12,
            ties=1,
            thread_mention_ids=["m_t1", "m_t2"],
        )
    )
    session.commit()
    session.expire_all()

    reason = session.query(AggregatePairReason).one()
    assert reason.addressability is Addressability.HARDWARE

    win = session.query(PairWinRate).one()
    assert win.a_wins + win.b_wins + win.ties == win.total_resolved_threads


def test_brief_citation_structure_round_trips(session: Session) -> None:
    _make_run(session)
    session.commit()

    session.add(
        Brief(
            run_id="run_test_1",
            scope_type=ScopeType.ASPECT_1_SKU,
            scope_id="alienware_16_aurora",
            narrative={
                "brief_title": "Alienware 16 Aurora — Voice",
                "sections": [
                    {
                        "heading": "Thermals",
                        "claims": [
                            {
                                "claim_text": "Reviewers consistently flag elevated fan noise.",
                                "cited_mention_ids": ["m_1", "m_2"],
                            }
                        ],
                    }
                ],
            },
            prompt_version="a1_brief_v1",
            model="claude-sonnet-4-6",
        )
    )
    session.commit()
    session.expire_all()

    brief = session.query(Brief).one()
    section = brief.narrative["sections"][0]
    assert section["claims"][0]["cited_mention_ids"] == ["m_1", "m_2"]


# ---------------------------------------------------------------------------
# LlmCache
# ---------------------------------------------------------------------------


def test_llm_cache_round_trip_and_nullable_parsed(session: Session) -> None:
    session.add(
        LlmCache(
            cache_key="a" * 64,
            input_hash="b" * 64,
            prompt_version="aspect_v1",
            model="qwen2.5:7b-q4_K_M",
            temperature=0.0,
            raw_output='{"aspects": []}',
            parsed_output={"aspects": []},
        )
    )
    session.add(
        LlmCache(
            cache_key="c" * 64,
            input_hash="d" * 64,
            prompt_version="aspect_v1",
            model="qwen2.5:7b-q4_K_M",
            temperature=0.0,
            raw_output="malformed",
            parsed_output=None,
        )
    )
    session.commit()
    session.expire_all()

    good = session.get(LlmCache, "a" * 64)
    assert good is not None
    assert good.parsed_output == {"aspects": []}
    assert good.created_at.tzinfo is not None

    bad = session.get(LlmCache, "c" * 64)
    assert bad is not None
    assert bad.parsed_output is None
