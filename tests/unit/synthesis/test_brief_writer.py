"""Tests for the four-quadrant Sonnet brief writer.

The Anthropic client is mocked at the class level (matching `test_dedup.py`):
the writer's structural logic — quadrant routing, placeholder rule, citation
wiring — is the focus. No real Sonnet spend.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmResponse, LlmResponseError
from pulse_check.storage.enums import (
    Aspect,
    AttributionType,
    Intensity,
    Polarity,
    SourceType,
)
from pulse_check.storage.models import AggregateAspectSku, Mention, Product, Run
from pulse_check.synthesis.brief_writer import (
    PLACEHOLDER_CLAIM_TEXT,
    SECTION_HEADINGS,
    write_a1_brief,
)
from pulse_check.synthesis.selector import AspectSelection, SelectedVerbatim

_PRODUCT_ID = "alienware_16"
_RUN_ID = "run_test_brief"


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


def _add_mention(session: Session, mid: str, text: str = "x") -> None:
    session.add(
        Mention(
            mention_id=mid,
            source_type=SourceType.REDDIT_POST,
            source_url="https://example.com",
            raw_text=text,
        )
    )


def _agg(
    *,
    aspect: Aspect,
    primary_pos: int = 0,
    primary_neg: int = 0,
    secondary_pos: int = 0,
    secondary_neg: int = 0,
    primary_ids: Sequence[str] = (),
    secondary_ids: Sequence[str] = (),
) -> AggregateAspectSku:
    return AggregateAspectSku(
        run_id=_RUN_ID,
        product_id=_PRODUCT_ID,
        aspect=aspect,
        total_mentions=primary_pos + primary_neg,
        polarity_counts={
            "positive": primary_pos,
            "negative": primary_neg,
            "neutral": 0,
            "mixed": 0,
        },
        net_sentiment=0.0,
        intensity_counts={},
        verified_share=0.0,
        by_source={},
        by_recency={},
        mention_ids=list(primary_ids),
        total_mentions_secondary=secondary_pos + secondary_neg,
        polarity_counts_secondary={
            "positive": secondary_pos,
            "negative": secondary_neg,
            "neutral": 0,
            "mixed": 0,
        },
        net_sentiment_secondary=0.0,
        intensity_counts_secondary={},
        verified_share_secondary=0.0,
        by_source_secondary={},
        by_recency_secondary={},
        mention_ids_secondary=list(secondary_ids),
    )


def _sv(mid: str, polarity: Polarity, bucket: AttributionType) -> SelectedVerbatim:
    return SelectedVerbatim(
        mention_id=mid, polarity=polarity, bucket=bucket, intensity=Intensity.HIGH
    )


def _selection(
    aspect: Aspect,
    *,
    pp: Sequence[str] = (),
    pn: Sequence[str] = (),
    sp: Sequence[str] = (),
    sn: Sequence[str] = (),
) -> AspectSelection:
    return AspectSelection(
        aspect=aspect,
        primary_positive=tuple(_sv(m, Polarity.POSITIVE, AttributionType.PRIMARY) for m in pp),
        primary_negative=tuple(_sv(m, Polarity.NEGATIVE, AttributionType.PRIMARY) for m in pn),
        secondary_positive=tuple(_sv(m, Polarity.POSITIVE, AttributionType.SECONDARY) for m in sp),
        secondary_negative=tuple(_sv(m, Polarity.NEGATIVE, AttributionType.SECONDARY) for m in sn),
    )


def _mock_client(
    claims: list[dict[str, Any]],
    brief_title: str = "Brief",
    summary: dict[str, Any] | None = None,
) -> Any:
    client = MagicMock()
    payload: dict[str, Any] = {"brief_title": brief_title, "claims": claims}
    if summary is not None:
        payload["summary"] = summary
    text = json.dumps(payload)
    client.generate_json.return_value = LlmResponse(raw_output=text, parsed_output=payload)
    return client


# ---------------------------------------------------------------------------
# Quadrant routing
# ---------------------------------------------------------------------------


def test_high_confidence_strengths_routed_to_quadrant_one(session: Session) -> None:
    p = _setup(session)
    for mid in ["m1", "m2", "m3"]:
        _add_mention(session, mid, "fast")
    session.commit()

    aggs = {
        Aspect.PERFORMANCE: _agg(
            aspect=Aspect.PERFORMANCE, primary_pos=5, primary_ids=["m1", "m2", "m3"]
        )
    }
    sels = {Aspect.PERFORMANCE: _selection(Aspect.PERFORMANCE, pp=["m1", "m2", "m3"])}
    client = _mock_client(
        claims=[{"quadrant_id": 1, "aspect": "performance", "header": "H", "claim_text": "Fast."}]
    )

    brief = write_a1_brief(session, client=client, product=p, aggregates=aggs, selections=sels)

    assert brief.brief_title == "Brief"
    q1 = next(s for s in brief.sections if s.heading == SECTION_HEADINGS[1])
    assert q1.claims[0].claim_text == "Fast."
    assert q1.claims[0].cited_mention_ids == ["m1", "m2", "m3"]


def test_quadrant_one_caps_at_three_aspects_ordered_by_count_desc(
    session: Session,
) -> None:
    p = _setup(session)
    for i in range(4):
        _add_mention(session, f"m{i}")
    session.commit()

    aggs = {
        Aspect.PERFORMANCE: _agg(aspect=Aspect.PERFORMANCE, primary_pos=10, primary_ids=["m0"]),
        Aspect.DISPLAY: _agg(aspect=Aspect.DISPLAY, primary_pos=8, primary_ids=["m1"]),
        Aspect.BATTERY: _agg(aspect=Aspect.BATTERY, primary_pos=5, primary_ids=["m2"]),
        Aspect.KEYBOARD: _agg(aspect=Aspect.KEYBOARD, primary_pos=3, primary_ids=["m3"]),
    }
    sels = {
        Aspect.PERFORMANCE: _selection(Aspect.PERFORMANCE, pp=["m0"]),
        Aspect.DISPLAY: _selection(Aspect.DISPLAY, pp=["m1"]),
        Aspect.BATTERY: _selection(Aspect.BATTERY, pp=["m2"]),
        Aspect.KEYBOARD: _selection(Aspect.KEYBOARD, pp=["m3"]),
    }
    client = _mock_client(
        claims=[
            {"quadrant_id": 1, "aspect": "performance", "header": "H", "claim_text": "perf."},
            {"quadrant_id": 1, "aspect": "display", "header": "H", "claim_text": "disp."},
            {"quadrant_id": 1, "aspect": "battery", "header": "H", "claim_text": "batt."},
        ]
    )

    brief = write_a1_brief(session, client=client, product=p, aggregates=aggs, selections=sels)

    q1 = next(s for s in brief.sections if s.heading == SECTION_HEADINGS[1])
    aspects_in_order = [c.cited_mention_ids[0] for c in q1.claims]
    assert aspects_in_order == ["m0", "m1", "m2"]
    assert len(q1.claims) == 3


def test_empty_quadrant_two_renders_placeholder_with_empty_citations(
    session: Session,
) -> None:
    p = _setup(session)
    _add_mention(session, "m1", "fast")
    session.commit()

    aggs = {Aspect.PERFORMANCE: _agg(aspect=Aspect.PERFORMANCE, primary_pos=5, primary_ids=["m1"])}
    sels = {Aspect.PERFORMANCE: _selection(Aspect.PERFORMANCE, pp=["m1"])}
    client = _mock_client(
        claims=[{"quadrant_id": 1, "aspect": "performance", "header": "H", "claim_text": "Fast."}]
    )

    brief = write_a1_brief(session, client=client, product=p, aggregates=aggs, selections=sels)

    q2 = next(s for s in brief.sections if s.heading == SECTION_HEADINGS[2])
    assert len(q2.claims) == 1
    assert q2.claims[0].claim_text == PLACEHOLDER_CLAIM_TEXT
    assert q2.claims[0].cited_mention_ids == []


def test_quadrant_three_excludes_aspects_already_in_quadrant_one(session: Session) -> None:
    p = _setup(session)
    for mid in ["m_p1", "m_p2", "m_p3", "m_s1"]:
        _add_mention(session, mid)
    session.commit()

    aggs = {
        Aspect.PERFORMANCE: _agg(
            aspect=Aspect.PERFORMANCE,
            primary_pos=5,
            primary_ids=["m_p1", "m_p2", "m_p3"],
            secondary_pos=2,
            secondary_ids=["m_s1"],
        )
    }
    sels = {
        Aspect.PERFORMANCE: _selection(
            Aspect.PERFORMANCE, pp=["m_p1", "m_p2", "m_p3"], sp=["m_s1"]
        ),
    }
    client = _mock_client(
        claims=[{"quadrant_id": 1, "aspect": "performance", "header": "H", "claim_text": "Fast."}]
    )

    brief = write_a1_brief(session, client=client, product=p, aggregates=aggs, selections=sels)

    headings = [s.heading for s in brief.sections]
    assert SECTION_HEADINGS[3] not in headings


def test_low_signal_only_aspect_routed_to_quadrant_three(session: Session) -> None:
    p = _setup(session)
    _add_mention(session, "m_s1", "love it")
    session.commit()

    aggs = {
        Aspect.AESTHETICS: _agg(aspect=Aspect.AESTHETICS, secondary_pos=1, secondary_ids=["m_s1"])
    }
    sels = {Aspect.AESTHETICS: _selection(Aspect.AESTHETICS, sp=["m_s1"])}
    client = _mock_client(
        claims=[
            {"quadrant_id": 3, "aspect": "aesthetics", "header": "H", "claim_text": "Looks good."}
        ]
    )

    brief = write_a1_brief(session, client=client, product=p, aggregates=aggs, selections=sels)

    q3 = next(s for s in brief.sections if s.heading == SECTION_HEADINGS[3])
    assert q3.claims[0].cited_mention_ids == ["m_s1"]


# ---------------------------------------------------------------------------
# Cache + LLM-failure paths
# ---------------------------------------------------------------------------


def test_second_call_with_same_inputs_hits_cache(session: Session) -> None:
    p = _setup(session)
    _add_mention(session, "m1", "fast")
    session.commit()

    aggs = {Aspect.PERFORMANCE: _agg(aspect=Aspect.PERFORMANCE, primary_pos=5, primary_ids=["m1"])}
    sels = {Aspect.PERFORMANCE: _selection(Aspect.PERFORMANCE, pp=["m1"])}
    client = _mock_client(
        claims=[{"quadrant_id": 1, "aspect": "performance", "header": "H", "claim_text": "Fast."}]
    )

    first = write_a1_brief(session, client=client, product=p, aggregates=aggs, selections=sels)
    second = write_a1_brief(session, client=client, product=p, aggregates=aggs, selections=sels)

    assert first == second
    assert client.generate_json.call_count == 1


def test_missing_claim_text_for_quadrant_aspect_raises(session: Session) -> None:
    p = _setup(session)
    _add_mention(session, "m1", "fast")
    session.commit()

    aggs = {Aspect.PERFORMANCE: _agg(aspect=Aspect.PERFORMANCE, primary_pos=5, primary_ids=["m1"])}
    sels = {Aspect.PERFORMANCE: _selection(Aspect.PERFORMANCE, pp=["m1"])}
    client = _mock_client(claims=[])  # Sonnet omitted the perf claim

    with pytest.raises(LlmResponseError, match="omitted header/claim_text"):
        write_a1_brief(session, client=client, product=p, aggregates=aggs, selections=sels)


def test_empty_brief_title_raises(session: Session) -> None:
    p = _setup(session)
    _add_mention(session, "m1", "fast")
    session.commit()

    aggs = {Aspect.PERFORMANCE: _agg(aspect=Aspect.PERFORMANCE, primary_pos=5, primary_ids=["m1"])}
    sels = {Aspect.PERFORMANCE: _selection(Aspect.PERFORMANCE, pp=["m1"])}
    client = _mock_client(
        claims=[{"quadrant_id": 1, "aspect": "performance", "header": "H", "claim_text": "Fast."}],
        brief_title="",
    )

    with pytest.raises(LlmResponseError, match="no brief_title"):
        write_a1_brief(session, client=client, product=p, aggregates=aggs, selections=sels)


def test_no_qualifying_aspects_short_circuits_sonnet_with_placeholder_only(
    session: Session,
) -> None:
    p = _setup(session)
    session.commit()
    client = _mock_client(claims=[])

    brief = write_a1_brief(session, client=client, product=p, aggregates={}, selections={})

    assert len(brief.sections) == 1
    assert brief.sections[0].heading == SECTION_HEADINGS[2]
    assert brief.sections[0].claims[0].claim_text == PLACEHOLDER_CLAIM_TEXT
    assert brief.brief_title == "Alienware 16 — A1 voice"
    client.generate_json.assert_not_called()


# ---------------------------------------------------------------------------
# Summary paragraph (a1_brief_v3)
# ---------------------------------------------------------------------------


def test_summary_carried_through_when_sonnet_returns_block(
    session: Session,
) -> None:
    p = _setup(session)
    for mid in ["m1", "m2"]:
        _add_mention(session, mid, "fast")
    session.commit()

    aggs = {
        Aspect.PERFORMANCE: _agg(
            aspect=Aspect.PERFORMANCE, primary_pos=5, primary_ids=["m1", "m2"]
        )
    }
    sels = {Aspect.PERFORMANCE: _selection(Aspect.PERFORMANCE, pp=["m1", "m2"])}
    client = _mock_client(
        claims=[
            {"quadrant_id": 1, "aspect": "performance", "header": "H", "claim_text": "Fast."}
        ],
        summary={
            "text": "Discussion centers on raw speed and responsiveness. "
            "Broad agreement on performance; divisive takes on price.",
            "cited_mention_ids": ["m1", "m2"],
        },
    )

    brief = write_a1_brief(session, client=client, product=p, aggregates=aggs, selections=sels)

    assert brief.summary is not None
    assert "Discussion centers on raw speed" in brief.summary.text
    assert brief.summary.cited_mention_ids == ["m1", "m2"]


def test_summary_absent_yields_none(session: Session) -> None:
    p = _setup(session)
    _add_mention(session, "m1", "fast")
    session.commit()

    aggs = {Aspect.PERFORMANCE: _agg(aspect=Aspect.PERFORMANCE, primary_pos=5, primary_ids=["m1"])}
    sels = {Aspect.PERFORMANCE: _selection(Aspect.PERFORMANCE, pp=["m1"])}
    client = _mock_client(
        claims=[
            {"quadrant_id": 1, "aspect": "performance", "header": "H", "claim_text": "Fast."}
        ],
        summary=None,
    )

    brief = write_a1_brief(session, client=client, product=p, aggregates=aggs, selections=sels)

    assert brief.summary is None


def test_summary_cited_ids_filtered_to_allowed_pool(session: Session) -> None:
    p = _setup(session)
    _add_mention(session, "m1", "fast")
    _add_mention(session, "m_external", "hallucinated")
    session.commit()

    aggs = {Aspect.PERFORMANCE: _agg(aspect=Aspect.PERFORMANCE, primary_pos=5, primary_ids=["m1"])}
    sels = {Aspect.PERFORMANCE: _selection(Aspect.PERFORMANCE, pp=["m1"])}
    client = _mock_client(
        claims=[
            {"quadrant_id": 1, "aspect": "performance", "header": "H", "claim_text": "Fast."}
        ],
        summary={
            "text": "Conversation focuses on raw speed.",
            "cited_mention_ids": ["m1", "m_external", "m_fabricated"],
        },
    )

    brief = write_a1_brief(session, client=client, product=p, aggregates=aggs, selections=sels)

    assert brief.summary is not None
    assert brief.summary.cited_mention_ids == ["m1"]


def test_summary_text_truncated_at_600_chars(session: Session) -> None:
    p = _setup(session)
    _add_mention(session, "m1", "fast")
    session.commit()

    aggs = {Aspect.PERFORMANCE: _agg(aspect=Aspect.PERFORMANCE, primary_pos=5, primary_ids=["m1"])}
    sels = {Aspect.PERFORMANCE: _selection(Aspect.PERFORMANCE, pp=["m1"])}
    long_text = "x" * 1200
    client = _mock_client(
        claims=[
            {"quadrant_id": 1, "aspect": "performance", "header": "H", "claim_text": "Fast."}
        ],
        summary={"text": long_text, "cited_mention_ids": ["m1"]},
    )

    brief = write_a1_brief(session, client=client, product=p, aggregates=aggs, selections=sels)

    assert brief.summary is not None
    assert len(brief.summary.text) == 600


def test_summary_malformed_yields_none(session: Session) -> None:
    """Sonnet returns a summary key but with bad shape; parser returns None."""
    p = _setup(session)
    _add_mention(session, "m1", "fast")
    session.commit()

    aggs = {Aspect.PERFORMANCE: _agg(aspect=Aspect.PERFORMANCE, primary_pos=5, primary_ids=["m1"])}
    sels = {Aspect.PERFORMANCE: _selection(Aspect.PERFORMANCE, pp=["m1"])}
    client = _mock_client(
        claims=[
            {"quadrant_id": 1, "aspect": "performance", "header": "H", "claim_text": "Fast."}
        ],
        summary={"text": "", "cited_mention_ids": ["m1"]},  # empty text
    )

    brief = write_a1_brief(session, client=client, product=p, aggregates=aggs, selections=sels)

    assert brief.summary is None


def test_summary_reads_legacy_vibe_summary_key_from_cached_response(
    session: Session,
) -> None:
    """Cached Sonnet responses written before the session-41 rename use the
    `vibe_summary` key. Parser must accept it for backward compatibility."""
    p = _setup(session)
    _add_mention(session, "m1", "fast")
    session.commit()

    aggs = {Aspect.PERFORMANCE: _agg(aspect=Aspect.PERFORMANCE, primary_pos=5, primary_ids=["m1"])}
    sels = {Aspect.PERFORMANCE: _selection(Aspect.PERFORMANCE, pp=["m1"])}
    # Build the cached-shape payload directly (legacy key).
    client = MagicMock()
    payload = {
        "brief_title": "Brief",
        "claims": [
            {"quadrant_id": 1, "aspect": "performance", "header": "H", "claim_text": "Fast."}
        ],
        "vibe_summary": {
            "text": "Legacy text from a cached response.",
            "cited_mention_ids": ["m1"],
        },
    }
    text = json.dumps(payload)
    client.generate_json.return_value = LlmResponse(raw_output=text, parsed_output=payload)

    brief = write_a1_brief(session, client=client, product=p, aggregates=aggs, selections=sels)

    assert brief.summary is not None
    assert brief.summary.text == "Legacy text from a cached response."


def test_truncate_verbatim_passes_short_text_unchanged() -> None:
    from pulse_check.synthesis.brief_writer import VERBATIM_TEXT_CAP_CHARS, _truncate_verbatim

    short = "y" * (VERBATIM_TEXT_CAP_CHARS - 1)
    assert _truncate_verbatim(short) == short


def test_truncate_verbatim_caps_long_text_with_ellipsis() -> None:
    from pulse_check.synthesis.brief_writer import VERBATIM_TEXT_CAP_CHARS, _truncate_verbatim

    long_text = "z" * (VERBATIM_TEXT_CAP_CHARS + 1000)
    out = _truncate_verbatim(long_text)
    assert out.endswith("...")
    body = out[:-3]
    assert len(body) <= VERBATIM_TEXT_CAP_CHARS
    assert len(out) < len(long_text)
