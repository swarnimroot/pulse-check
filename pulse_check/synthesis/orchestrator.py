"""Top-level A1 synthesis orchestrator: dedup → selector → writer → validator.

Sequences the synthesis stages, persists the resulting Brief row, and returns
it. Single entry point for downstream callers (`scripts/synthesize.py`, the
FastAPI brief handler in Wave 2 backend).

Retry policy (operator-locked, session 12): if the citation validator reports
fabricated mention IDs, the brief writer is re-called once with
prompt_version `a1_brief_v1_strict`. Other validator warnings (out-of-context,
numerical drift, empty claims) soft-warn straight through — they're persisted
under `narrative["flagged_citation_issues"]` on the Brief row.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.storage.enums import Aspect, ScopeType
from pulse_check.storage.models import (
    AggregateAspectSku,
    Brief,
    Mention,
    Product,
)
from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.synthesis.brief_writer import (
    BRIEF_MODEL,
    BRIEF_PROMPT_VERSION,
    BRIEF_PROMPT_VERSION_STRICT,
    write_a1_brief,
)
from pulse_check.synthesis.citation_validator import (
    validate_citations,
    validate_pair_citations,
)
from pulse_check.synthesis.dedup import cluster_near_duplicates
from pulse_check.synthesis.pair_brief_writer import (
    PAIR_BRIEF_MODEL,
    PAIR_BRIEF_PROMPT_VERSION,
    PAIR_BRIEF_PROMPT_VERSION_STRICT,
    write_pair_brief,
)
from pulse_check.synthesis.selector import AspectSelection, select_a1_verbatims

log = logging.getLogger(__name__)

DEDUP_PROMPT_VERSION = "a1_dedup_v1"


def synthesize_a1(
    session: Session,
    *,
    client: AnthropicClient,
    run_id: str,
    product_id: str,
) -> Brief:
    """Run the full A1 pipeline for one product within a run.

    Stages:
        1. Load product + aggregates.
        2. Build allowed_pool = PRIMARY ∪ SECONDARY mention IDs across aspects.
        3. Haiku dedup the PRIMARY pool into clusters.
        4. Per aspect: deterministic selector picks ≤3 mentions per
           (polarity, bucket) → AspectSelection.
        5. Sonnet brief writer assembles the §6.3 four-quadrant BriefNarrative.
        6. Citation validator soft-warns; on fabricated_ids, retry brief writer
           once with prompt_version `a1_brief_v1_strict` and re-validate.
        7. Persist Brief row (scope_type=ASPECT_1_SKU); narrative dict carries
           `flagged_citation_issues` from the final ValidationResult.
    """
    product = session.get(Product, product_id)
    if product is None:
        msg = f"product not found: {product_id}"
        raise ValueError(msg)

    aggregate_rows = list(
        session.execute(
            select(AggregateAspectSku).where(
                AggregateAspectSku.product_id == product_id,
                AggregateAspectSku.run_id == run_id,
            )
        ).scalars()
    )
    if not aggregate_rows:
        msg = (
            f"no aggregates_aspect_sku rows for product={product_id} "
            f"run={run_id}"
        )
        raise ValueError(msg)
    aggregates_by_aspect: dict[Aspect, AggregateAspectSku] = {
        agg.aspect: agg for agg in aggregate_rows
    }

    primary_ids: set[str] = set()
    secondary_ids: set[str] = set()
    for agg in aggregate_rows:
        primary_ids.update(agg.mention_ids or [])
        secondary_ids.update(agg.mention_ids_secondary or [])
    allowed_pool = primary_ids | secondary_ids

    if primary_ids:
        primary_mentions = list(
            session.execute(
                select(Mention).where(Mention.mention_id.in_(primary_ids))
            ).scalars()
        )
        clusters = cluster_near_duplicates(
            session,
            primary_mentions,
            client=client,
            prompt_version=DEDUP_PROMPT_VERSION,
        )
    else:
        clusters = {}

    selections: dict[Aspect, AspectSelection] = {}
    for aspect, agg in aggregates_by_aspect.items():
        selections[aspect] = select_a1_verbatims(
            session,
            product_id=product_id,
            aspect=aspect,
            primary_mention_pool=list(agg.mention_ids or []),
            secondary_mention_pool=list(agg.mention_ids_secondary or []),
            clusters=clusters,
        )

    used_prompt_version = BRIEF_PROMPT_VERSION
    narrative = write_a1_brief(
        session,
        client=client,
        product=product,
        aggregates=aggregates_by_aspect,
        selections=selections,
        prompt_version=BRIEF_PROMPT_VERSION,
    )
    result = validate_citations(
        session,
        narrative=narrative,
        aggregates=aggregates_by_aspect,
        allowed_pool=allowed_pool,
    )

    if result.fabricated_ids:
        log.warning(
            "brief writer produced fabricated mention IDs %s -- retrying with %s",
            sorted(result.fabricated_ids),
            BRIEF_PROMPT_VERSION_STRICT,
        )
        used_prompt_version = BRIEF_PROMPT_VERSION_STRICT
        narrative = write_a1_brief(
            session,
            client=client,
            product=product,
            aggregates=aggregates_by_aspect,
            selections=selections,
            prompt_version=BRIEF_PROMPT_VERSION_STRICT,
        )
        result = validate_citations(
            session,
            narrative=narrative,
            aggregates=aggregates_by_aspect,
            allowed_pool=allowed_pool,
        )

    narrative_dict: dict[str, Any] = narrative.model_dump()
    narrative_dict["flagged_citation_issues"] = result.model_dump()

    brief = Brief(
        run_id=run_id,
        scope_type=ScopeType.ASPECT_1_SKU,
        scope_id=product_id,
        narrative=narrative_dict,
        prompt_version=used_prompt_version,
        model=BRIEF_MODEL,
    )
    session.add(brief)
    session.flush()

    return brief


def synthesize_pair(
    session: Session,
    *,
    client: AnthropicClient,
    run_id: str,
    pair_id: str,
    primary_product_id: str,
    comparator_product_id: str,
) -> Brief:
    """Run the pair-brief pipeline for one product pair within a run.

    Stages (mirror `synthesize_a1` shape; A2-deliberation tables are NOT
    touched — pair brief lazy-joins two A1 aggregate rows per ARCHITECTURE
    §6.4):
        1. Load both products + their `aggregates_aspect_sku` rows for `run_id`.
        2. Per side: build PRIMARY ∪ SECONDARY allowed_pool across aspects;
           Haiku-cluster the PRIMARY pool; run `select_a1_verbatims` per aspect.
        3. Sonnet pair writer assembles the §6.4 single-paragraph
           PairBriefNarrative against both sides' aggregates + selections.
        4. Citation validator soft-warns; on fabricated_ids, retry once with
           prompt_version `pair_brief_v1_strict` and re-validate.
        5. Persist Brief row (scope_type=ASPECT_2_PAIR, scope_id=pair_id);
           narrative dict carries `flagged_citation_issues` from the final
           ValidationResult.

    `pair_id` is the operator-supplied identifier (e.g.
    `"alienware_16_aurora_vs_rog_strix_g16"`) — typically `<primary>_vs_<comp>`
    matching `configs/pair_plan_*.yaml`. The scope_id is opaque to the schema;
    convention is enforced by the pair-plan YAML.
    """
    primary = session.get(Product, primary_product_id)
    if primary is None:
        msg = f"product not found: {primary_product_id}"
        raise ValueError(msg)
    comparator = session.get(Product, comparator_product_id)
    if comparator is None:
        msg = f"product not found: {comparator_product_id}"
        raise ValueError(msg)

    def _load_side(product_id: str) -> tuple[
        dict[Aspect, AggregateAspectSku],
        dict[Aspect, AspectSelection],
        set[str],
    ]:
        rows = list(
            session.execute(
                select(AggregateAspectSku).where(
                    AggregateAspectSku.product_id == product_id,
                    AggregateAspectSku.run_id == run_id,
                )
            ).scalars()
        )
        aggs: dict[Aspect, AggregateAspectSku] = {agg.aspect: agg for agg in rows}
        primary_ids: set[str] = set()
        secondary_ids: set[str] = set()
        for agg in rows:
            primary_ids.update(agg.mention_ids or [])
            secondary_ids.update(agg.mention_ids_secondary or [])
        if primary_ids:
            primary_mentions = list(
                session.execute(
                    select(Mention).where(Mention.mention_id.in_(primary_ids))
                ).scalars()
            )
            clusters = cluster_near_duplicates(
                session,
                primary_mentions,
                client=client,
                prompt_version=DEDUP_PROMPT_VERSION,
            )
        else:
            clusters = {}
        sels: dict[Aspect, AspectSelection] = {}
        for aspect, agg in aggs.items():
            sels[aspect] = select_a1_verbatims(
                session,
                product_id=product_id,
                aspect=aspect,
                primary_mention_pool=list(agg.mention_ids or []),
                secondary_mention_pool=list(agg.mention_ids_secondary or []),
                clusters=clusters,
            )
        return aggs, sels, primary_ids | secondary_ids

    primary_aggs, primary_selections, primary_pool = _load_side(primary_product_id)
    comparator_aggs, comparator_selections, comparator_pool = _load_side(
        comparator_product_id
    )
    if not primary_aggs and not comparator_aggs:
        msg = (
            f"no aggregates_aspect_sku rows on either side for pair={pair_id} "
            f"run={run_id}"
        )
        raise ValueError(msg)
    allowed_pool = primary_pool | comparator_pool

    used_prompt_version = PAIR_BRIEF_PROMPT_VERSION
    narrative = write_pair_brief(
        session,
        client=client,
        primary=primary,
        comparator=comparator,
        primary_aggregates=primary_aggs,
        comparator_aggregates=comparator_aggs,
        primary_selections=primary_selections,
        comparator_selections=comparator_selections,
        prompt_version=PAIR_BRIEF_PROMPT_VERSION,
    )
    result = validate_pair_citations(
        session,
        narrative=narrative,
        allowed_pool=allowed_pool,
    )

    if result.fabricated_ids:
        log.warning(
            "pair brief writer produced fabricated mention IDs %s -- retrying with %s",
            sorted(result.fabricated_ids),
            PAIR_BRIEF_PROMPT_VERSION_STRICT,
        )
        used_prompt_version = PAIR_BRIEF_PROMPT_VERSION_STRICT
        narrative = write_pair_brief(
            session,
            client=client,
            primary=primary,
            comparator=comparator,
            primary_aggregates=primary_aggs,
            comparator_aggregates=comparator_aggs,
            primary_selections=primary_selections,
            comparator_selections=comparator_selections,
            prompt_version=PAIR_BRIEF_PROMPT_VERSION_STRICT,
        )
        result = validate_pair_citations(
            session,
            narrative=narrative,
            allowed_pool=allowed_pool,
        )

    narrative_dict: dict[str, Any] = narrative.model_dump()
    narrative_dict["flagged_citation_issues"] = result.model_dump()

    brief = Brief(
        run_id=run_id,
        scope_type=ScopeType.ASPECT_2_PAIR,
        scope_id=pair_id,
        narrative=narrative_dict,
        prompt_version=used_prompt_version,
        model=PAIR_BRIEF_MODEL,
    )
    session.add(brief)
    session.flush()

    return brief
