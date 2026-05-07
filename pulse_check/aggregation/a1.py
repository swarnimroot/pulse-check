"""A1 aggregator: roll aspect_tags into aggregates_aspect_sku rows.

Per (product_id, aspect) group, two parallel buckets are computed:

**PRIMARY bucket** — contributions from PRIMARY ``MentionAttribution`` rows.
Drives the legacy column set (``total_mentions``, ``polarity_counts``,
``net_sentiment``, ``intensity_counts``, ``verified_share``, ``by_source``,
``by_recency``, ``mention_ids``).

**SECONDARY bucket** — contributions from SECONDARY-only attributions
(a ``(mention, product)`` pair with PRIMARY attribution lands in the
PRIMARY bucket; the SECONDARY bucket excludes it to avoid double-count).
Mirrors the same eight fields under ``*_secondary`` columns. Surfaces
comment-inheritance density that A1's PRIMARY-only filter previously made
invisible at the aggregate layer (see ARCHITECTURE §3.3 / §5 / §7.1).

Per-bucket arithmetic:
- ``total_mentions`` — count of distinct contributing mention_ids.
- ``polarity_counts`` / ``intensity_counts`` — zero-filled distributions
  over tags. The unique key on ``aspect_tags`` guarantees one tag per
  (mention, product, aspect, taxonomy_version, prompt_version), so per-tag
  here means per-mention.
- ``net_sentiment`` — ``(positive - negative) / total_mentions`` in
  [-1.0, 1.0]. Flat per-mention formula; no weighting by intensity,
  recency, source, or anything else (CLAUDE.md "every mention = 1.0").
  ``0.0`` when ``total_mentions == 0`` (empty bucket).
- ``verified_share`` — fraction of contributing mentions whose
  ``metadata_["verified_purchase"]`` is True; missing key reads as False.
  ``0.0`` when bucket is empty.
- ``by_source`` — ``{source_value: {"total": int, "polarity_counts": ...}}``.
- ``by_recency`` — count per bucket (``0_30``, ``30_90``, ``90_180``,
  ``180_plus``, ``unknown``) on ``mention.published_at`` vs. ``now``.
- ``mention_ids`` — sorted, deduped contributing IDs (provenance per the
  evidence-first principle).

A row is written whenever EITHER bucket has at least one contribution; the
empty side carries zero/empty fields. Caller owns the transaction
(``flush`` only). Idempotent rerun via delete-then-insert keyed on
``(run_id, product_id)``: an aspect that drops to zero on both sides
correctly removes its prior row.
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

    ``mentions_contributing`` sums distinct mentions across PRIMARY groups;
    a mention tagged on N aspects contributes N times. Legacy semantics —
    PRIMARY-bucket-only — preserved for back-compat. ``mentions_contributing_secondary``
    is the same count for the SECONDARY bucket.
    """

    groups_seen: int
    aggregates_upserted: int
    mentions_contributing: int
    mentions_contributing_secondary: int = 0


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


@dataclass(frozen=True)
class _BucketResult:
    total_mentions: int
    polarity_counts: dict[str, int]
    net_sentiment: float
    intensity_counts: dict[str, int]
    verified_share: float
    by_source: dict[str, Any]
    by_recency: dict[str, int]
    mention_ids: list[str]


def _empty_bucket() -> _BucketResult:
    return _BucketResult(
        total_mentions=0,
        polarity_counts=_zero_polarity(),
        net_sentiment=0.0,
        intensity_counts=_zero_intensity(),
        verified_share=0.0,
        by_source={},
        by_recency=_zero_recency(),
        mention_ids=[],
    )


def _compute_bucket(
    tags: list[AspectTag],
    mentions: dict[str, Mention],
    now: datetime,
) -> _BucketResult:
    """Compute the eight per-bucket fields from a list of aspect tags.

    Mentions missing from ``mentions`` are skipped with a warning (their
    polarity/intensity still contribute to the count distributions, but
    their source/recency/verified attributes do not). This matches the
    pre-Option-3 behavior.
    """
    if not tags:
        return _empty_bucket()

    seen_mention_ids: set[str] = {t.mention_id for t in tags}
    polarity_counts = _zero_polarity()
    intensity_counts = _zero_intensity()
    by_source: dict[str, dict[str, Any]] = {}
    by_recency = _zero_recency()
    verified_count = 0

    for tag in tags:
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

    return _BucketResult(
        total_mentions=total_mentions,
        polarity_counts=polarity_counts,
        net_sentiment=net_sentiment,
        intensity_counts=intensity_counts,
        verified_share=verified_share,
        by_source=by_source,
        by_recency=by_recency,
        mention_ids=sorted(seen_mention_ids),
    )


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
        Products in scope. Out-of-scope products are skipped entirely
        (both buckets).
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
        return BatchAggregateStats(0, 0, 0, 0)

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
    secondary_pairs_all = set(
        session.execute(
            select(MentionAttribution.mention_id, MentionAttribution.product_id)
            .where(
                MentionAttribution.attribution_type == AttributionType.SECONDARY,
                MentionAttribution.product_id.in_(product_id_set),
            )
            .distinct()
        )
        .tuples()
        .all()
    )
    # PRIMARY takes precedence: a (mention, product) with both attributions
    # contributes to PRIMARY only. Preserves "every mention = 1.0".
    secondary_pairs = secondary_pairs_all - primary_pairs

    # Wipe prior aggregates for these (run_id, product_id) pairs. Doing this
    # unconditionally up front means an aspect that drops to zero on both
    # sides has its stale row removed without a separate sweep.
    session.execute(
        delete(AggregateAspectSku).where(
            AggregateAspectSku.run_id == run_id,
            AggregateAspectSku.product_id.in_(product_id_set),
        )
    )

    if not primary_pairs and not secondary_pairs:
        session.flush()
        return BatchAggregateStats(0, 0, 0, 0)

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
    primary_tags = [t for t in tags if (t.mention_id, t.product_id) in primary_pairs]
    secondary_tags = [t for t in tags if (t.mention_id, t.product_id) in secondary_pairs]

    if not primary_tags and not secondary_tags:
        session.flush()
        return BatchAggregateStats(0, 0, 0, 0)

    needed_mention_ids = {t.mention_id for t in primary_tags} | {
        t.mention_id for t in secondary_tags
    }
    mentions: dict[str, Mention] = {
        m.mention_id: m
        for m in session.execute(
            select(Mention).where(Mention.mention_id.in_(needed_mention_ids))
        )
        .scalars()
        .all()
    }

    primary_groups: dict[tuple[str, Aspect], list[AspectTag]] = defaultdict(list)
    for tag in primary_tags:
        primary_groups[(tag.product_id, tag.aspect)].append(tag)
    secondary_groups: dict[tuple[str, Aspect], list[AspectTag]] = defaultdict(list)
    for tag in secondary_tags:
        secondary_groups[(tag.product_id, tag.aspect)].append(tag)

    all_keys = set(primary_groups.keys()) | set(secondary_groups.keys())

    aggregates_inserted = 0
    mentions_contributing = 0
    mentions_contributing_secondary = 0

    for product_id, aspect in sorted(all_keys, key=lambda k: (k[0], k[1].value)):
        p = _compute_bucket(primary_groups.get((product_id, aspect), []), mentions, now)
        s = _compute_bucket(secondary_groups.get((product_id, aspect), []), mentions, now)

        session.add(
            AggregateAspectSku(
                run_id=run_id,
                product_id=product_id,
                aspect=aspect,
                total_mentions=p.total_mentions,
                polarity_counts=p.polarity_counts,
                net_sentiment=p.net_sentiment,
                intensity_counts=p.intensity_counts,
                verified_share=p.verified_share,
                by_source=p.by_source,
                by_recency=p.by_recency,
                mention_ids=p.mention_ids,
                total_mentions_secondary=s.total_mentions,
                polarity_counts_secondary=s.polarity_counts,
                net_sentiment_secondary=s.net_sentiment,
                intensity_counts_secondary=s.intensity_counts,
                verified_share_secondary=s.verified_share,
                by_source_secondary=s.by_source,
                by_recency_secondary=s.by_recency,
                mention_ids_secondary=s.mention_ids,
            )
        )
        aggregates_inserted += 1
        mentions_contributing += p.total_mentions
        mentions_contributing_secondary += s.total_mentions

    session.flush()
    return BatchAggregateStats(
        groups_seen=len(all_keys),
        aggregates_upserted=aggregates_inserted,
        mentions_contributing=mentions_contributing,
        mentions_contributing_secondary=mentions_contributing_secondary,
    )
