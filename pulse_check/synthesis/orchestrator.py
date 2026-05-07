"""Top-level A1 synthesis orchestrator: dedup → selector → writer → validator.

Sequences the four synthesis stages, persists the resulting Brief row, and
returns it. Single entry point for downstream callers (`scripts/synthesize.py`,
the FastAPI brief handler in Wave 2 backend).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from pulse_check.storage.models import Brief


def synthesize_a1(
    session: Session,
    *,
    run_id: str,
    product_id: str,
) -> Brief:
    """Run the full A1 pipeline for one product within a run.

    Stages:
        1. Build PRIMARY mention pool from aggregates (per aspect).
        2. Haiku dedup the pool into clusters.
        3. Sonnet selector picks ~3 positive + ~3 negative verbatim IDs per
           aspect.
        4. Sonnet brief writer turns aggregates + selected verbatims into a
           BriefNarrative.
        5. citation_validator soft-warns on integrity violations.
        6. Persist Brief row (`scope_type=ASPECT_1_SKU`, `scope_id=product_id`).
    """
    raise NotImplementedError(
        "synthesis.orchestrator not implemented (sub-bite 10.4)"
    )
