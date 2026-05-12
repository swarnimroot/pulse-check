"""CLI: build Sonnet-labeled deliberation + reason gold sets — bite 13.c.3.

Two-stage pipeline:

    Stage 1 — deliberation: select up to ``--candidate-cap`` reddit_post
              threads via the (b) ∪ (c) heuristic + content-type strict gate,
              Sonnet-label every candidate, then stratified-sample with B/C/D
              force-includes down to ``--target-size``.

    Stage 2 — reason: per resolved thread, Sonnet-reason-label every
              top-level comment, then select reason-gold comments
              polarity-agnostically with NEG-toward-winner force-include.

All LLM calls are cached. Re-running on the same corpus + seed is free.

Usage::

    python scripts/build_deliberation_gold_set.py \\
        --candidate-cap 100 \\
        --target-size 40 \\
        --seed 42

Outputs:
    data/gold_sets/deliberation_v1.jsonl
    data/gold_sets/reason_tagging_v1.jsonl

Operator review: ``scripts/review_gold_set.py`` (extended in bite 13.c.4).
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from pathlib import Path

from sqlalchemy import select

from pulse_check.eval.deliberation_gold_set import (
    BuildStats,
    build_gold_sets,
)
from pulse_check.eval.deliberation_labeler import DeliberationLabeler
from pulse_check.eval.reason_labeler import ReasonLabeler
from pulse_check.eval.sampler import (
    DEFAULT_CANDIDATE_CAP,
    DEFAULT_TARGET_SIZE,
)
from pulse_check.logging_config import configure_logging
from pulse_check.settings import get_settings
from pulse_check.storage.models import Product
from pulse_check.storage.session import session_scope
from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.tagging.aspect_classifier import ProductContext

log = logging.getLogger("pulse_check.scripts.build_deliberation_gold_set")

_GOLD_SET_DIR = Path("data/gold_sets")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pulse-check build-deliberation-gold-set",
        description=(
            "Sample reddit threads + Sonnet-label them into "
            "deliberation + reason JSONL gold sets."
        ),
    )
    parser.add_argument(
        "--candidate-cap",
        type=int,
        default=DEFAULT_CANDIDATE_CAP,
        help="Max reddit_post candidates before Sonnet labeling (default: %(default)s).",
    )
    parser.add_argument(
        "--target-size",
        type=int,
        default=DEFAULT_TARGET_SIZE,
        help="Target deliberation gold-set size after stratification (default: %(default)s).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for reproducibility (default: %(default)s).",
    )
    parser.add_argument(
        "--deliberation-out",
        type=Path,
        default=_GOLD_SET_DIR / "deliberation_v1.jsonl",
        help="Output path for deliberation gold-set JSONL.",
    )
    parser.add_argument(
        "--reason-out",
        type=Path,
        default=_GOLD_SET_DIR / "reason_tagging_v1.jsonl",
        help="Output path for reason gold-set JSONL.",
    )
    return parser.parse_args(argv)


def _load_product_universe() -> tuple[ProductContext, ...]:
    """Load all Product rows as ProductContext objects, sorted by product_id."""
    with session_scope() as session:
        rows = list(
            session.execute(select(Product).order_by(Product.product_id.asc())).scalars()
        )
    return tuple(
        ProductContext(product_id=p.product_id, display_name=p.display_name) for p in rows
    )


def _log_stats(stats: BuildStats) -> None:
    log.info(
        "deliberation: candidates_selected=%d built=%d labeled=%d unbuildable=%d",
        stats.candidates_selected,
        stats.candidates_built,
        stats.candidates_labeled,
        len(stats.skipped_candidates_unbuildable),
    )
    log.info(
        "deliberation: entries_written=%d force_include_B=%d C=%d D=%d",
        stats.deliberation_entries_written,
        stats.force_include_b,
        stats.force_include_c,
        stats.force_include_d,
    )
    log.info(
        "reason: resolved_threads=%d comments_labeled=%d entries_written=%d",
        stats.resolved_threads,
        stats.comments_labeled,
        stats.reason_entries_written,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    configure_logging()

    settings = get_settings()
    if not settings.anthropic_api_key:
        log.error("ANTHROPIC_API_KEY is not set; cannot call Sonnet.")
        return 2

    products = _load_product_universe()
    if not products:
        log.error(
            "no Product rows in the DB — run scripts/scrape.py first to populate "
            "the product universe."
        )
        return 1
    log.info("product universe: %d products", len(products))

    client = AnthropicClient(api_key=settings.anthropic_api_key)
    deliberation_labeler = DeliberationLabeler(client, model=settings.anthropic_sonnet_model)
    reason_labeler = ReasonLabeler(client, model=settings.anthropic_sonnet_model)

    rng = random.Random(args.seed)
    log.info(
        "build starting: candidate_cap=%d target_size=%d seed=%d",
        args.candidate_cap,
        args.target_size,
        args.seed,
    )

    with session_scope() as session:
        stats = build_gold_sets(
            session,
            deliberation_labeler=deliberation_labeler,
            reason_labeler=reason_labeler,
            products=products,
            rng=rng,
            deliberation_output_path=args.deliberation_out,
            reason_output_path=args.reason_out,
            candidate_cap=args.candidate_cap,
            target_size=args.target_size,
        )

    _log_stats(stats)
    print()
    print(json.dumps(
        {
            "deliberation_entries_written": stats.deliberation_entries_written,
            "reason_entries_written": stats.reason_entries_written,
            "force_include_b": stats.force_include_b,
            "force_include_c": stats.force_include_c,
            "force_include_d": stats.force_include_d,
            "resolved_threads": stats.resolved_threads,
            "comments_labeled": stats.comments_labeled,
            "skipped_candidates_unbuildable": stats.skipped_candidates_unbuildable,
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
