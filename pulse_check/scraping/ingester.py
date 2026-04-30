"""Upsert scrapers-lib fetcher results into the analytical store.

The Scheduler delivers each fetcher's output (a `list[RawMention]` or
`list[ProductSnapshot]`) to `ingest_batch(session, results)`. The ingester:

- skips ProductSnapshot entries (v1 has no snapshot table — deferred)
- upserts each RawMention by `mention_id` (idempotent on re-fetch)
- appends one PRIMARY MentionAttribution per `RawMention.attribution`,
  deduplicated on (mention_id, product_id, attribution_type) so repeat anchor
  matches on re-runs don't violate the unique constraint.

`attribute_regex_all` can emit one RawMention per matched anchor carrying the
same `mention_id` — e.g. a Reddit post that matches two product anchors
arrives as two RawMentions. The upsert-then-append pattern folds these into
one Mention with multiple attributions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from scrapers_lib import ProductSnapshot, RawMention
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.scraping.converter import (
    attribution_to_row,
    raw_mention_to_mention,
)
from pulse_check.storage.models import Mention, MentionAttribution

log = logging.getLogger(__name__)


@dataclass
class IngestStats:
    """Summary of one ingest call. Counters accumulate across batches."""

    new_mentions: int = 0
    existing_mentions: int = 0
    new_attributions: int = 0
    existing_attributions: int = 0
    skipped_snapshots: int = 0
    skipped_without_attribution: int = 0


def ingest_batch(
    session: Session,
    results: list[RawMention | ProductSnapshot],
    *,
    stats: IngestStats | None = None,
) -> IngestStats:
    """Ingest one batch of fetcher results. Does not commit — caller owns txn."""
    if stats is None:
        stats = IngestStats()

    for item in results:
        if isinstance(item, ProductSnapshot):
            stats.skipped_snapshots += 1
            continue
        if isinstance(item, RawMention):
            _ingest_raw_mention(session, item, stats)
            continue
        log.warning("ingester received unexpected type %s; skipping", type(item).__name__)

    session.flush()
    return stats


def _ingest_raw_mention(session: Session, mention: RawMention, stats: IngestStats) -> None:
    existing = session.get(Mention, mention.mention_id)
    if existing is None:
        session.add(raw_mention_to_mention(mention))
        stats.new_mentions += 1
    else:
        stats.existing_mentions += 1

    if mention.attribution is None:
        stats.skipped_without_attribution += 1
        return

    # Dedup (mention_id, product_id, attribution_type) to honour the unique constraint.
    existing_attr = session.execute(
        select(MentionAttribution).where(
            MentionAttribution.mention_id == mention.mention_id,
            MentionAttribution.product_id == mention.attribution.anchor_id,
            MentionAttribution.attribution_type
            == attribution_to_row(mention.mention_id, mention.attribution).attribution_type,
        )
    ).scalar_one_or_none()
    if existing_attr is not None:
        stats.existing_attributions += 1
        return

    session.add(attribution_to_row(mention.mention_id, mention.attribution))
    stats.new_attributions += 1
