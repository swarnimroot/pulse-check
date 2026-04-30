"""A1 aggregator: roll aspect_tags into aggregates_aspect_sku rows.

Per (product_id, aspect) group:
- ``total_mentions`` — count of distinct contributing mention_ids.
- ``polarity_counts`` / ``intensity_counts`` — zero-filled distributions
  over tags. The unique key on ``aspect_tags`` guarantees one tag per
  (mention, product, aspect, taxonomy_version, prompt_version), so per-tag
  here means per-mention.
- ``net_sentiment`` — ``(positive - negative) / total_mentions`` in
  [-1.0, 1.0]. Flat per-mention formula; no weighting by intensity,
  recency, source, or anything else (CLAUDE.md "every mention = 1.0").
- ``verified_share`` — fraction of contributing mentions whose
  ``metadata_["verified_purchase"]`` is True; missing key reads as False.
- ``by_source`` — ``{source_value: {"total": int, "polarity_counts": ...}}``.
- ``by_recency`` — count per bucket (``0_30``, ``30_90``, ``90_180``,
  ``180_plus``, ``unknown``) on ``mention.published_at`` vs. ``now``.
- ``mention_ids`` — sorted, deduped contributing IDs (provenance per the
  evidence-first principle).

Scope: PRIMARY ``MentionAttribution`` only — secondary attributions are
A2's "considered mention" corpus. Caller owns the transaction
(``flush`` only). Idempotent rerun via delete-then-insert keyed on
``(run_id, product_id)``: an aspect that drops to zero correctly removes
its prior row.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pulse_check.storage.enums import Aspect, AttributionType, Intensity, Polarity
from pulse_check.storage.models import (
    AggregateAspectSku,
    AspectTag,
    Mention,
    MentionAttribution,
)

log = logging.getLogger(__name__)


_POLARITY_KEYS: tuple[str, ...] = tuple(p.value for p in Polarity)
_INTENSITY_KEYS: tuple[str, ...] = tuple(i.value for i in Intensity)
_RECENCY_KEYS: tuple[str, ...] = ("0_30", "30_90", "90_180", "180_plus", "unknown")


@dataclass(frozen=True)
class BatchAggregateStats:
    """Outcome summary of one A1 aggregation pass.

    ``mentions_contributing`` sums distinct mentions across groups; a
    mention tagged on N aspects contributes N times.
    """

    groups_seen: int
    aggregates_upserted: int
    mentions_contributing: int


def _zero_polarity() -> dict[str, int]:
    return dict.fromkeys(_POLARITY_KEYS, 0)


def _zero_intensity() -> dict[str, int]:
    return dict.fromkeys(_INTENSITY_KEYS, 0)


def _zero_recency() -> dict[str, int]:
    return dict.fromkeys(_RECENCY_KEYS, 0)


def _recency_bucket(published_at: datetime | None, now: datetime) -> str:
    if published_at is None:
        return "unknown"
    days = (now - published_at).days
    if days < 30:
        return "0_30"
    if days < 90:
        return "30_90"
    if days < 180:
        return "90_180"
    return "180_plus"


def aggregate_a1(
    session: Session,
    *,
    run_id: str,
    product_ids: Iterable[str],
    taxonomy_version: str,
    prompt_version: str,
    now: datetime | None = None,
) -> BatchAggregateStats:
    """Aggregate aspect tags into per-(product, aspect) rows.

    Arguments
    ---------
    session:
        Open SQLAlchemy session. Function flushes but does not commit;
        caller owns the transaction boundary.
    run_id:
        FK into ``runs.run_id``. The Run row must exist.
    product_ids:
        Products in scope. Out-of-scope products are skipped entirely.
    taxonomy_version, prompt_version:
        Filters on ``aspect_tags``. Aggregates derived from this single
        version pair only — calling against a different version wipes any
        prior aggregates for the same ``(run_id, product_id)`` since the
        aggregate row carries no version column (deliberate: per
        ``ARCHITECTURE`` §3.3 the aggregate represents the "current" pass
        for that run).
    now:
        Injectable clock for deterministic recency bucketing in tests.
    """
    if now is None:
        now = datetime.now(UTC)

    product_id_set = set(product_ids)
    if not product_id_set:
        return BatchAggregateStats(0, 0, 0)

    primary_pairs = set(
        session.execute(
            select(MentionAttribution.mention_id, MentionAttribution.product_id)
            .where(
                MentionAttribution.attribution_type == AttributionType.PRIMARY,
                MentionAttribution.product_id.in_(product_id_set),
            )
            .distinct()
        )
        .tuples()
        .all()
    )

    # Wipe prior aggregates for these (run_id, product_id) pairs. Doing this
    # unconditionally up front means an aspect that drops to zero on rerun
    # has its stale row removed without a separate sweep.
    session.execute(
        delete(AggregateAspectSku).where(
            AggregateAspectSku.run_id == run_id,
            AggregateAspectSku.product_id.in_(product_id_set),
        )
    )

    if not primary_pairs:
        session.flush()
        return BatchAggregateStats(0, 0, 0)

    tags = (
        session.execute(
            select(AspectTag).where(
                AspectTag.product_id.in_(product_id_set),
                AspectTag.taxonomy_version == taxonomy_version,
                AspectTag.prompt_version == prompt_version,
            )
        )
        .scalars()
        .all()
    )
    in_scope_tags = [t for t in tags if (t.mention_id, t.product_id) in primary_pairs]

    if not in_scope_tags:
        session.flush()
        return BatchAggregateStats(0, 0, 0)

    needed_mention_ids = {t.mention_id for t in in_scope_tags}
    mentions: dict[str, Mention] = {
        m.mention_id: m
        for m in session.execute(
            select(Mention).where(Mention.mention_id.in_(needed_mention_ids))
        )
        .scalars()
        .all()
    }

    groups: dict[tuple[str, Aspect], list[AspectTag]] = defaultdict(list)
    for tag in in_scope_tags:
        groups[(tag.product_id, tag.aspect)].append(tag)

    aggregates_inserted = 0
    mentions_contributing = 0

    for product_id, aspect in sorted(groups.keys(), key=lambda k: (k[0], k[1].value)):
        group_tags = groups[(product_id, aspect)]
        seen_mention_ids: set[str] = {t.mention_id for t in group_tags}

        polarity_counts = _zero_polarity()
        intensity_counts = _zero_intensity()
        by_source: dict[str, dict[str, Any]] = {}
        by_recency = _zero_recency()
        verified_count = 0

        for tag in group_tags:
            polarity_counts[tag.polarity.value] += 1
            intensity_counts[tag.intensity.value] += 1

            mention = mentions.get(tag.mention_id)
            if mention is None:
                log.warning(
                    "aggregate_a1: tag references missing mention_id=%s; skipping",
                    tag.mention_id,
                )
                continue

            source_key = mention.source_type.value
            entry = by_source.setdefault(
                source_key,
                {"total": 0, "polarity_counts": _zero_polarity()},
            )
            entry["total"] += 1
            entry["polarity_counts"][tag.polarity.value] += 1

            by_recency[_recency_bucket(mention.published_at, now)] += 1

            if mention.metadata_.get("verified_purchase") is True:
                verified_count += 1

        total_mentions = len(seen_mention_ids)
        net_sentiment = (
            polarity_counts["positive"] - polarity_counts["negative"]
        ) / total_mentions
        verified_share = verified_count / total_mentions

        session.add(
            AggregateAspectSku(
                run_id=run_id,
                product_id=product_id,
                aspect=aspect,
                total_mentions=total_mentions,
                polarity_counts=polarity_counts,
                net_sentiment=net_sentiment,
                intensity_counts=intensity_counts,
                verified_share=verified_share,
                by_source=by_source,
                by_recency=by_recency,
                mention_ids=sorted(seen_mention_ids),
            )
        )
        aggregates_inserted += 1
        mentions_contributing += total_mentions

    session.flush()
    return BatchAggregateStats(
        groups_seen=len(groups),
        aggregates_upserted=aggregates_inserted,
        mentions_contributing=mentions_contributing,
    )
