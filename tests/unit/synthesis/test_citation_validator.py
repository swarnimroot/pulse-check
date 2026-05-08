"""Tests for the citation validator (TESTING §6, soft-warn policy).

Validator queries the in-memory SQLite session for fabricated-id checks; all
other checks are pure functions over the BriefNarrative + aggregates.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from pulse_check.storage.enums import Aspect, SourceType
from pulse_check.storage.models import AggregateAspectSku, Mention, Product, Run
from pulse_check.synthesis.brief_writer import (
    PLACEHOLDER_CLAIM_TEXT,
    SECTION_HEADINGS,
)
from pulse_check.synthesis.citation_validator import validate_citations
from pulse_check.synthesis.contracts import (
    BriefNarrative,
    BriefSection,
    Claim,
)

_PRODUCT_ID = "alienware_16"
_RUN_ID = "run_test_validator"


def _setup(session: Session) -> Product:
    session.add(
        Run(
            run_id=_RUN_ID,
            config_snapshot={"run_id": _RUN_ID},
            taxonomy_version="v0",
            prompt_versions={},
        )
    )
    p = Product(product_id=_PRODUCT_ID, display_name="Alienware 16", brand="dell")
    session.add(p)
    session.flush()
    return p


def _add_mention(session: Session, mid: str) -> None:
    session.add(
        Mention(
            mention_id=mid,
            source_type=SourceType.REDDIT_POST,
            source_url="https://example.com",
            raw_text="x",
        )
    )


def _agg(
    *,
    aspect: Aspect,
    primary_ids: Sequence[str] = (),
    secondary_ids: Sequence[str] = (),
) -> AggregateAspectSku:
    return AggregateAspectSku(
        run_id=_RUN_ID,
        product_id=_PRODUCT_ID,
        aspect=aspect,
        total_mentions=len(primary_ids),
        polarity_counts={},
        net_sentiment=0.0,
        intensity_counts={},
        verified_share=0.0,
        by_source={},
        by_recency={},
        mention_ids=list(primary_ids),
        total_mentions_secondary=len(secondary_ids),
        polarity_counts_secondary={},
        net_sentiment_secondary=0.0,
        intensity_counts_secondary={},
        verified_share_secondary=0.0,
        by_source_secondary={},
        by_recency_secondary={},
        mention_ids_secondary=list(secondary_ids),
    )


def _narrative(
    *, heading: str = SECTION_HEADINGS[1], claims: list[Claim]
) -> BriefNarrative:
    return BriefNarrative(
        brief_title="Test brief",
        sections=[BriefSection(heading=heading, claims=claims)],
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_clean_brief_passes_all_four_checks(session: Session) -> None:
    _setup(session)
    for mid in ("m1", "m2", "m3"):
        _add_mention(session, mid)
    session.flush()
    agg = _agg(aspect=Aspect.PERFORMANCE, primary_ids=("m1", "m2", "m3"))
    aggregates = {Aspect.PERFORMANCE: agg}

    narrative = _narrative(
        claims=[
            Claim(claim_text="Owners praise the performance.", cited_mention_ids=["m1", "m2"]),
        ]
    )

    result = validate_citations(
        session,
        narrative=narrative,
        aggregates=aggregates,
        allowed_pool={"m1", "m2", "m3"},
    )

    assert result.is_valid is True
    assert result.fabricated_ids == []
    assert result.out_of_context_ids == []
    assert result.empty_claims == []
    assert result.numerical_drift == []


# ---------------------------------------------------------------------------
# Check 1: fabricated IDs
# ---------------------------------------------------------------------------


def test_fabricated_id_caught(session: Session) -> None:
    _setup(session)
    _add_mention(session, "m1")
    session.flush()
    agg = _agg(aspect=Aspect.PERFORMANCE, primary_ids=("m1",))

    narrative = _narrative(
        claims=[
            Claim(
                claim_text="Owners praise the performance.",
                cited_mention_ids=["m1", "fake_id_999"],
            ),
        ]
    )

    result = validate_citations(
        session,
        narrative=narrative,
        aggregates={Aspect.PERFORMANCE: agg},
        allowed_pool={"m1", "fake_id_999"},
    )

    assert result.is_valid is False
    assert result.fabricated_ids == ["fake_id_999"]
    assert result.out_of_context_ids == []


# ---------------------------------------------------------------------------
# Check 2: out-of-context IDs
# ---------------------------------------------------------------------------


def test_out_of_context_id_caught(session: Session) -> None:
    _setup(session)
    for mid in ("m1", "stray_mention"):
        _add_mention(session, mid)
    session.flush()
    agg = _agg(aspect=Aspect.PERFORMANCE, primary_ids=("m1",))

    narrative = _narrative(
        claims=[
            Claim(
                claim_text="Owners praise the performance.",
                cited_mention_ids=["m1", "stray_mention"],
            ),
        ]
    )

    result = validate_citations(
        session,
        narrative=narrative,
        aggregates={Aspect.PERFORMANCE: agg},
        allowed_pool={"m1"},
    )

    assert result.is_valid is False
    assert result.fabricated_ids == []
    assert result.out_of_context_ids == ["stray_mention"]


# ---------------------------------------------------------------------------
# Check 4: empty claims (placeholder exempt)
# ---------------------------------------------------------------------------


def test_empty_claim_with_placeholder_text_allowed(session: Session) -> None:
    _setup(session)
    session.flush()

    narrative = BriefNarrative(
        brief_title="Test",
        sections=[
            BriefSection(
                heading=SECTION_HEADINGS[2],
                claims=[Claim(claim_text=PLACEHOLDER_CLAIM_TEXT, cited_mention_ids=[])],
            ),
        ],
    )

    result = validate_citations(
        session, narrative=narrative, aggregates={}, allowed_pool=set()
    )

    assert result.is_valid is True
    assert result.empty_claims == []


def test_empty_claim_with_non_placeholder_text_flagged(session: Session) -> None:
    _setup(session)
    session.flush()

    narrative = BriefNarrative(
        brief_title="Test",
        sections=[
            BriefSection(
                heading=SECTION_HEADINGS[1],
                claims=[Claim(claim_text="Owners are mostly happy.", cited_mention_ids=[])],
            ),
        ],
    )

    result = validate_citations(
        session, narrative=narrative, aggregates={}, allowed_pool=set()
    )

    assert result.is_valid is False
    assert result.empty_claims == ["Owners are mostly happy."]


# ---------------------------------------------------------------------------
# Check 3: numerical drift
# ---------------------------------------------------------------------------


def test_numerical_drift_flagged_on_count_noun(session: Session) -> None:
    _setup(session)
    for mid in ("m1", "m2", "m3"):
        _add_mention(session, mid)
    session.flush()
    agg = _agg(aspect=Aspect.PERFORMANCE, primary_ids=("m1", "m2", "m3"))

    narrative = _narrative(
        claims=[
            Claim(
                claim_text="60 users praised the performance.",
                cited_mention_ids=["m1", "m2"],
            ),
        ]
    )

    result = validate_citations(
        session,
        narrative=narrative,
        aggregates={Aspect.PERFORMANCE: agg},
        allowed_pool={"m1", "m2", "m3"},
    )

    assert result.is_valid is False
    assert len(result.numerical_drift) == 1
    drift = result.numerical_drift[0]
    assert drift.claimed_n == 60
    assert drift.actual_n == 3


def test_numerical_drift_within_tolerance_passes(session: Session) -> None:
    _setup(session)
    for mid in ("m1", "m2", "m3"):
        _add_mention(session, mid)
    session.flush()
    agg = _agg(aspect=Aspect.PERFORMANCE, primary_ids=("m1", "m2", "m3"))

    narrative = _narrative(
        claims=[
            Claim(
                claim_text="3 users praised the performance.",
                cited_mention_ids=["m1", "m2"],
            ),
        ]
    )

    result = validate_citations(
        session,
        narrative=narrative,
        aggregates={Aspect.PERFORMANCE: agg},
        allowed_pool={"m1", "m2", "m3"},
    )

    assert result.is_valid is True
    assert result.numerical_drift == []


def test_numerical_drift_ignores_non_count_integers(session: Session) -> None:
    _setup(session)
    for mid in ("m1", "m2", "m3"):
        _add_mention(session, mid)
    session.flush()
    agg = _agg(aspect=Aspect.DISPLAY, primary_ids=("m1", "m2", "m3"))

    narrative = _narrative(
        claims=[
            Claim(
                claim_text="The 1080p display is well regarded.",
                cited_mention_ids=["m1"],
            ),
        ]
    )

    result = validate_citations(
        session,
        narrative=narrative,
        aggregates={Aspect.DISPLAY: agg},
        allowed_pool={"m1", "m2", "m3"},
    )

    assert result.is_valid is True
    assert result.numerical_drift == []


def test_drift_falls_back_to_citation_count_when_aggregate_unknown(
    session: Session,
) -> None:
    _setup(session)
    for mid in ("m1", "m2"):
        _add_mention(session, mid)
    session.flush()

    narrative = _narrative(
        claims=[
            Claim(
                claim_text="50 users praised the performance.",
                cited_mention_ids=["m1", "m2"],
            ),
        ]
    )

    result = validate_citations(
        session,
        narrative=narrative,
        aggregates={},
        allowed_pool={"m1", "m2"},
    )

    assert result.is_valid is False
    assert len(result.numerical_drift) == 1
    assert result.numerical_drift[0].actual_n == 2


def test_drift_uses_secondary_aggregate_when_cited_set_matches_secondary(
    session: Session,
) -> None:
    _setup(session)
    for mid in ("p1",) + tuple(f"s{i}" for i in range(1, 11)):
        _add_mention(session, mid)
    session.flush()
    agg = _agg(
        aspect=Aspect.KEYBOARD,
        primary_ids=("p1",),
        secondary_ids=tuple(f"s{i}" for i in range(1, 11)),
    )

    narrative = BriefNarrative(
        brief_title="Test",
        sections=[
            BriefSection(
                heading=SECTION_HEADINGS[4],
                claims=[
                    Claim(
                        claim_text="11 reviewers raised concerns.",
                        cited_mention_ids=["s1", "s2"],
                    ),
                ],
            ),
        ],
    )

    result = validate_citations(
        session,
        narrative=narrative,
        aggregates={Aspect.KEYBOARD: agg},
        allowed_pool={"p1", *(f"s{i}" for i in range(1, 11))},
    )

    # 11 vs actual=10 → drift = 1/10 = 0.1 > 0.05 → flagged.
    assert len(result.numerical_drift) == 1
    assert result.numerical_drift[0].claimed_n == 11
    assert result.numerical_drift[0].actual_n == 10


def test_validator_handles_brief_with_no_citations(session: Session) -> None:
    _setup(session)
    session.flush()

    narrative = BriefNarrative(
        brief_title="Test",
        sections=[
            BriefSection(
                heading=SECTION_HEADINGS[2],
                claims=[Claim(claim_text=PLACEHOLDER_CLAIM_TEXT, cited_mention_ids=[])],
            ),
        ],
    )

    result = validate_citations(
        session, narrative=narrative, aggregates={}, allowed_pool=set()
    )

    assert result.is_valid is True
    assert result.fabricated_ids == []
    assert result.out_of_context_ids == []
    assert result.empty_claims == []
    assert result.numerical_drift == []
