"""Post-fetch secondary attribution sweep.

Primary attribution happens at fetch time (ARCHITECTURE §5); this pass runs
afterwards over every stored mention's `raw_text` against each product's
combined primary+secondary patterns. Matches that don't already have a
PRIMARY attribution for the same (mention, product) pair are recorded as
SECONDARY.

This pass is idempotent: running it twice produces no new rows on the second
invocation. Pattern refinements in `configs/product_set_*.yaml` propagate
without re-scraping by re-running this pass alone.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from scrapers_lib import Anchor
from scrapers_lib.core.attribution import attribute_regex_all
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.config.models import ProductSet
from pulse_check.scraping.anchors import to_anchor_with_secondary
from pulse_check.storage.enums import AttributionMethod, AttributionType
from pulse_check.storage.models import Mention, MentionAttribution

log = logging.getLogger(__name__)


@dataclass
class SecondaryAttributionStats:
    mentions_scanned: int = 0
    new_attributions: int = 0
    already_primary: int = 0
    already_secondary: int = 0


def apply_secondary_attribution(
    session: Session, product_set: ProductSet
) -> SecondaryAttributionStats:
    """Scan every mention; record SECONDARY attributions against products whose
    combined primary+secondary patterns match."""
    anchors: list[Anchor] = []
    for product in product_set.products:
        anchor = to_anchor_with_secondary(product)
        if anchor is None:
            log.info(
                "product %s has no attribution patterns; skipping in secondary pass",
                product.product_id,
            )
            continue
        anchors.append(anchor)

    if not anchors:
        log.info("secondary attribution pass: no buildable anchors; skipping")
        return SecondaryAttributionStats()

    stats = SecondaryAttributionStats()

    # Cache existing attribution keys to avoid N queries per mention.
    existing = session.execute(
        select(
            MentionAttribution.mention_id,
            MentionAttribution.product_id,
            MentionAttribution.attribution_type,
        )
    ).all()
    existing_set: set[tuple[str, str, AttributionType]] = {
        (mid, pid, atype) for (mid, pid, atype) in existing
    }

    for mention in session.scalars(select(Mention)):
        stats.mentions_scanned += 1
        matches = attribute_regex_all(mention.raw_text, anchors)
        for match in matches:
            key_primary = (
                mention.mention_id,
                match.anchor_id,
                AttributionType.PRIMARY,
            )
            if key_primary in existing_set:
                stats.already_primary += 1
                continue

            key_secondary = (
                mention.mention_id,
                match.anchor_id,
                AttributionType.SECONDARY,
            )
            if key_secondary in existing_set:
                stats.already_secondary += 1
                continue

            session.add(
                MentionAttribution(
                    mention_id=mention.mention_id,
                    product_id=match.anchor_id,
                    attribution_type=AttributionType.SECONDARY,
                    attribution_method=AttributionMethod.REGEX,
                )
            )
            existing_set.add(key_secondary)
            stats.new_attributions += 1

    session.flush()
    return stats
