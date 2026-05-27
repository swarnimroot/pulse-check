"""Tests for the Sonnet pair-brief writer (ARCHITECTURE §6.4).

The Anthropic client is mocked at the class level (matching `test_brief_writer.py`):
the writer's structural logic — aspect routing, leader/delta, placeholder
short-circuit, cite-pool filtering — is the focus. No real Sonnet spend.
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
from pulse_check.synthesis.pair_brief_writer import (
    _PAIR_PROMPT_TEMPLATES,
    PAIR_BRIEF_PROMPT_VERSION,
    PAIR_BRIEF_PROMPT_VERSION_STRICT,
    PAIR_PLACEHOLDER_CONTRAST_TEXT,
    _compute_pair_entries,
    write_pair_brief,
)
from pulse_check.synthesis.selector import AspectSelection, SelectedVerbatim

_PRIMARY_ID = "alienware_16_aurora"
_COMPARATOR_ID = "rog_strix_g16"
_RUN_ID = "run_test_pair"


def _setup(session: Session) -> tuple[Product, Product]:
    session.add(
        Run(
            run_id=_RUN_ID,
            config_snapshot={"run_id": _RUN_ID},
            taxonomy_version="v0",
            prompt_versions={},
        )
    )
    p = Product(product_id=_PRIMARY_ID, display_name="Alienware 16 Aurora", brand="dell")
    c = Product(product_id=_COMPARATOR_ID, display_name="ROG Strix G16", brand="asus")
    session.add_all([p, c])
    session.flush()
    return p, c


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
    product_id: str,
    aspect: Aspect,
    pos: int = 0,
    neg: int = 0,
    net: float = 0.0,
    primary_ids: Sequence[str] = (),
) -> AggregateAspectSku:
    return AggregateAspectSku(
        run_id=_RUN_ID,
        product_id=product_id,
        aspect=aspect,
        total_mentions=pos + neg,
        polarity_counts={"positive": pos, "negative": neg, "neutral": 0, "mixed": 0},
        net_sentiment=net,
        intensity_counts={},
        verified_share=0.0,
        by_source={},
        by_recency={},
        mention_ids=list(primary_ids),
        total_mentions_secondary=0,
        polarity_counts_secondary={"positive": 0, "negative": 0, "neutral": 0, "mixed": 0},
        net_sentiment_secondary=0.0,
        intensity_counts_secondary={},
        verified_share_secondary=0.0,
        by_source_secondary={},
        by_recency_secondary={},
        mention_ids_secondary=[],
    )


def _sv(mid: str, polarity: Polarity = Polarity.POSITIVE) -> SelectedVerbatim:
    return SelectedVerbatim(
        mention_id=mid,
        polarity=polarity,
        bucket=AttributionType.PRIMARY,
        intensity=Intensity.HIGH,
    )


def _selection(
    aspect: Aspect, *, pp: Sequence[str] = (), pn: Sequence[str] = ()
) -> AspectSelection:
    return AspectSelection(
        aspect=aspect,
        primary_positive=tuple(_sv(m, Polarity.POSITIVE) for m in pp),
        primary_negative=tuple(_sv(m, Polarity.NEGATIVE) for m in pn),
        secondary_positive=(),
        secondary_negative=(),
    )


def _mock_client(
    contrast_text: str = "Primary leads on thermals. Comparator leads on display.",
    cited: Sequence[str] = (),
    brief_title: str = "Alienware 16 Aurora vs ROG Strix G16",
) -> Any:
    client = MagicMock()
    payload: dict[str, Any] = {
        "brief_title": brief_title,
        "contrast": {"text": contrast_text, "cited_mention_ids": list(cited)},
    }
    text = json.dumps(payload)
    client.generate_json.return_value = LlmResponse(raw_output=text, parsed_output=payload)
    return client


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_writes_pair_brief_with_contrast_and_cites(session: Session) -> None:
    p, c = _setup(session)
    for mid in ["mp1", "mp2", "mc1", "mc2"]:
        _add_mention(session, mid, f"text {mid}")
    session.commit()

    primary_aggs = {
        Aspect.THERMALS: _agg(
            product_id=_PRIMARY_ID,
            aspect=Aspect.THERMALS,
            pos=8,
            net=0.5,
            primary_ids=["mp1", "mp2"],
        ),
    }
    comparator_aggs = {
        Aspect.THERMALS: _agg(
            product_id=_COMPARATOR_ID,
            aspect=Aspect.THERMALS,
            pos=5,
            net=0.1,
            primary_ids=["mc1", "mc2"],
        ),
    }
    primary_sels = {Aspect.THERMALS: _selection(Aspect.THERMALS, pp=["mp1", "mp2"])}
    comparator_sels = {Aspect.THERMALS: _selection(Aspect.THERMALS, pp=["mc1", "mc2"])}
    client = _mock_client(cited=["mp1", "mc1"])

    narrative = write_pair_brief(
        session,
        client=client,
        primary=p,
        comparator=c,
        primary_aggregates=primary_aggs,
        comparator_aggregates=comparator_aggs,
        primary_selections=primary_sels,
        comparator_selections=comparator_sels,
    )

    assert narrative.brief_title == "Alienware 16 Aurora vs ROG Strix G16"
    assert narrative.contrast.text.startswith("Primary leads")
    assert narrative.contrast.cited_mention_ids == ["mp1", "mc1"]


# ---------------------------------------------------------------------------
# Placeholder short-circuit
# ---------------------------------------------------------------------------


def test_no_aspect_crosses_threshold_short_circuits_to_placeholder(session: Session) -> None:
    p, c = _setup(session)
    session.commit()

    # Both sides have aspect rows but mentions count below PAIR_ASPECT_MIN_MENTIONS=3
    primary_aggs = {
        Aspect.THERMALS: _agg(product_id=_PRIMARY_ID, aspect=Aspect.THERMALS, pos=1, neg=0),
    }
    comparator_aggs = {
        Aspect.THERMALS: _agg(product_id=_COMPARATOR_ID, aspect=Aspect.THERMALS, pos=2, neg=0),
    }
    client = _mock_client()  # should not be called

    narrative = write_pair_brief(
        session,
        client=client,
        primary=p,
        comparator=c,
        primary_aggregates=primary_aggs,
        comparator_aggregates=comparator_aggs,
        primary_selections={},
        comparator_selections={},
    )

    assert narrative.contrast.text == PAIR_PLACEHOLDER_CONTRAST_TEXT
    assert narrative.contrast.cited_mention_ids == []
    client.generate_json.assert_not_called()


def test_no_aggregates_either_side_short_circuits(session: Session) -> None:
    p, c = _setup(session)
    session.commit()
    client = _mock_client()

    narrative = write_pair_brief(
        session,
        client=client,
        primary=p,
        comparator=c,
        primary_aggregates={},
        comparator_aggregates={},
        primary_selections={},
        comparator_selections={},
    )

    assert narrative.contrast.text == PAIR_PLACEHOLDER_CONTRAST_TEXT
    client.generate_json.assert_not_called()


# ---------------------------------------------------------------------------
# Cite-pool filtering
# ---------------------------------------------------------------------------


def test_fabricated_cite_is_filtered_against_pool(session: Session) -> None:
    p, c = _setup(session)
    for mid in ["mp1", "mc1"]:
        _add_mention(session, mid)
    session.commit()

    primary_aggs = {
        Aspect.THERMALS: _agg(
            product_id=_PRIMARY_ID, aspect=Aspect.THERMALS, pos=5, net=0.4, primary_ids=["mp1"]
        ),
    }
    comparator_aggs = {
        Aspect.THERMALS: _agg(
            product_id=_COMPARATOR_ID, aspect=Aspect.THERMALS, pos=5, net=0.3, primary_ids=["mc1"]
        ),
    }
    primary_sels = {Aspect.THERMALS: _selection(Aspect.THERMALS, pp=["mp1"])}
    comparator_sels = {Aspect.THERMALS: _selection(Aspect.THERMALS, pp=["mc1"])}
    # Sonnet returns one valid cite + one fabricated; the fabricated is filtered silently.
    client = _mock_client(cited=["mp1", "made_up"])

    narrative = write_pair_brief(
        session,
        client=client,
        primary=p,
        comparator=c,
        primary_aggregates=primary_aggs,
        comparator_aggregates=comparator_aggs,
        primary_selections=primary_sels,
        comparator_selections=comparator_sels,
    )

    assert narrative.contrast.cited_mention_ids == ["mp1"]


def test_cite_from_either_side_is_allowed(session: Session) -> None:
    p, c = _setup(session)
    for mid in ["mp1", "mc1"]:
        _add_mention(session, mid)
    session.commit()

    primary_aggs = {
        Aspect.THERMALS: _agg(
            product_id=_PRIMARY_ID, aspect=Aspect.THERMALS, pos=5, net=0.4, primary_ids=["mp1"]
        ),
    }
    comparator_aggs = {
        Aspect.THERMALS: _agg(
            product_id=_COMPARATOR_ID, aspect=Aspect.THERMALS, pos=5, net=0.3, primary_ids=["mc1"]
        ),
    }
    primary_sels = {Aspect.THERMALS: _selection(Aspect.THERMALS, pp=["mp1"])}
    comparator_sels = {Aspect.THERMALS: _selection(Aspect.THERMALS, pp=["mc1"])}
    client = _mock_client(cited=["mc1"])  # comparator-side cite

    narrative = write_pair_brief(
        session,
        client=client,
        primary=p,
        comparator=c,
        primary_aggregates=primary_aggs,
        comparator_aggregates=comparator_aggs,
        primary_selections=primary_sels,
        comparator_selections=comparator_sels,
    )

    assert narrative.contrast.cited_mention_ids == ["mc1"]


# ---------------------------------------------------------------------------
# Pure-function routing
# ---------------------------------------------------------------------------


def test_leader_is_primary_when_delta_exceeds_threshold() -> None:
    primary_aggs = {
        Aspect.THERMALS: _agg(product_id=_PRIMARY_ID, aspect=Aspect.THERMALS, pos=8, net=0.6),
    }
    comparator_aggs = {
        Aspect.THERMALS: _agg(product_id=_COMPARATOR_ID, aspect=Aspect.THERMALS, pos=8, net=0.1),
    }
    entries = _compute_pair_entries(primary_aggs, comparator_aggs, {}, {})
    assert len(entries) == 1
    assert entries[0].leader == "primary"
    assert entries[0].delta == pytest.approx(0.5)


def test_leader_is_comparator_when_delta_is_negative() -> None:
    primary_aggs = {
        Aspect.THERMALS: _agg(product_id=_PRIMARY_ID, aspect=Aspect.THERMALS, pos=5, net=-0.2),
    }
    comparator_aggs = {
        Aspect.THERMALS: _agg(product_id=_COMPARATOR_ID, aspect=Aspect.THERMALS, pos=5, net=0.4),
    }
    entries = _compute_pair_entries(primary_aggs, comparator_aggs, {}, {})
    assert entries[0].leader == "comparator"


def test_leader_is_tie_when_delta_within_threshold() -> None:
    primary_aggs = {
        Aspect.THERMALS: _agg(product_id=_PRIMARY_ID, aspect=Aspect.THERMALS, pos=5, net=0.2),
    }
    comparator_aggs = {
        Aspect.THERMALS: _agg(product_id=_COMPARATOR_ID, aspect=Aspect.THERMALS, pos=5, net=0.15),
    }
    entries = _compute_pair_entries(primary_aggs, comparator_aggs, {}, {})
    assert entries[0].leader == "tie"


def test_aspect_below_min_mentions_on_both_sides_is_dropped() -> None:
    primary_aggs = {
        Aspect.THERMALS: _agg(product_id=_PRIMARY_ID, aspect=Aspect.THERMALS, pos=1, net=0.5),
        Aspect.DISPLAY: _agg(product_id=_PRIMARY_ID, aspect=Aspect.DISPLAY, pos=4, net=0.5),
    }
    comparator_aggs = {
        Aspect.THERMALS: _agg(product_id=_COMPARATOR_ID, aspect=Aspect.THERMALS, pos=2, net=0.0),
        Aspect.DISPLAY: _agg(product_id=_COMPARATOR_ID, aspect=Aspect.DISPLAY, pos=5, net=0.2),
    }
    entries = _compute_pair_entries(primary_aggs, comparator_aggs, {}, {})
    aspects = {e.aspect for e in entries}
    assert Aspect.THERMALS not in aspects  # both sides under 3
    assert Aspect.DISPLAY in aspects


def test_one_sided_aspect_kept_when_one_side_crosses_threshold() -> None:
    primary_aggs = {
        Aspect.THERMALS: _agg(product_id=_PRIMARY_ID, aspect=Aspect.THERMALS, pos=10, net=0.5),
    }
    comparator_aggs: dict[Aspect, AggregateAspectSku] = {}  # no comparator coverage
    entries = _compute_pair_entries(primary_aggs, comparator_aggs, {}, {})
    assert len(entries) == 1
    assert entries[0].primary is not None
    assert entries[0].comparator is None
    assert entries[0].leader == "primary"  # comparator missing → 0.0 net → delta = 0.5


def test_entries_sorted_by_abs_delta_desc() -> None:
    primary_aggs = {
        Aspect.THERMALS: _agg(product_id=_PRIMARY_ID, aspect=Aspect.THERMALS, pos=5, net=0.15),
        Aspect.DISPLAY: _agg(product_id=_PRIMARY_ID, aspect=Aspect.DISPLAY, pos=5, net=0.9),
        Aspect.BATTERY: _agg(product_id=_PRIMARY_ID, aspect=Aspect.BATTERY, pos=5, net=-0.4),
    }
    comparator_aggs = {
        Aspect.THERMALS: _agg(product_id=_COMPARATOR_ID, aspect=Aspect.THERMALS, pos=5, net=0.2),
        Aspect.DISPLAY: _agg(product_id=_COMPARATOR_ID, aspect=Aspect.DISPLAY, pos=5, net=0.1),
        Aspect.BATTERY: _agg(product_id=_COMPARATOR_ID, aspect=Aspect.BATTERY, pos=5, net=0.5),
    }
    entries = _compute_pair_entries(primary_aggs, comparator_aggs, {}, {})
    deltas_abs = [abs(e.delta) for e in entries]
    assert deltas_abs == sorted(deltas_abs, reverse=True)


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_unknown_prompt_version_raises(session: Session) -> None:
    p, c = _setup(session)
    session.commit()
    client = _mock_client()
    with pytest.raises(ValueError, match="unknown pair brief prompt_version"):
        write_pair_brief(
            session,
            client=client,
            primary=p,
            comparator=c,
            primary_aggregates={},
            comparator_aggregates={},
            primary_selections={},
            comparator_selections={},
            prompt_version="bogus",
        )


def test_malformed_contrast_block_raises(session: Session) -> None:
    p, c = _setup(session)
    for mid in ["mp1", "mc1"]:
        _add_mention(session, mid)
    session.commit()

    primary_aggs = {
        Aspect.THERMALS: _agg(
            product_id=_PRIMARY_ID, aspect=Aspect.THERMALS, pos=5, net=0.4, primary_ids=["mp1"]
        ),
    }
    comparator_aggs = {
        Aspect.THERMALS: _agg(
            product_id=_COMPARATOR_ID, aspect=Aspect.THERMALS, pos=5, net=0.3, primary_ids=["mc1"]
        ),
    }
    primary_sels = {Aspect.THERMALS: _selection(Aspect.THERMALS, pp=["mp1"])}
    comparator_sels = {Aspect.THERMALS: _selection(Aspect.THERMALS, pp=["mc1"])}

    client = MagicMock()
    bad_payload = {"brief_title": "T", "contrast": "not a dict"}
    client.generate_json.return_value = LlmResponse(
        raw_output=json.dumps(bad_payload), parsed_output=bad_payload
    )

    with pytest.raises(LlmResponseError, match="malformed or empty contrast"):
        write_pair_brief(
            session,
            client=client,
            primary=p,
            comparator=c,
            primary_aggregates=primary_aggs,
            comparator_aggregates=comparator_aggs,
            primary_selections=primary_sels,
            comparator_selections=comparator_sels,
        )


def test_strict_prompt_template_includes_strict_preamble() -> None:
    strict = _PAIR_PROMPT_TEMPLATES[PAIR_BRIEF_PROMPT_VERSION_STRICT]
    base = _PAIR_PROMPT_TEMPLATES[PAIR_BRIEF_PROMPT_VERSION]
    assert "STRICT MODE" in strict
    assert strict.endswith(base)


def test_truncate_passes_short_text_unchanged() -> None:
    from pulse_check.synthesis.pair_brief_writer import VERBATIM_TEXT_CAP_CHARS, _truncate

    short = "x" * (VERBATIM_TEXT_CAP_CHARS - 1)
    assert _truncate(short) == short


def test_truncate_caps_long_text_with_ellipsis_marker() -> None:
    from pulse_check.synthesis.pair_brief_writer import VERBATIM_TEXT_CAP_CHARS, _truncate

    long_text = "a" * (VERBATIM_TEXT_CAP_CHARS + 5000)
    out = _truncate(long_text)
    assert out.endswith("...")
    # body without the marker fits inside the cap (rstrip may trim trailing
    # spaces inside the slice; assert against the un-suffixed length)
    body = out[:-3]
    assert len(body) <= VERBATIM_TEXT_CAP_CHARS
    assert len(out) < len(long_text)
