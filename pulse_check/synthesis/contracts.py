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
    """One factual statement in the brief, citing zero or more mention IDs.

    `cited_mention_ids` is normally non-empty; the citation validator catches
    fabrication and out-of-context IDs as a defense-in-depth check (TESTING
    §6). Empty list is permitted ONLY for the §6.3 "A1 brief layout"
    placeholder claim (empty section 2 — operator-locked, session 11). The
    validator is aware of this exemption.

    `header` is a 2-5 word bold lead-in shown ahead of `claim_text` in the
    UI bullet (added in prompt_version `a1_brief_v2`). Stored briefs written
    before v2 do not carry this field; the frontend renders gracefully
    when it's absent.
    """

    header: str = Field(..., min_length=1, max_length=80)
    claim_text: str = Field(..., min_length=1)
    cited_mention_ids: list[str] = Field(..., min_length=0)


class BriefSection(BaseModel):
    """One heading with one or more claims under it."""

    heading: str = Field(..., min_length=1)
    claims: list[Claim] = Field(..., min_length=1)


class BriefSummary(BaseModel):
    """One short paragraph capturing the texture of consumer chatter for a
    product, with 2-3 citations into the same mention pool the sections cite.

    Added in `a1_brief_v3` (session 41; originally `VibeSummary` →
    `BriefSummary` later in session 41 per operator-preferred register). The
    paragraph sits between the snapshot row and the strengths section in both
    the on-page brief and the export sheet. Content rules live in the Sonnet
    prompt; this contract enforces only the length bound and the citation-list
    shape. Briefs from `a1_brief_v2` and earlier have `summary = None`; the
    frontend renders nothing for that branch.
    """

    text: str = Field(..., min_length=1, max_length=600)
    cited_mention_ids: list[str] = Field(..., min_length=0)


class BriefNarrative(BaseModel):
    """Top-level brief shape; serializes to the `briefs.narrative` JSON column.

    The Wave 4 frontend (BriefPanel) renders one section per heading and a
    citation popover per claim hovering over `cited_mention_ids`.
    """

    brief_title: str = Field(..., min_length=1)
    sections: list[BriefSection] = Field(..., min_length=1)
    summary: BriefSummary | None = None


class PairBriefContrast(BaseModel):
    """Two-side contrast paragraph for a pair brief.

    Shaped like `BriefSummary` (text + cited_mention_ids) but with a wider
    char cap (800 vs 600). Reason: pair briefs naturally run longer than A1
    summaries because each sentence enumerates aspects on one side; 50-80
    word target × two products of aspect lists pushes character count past
    the A1 ceiling on roughly 1-in-5 pairs (observed session 42 smoke).
    Cap session-locked at 800 after first 10-pair batch — see
    SESSION_LOG session 42 D2.
    """

    text: str = Field(..., min_length=1, max_length=800)
    cited_mention_ids: list[str] = Field(..., min_length=0)


class PairBriefNarrative(BaseModel):
    """Top-level pair-brief shape; serializes to `briefs.narrative` JSON on
    rows with `scope_type=ASPECT_2_PAIR`.

    Designed in session 42 (ARCHITECTURE §6.4 — pair brief layout). Single
    contrast paragraph framing where the primary product leads, where the
    comparator leads, and where opinions converge. No multi-section structure:
    the existing Pair page scorecard supplies the per-aspect numerical detail;
    the contrast paragraph supplies the texture.

    `contrast` is `PairBriefContrast` (50-80 word paragraph, 800-char ceiling,
    2-3 cited mention IDs drawn from BOTH sides' verbatim pools). The
    placeholder branch (no aspect crosses the per-side minimum) still emits a
    valid `PairBriefContrast` carrying fixed text and no cites — see
    `pair_brief_writer.PAIR_PLACEHOLDER_CONTRAST_TEXT`.
    """

    brief_title: str = Field(..., min_length=1)
    contrast: PairBriefContrast


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
