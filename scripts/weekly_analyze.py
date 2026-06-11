"""Weekly analysis entry point (daily-ingestion cadence — step 2).

Runs the *analysis* tier of the three-cadence model (see
``docs/DAILY_INGESTION_DESIGN.md``): incremental aspect tagging over whatever
mentions the daily collector has accumulated, then a fresh A1 aggregate
**snapshot** keyed by a per-week ``run_id`` (e.g. ``run_2026_w24``). The
sequence of weekly snapshots is the trend read by ``/api/trend`` (step 4).

Deliberately **does not** synthesize briefs — brief synthesis stays on the
quarterly cadence (``scripts/refresh.py``). This script is the cheap weekly
pass: Qwen-local tagging (incremental, only new mentions hit the LLM) plus
pure-Python aggregation.

Idempotency:
- Tagging (``tag_corpus_aspects``) skips ``(mention, product)`` pairs already
  tagged at the same ``taxonomy_version`` + ``prompt_version``.
- Aggregation is delete-then-insert scoped to *this week's* ``run_id`` only, so
  re-running within the same week overwrites that week and leaves prior weeks
  intact. The aggregate is full corpus-to-date (locked decision — no trailing
  window).

Usage::

    python scripts/weekly_analyze.py --run-config configs/run_wave5_v1.yaml
    python scripts/weekly_analyze.py --run-config configs/run_wave5_v1.yaml --provider anthropic
    python scripts/weekly_analyze.py --run-config configs/run_wave5_v1.yaml --as-of 2026-06-08
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from pulse_check.aggregation.a1 import aggregate_a1
from pulse_check.config import load_run
from pulse_check.logging_config import configure_logging
from pulse_check.scheduling.weekly_snapshot import ensure_run_row, snapshot_run_id
from pulse_check.settings import get_settings
from pulse_check.storage.enums import ContentType
from pulse_check.storage.session import session_scope
from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.tagging import AspectClassifier, ProductContext
from pulse_check.tagging.aspect_classifier import PROMPT_VERSION, TAXONOMY_VERSION
from pulse_check.tagging.batch import tag_corpus_aspects
from pulse_check.tagging.ollama import OllamaClient

log = logging.getLogger("pulse_check.scripts.weekly_analyze")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pulse-check weekly-analyze",
        description=(
            "Weekly analysis pass: incremental aspect tagging + per-week "
            "aggregate snapshot. No brief synthesis (quarterly cadence)."
        ),
    )
    parser.add_argument(
        "--run-config",
        type=Path,
        required=True,
        help="Path to a run YAML (e.g. configs/run_wave5_v1.yaml).",
    )
    parser.add_argument(
        "--provider",
        choices=("ollama", "anthropic"),
        default="ollama",
        help=(
            "Which LLM provider drives aspect tagging. 'ollama' (default) runs"
            " Qwen locally — the volume tagger for the weekly cadence;"
            " 'anthropic' runs Haiku as a fallback (CLAUDE.md routing)."
        ),
    )
    parser.add_argument(
        "--commit-every",
        type=int,
        default=50,
        help=(
            "Commit aspect_tags every N classifications (each == one LLM call)."
            " Preserves paid calls on a mid-batch crash. Mirrors tag.py."
        ),
    )
    parser.add_argument(
        "--as-of",
        type=str,
        default=None,
        help=(
            "ISO date (YYYY-MM-DD) to derive the weekly snapshot id from."
            " Defaults to now (UTC). Use for backfill / deterministic re-runs."
        ),
    )
    parser.add_argument(
        "--skip-tagging",
        action="store_true",
        help="Skip the tagging step (aggregate already-tagged corpus only).",
    )
    parser.add_argument(
        "--skip-aggregation",
        action="store_true",
        help="Skip the aggregation step (tag only).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    configure_logging()

    settings = get_settings()
    run_config, product_set, _pair_plan, _rss_sources = load_run(args.run_config)
    products = [
        ProductContext(product_id=p.product_id, display_name=p.display_name)
        for p in product_set.products
    ]

    as_of = (
        datetime.fromisoformat(args.as_of).replace(tzinfo=UTC)
        if args.as_of
        else datetime.now(UTC)
    )
    snapshot_id = snapshot_run_id(as_of)
    log.info(
        "starting weekly analysis: snapshot_run_id=%s products=%d taxonomy=%s "
        "provider=%s as_of=%s",
        snapshot_id,
        len(products),
        TAXONOMY_VERSION,
        args.provider,
        as_of.date().isoformat(),
    )

    # --- Step 1: incremental aspect tagging --------------------------------
    if args.skip_tagging:
        log.info("weekly tagging: SKIPPED (--skip-tagging)")
    elif args.provider == "anthropic":
        if not settings.anthropic_api_key:
            log.error("--provider anthropic requires ANTHROPIC_API_KEY in env/.env")
            return 1
        client = AnthropicClient(api_key=settings.anthropic_api_key, timeout=300.0)
        classifier = AspectClassifier(client, model=settings.anthropic_haiku_model)
        with session_scope() as session:
            stats = tag_corpus_aspects(
                session,
                classifier=classifier,
                products=products,
                taxonomy_version=TAXONOMY_VERSION,
                exclude_content_types=frozenset({ContentType.DEAL}),
                commit_every=args.commit_every,
            )
        log.info(
            "tagging done: seen=%d skipped_existing=%d filtered=%d classified=%d "
            "inserted=%d",
            stats.attributions_seen,
            stats.attributions_skipped_existing,
            stats.attributions_skipped_content_filter,
            stats.attributions_classified,
            stats.aspect_tags_inserted,
        )
    else:
        with OllamaClient(host=settings.ollama_host) as ollama_client:
            classifier = AspectClassifier(ollama_client, model=settings.ollama_model)
            with session_scope() as session:
                stats = tag_corpus_aspects(
                    session,
                    classifier=classifier,
                    products=products,
                    taxonomy_version=TAXONOMY_VERSION,
                    exclude_content_types=frozenset({ContentType.DEAL}),
                    commit_every=args.commit_every,
                )
        log.info(
            "tagging done: seen=%d skipped_existing=%d filtered=%d classified=%d "
            "inserted=%d",
            stats.attributions_seen,
            stats.attributions_skipped_existing,
            stats.attributions_skipped_content_filter,
            stats.attributions_classified,
            stats.aspect_tags_inserted,
        )

    # --- Step 2: weekly aggregate snapshot ---------------------------------
    if args.skip_aggregation:
        log.info("weekly aggregation: SKIPPED (--skip-aggregation)")
        return 0

    with session_scope() as session:
        inserted = ensure_run_row(
            session,
            run_id=snapshot_id,
            taxonomy_version=TAXONOMY_VERSION,
            prompt_version=PROMPT_VERSION,
            config_snapshot={
                "cadence": "weekly",
                "source_run_id": run_config.run_id,
                "as_of": as_of.date().isoformat(),
            },
        )
        log.info(
            "run row %s: %s",
            snapshot_id,
            "inserted" if inserted else "already exists",
        )
        agg_stats = aggregate_a1(
            session,
            run_id=snapshot_id,
            product_ids=[p.product_id for p in products],
            taxonomy_version=TAXONOMY_VERSION,
            prompt_version=PROMPT_VERSION,
        )
    log.info(
        "done: snapshot_run_id=%s groups=%d upserted=%d primary_contrib=%d "
        "secondary_contrib=%d",
        snapshot_id,
        agg_stats.groups_seen,
        agg_stats.aggregates_upserted,
        agg_stats.mentions_contributing,
        agg_stats.mentions_contributing_secondary,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
