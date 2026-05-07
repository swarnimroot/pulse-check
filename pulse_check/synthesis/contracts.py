"""Pydantic contracts for the A1 synthesis pipeline.

Locks the §6.3 brief shape (`brief_title` / `sections` / `claims`) and the
`ValidationResult` shape returned by `citation_validator`. Every stage of the
pipeline (dedup → selector → brief_writer → citation_validator) imports from
this module so the contract is single-sourced.

`BriefNarrative.model_dump()` is the JSON written into the `briefs.narrative`
column. See ARCHITECTURE §6.3.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Claim(BaseModel):
    """One factual statement in the brief, citing one or more mention IDs.

    `cited_mention_ids` MUST be non-empty; an empty list is a semantic error
    that the citation validator also catches as a defense-in-depth check
    (TESTING §6).
    """

    claim_text: str = Field(..., min_length=1)
    cited_mention_ids: list[str] = Field(..., min_length=1)


class BriefSection(BaseModel):
    """One heading with one or more claims under it."""

    heading: str = Field(..., min_length=1)
    claims: list[Claim] = Field(..., min_length=1)


class BriefNarrative(BaseModel):
    """Top-level brief shape; serializes to the `briefs.narrative` JSON column.

    The Wave 4 frontend (BriefPanel) renders one section per heading and a
    citation popover per claim hovering over `cited_mention_ids`.
    """

    brief_title: str = Field(..., min_length=1)
    sections: list[BriefSection] = Field(..., min_length=1)


class NumericalDrift(BaseModel):
    """A claim whose stated count diverges from the citation list size by more
    than the validator's tolerance (TESTING §6, default ±5%)."""

    claim_text: str
    claimed_n: int
    actual_n: int


class ValidationResult(BaseModel):
    """Outcome of `citation_validator.validate_citations`.

    Soft-warn policy (operator decision, session 10): the brief is still
    persisted when `is_valid` is False. Violations populate the four
    list/struct fields below; the orchestrator surfaces them in a
    `flagged_citation_issues` field on the persisted narrative so the UI
    can flag the brief without blocking it.
    """

    is_valid: bool
    fabricated_ids: list[str] = Field(default_factory=list)
    out_of_context_ids: list[str] = Field(default_factory=list)
    numerical_drift: list[NumericalDrift] = Field(default_factory=list)
    empty_claims: list[str] = Field(default_factory=list)
