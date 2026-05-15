"""Bite 30.f.b Stage B — full A1 corpus pilot (59-product run).

Extension of run_stage_a.py to the full product set under the same
``run_wave5_v1`` run_id. Stage A validated the pipeline on 3 anchor
products; Stage B completes the pilot artifact.

Idempotency:
- Aspect tagging (``tag_corpus_aspects``) skips ``(mention, product)``
  pairs already tagged at the same ``taxonomy_version`` + ``prompt_version``,
  so the 3 Stage A anchors (and any other pre-existing rows) skip the LLM.
- Aggregation upserts on ``(run_id, product_id, aspect)``.
- Brief synthesis (``synthesize_a1``) is NOT idempotent — it appends a
  new ``briefs`` row each time. The 3 Stage A anchors are skipped by
  default; ``--include-stage-a-briefs`` overrides.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pulse_check.aggregation.a1 import aggregate_a1
from pulse_check.config.loader import load_product_set
from pulse_check.logging_config import configure_logging
from pulse_check.settings import get_settings
from pulse_check.storage.enums import ContentType
from pulse_check.storage.session import session_scope
from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.synthesis.orchestrator import synthesize_a1
from pulse_check.tagging import AspectClassifier, ProductContext
from pulse_check.tagging.aspect_classifier import PROMPT_VERSION, TAXONOMY_VERSION
from pulse_check.tagging.batch import tag_corpus_aspects

log = logging.getLogger("pulse_check.scripts.run_stage_b")

RUN_ID = "run_wave5_v1"
STAGE_A_PRODUCT_IDS = frozenset(
    {"alienware_16_aurora", "rog_strix_scar_16", "hp_omen_max_16"}
)
DEFAULT_PRODUCT_SET = Path("configs/product_set_gaming_laptops_2026.yaml")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run-stage-b")
    parser.add_argument(
        "--product-set",
        type=Path,
        default=DEFAULT_PRODUCT_SET,
        help="Path to product_set YAML.",
    )
    parser.add_argument(
        "--commit-every",
        type=int,
        default=50,
        help="Commit aspect_tags every N classifications (preserves paid calls on crash).",
    )
    parser.add_argument("--skip-tagging", action="store_true")
    parser.add_argument("--skip-aggregation", action="store_true")
    parser.add_argument("--skip-briefs", action="store_true")
    parser.add_argument(
        "--include-stage-a-briefs",
        action="store_true",
        help="Re-run Sonnet brief for the 3 Stage A anchors (default: skip; non-idempotent).",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    configure_logging()
    settings = get_settings()
    if not settings.anthropic_api_key:
        log.error("ANTHROPIC_API_KEY not set")
        return 2

    product_set = load_product_set(args.product_set)
    all_products = [
        ProductContext(product_id=p.product_id, display_name=p.display_name)
        for p in product_set.products
    ]
    log.info(
        "Stage B: %d products loaded from %s", len(all_products), args.product_set
    )

    client = AnthropicClient(api_key=settings.anthropic_api_key, timeout=300.0)
    haiku_model = settings.anthropic_haiku_model

    # --- Step 1: Aspect tagging (idempotent; cache + already_tagged guard) --
    if not args.skip_tagging:
        log.info(
            "Stage B tagging: products=%d model=%s exclude=deal commit_every=%d",
            len(all_products),
            haiku_model,
            args.commit_every,
        )
        classifier = AspectClassifier(client, model=haiku_model)
        with session_scope() as session:
            stats = tag_corpus_aspects(
                session,
                classifier=classifier,
                products=all_products,
                taxonomy_version=TAXONOMY_VERSION,
                exclude_content_types=frozenset({ContentType.DEAL}),
                commit_every=args.commit_every,
            )
        log.info(
            "tagging done: seen=%d skipped_existing=%d filtered=%d "
            "classified=%d inserted=%d",
            stats.attributions_seen,
            stats.attributions_skipped_existing,
            stats.attributions_skipped_content_filter,
            stats.attributions_classified,
            stats.aspect_tags_inserted,
        )
    else:
        log.info("Stage B tagging: SKIPPED (--skip-tagging)")

    # --- Step 2: A1 aggregation (upsert) ------------------------------------
    if not args.skip_aggregation:
        log.info(
            "Stage B aggregation: run_id=%s products=%d",
            RUN_ID,
            len(all_products),
        )
        with session_scope() as session:
            agg_stats = aggregate_a1(
                session,
                run_id=RUN_ID,
                product_ids=[p.product_id for p in all_products],
                taxonomy_version=TAXONOMY_VERSION,
                prompt_version=PROMPT_VERSION,
            )
        log.info(
            "aggregation done: groups=%d upserted=%d primary_contrib=%d "
            "secondary_contrib=%d",
            agg_stats.groups_seen,
            agg_stats.aggregates_upserted,
            agg_stats.mentions_contributing,
            agg_stats.mentions_contributing_secondary,
        )
    else:
        log.info("Stage B aggregation: SKIPPED (--skip-aggregation)")

    # --- Step 3: Brief synthesis (skip Stage A anchors by default) ----------
    if args.skip_briefs:
        log.info("Stage B briefs: SKIPPED (--skip-briefs)")
        return 0

    if args.include_stage_a_briefs:
        brief_products = list(all_products)
    else:
        brief_products = [
            p for p in all_products if p.product_id not in STAGE_A_PRODUCT_IDS
        ]
    skipped = len(all_products) - len(brief_products)
    log.info(
        "Stage B briefs: synthesizing %d products (skipping %d Stage A anchors)",
        len(brief_products),
        skipped,
    )

    succeeded = 0
    failed: list[tuple[str, str]] = []
    for i, p in enumerate(brief_products, 1):
        log.info(
            "[%d/%d] synthesizing brief: product=%s",
            i,
            len(brief_products),
            p.product_id,
        )
        with session_scope() as session:
            try:
                brief = synthesize_a1(
                    session,
                    client=client,
                    run_id=RUN_ID,
                    product_id=p.product_id,
                )
            except ValueError as exc:
                log.warning(
                    "[%d/%d] brief SKIP/FAIL: product=%s reason=%s",
                    i,
                    len(brief_products),
                    p.product_id,
                    exc,
                )
                failed.append((p.product_id, str(exc)))
                continue
            narrative = (
                dict(brief.narrative) if isinstance(brief.narrative, dict) else {}
            )
        flags = narrative.get("flagged_citation_issues") or {}
        log.info(
            "[%d/%d] brief OK: product=%s is_valid=%s fab=%d ooc=%d drift=%d empty=%d",
            i,
            len(brief_products),
            p.product_id,
            flags.get("is_valid"),
            len(flags.get("fabricated_ids") or []),
            len(flags.get("out_of_context_ids") or []),
            len(flags.get("numerical_drift") or []),
            len(flags.get("empty_claims") or []),
        )
        succeeded += 1

    log.info(
        "Stage B complete: %d briefs succeeded, %d failed/skipped",
        succeeded,
        len(failed),
    )
    for pid, reason in failed:
        log.info("  fail: %s -> %s", pid, reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
