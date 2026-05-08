"""Tests for the A1 synthesis orchestrator.

Mocks the Anthropic client at the brief-writer call layer and patches
`cluster_near_duplicates` + `validate_citations` to drive control-flow
branches deterministically. The selector and brief writer's deterministic
parts run for real against the in-memory SQLite session.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmResponse
from pulse_check.storage.enums import (
    Aspect,
    Intensity,
    Polarity,
    ScopeType,
    SourceType,
)
from pulse_check.storage.models import (
    AggregateAspectSku,
    AspectTag,
    Brief,
    Mention,
    Product,
    Run,
)
from pulse_check.synthesis import orchestrator as orch
from pulse_check.synthesis.brief_writer import (
    BRIEF_MODEL,
    BRIEF_PROMPT_VERSION,
    BRIEF_PROMPT_VERSION_STRICT,
)
from pulse_check.synthesis.contracts import ValidationResult
from pulse_check.synthesis.orchestrator import synthesize_a1

_PRODUCT_ID = "alienware_16"
_RUN_ID = "run_test_orchestrator"


def _setup_corpus(session: Session) -> Product:
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

    primary_ids = ["mp1", "mp2", "mp3"]
    for mid in primary_ids:
        session.add(
            Mention(
                mention_id=mid,
                source_type=SourceType.REDDIT_POST,
                source_url="https://example.com",
                raw_text=f"Performance is great on {mid}.",
            )
        )
        session.add(
            AspectTag(
                mention_id=mid,
                product_id=_PRODUCT_ID,
                aspect=Aspect.PERFORMANCE,
                polarity=Polarity.POSITIVE,
                intensity=Intensity.HIGH,
                taxonomy_version="v0",
                prompt_version="aspect_classifier_v1",
                model="haiku-test",
                temperature=0.0,
            )
        )

    session.add(
        AggregateAspectSku(
            run_id=_RUN_ID,
            product_id=_PRODUCT_ID,
            aspect=Aspect.PERFORMANCE,
            total_mentions=3,
            polarity_counts={"positive": 3, "negative": 0, "neutral": 0, "mixed": 0},
            net_sentiment=1.0,
            intensity_counts={"high": 3},
            verified_share=0.0,
            by_source={},
            by_recency={},
            mention_ids=primary_ids,
            total_mentions_secondary=0,
            polarity_counts_secondary={},
            net_sentiment_secondary=0.0,
            intensity_counts_secondary={},
            verified_share_secondary=0.0,
            by_source_secondary={},
            by_recency_secondary={},
            mention_ids_secondary=[],
        )
    )
    session.flush()
    return p


def _stub_dedup(monkeypatch: pytest.MonkeyPatch, mapping: dict[str, str]) -> None:
    def _fake(session: Session, mentions: Iterable[Mention], **_kwargs: Any) -> dict[str, str]:
        return {m.mention_id: mapping.get(m.mention_id, f"c_{m.mention_id}") for m in mentions}

    monkeypatch.setattr(orch, "cluster_near_duplicates", _fake)


def _stub_validator(
    monkeypatch: pytest.MonkeyPatch, results: list[ValidationResult]
) -> list[int]:
    """Patch `validate_citations` to return `results` in order. Returns a
    counter list (length = number of calls made) for assertions."""
    calls: list[int] = []

    def _fake(*_args: Any, **_kwargs: Any) -> ValidationResult:
        calls.append(1)
        return results[len(calls) - 1]

    monkeypatch.setattr(orch, "validate_citations", _fake)
    return calls


def _mock_brief_client(claims: list[dict[str, Any]], brief_title: str = "Test") -> Any:
    client = MagicMock()
    payload = {"brief_title": brief_title, "claims": claims}
    text = json.dumps(payload)
    client.generate_json.return_value = LlmResponse(raw_output=text, parsed_output=payload)
    return client


def _mock_brief_client_two_responses(
    first: dict[str, Any], second: dict[str, Any]
) -> Any:
    client = MagicMock()
    client.generate_json.side_effect = [
        LlmResponse(raw_output=json.dumps(first), parsed_output=first),
        LlmResponse(raw_output=json.dumps(second), parsed_output=second),
    ]
    return client


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_orchestrator_persists_brief_row(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_corpus(session)
    _stub_dedup(monkeypatch, {})

    client = _mock_brief_client(
        claims=[
            {"quadrant_id": 1, "aspect": "performance", "claim_text": "Owners praise it."}
        ]
    )

    brief = synthesize_a1(
        session, client=client, run_id=_RUN_ID, product_id=_PRODUCT_ID
    )

    assert brief.brief_id is not None
    assert brief.run_id == _RUN_ID
    assert brief.scope_type == ScopeType.ASPECT_1_SKU
    assert brief.scope_id == _PRODUCT_ID
    assert brief.prompt_version == BRIEF_PROMPT_VERSION
    assert brief.model == BRIEF_MODEL

    persisted = session.get(Brief, brief.brief_id)
    assert persisted is not None
    assert persisted.narrative["brief_title"] == "Test"
    # Q1 has 3 PRIMARY positives → real section; Q2 is empty → α placeholder.
    assert len(persisted.narrative["sections"]) == 2


def test_orchestrator_includes_flagged_citation_issues(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_corpus(session)
    _stub_dedup(monkeypatch, {})

    client = _mock_brief_client(
        claims=[
            {"quadrant_id": 1, "aspect": "performance", "claim_text": "Owners praise it."}
        ]
    )

    brief = synthesize_a1(
        session, client=client, run_id=_RUN_ID, product_id=_PRODUCT_ID
    )

    assert "flagged_citation_issues" in brief.narrative
    flags = brief.narrative["flagged_citation_issues"]
    assert flags["is_valid"] is True
    assert flags["fabricated_ids"] == []
    assert flags["out_of_context_ids"] == []
    assert flags["numerical_drift"] == []
    assert flags["empty_claims"] == []


# ---------------------------------------------------------------------------
# Retry on fabricated_ids
# ---------------------------------------------------------------------------


def test_orchestrator_retries_on_fabricated_ids(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_corpus(session)
    _stub_dedup(monkeypatch, {})

    _stub_validator(
        monkeypatch,
        results=[
            ValidationResult(is_valid=False, fabricated_ids=["fake_x"]),
            ValidationResult(is_valid=True),
        ],
    )

    client = _mock_brief_client_two_responses(
        first={
            "brief_title": "First",
            "claims": [
                {"quadrant_id": 1, "aspect": "performance", "claim_text": "First take."}
            ],
        },
        second={
            "brief_title": "Strict",
            "claims": [
                {"quadrant_id": 1, "aspect": "performance", "claim_text": "Strict take."}
            ],
        },
    )

    brief = synthesize_a1(
        session, client=client, run_id=_RUN_ID, product_id=_PRODUCT_ID
    )

    assert client.generate_json.call_count == 2
    assert brief.prompt_version == BRIEF_PROMPT_VERSION_STRICT
    assert brief.narrative["brief_title"] == "Strict"
    assert brief.narrative["flagged_citation_issues"]["is_valid"] is True


def test_orchestrator_does_not_retry_on_other_warnings(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _setup_corpus(session)
    _stub_dedup(monkeypatch, {})

    only_drift = ValidationResult(
        is_valid=False,
        fabricated_ids=[],
        out_of_context_ids=["stray_mention"],
        empty_claims=[],
    )
    calls = _stub_validator(monkeypatch, results=[only_drift])

    client = _mock_brief_client(
        claims=[
            {"quadrant_id": 1, "aspect": "performance", "claim_text": "Some take."}
        ]
    )

    brief = synthesize_a1(
        session, client=client, run_id=_RUN_ID, product_id=_PRODUCT_ID
    )

    assert client.generate_json.call_count == 1
    assert len(calls) == 1
    assert brief.prompt_version == BRIEF_PROMPT_VERSION
    flags = brief.narrative["flagged_citation_issues"]
    assert flags["out_of_context_ids"] == ["stray_mention"]
    assert flags["is_valid"] is False


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_orchestrator_raises_when_product_missing(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_dedup(monkeypatch, {})
    client = _mock_brief_client(claims=[])

    with pytest.raises(ValueError, match="product not found"):
        synthesize_a1(
            session, client=client, run_id=_RUN_ID, product_id="ghost_product"
        )


def test_orchestrator_raises_when_no_aggregates(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.add(
        Run(
            run_id=_RUN_ID,
            config_snapshot={"run_id": _RUN_ID},
            taxonomy_version="v0",
            prompt_versions={},
        )
    )
    session.add(
        Product(product_id=_PRODUCT_ID, display_name="Alienware 16", brand="dell")
    )
    session.flush()

    _stub_dedup(monkeypatch, {})
    client = _mock_brief_client(claims=[])

    with pytest.raises(ValueError, match="no aggregates_aspect_sku rows"):
        synthesize_a1(
            session, client=client, run_id=_RUN_ID, product_id=_PRODUCT_ID
        )


# ---------------------------------------------------------------------------
# All-empty corpus
# ---------------------------------------------------------------------------


def test_orchestrator_handles_aggregates_with_no_mention_ids(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aggregate row exists but its mention_ids lists are empty.

    Brief writer short-circuits Sonnet (no qualifying aspects); validator
    sees only the placeholder claim. No retry expected.
    """
    session.add(
        Run(
            run_id=_RUN_ID,
            config_snapshot={"run_id": _RUN_ID},
            taxonomy_version="v0",
            prompt_versions={},
        )
    )
    session.add(
        Product(product_id=_PRODUCT_ID, display_name="Alienware 16", brand="dell")
    )
    session.add(
        AggregateAspectSku(
            run_id=_RUN_ID,
            product_id=_PRODUCT_ID,
            aspect=Aspect.PERFORMANCE,
            total_mentions=0,
            polarity_counts={},
            net_sentiment=0.0,
            intensity_counts={},
            verified_share=0.0,
            by_source={},
            by_recency={},
            mention_ids=[],
            total_mentions_secondary=0,
            polarity_counts_secondary={},
            net_sentiment_secondary=0.0,
            intensity_counts_secondary={},
            verified_share_secondary=0.0,
            by_source_secondary={},
            by_recency_secondary={},
            mention_ids_secondary=[],
        )
    )
    session.flush()

    _stub_dedup(monkeypatch, {})
    client = MagicMock()  # should never be called

    brief = synthesize_a1(
        session, client=client, run_id=_RUN_ID, product_id=_PRODUCT_ID
    )

    assert client.generate_json.call_count == 0
    assert brief.prompt_version == BRIEF_PROMPT_VERSION
    sections = brief.narrative["sections"]
    assert len(sections) == 1
    assert sections[0]["claims"][0]["cited_mention_ids"] == []
