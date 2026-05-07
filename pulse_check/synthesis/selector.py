"""Sonnet verbatim selector — picks mention IDs only, never invents text.

Returns the IDs of mentions to cite in the brief. The brief writer then
reads each Mention's verbatim text from the DB and quotes it. The selector
NEVER produces text. This separation is the core of the no-fabrication
contract (ARCHITECTURE §6.3, evidence-first principle in CLAUDE.md).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from pulse_check.storage.enums import Aspect

SELECTOR_PROMPT_VERSION = "a1_selector_v1"


def select_a1_verbatims(
    session: Session,
    *,
    product_id: str,
    aspect: Aspect,
    primary_mention_pool: list[str],
    clusters: dict[str, str],
    prompt_version: str = SELECTOR_PROMPT_VERSION,
) -> list[str]:
    """Return mention IDs to cite for `(product_id, aspect)`.

    Targets ~3 positive + ~3 negative biased to high-intensity (ARCHITECTURE
    §7.1 step 4), with one representative per cluster — `clusters` is the
    `{mention_id: cluster_id}` map from `dedup.cluster_near_duplicates`.

    SECONDARY-attribution mentions are not in `primary_mention_pool` and
    therefore cannot be cited (CLAUDE.md citation contract).
    """
    raise NotImplementedError("synthesis.selector not implemented (sub-bite 10.3)")
