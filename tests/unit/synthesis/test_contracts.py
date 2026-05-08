"""Tests for the A1 synthesis Pydantic contracts.

Validates that `BriefNarrative.model_dump()` round-trips through the
`briefs.narrative` JSON column, and that Pydantic enforces the
"every claim cites at least one mention" invariant at the contract layer.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from pulse_check.storage.enums import ScopeType
from pulse_check.storage.models import Brief, Run
from pulse_check.synthesis.contracts import (
    BriefNarrative,
    BriefSection,
    Claim,
    NumericalDrift,
    ValidationResult,
)


def _sample_narrative() -> BriefNarrative:
    return BriefNarrative(
        brief_title="Alienware 16 Aurora — Voice",
        sections=[
            BriefSection(
                heading="Thermals",
                claims=[
                    Claim(
                        claim_text="Reviewers consistently flag elevated fan noise.",
                        cited_mention_ids=["m_1", "m_2"],
                    )
                ],
            )
        ],
    )


def test_brief_narrative_round_trips_through_briefs_table(session: Session) -> None:
    session.add(
        Run(
            run_id="run_test_1",
            config_snapshot={"run_id": "run_test_1"},
            taxonomy_version="v0",
            prompt_versions={"a1_brief": "a1_brief_v1"},
        )
    )
    session.commit()

    narrative = _sample_narrative()
    session.add(
        Brief(
            run_id="run_test_1",
            scope_type=ScopeType.ASPECT_1_SKU,
            scope_id="alienware_16_aurora",
            narrative=narrative.model_dump(),
            prompt_version="a1_brief_v1",
            model="claude-sonnet-4-6",
        )
    )
    session.commit()

    fetched = session.query(Brief).one()
    rebuilt = BriefNarrative.model_validate(fetched.narrative)
    assert rebuilt == narrative


def test_claim_allows_empty_citation_list_for_placeholder() -> None:
    """Operator-locked, session 11: empty `cited_mention_ids` is permitted
    so the §6.3 A1 brief can render its empty-section-2 placeholder claim
    (`"No top-of-mind criticism in PRIMARY chatter — see §4 below"`)."""
    claim = Claim(claim_text="A placeholder.", cited_mention_ids=[])
    assert claim.cited_mention_ids == []


def test_claim_rejects_empty_text() -> None:
    with pytest.raises(ValidationError):
        Claim(claim_text="", cited_mention_ids=["m_1"])


def test_brief_section_rejects_empty_claims() -> None:
    with pytest.raises(ValidationError):
        BriefSection(heading="Thermals", claims=[])


def test_brief_narrative_rejects_empty_sections() -> None:
    with pytest.raises(ValidationError):
        BriefNarrative(brief_title="Foo", sections=[])


def test_validation_result_defaults_to_empty_lists() -> None:
    result = ValidationResult(is_valid=True)
    assert result.fabricated_ids == []
    assert result.out_of_context_ids == []
    assert result.numerical_drift == []
    assert result.empty_claims == []


def test_validation_result_carries_drift_payload() -> None:
    result = ValidationResult(
        is_valid=False,
        numerical_drift=[
            NumericalDrift(
                claim_text="Appears in 60 threads.",
                claimed_n=60,
                actual_n=42,
            )
        ],
    )
    assert result.is_valid is False
    assert len(result.numerical_drift) == 1
    assert result.numerical_drift[0].actual_n == 42
