"""Bite 30.f Stage A — end-to-end pilot demo on 3 anchor products.

One-off driver that exercises the full A1 path (tag → aggregate → brief)
on a 3-product subset to validate the pipeline before committing to the
full 59-product corpus run.

Steps (idempotent at each stage):
1. Upsert Run row for ``run_wave5_v1`` (PK; OK to re-run).
2. Aspect-tag every (mention, product) attribution for the 3 products,
   filtered by ``content_type != deal``. Uses Haiku per ARCH §6.5 with
   ``commit_every=50`` so a mid-batch crash preserves paid calls.
3. Aggregate A1 rollups for the 3 products into ``run_wave5_v1``.
4. Synthesize one A1 brief per product via Sonnet.

Anchor products (manufacturer / premium competitor / mid-tier alternative):
- ``alienware_16_aurora``
- ``rog_strix_scar_16``
- ``hp_omen_max_16``

Per the session-31 cost estimate the budget is ~$1.65–2.15 (tagging
~$1.50–2.00 fresh + 3 Sonnet briefs ~$0.15).
"""

from __future__ import annotations

import argparse
import logging
import sys

from pulse_check.aggregation.a1 import aggregate_a1
from pulse_check.logging_config import configure_logging
from pulse_check.settings import get_settings
from pulse_check.storage.enums import ContentType
from pulse_check.storage.models import Run
from pulse_check.storage.session import session_scope
from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.synthesis.orchestrator import synthesize_a1
from pulse_check.tagging import AspectClassifier, ProductContext
from pulse_check.tagging.aspect_classifier import PROMPT_VERSION, TAXONOMY_VERSION
from pulse_check.tagging.batch import tag_corpus_aspects

log = logging.getLogger("pulse_check.scripts.run_stage_a")

RUN_ID = "run_wave5_v1"
ANCHOR_PRODUCTS = [
    ("alienware_16_aurora", "Alienware 16 Aurora"),
    ("rog_strix_scar_16", "ROG Strix Scar 16"),
    ("hp_omen_max_16", "HP Omen Max 16"),
]


def _ensure_run_row(session) -> None:  # type: ignore[no-untyped-def]
    existing = session.get(Run, RUN_ID)
    if existing is not None:
        log.info("Run row already exists: %s", RUN_ID)
        return
    session.add(
        Run(
            run_id=RUN_ID,
            config_snapshot={
                "bite": "30.f stage_a",
                "anchor_products": [pid for pid, _ in ANCHOR_PRODUCTS],
            },
            taxonomy_version=TAXONOMY_VERSION,
            prompt_versions={"aspect_classifier": PROMPT_VERSION},
        )
    )
    session.commit()
    log.info("inserted Run row: %s", RUN_ID)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run-stage-a")
    parser.add_argument(
        "--skip-tagging",
        action="store_true",
        help="Skip the aspect-tagging step (assume already done).",
    )
    parser.add_argument(
        "--skip-aggregation",
        action="store_true",
        help="Skip the aggregation step (assume already done).",
    )
    parser.add_argument(
        "--skip-briefs",
        action="store_true",
        help="Skip the brief-synthesis step.",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    configure_logging()
    settings = get_settings()
    if not settings.anthropic_api_key:
        log.error("ANTHROPIC_API_KEY not set")
        return 2

    product_contexts = [
        ProductContext(product_id=pid, display_name=name)
        for pid, name in ANCHOR_PRODUCTS
    ]

    client = AnthropicClient(api_key=settings.anthropic_api_key, timeout=300.0)
    haiku_model = settings.anthropic_haiku_model

    # --- Step 1: Run row -----------------------------------------------------
    with session_scope() as session:
        _ensure_run_row(session)

    # --- Step 2: Aspect tagging ---------------------------------------------
    if not args.skip_tagging:
        log.info(
            "Stage A tagging: products=%d model=%s exclude=deal commit_every=50",
            len(product_contexts),
            haiku_model,
        )
        classifier = AspectClassifier(client, model=haiku_model)
        with session_scope() as session:
            stats = tag_corpus_aspects(
                session,
                classifier=classifier,
                products=product_contexts,
                taxonomy_version=TAXONOMY_VERSION,
                exclude_content_types=frozenset({ContentType.DEAL}),
                commit_every=50,
            )
        log.info(
            "tagging done: seen=%d skipped=%d filtered=%d classified=%d "
            "inserted=%d",
            stats.attributions_seen,
            stats.attributions_skipped_existing,
            stats.attributions_skipped_content_filter,
            stats.attributions_classified,
            stats.aspect_tags_inserted,
        )
    else:
        log.info("Stage A tagging: SKIPPED (--skip-tagging)")

    # --- Step 3: A1 aggregation ---------------------------------------------
    if not args.skip_aggregation:
        log.info("Stage A aggregation: run_id=%s", RUN_ID)
        with session_scope() as session:
            agg_stats = aggregate_a1(
                session,
                run_id=RUN_ID,
                product_ids=[pid for pid, _ in ANCHOR_PRODUCTS],
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
        log.info("Stage A aggregation: SKIPPED (--skip-aggregation)")

    # --- Step 4: Brief synthesis -------------------------------------------
    if args.skip_briefs:
        log.info("Stage A briefs: SKIPPED (--skip-briefs)")
        return 0

    print()
    print("=" * 70)
    print("STAGE A BRIEFS")
    print("=" * 70)
    for pid, name in ANCHOR_PRODUCTS:
        log.info("synthesizing brief: product=%s", pid)
        with session_scope() as session:
            try:
                brief = synthesize_a1(
                    session,
                    client=client,
                    run_id=RUN_ID,
                    product_id=pid,
                )
            except ValueError as exc:
                log.error("synthesize failed for %s: %s", pid, exc)
                continue
            narrative = dict(brief.narrative)

        sections = narrative.get("sections", []) or []
        flags = narrative.get("flagged_citation_issues", {}) or {}
        print()
        print(f"--- {name} ({pid}) ---")
        print(f"Title: {narrative.get('brief_title', '?')}")
        print(f"Validation: is_valid={flags.get('is_valid')} "
              f"fabricated={len(flags.get('fabricated_ids') or [])} "
              f"out_of_context={len(flags.get('out_of_context_ids') or [])} "
              f"drift={len(flags.get('numerical_drift') or [])} "
              f"empty={len(flags.get('empty_claims') or [])}")
        for i, section in enumerate(sections, 1):
            heading = section.get("heading", "?")
            claims = section.get("claims") or []
            print(f"  §{i}. {heading} ({len(claims)} claim{'s' if len(claims) != 1 else ''})")
            for claim in claims:
                claim_text = claim.get("claim_text", "")
                cited = claim.get("cited_mention_ids") or []
                print(f"     - {claim_text}")
                print(f"       cites: {cited}")
        print()

    print("=" * 70)
    print("Stage A complete")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
