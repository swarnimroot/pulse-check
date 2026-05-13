"""CLI entry point: run a scrape for a given run config.

Usage:
    python scripts/scrape.py --run-config configs/run_smoke_test.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pulse_check.config import load_run
from pulse_check.logging_config import configure_logging
from pulse_check.scraping import run_scrape
from pulse_check.scraping.discovered_urls import load_approved_discovered_urls
from pulse_check.storage.session import session_scope

log = logging.getLogger("pulse_check.scripts.scrape")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pulse-check scrape",
        description="Run a full scrape for a pulse-check run config.",
    )
    parser.add_argument(
        "--run-config",
        type=Path,
        required=True,
        help="Path to a run YAML (e.g. configs/run_smoke_test.yaml).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    configure_logging()

    run_config, product_set, _pair_plan, rss_sources = load_run(args.run_config)
    discovered_urls = (
        load_approved_discovered_urls(run_config.discovered_urls_sources)
        if run_config.discovered_urls_sources is not None
        else None
    )
    log.info(
        "starting scrape: run_id=%s products=%d rss_sources=%s discovered_urls=%s",
        run_config.run_id,
        len(product_set.products),
        "yes" if rss_sources is not None else "no",
        f"{len(discovered_urls)} entries" if discovered_urls is not None else "no",
    )

    with session_scope() as session:
        ingest_stats, secondary_stats, inheritance_stats = run_scrape(
            session,
            run_config,
            product_set,
            rss_sources=rss_sources,
            discovered_urls=discovered_urls,
        )

    log.info(
        "done: mentions new=%d existing=%d | primary=%d secondary=%d "
        "inherited=%d | snapshots skipped=%d",
        ingest_stats.new_mentions,
        ingest_stats.existing_mentions,
        ingest_stats.new_attributions,
        secondary_stats.new_attributions,
        inheritance_stats.new_attributions,
        ingest_stats.skipped_snapshots,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
