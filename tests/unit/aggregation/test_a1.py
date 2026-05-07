"""A1 aggregator tests.

Coverage priorities:
- Happy path: distinct (product, aspect) groups, mention_ids sorted+deduped
- polarity_counts / intensity_counts zero-filled
- net_sentiment formula correct on a known mix (flat per-mention, no weighting)
- verified_share counts metadata_["verified_purchase"] is True; missing key is False
- by_source carries per-source totals + polarity_counts
- by_recency buckets correctly across all 5 buckets including unknown
- Out-of-scope products skipped
- (taxonomy_version, prompt_version) filter scoped correctly
- Idempotent rerun produces the same row count + values
- Empty product set / no matching tags → no-op
- Option 3 dual-track:
  - PRIMARY-only path: SECONDARY columns zero/empty (legacy preserved)
  - SECONDARY-only path: PRIMARY columns zero/empty, SECONDARY populated
  - Mixed path: both buckets populated independently for the same (P, A)
  - PRIMARY precedence: a (mention, product) attributed both ways lands in PRIMARY only
  - SECONDARY out-of-scope products excluded
  - Idempotent rerun preserves both buckets
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from pulse_check.aggregation.a1 import BatchAggregateStats, aggregate_a1
from pulse_check.storage.enums import (
    Aspect,
    AttributionMethod,
    AttributionType,
    Intensity,
    Polarity,
    SourceType,
)
from pulse_check.storage.models import (
    AggregateAspectSku,
    AspectTag,
    Mention,
    MentionAttribution,
    Product,
    Run,
)

_TAX = "v0"
_PROMPT = "aspect_classifier_v1"
_RUN = "run_test"
_NOW = datetime(2026, 4, 30, tzinfo=UTC)


def _make_run(session: Session, run_id: str = _RUN) -> Run:
    r = Run(
        run_id=run_id,
        config_snapshot={},
        taxonomy_version=_TAX,
        prompt_versions={},
    )
    session.add(r)
    return r


def _make_product(session: Session, product_id: str) -> Product:
    p = Product(
        product_id=product_id,
        display_name=product_id.replace("_", " ").title(),
        brand="brand",
    )
    session.add(p)
    return p


def _make_mention(
    session: Session,
    mention_id: str,
    *,
    source_type: SourceType = SourceType.REDDIT_POST,
    published_at: datetime | None = None,
    verified: bool | None = None,
) -> Mention:
    metadata: dict[str, Any] = {}
    if verified is not None:
        metadata["verified_purchase"] = verified
    m = Mention(
        mention_id=mention_id,
        source_type=source_type,
        source_url=f"https://example.com/{mention_id}",
        raw_text="text",
        published_at=published_at,
        metadata_=metadata,
    )
    session.add(m)
    return m


def _attach(
    session: Session,
    mention_id: str,
    product_id: str,
    *,
    attribution_type: AttributionType = AttributionType.PRIMARY,
) -> MentionAttribution:
    a = MentionAttribution(
        mention_id=mention_id,
        product_id=product_id,
        attribution_type=attribution_type,
        attribution_method=AttributionMethod.REGEX,
    )
    session.add(a)
    return a


def _tag(
    session: Session,
    mention_id: str,
    product_id: str,
    aspect: Aspect,
    polarity: Polarity,
    intensity: Intensity,
    *,
    taxonomy_version: str = _TAX,
    prompt_version: str = _PROMPT,
) -> AspectTag:
    t = AspectTag(
        mention_id=mention_id,
        product_id=product_id,
        aspect=aspect,
        polarity=polarity,
        intensity=intensity,
        classifier_confidence=0.9,
        taxonomy_version=taxonomy_version,
        prompt_version=prompt_version,
        model="qwen2.5:7b-q4_K_M",
        temperature=0.0,
    )
    session.add(t)
    return t


def _rows_by_key(session: Session) -> dict[tuple[str, str], AggregateAspectSku]:
    return {
        (r.product_id, r.aspect.value): r
        for r in session.query(AggregateAspectSku).all()
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_aggregate_a1_happy_path(session: Session) -> None:
    _make_run(session)
    _make_product(session, "aw16")
    _make_product(session, "strix")
    _make_mention(session, "m1", published_at=_NOW - timedelta(days=10))
    _make_mention(session, "m2", published_at=_NOW - timedelta(days=20))
    _make_mention(session, "m3", published_at=_NOW - timedelta(days=5))
    _attach(session, "m1", "aw16")
    _attach(session, "m2", "aw16")
    _attach(session, "m3", "strix")
    _tag(session, "m1", "aw16", Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)
    _tag(session, "m2", "aw16", Aspect.THERMALS, Polarity.NEGATIVE, Intensity.MEDIUM)
    _tag(session, "m3", "strix", Aspect.PERFORMANCE, Polarity.POSITIVE, Intensity.HIGH)
    session.flush()

    stats = aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16", "strix"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    assert stats == BatchAggregateStats(
        groups_seen=2, aggregates_upserted=2, mentions_contributing=3
    )
    rows = _rows_by_key(session)
    aw16 = rows[("aw16", "thermals")]
    assert aw16.total_mentions == 2
    assert aw16.polarity_counts == {"negative": 2, "neutral": 0, "positive": 0}
    assert aw16.net_sentiment == -1.0
    assert aw16.intensity_counts == {"low": 0, "medium": 1, "high": 1}
    assert aw16.mention_ids == ["m1", "m2"]
    strix = rows[("strix", "performance")]
    assert strix.polarity_counts == {"negative": 0, "neutral": 0, "positive": 1}
    assert strix.net_sentiment == 1.0
    assert strix.mention_ids == ["m3"]


# ---------------------------------------------------------------------------
# Zero-fill distributions
# ---------------------------------------------------------------------------


def test_aggregate_a1_polarity_intensity_zero_fill(session: Session) -> None:
    _make_run(session)
    _make_product(session, "aw16")
    _make_mention(session, "m1", published_at=_NOW - timedelta(days=1))
    _attach(session, "m1", "aw16")
    _tag(session, "m1", "aw16", Aspect.THERMALS, Polarity.NEUTRAL, Intensity.LOW)
    session.flush()

    aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    row = _rows_by_key(session)[("aw16", "thermals")]
    assert row.polarity_counts == {"negative": 0, "neutral": 1, "positive": 0}
    assert row.intensity_counts == {"low": 1, "medium": 0, "high": 0}


# ---------------------------------------------------------------------------
# Net sentiment formula
# ---------------------------------------------------------------------------


def test_aggregate_a1_net_sentiment_formula(session: Session) -> None:
    _make_run(session)
    _make_product(session, "aw16")
    # 3 positive, 1 negative, 1 neutral → (3 - 1) / 5 = 0.4
    for i in range(3):
        _make_mention(session, f"p{i}", published_at=_NOW - timedelta(days=10))
        _attach(session, f"p{i}", "aw16")
        _tag(session, f"p{i}", "aw16", Aspect.PERFORMANCE, Polarity.POSITIVE, Intensity.MEDIUM)
    _make_mention(session, "n1", published_at=_NOW - timedelta(days=10))
    _attach(session, "n1", "aw16")
    _tag(session, "n1", "aw16", Aspect.PERFORMANCE, Polarity.NEGATIVE, Intensity.MEDIUM)
    _make_mention(session, "u1", published_at=_NOW - timedelta(days=10))
    _attach(session, "u1", "aw16")
    _tag(session, "u1", "aw16", Aspect.PERFORMANCE, Polarity.NEUTRAL, Intensity.MEDIUM)
    session.flush()

    aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    row = _rows_by_key(session)[("aw16", "performance")]
    assert row.total_mentions == 5
    assert row.net_sentiment == 0.4


# ---------------------------------------------------------------------------
# Verified share
# ---------------------------------------------------------------------------


def test_aggregate_a1_verified_share(session: Session) -> None:
    _make_run(session)
    _make_product(session, "aw16")
    _make_mention(
        session, "vt", source_type=SourceType.AMAZON_REVIEW,
        published_at=_NOW - timedelta(days=10), verified=True,
    )
    _make_mention(
        session, "vf", source_type=SourceType.AMAZON_REVIEW,
        published_at=_NOW - timedelta(days=10), verified=False,
    )
    _make_mention(
        session, "vn", source_type=SourceType.REDDIT_POST,
        published_at=_NOW - timedelta(days=10),
    )
    for mid in ("vt", "vf", "vn"):
        _attach(session, mid, "aw16")
        _tag(session, mid, "aw16", Aspect.BUILD_QUALITY, Polarity.POSITIVE, Intensity.MEDIUM)
    session.flush()

    aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    row = _rows_by_key(session)[("aw16", "build_quality")]
    assert row.verified_share == 1 / 3


# ---------------------------------------------------------------------------
# By-source split
# ---------------------------------------------------------------------------


def test_aggregate_a1_by_source_split(session: Session) -> None:
    _make_run(session)
    _make_product(session, "aw16")
    _make_mention(
        session, "r1", source_type=SourceType.REDDIT_POST,
        published_at=_NOW - timedelta(days=10),
    )
    _make_mention(
        session, "a1", source_type=SourceType.AMAZON_REVIEW,
        published_at=_NOW - timedelta(days=10),
    )
    _attach(session, "r1", "aw16")
    _attach(session, "a1", "aw16")
    _tag(session, "r1", "aw16", Aspect.DISPLAY, Polarity.POSITIVE, Intensity.HIGH)
    _tag(session, "a1", "aw16", Aspect.DISPLAY, Polarity.NEGATIVE, Intensity.LOW)
    session.flush()

    aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    row = _rows_by_key(session)[("aw16", "display")]
    assert set(row.by_source.keys()) == {"reddit_post", "amazon_review"}
    assert row.by_source["reddit_post"]["total"] == 1
    assert row.by_source["reddit_post"]["polarity_counts"]["positive"] == 1
    assert row.by_source["amazon_review"]["polarity_counts"]["negative"] == 1


# ---------------------------------------------------------------------------
# By-recency buckets
# ---------------------------------------------------------------------------


def test_aggregate_a1_by_recency_buckets(session: Session) -> None:
    _make_run(session)
    _make_product(session, "aw16")
    _make_mention(session, "m_recent", published_at=_NOW - timedelta(days=5))
    _make_mention(session, "m_30_90", published_at=_NOW - timedelta(days=60))
    _make_mention(session, "m_90_180", published_at=_NOW - timedelta(days=120))
    _make_mention(session, "m_old", published_at=_NOW - timedelta(days=300))
    _make_mention(session, "m_unknown", published_at=None)
    for mid in ("m_recent", "m_30_90", "m_90_180", "m_old", "m_unknown"):
        _attach(session, mid, "aw16")
        _tag(session, mid, "aw16", Aspect.PORTABILITY, Polarity.POSITIVE, Intensity.MEDIUM)
    session.flush()

    aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    row = _rows_by_key(session)[("aw16", "portability")]
    assert row.by_recency == {
        "0_30": 1,
        "30_90": 1,
        "90_180": 1,
        "180_plus": 1,
        "unknown": 1,
    }


# ---------------------------------------------------------------------------
# Option 3 — dual-track PRIMARY / SECONDARY buckets
# ---------------------------------------------------------------------------


def test_aggregate_a1_routes_primary_and_secondary_into_separate_buckets(
    session: Session,
) -> None:
    """A SECONDARY-attributed mention now contributes to *_secondary columns
    rather than being silently dropped (pre-Option-3 behavior)."""
    _make_run(session)
    _make_product(session, "aw16")
    _make_mention(session, "primary_m", published_at=_NOW - timedelta(days=10))
    _make_mention(session, "secondary_m", published_at=_NOW - timedelta(days=10))
    _attach(session, "primary_m", "aw16", attribution_type=AttributionType.PRIMARY)
    _attach(session, "secondary_m", "aw16", attribution_type=AttributionType.SECONDARY)
    _tag(session, "primary_m", "aw16", Aspect.KEYBOARD, Polarity.POSITIVE, Intensity.MEDIUM)
    _tag(session, "secondary_m", "aw16", Aspect.KEYBOARD, Polarity.NEGATIVE, Intensity.HIGH)
    session.flush()

    stats = aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    assert stats.aggregates_upserted == 1
    assert stats.mentions_contributing == 1
    assert stats.mentions_contributing_secondary == 1
    row = _rows_by_key(session)[("aw16", "keyboard")]
    # PRIMARY bucket (legacy columns)
    assert row.total_mentions == 1
    assert row.mention_ids == ["primary_m"]
    assert row.polarity_counts == {"negative": 0, "neutral": 0, "positive": 1}
    assert row.net_sentiment == 1.0
    # SECONDARY bucket
    assert row.total_mentions_secondary == 1
    assert row.mention_ids_secondary == ["secondary_m"]
    assert row.polarity_counts_secondary == {"negative": 1, "neutral": 0, "positive": 0}
    assert row.net_sentiment_secondary == -1.0
    assert row.intensity_counts_secondary == {"low": 0, "medium": 0, "high": 1}


# ---------------------------------------------------------------------------
# Out-of-scope products
# ---------------------------------------------------------------------------


def test_aggregate_a1_skips_out_of_scope_products(session: Session) -> None:
    _make_run(session)
    _make_product(session, "aw16")
    _make_product(session, "legion")
    _make_mention(session, "m1", published_at=_NOW - timedelta(days=10))
    _make_mention(session, "m2", published_at=_NOW - timedelta(days=10))
    _attach(session, "m1", "aw16")
    _attach(session, "m2", "legion")
    _tag(session, "m1", "aw16", Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)
    _tag(session, "m2", "legion", Aspect.THERMALS, Polarity.POSITIVE, Intensity.LOW)
    session.flush()

    aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    rows = _rows_by_key(session)
    assert ("aw16", "thermals") in rows
    assert ("legion", "thermals") not in rows


# ---------------------------------------------------------------------------
# Version scoping
# ---------------------------------------------------------------------------


def test_aggregate_a1_version_scoping(session: Session) -> None:
    _make_run(session)
    _make_product(session, "aw16")
    _make_mention(session, "m1", published_at=_NOW - timedelta(days=10))
    _attach(session, "m1", "aw16")
    _tag(
        session, "m1", "aw16", Aspect.AESTHETICS, Polarity.POSITIVE, Intensity.HIGH,
        taxonomy_version="v0", prompt_version="aspect_classifier_v1",
    )
    session.flush()

    # v2 → no in-scope tags → 0 rows.
    stats = aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version="v0",
        prompt_version="aspect_classifier_v2",
        now=_NOW,
    )
    session.commit()
    assert stats.aggregates_upserted == 0
    assert _rows_by_key(session) == {}

    # v1 → 1 row.
    stats = aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version="v0",
        prompt_version="aspect_classifier_v1",
        now=_NOW,
    )
    session.commit()
    assert stats.aggregates_upserted == 1


# ---------------------------------------------------------------------------
# Idempotent rerun
# ---------------------------------------------------------------------------


def test_aggregate_a1_idempotent_rerun(session: Session) -> None:
    _make_run(session)
    _make_product(session, "aw16")
    _make_mention(session, "m1", published_at=_NOW - timedelta(days=10))
    _attach(session, "m1", "aw16")
    _tag(session, "m1", "aw16", Aspect.BATTERY, Polarity.NEGATIVE, Intensity.HIGH)
    session.flush()

    aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()
    first_count = session.query(AggregateAspectSku).count()
    first_polarity = dict(_rows_by_key(session)[("aw16", "battery")].polarity_counts)

    aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    assert session.query(AggregateAspectSku).count() == first_count
    assert _rows_by_key(session)[("aw16", "battery")].polarity_counts == first_polarity


# ---------------------------------------------------------------------------
# Empty / no-op
# ---------------------------------------------------------------------------


def test_aggregate_a1_no_matching_tags_is_noop(session: Session) -> None:
    _make_run(session)
    _make_product(session, "aw16")
    stats = aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()
    assert stats == BatchAggregateStats(0, 0, 0)
    assert session.query(AggregateAspectSku).count() == 0


def test_aggregate_a1_empty_product_set_is_noop(session: Session) -> None:
    _make_run(session)
    stats = aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=[],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()
    assert stats == BatchAggregateStats(0, 0, 0)


# ---------------------------------------------------------------------------
# Option 3 — additional dual-track coverage
# ---------------------------------------------------------------------------


def test_aggregate_a1_primary_only_leaves_secondary_columns_empty(
    session: Session,
) -> None:
    """Legacy-shape input (PRIMARY-only, no SECONDARY anywhere) writes zero
    SECONDARY fields and an empty SECONDARY mention_ids list."""
    _make_run(session)
    _make_product(session, "aw16")
    _make_mention(session, "m1", published_at=_NOW - timedelta(days=10))
    _attach(session, "m1", "aw16", attribution_type=AttributionType.PRIMARY)
    _tag(session, "m1", "aw16", Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)
    session.flush()

    stats = aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    assert stats.mentions_contributing == 1
    assert stats.mentions_contributing_secondary == 0
    row = _rows_by_key(session)[("aw16", "thermals")]
    assert row.total_mentions == 1
    assert row.total_mentions_secondary == 0
    assert row.polarity_counts_secondary == {"negative": 0, "neutral": 0, "positive": 0}
    assert row.intensity_counts_secondary == {"low": 0, "medium": 0, "high": 0}
    assert row.net_sentiment_secondary == 0.0
    assert row.verified_share_secondary == 0.0
    assert row.by_source_secondary == {}
    assert row.by_recency_secondary == {
        "0_30": 0, "30_90": 0, "90_180": 0, "180_plus": 0, "unknown": 0,
    }
    assert row.mention_ids_secondary == []


def test_aggregate_a1_secondary_only_path(session: Session) -> None:
    """A (product, aspect) with only SECONDARY contributions writes a row
    with PRIMARY columns zero/empty and SECONDARY populated."""
    _make_run(session)
    _make_product(session, "aw16")
    _make_mention(session, "s1", published_at=_NOW - timedelta(days=10))
    _make_mention(session, "s2", published_at=_NOW - timedelta(days=20))
    _attach(session, "s1", "aw16", attribution_type=AttributionType.SECONDARY)
    _attach(session, "s2", "aw16", attribution_type=AttributionType.SECONDARY)
    _tag(session, "s1", "aw16", Aspect.THERMALS, Polarity.NEGATIVE, Intensity.MEDIUM)
    _tag(session, "s2", "aw16", Aspect.THERMALS, Polarity.POSITIVE, Intensity.LOW)
    session.flush()

    stats = aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    assert stats.aggregates_upserted == 1
    assert stats.mentions_contributing == 0
    assert stats.mentions_contributing_secondary == 2
    row = _rows_by_key(session)[("aw16", "thermals")]
    # PRIMARY zero / empty
    assert row.total_mentions == 0
    assert row.mention_ids == []
    assert row.net_sentiment == 0.0
    assert row.verified_share == 0.0
    assert row.by_source == {}
    # SECONDARY populated
    assert row.total_mentions_secondary == 2
    assert sorted(row.mention_ids_secondary) == ["s1", "s2"]
    assert row.polarity_counts_secondary == {"negative": 1, "neutral": 0, "positive": 1}
    assert row.net_sentiment_secondary == 0.0
    assert row.intensity_counts_secondary == {"low": 1, "medium": 1, "high": 0}


def test_aggregate_a1_primary_takes_precedence_over_secondary_pair(
    session: Session,
) -> None:
    """A (mention, product) pair with both PRIMARY and SECONDARY attribution
    rows contributes to PRIMARY only — preserves "every mention = 1.0"."""
    _make_run(session)
    _make_product(session, "aw16")
    _make_mention(session, "m1", published_at=_NOW - timedelta(days=10))
    _attach(session, "m1", "aw16", attribution_type=AttributionType.PRIMARY)
    _attach(session, "m1", "aw16", attribution_type=AttributionType.SECONDARY)
    _tag(session, "m1", "aw16", Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)
    session.flush()

    stats = aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    row = _rows_by_key(session)[("aw16", "thermals")]
    assert row.total_mentions == 1
    assert row.mention_ids == ["m1"]
    assert row.total_mentions_secondary == 0
    assert row.mention_ids_secondary == []
    assert stats.mentions_contributing == 1
    assert stats.mentions_contributing_secondary == 0


def test_aggregate_a1_skips_secondary_for_out_of_scope_products(
    session: Session,
) -> None:
    """SECONDARY attributions on products outside the in-scope set are skipped,
    matching the existing primary-side behavior."""
    _make_run(session)
    _make_product(session, "aw16")
    _make_product(session, "legion")
    _make_mention(session, "m1", published_at=_NOW - timedelta(days=10))
    _attach(session, "m1", "legion", attribution_type=AttributionType.SECONDARY)
    _tag(session, "m1", "legion", Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)
    session.flush()

    stats = aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],  # legion not in scope
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    assert stats.aggregates_upserted == 0
    assert _rows_by_key(session) == {}


def test_aggregate_a1_idempotent_rerun_with_both_buckets(session: Session) -> None:
    """Rerunning over a corpus with both PRIMARY and SECONDARY contributions
    produces the same row count and identical bucket values."""
    _make_run(session)
    _make_product(session, "aw16")
    _make_mention(session, "p1", published_at=_NOW - timedelta(days=10))
    _make_mention(session, "s1", published_at=_NOW - timedelta(days=20))
    _attach(session, "p1", "aw16", attribution_type=AttributionType.PRIMARY)
    _attach(session, "s1", "aw16", attribution_type=AttributionType.SECONDARY)
    _tag(session, "p1", "aw16", Aspect.BATTERY, Polarity.POSITIVE, Intensity.HIGH)
    _tag(session, "s1", "aw16", Aspect.BATTERY, Polarity.NEGATIVE, Intensity.LOW)
    session.flush()

    aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()
    first_count = session.query(AggregateAspectSku).count()
    first_row = _rows_by_key(session)[("aw16", "battery")]
    first_p_polarity = dict(first_row.polarity_counts)
    first_s_polarity = dict(first_row.polarity_counts_secondary)
    first_s_ids = list(first_row.mention_ids_secondary)

    aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=["aw16"],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    assert session.query(AggregateAspectSku).count() == first_count
    second_row = _rows_by_key(session)[("aw16", "battery")]
    assert dict(second_row.polarity_counts) == first_p_polarity
    assert dict(second_row.polarity_counts_secondary) == first_s_polarity
    assert list(second_row.mention_ids_secondary) == first_s_ids
