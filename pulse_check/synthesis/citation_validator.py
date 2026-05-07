"""Citation integrity check for a generated BriefNarrative (TESTING §6).

Soft-warn policy (operator decision, session 10): violations populate
`ValidationResult` but do NOT block brief persistence. The orchestrator
surfaces violations in `flagged_citation_issues` on the persisted narrative.

Four checks:
    1. Every cited ID resolves to a real `mentions` row (no fabricated IDs).
    2. Every cited ID was in the input mention pool (no out-of-context IDs).
    3. Numerical claims like "appears in N threads" are within ±5% of the
       citation list length.
    4. No claim has `cited_mention_ids == []` (Pydantic catches this at the
       contract layer; we re-check defensively).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from pulse_check.synthesis.contracts import BriefNarrative, ValidationResult

NUMERICAL_DRIFT_TOLERANCE = 0.05


def validate_citations(
    session: Session,
    *,
    narrative: BriefNarrative,
    primary_pool: set[str],
    drift_tolerance: float = NUMERICAL_DRIFT_TOLERANCE,
) -> ValidationResult:
    """Run the four citation-integrity checks against `narrative`.

    `primary_pool` is the set of mention IDs the selector was allowed to
    pick from; the citation contract requires every cited ID to be drawn
    from this set.
    """
    raise NotImplementedError(
        "synthesis.citation_validator not implemented (sub-bite 10.4)"
    )
