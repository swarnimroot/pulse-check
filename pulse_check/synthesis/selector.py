"""Verbatim selector — deterministic; picks mention IDs only, never invents text.

For one (product, aspect): per (polarity, bucket), picks up to 3 mention IDs
from the supplied pool, ranked by `aspect_tags.intensity` (HIGH > MEDIUM >
LOW) with cluster-dedup. Returns IDs only with their polarity/intensity/bucket
metadata for downstream routing — the brief writer fetches `raw_text` and
quotes it. This separation is the core of the no-fabrication contract
(ARCHITECTURE §6.3, evidence-first principle in CLAUDE.md).

Operator-locked, session 11 (bite 10.3): deterministic over Sonnet selector.
The selector picks; Sonnet (in `brief_writer`) writes the claim text that
summarizes the selected verbatims.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.storage.enums import Aspect, AttributionType, Intensity, Polarity
from pulse_check.storage.models import AspectTag

SELECTOR_PER_BUCKET_CAP = 3

_INTENSITY_RANK: dict[Intensity, int] = {
    Intensity.HIGH: 3,
    Intensity.MEDIUM: 2,
    Intensity.LOW: 1,
}


@dataclass(frozen=True)
class SelectedVerbatim:
    """One mention selected for citation, with the metadata needed for routing
    to a brief quadrant. The verbatim TEXT is fetched downstream from
    `mentions.raw_text` — never carried here."""

    mention_id: str
    polarity: Polarity
    bucket: AttributionType
    intensity: Intensity


@dataclass(frozen=True)
class AspectSelection:
    """Per-aspect partition of selected mentions across the four quadrants of
    the §6.3 A1 brief layout. Empty tuples indicate the corresponding
    quadrant has no qualifying mentions for this aspect."""

    aspect: Aspect
    primary_positive: tuple[SelectedVerbatim, ...]
    primary_negative: tuple[SelectedVerbatim, ...]
    secondary_positive: tuple[SelectedVerbatim, ...]
    secondary_negative: tuple[SelectedVerbatim, ...]


def select_a1_verbatims(
    session: Session,
    *,
    product_id: str,
    aspect: Aspect,
    primary_mention_pool: list[str],
    secondary_mention_pool: list[str],
    clusters: Mapping[str, str] | None = None,
) -> AspectSelection:
    """Return up to 3 mentions per (polarity, bucket) for one (product, aspect).

    `primary_mention_pool` and `secondary_mention_pool` are the per-aspect
    PRIMARY / SECONDARY mention_id lists from the caller (typically the
    `aggregates_aspect_sku` row's `mention_ids` and `mention_ids_secondary`
    columns). They MUST be disjoint (PRIMARY precedence per §7.1).

    `clusters` is the `{mention_id: cluster_id}` map from
    `dedup.cluster_near_duplicates`. If `None` or a mention is missing from
    the map, that mention is treated as its own singleton cluster.

    Per (polarity, bucket):
      1. fetch `aspect_tags` rows matching (product_id, aspect, mention_id ∈ pool);
      2. filter to the target polarity (POSITIVE or NEGATIVE — neutral and
         mixed are never cited as evidence);
      3. sort by intensity rank desc (HIGH > MEDIUM > LOW), then mention_id
         asc as a stable tiebreak;
      4. dedup by cluster_id — keep the first mention per cluster (highest
         intensity / lowest mention_id wins);
      5. cap at `SELECTOR_PER_BUCKET_CAP`.

    No LLM call. Pure function of DB state + clusters.
    """
    all_pool = sorted(set(primary_mention_pool) | set(secondary_mention_pool))
    if not all_pool:
        return AspectSelection(
            aspect=aspect,
            primary_positive=(),
            primary_negative=(),
            secondary_positive=(),
            secondary_negative=(),
        )

    rows = session.execute(
        select(
            AspectTag.mention_id,
            AspectTag.polarity,
            AspectTag.intensity,
        ).where(
            AspectTag.product_id == product_id,
            AspectTag.aspect == aspect,
            AspectTag.mention_id.in_(all_pool),
        )
    ).all()

    # If multiple aspect_tag rows exist for one mention (multiple
    # taxonomy/prompt combos), keep the highest-intensity row — pragmatic
    # and stable. Single-row case is the norm under one taxonomy/prompt.
    per_mention: dict[str, tuple[Polarity, Intensity]] = {}
    for mid, polarity, intensity in rows:
        existing = per_mention.get(mid)
        if existing is None or _INTENSITY_RANK[intensity] > _INTENSITY_RANK[existing[1]]:
            per_mention[mid] = (polarity, intensity)

    primary_set = set(primary_mention_pool)
    secondary_set = set(secondary_mention_pool)
    cluster_map = clusters or {}

    def _pick(
        target_polarity: Polarity,
        bucket_pool: set[str],
        bucket: AttributionType,
    ) -> tuple[SelectedVerbatim, ...]:
        candidates = [
            SelectedVerbatim(mention_id=mid, polarity=pol, bucket=bucket, intensity=intensity)
            for mid, (pol, intensity) in per_mention.items()
            if mid in bucket_pool and pol == target_polarity
        ]
        candidates.sort(key=lambda v: (-_INTENSITY_RANK[v.intensity], v.mention_id))
        seen_clusters: set[str] = set()
        picked: list[SelectedVerbatim] = []
        for v in candidates:
            cluster_id = cluster_map.get(v.mention_id, f"_singleton_{v.mention_id}")
            if cluster_id in seen_clusters:
                continue
            seen_clusters.add(cluster_id)
            picked.append(v)
            if len(picked) >= SELECTOR_PER_BUCKET_CAP:
                break
        return tuple(picked)

    return AspectSelection(
        aspect=aspect,
        primary_positive=_pick(Polarity.POSITIVE, primary_set, AttributionType.PRIMARY),
        primary_negative=_pick(Polarity.NEGATIVE, primary_set, AttributionType.PRIMARY),
        secondary_positive=_pick(Polarity.POSITIVE, secondary_set, AttributionType.SECONDARY),
        secondary_negative=_pick(Polarity.NEGATIVE, secondary_set, AttributionType.SECONDARY),
    )
