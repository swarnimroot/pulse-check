"""CLI: build a Sonnet-labeled gold set for aspect tagging.

Usage::

    python scripts/build_gold_set.py \\
        --task aspect_tagging \\
        --run-config configs/run_smoke_test.yaml \\
        --total 150 \\
        --seed 42

Stratified across source_type buckets; Sonnet labels via ``call_with_cache``
so re-running is free. Writes to ``data/gold_sets/<task>_v1.jsonl``. Operator
reviews the file with ``scripts/review_gold_set.py``.
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
from pathlib import Path

from pulse_check.config import load_run
from pulse_check.eval.gold_set import (
    label_with_sonnet,
    sample_attributions_stratified,
    write_jsonl,
)
from pulse_check.logging_config import configure_logging
from pulse_check.settings import get_settings
from pulse_check.storage.session import session_scope
from pulse_check.synthesis.anthropic_client import AnthropicClient

log = logging.getLogger("pulse_check.scripts.build_gold_set")

_GOLD_SET_DIR = Path("data/gold_sets")
_SUPPORTED_TASKS = ("aspect_tagging",)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pulse-check build-gold-set",
        description="Sample mentions and Sonnet-label them into a JSONL gold set.",
    )
    parser.add_argument(
        "--task",
        choices=_SUPPORTED_TASKS,
        required=True,
        help="Which gold set to build (v1: aspect_tagging only).",
    )
    parser.add_argument("--run-config", type=Path, required=True)
    parser.add_argument(
        "--total",
        type=int,
        default=150,
        help="Total (mention, product) pairs to sample and label.",
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility.")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"Output path. Defaults to {_GOLD_SET_DIR}/<task>_v1.jsonl.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    configure_logging()

    settings = get_settings()
    if not settings.anthropic_api_key:
        log.error("ANTHROPIC_API_KEY is not set; cannot call Sonnet.")
        return 2

    _run_config, product_set, _pair_plan, _rss_sources = load_run(args.run_config)
    product_ids = {p.product_id for p in product_set.products}
    out_path: Path = args.out or (_GOLD_SET_DIR / f"{args.task}_v1.jsonl")

    rng = random.Random(args.seed)
    log.info(
        "sampling up to %d (mention, product) pairs across %d products, seed=%d",
        args.total,
        len(product_ids),
        args.seed,
    )

    with session_scope() as session:
        samples = sample_attributions_stratified(
            session,
            product_ids=product_ids,
            total=args.total,
            rng=rng,
        )
        log.info("sampled %d attributions", len(samples))
        if not samples:
            log.warning(
                "no attributions matched — is the corpus populated? run scripts/scrape.py first."
            )
            return 1

        client = AnthropicClient(api_key=settings.anthropic_api_key)
        entries = label_with_sonnet(
            session,
            samples=samples,
            client=client,
            model=settings.anthropic_sonnet_model,
        )

    write_jsonl(entries, out_path)
    log.info("wrote gold set: %s (%d entries)", out_path, len(entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
