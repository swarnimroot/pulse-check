"""Citation integrity check for a generated BriefNarrative (TESTING §6).

Soft-warn policy (operator decision, session 10): violations populate
`ValidationResult` but do NOT block brief persistence. The orchestrator
surfaces violations in `flagged_citation_issues` on the persisted narrative.

Four checks:
    1. Fabricated IDs — every cited ID resolves to a real `mentions` row.
    2. Out-of-context IDs — every cited ID was in the input mention pool the
       selector was given (`allowed_pool`); IDs in the DB but outside the
       pool indicate cross-product / cross-run leakage.
    3. Numerical drift — claims like "appears in N threads" must match the
       cited aggregate's mention_ids length within ±5%.
    4. Empty claims — every claim must have ≥1 cited_mention_id, EXCEPT the
       §6.3 placeholder claim with the operator-locked exact text.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.storage.enums import Aspect
from pulse_check.storage.models import AggregateAspectSku, Mention
from pulse_check.synthesis.brief_writer import PLACEHOLDER_CLAIM_TEXT
from pulse_check.synthesis.contracts import (
    BriefNarrative,
    NumericalDrift,
    ValidationResult,
)

NUMERICAL_DRIFT_TOLERANCE = 0.05

# Match an integer followed by a count-shaped noun. Tighter than \b\d+\b —
# avoids false positives like "1080p display" or "16GB RAM". Case-insensitive.
_COUNT_NOUN_PATTERN = re.compile(
    r"\b(\d+)\s+"
    r"(?:user|mention|thread|reviewer|comment|post|review|owner|customer|"
    r"complaint|complain|praise|report)s?\b",
    re.IGNORECASE,
)


def validate_citations(
    session: Session,
    *,
    narrative: BriefNarrative,
    aggregates: Mapping[Aspect, AggregateAspectSku],
    allowed_pool: set[str],
    drift_tolerance: float = NUMERICAL_DRIFT_TOLERANCE,
) -> ValidationResult:
    """Run the four citation-integrity checks against `narrative`.

    `allowed_pool` is the union of PRIMARY + SECONDARY mention IDs the
    orchestrator passed to the selector for this product (across all aspects).
    Cited IDs outside this set indicate out-of-context leakage.

    `aggregates` is used to determine the actual mention count for the drift
    check: each claim's cited IDs are matched against an aggregate's
    `mention_ids` (PRIMARY) or `mention_ids_secondary` (SECONDARY) to find
    which aspect/bucket the claim summarizes.

    Soft-warn: never raises. Returns `ValidationResult` with `is_valid=True`
    only when all four lists are empty.
    """
    fabricated: list[str] = []
    out_of_context: list[str] = []
    numerical_drift: list[NumericalDrift] = []
    empty_claims: list[str] = []

    cited_ids: set[str] = set()
    for section in narrative.sections:
        for claim in section.claims:
            cited_ids.update(claim.cited_mention_ids)
    if narrative.summary is not None:
        cited_ids.update(narrative.summary.cited_mention_ids)

    if cited_ids:
        existing_rows = session.execute(
            select(Mention.mention_id).where(Mention.mention_id.in_(cited_ids))
        ).all()
        existing_ids = {row[0] for row in existing_rows}
        fabricated = sorted(cited_ids - existing_ids)
        out_of_context = sorted((cited_ids & existing_ids) - allowed_pool)

    for section in narrative.sections:
        for claim in section.claims:
            if claim.cited_mention_ids:
                continue
            if claim.claim_text != PLACEHOLDER_CLAIM_TEXT:
                empty_claims.append(claim.claim_text)

    for section in narrative.sections:
        for claim in section.claims:
            if not claim.cited_mention_ids:
                continue
            actual_n = _resolve_actual_n(claim.cited_mention_ids, aggregates)
            divisor = max(actual_n, 1)
            for match in _COUNT_NOUN_PATTERN.finditer(claim.claim_text):
                claimed_n = int(match.group(1))
                drift = abs(claimed_n - actual_n) / divisor
                if drift > drift_tolerance:
                    numerical_drift.append(
                        NumericalDrift(
                            claim_text=claim.claim_text,
                            claimed_n=claimed_n,
                            actual_n=actual_n,
                        )
                    )

    is_valid = not (fabricated or out_of_context or numerical_drift or empty_claims)
    return ValidationResult(
        is_valid=is_valid,
        fabricated_ids=fabricated,
        out_of_context_ids=out_of_context,
        numerical_drift=numerical_drift,
        empty_claims=empty_claims,
    )


def _resolve_actual_n(
    cited_mention_ids: list[str],
    aggregates: Mapping[Aspect, AggregateAspectSku],
) -> int:
    """Return the count for the aggregate/bucket the cited IDs belong to.

    The brief writer constructs claims per (quadrant, aspect): all cited IDs
    of one claim come from one bucket of one aggregate. Match cited_set
    against `mention_ids` (PRIMARY) or `mention_ids_secondary` (SECONDARY) to
    locate that bucket and return its count. Fall back to the citation list
    size if no aggregate matches (cross-bucket or unknown).
    """
    cited_set = set(cited_mention_ids)
    for agg in aggregates.values():
        primary_set = set(agg.mention_ids or [])
        if cited_set <= primary_set:
            return len(primary_set)
        secondary_set = set(agg.mention_ids_secondary or [])
        if cited_set <= secondary_set:
            return len(secondary_set)
    return len(cited_mention_ids)
