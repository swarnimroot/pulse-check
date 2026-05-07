"""Haiku near-duplicate clustering for verbatim-mention pools.

The selector picks ~3 positive + ~3 negative verbatims per aspect
(ARCHITECTURE §7.1 step 4). Without dedup, near-paraphrase mentions
("fans run loud" vs "the fans are loud") flood the selector and starve
diverse coverage. This module clusters mentions that say the same thing
so the selector picks one representative per cluster.

Routed to Haiku per LLM_ROUTING (ARCHITECTURE §6.1): cheap, fast, and the
"these two say the same thing" judgment doesn't need Sonnet's reasoning.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from pulse_check.storage.models import Mention

DEDUP_PROMPT_VERSION = "a1_dedup_v1"


def cluster_near_duplicates(
    session: Session,
    mentions: list[Mention],
    *,
    prompt_version: str = DEDUP_PROMPT_VERSION,
) -> dict[str, str]:
    """Return a `{mention_id: cluster_id}` map.

    Mentions that paraphrase each other share a cluster_id; mentions that
    don't paraphrase any other mention get a unique cluster_id (typically
    derived from their own mention_id).

    Determinism: identical input mention pool + same prompt_version yields
    identical cluster assignments via the LLM cache layer.
    """
    raise NotImplementedError("synthesis.dedup not implemented (sub-bite 10.2)")
