"""Sonnet brief writer — turns selected verbatims into a §6.3 BriefNarrative.

Receives the aggregates (numerical evidence) and the selected mention IDs
(qualitative evidence) and returns a `BriefNarrative` whose claims each
cite real mention IDs from the input pool.

Structured to make fabrication mechanically harder: the prompt enumerates
the cite-able mention IDs, asks for `sections[].claims[]` with
`cited_mention_ids` referencing only those, and `citation_validator`
catches anything that slips through.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from pulse_check.storage.enums import Aspect
from pulse_check.storage.models import AggregateAspectSku, Product
from pulse_check.synthesis.contracts import BriefNarrative

BRIEF_PROMPT_VERSION = "a1_brief_v1"


def write_a1_brief(
    session: Session,
    *,
    product: Product,
    aggregates: list[AggregateAspectSku],
    selected_verbatims: dict[Aspect, list[str]],
    prompt_version: str = BRIEF_PROMPT_VERSION,
) -> BriefNarrative:
    """Generate the brief narrative for one product across selected aspects.

    `selected_verbatims` is `{aspect: [mention_id, ...]}` from the selector.
    The writer reads each mention's verbatim text from the DB and includes
    it in the prompt as the cite-able pool.
    """
    raise NotImplementedError("synthesis.brief_writer not implemented (sub-bite 10.3)")
