"""Daily ingestion collector.

Thin wrapper around the existing full-scrape path (``scripts/scrape.py`` /
``run_scrape``) for the *daily* ingestion tier introduced in session 45 — see
``docs/DAILY_INGESTION_DESIGN.md``.

What it adds over ``scrape.py``:

- **Gap detection.** Reads the daily-collector state before running. If the last
  successful run was more than ``GAP_THRESHOLD_HOURS`` ago, logs a loud WARNING:
  a day (or more) of perishable Reddit data was likely missed. Reddit has no
  backfill, so the gap is recorded, not recovered.
- **Run-state persistence.** After a successful collection, atomically records
  the timestamp, run id, and new-mention count so the next run can detect gaps
  and so cadence health is inspectable.

It deliberately reuses the run config's full backfill window each day. Dedup
happens at ingest (new vs existing ``mention_id``), so re-sweeping is correct —
just not bandwidth-minimal. Re-sweeping the full window is the safe choice: it
never misses a gap.

No LLM runs here — this is collection only. Analysis (aspect tagging,
aggregates, briefs) is a separate weekly/quarterly tier.

Usage::

    python scripts/daily_collect.py --run-config configs/run_wave5_v1.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from pulse_check.config import load_run
from pulse_check.logging_config import configure_logging
from pulse_check.scheduling.daily_state import (
    DailyCollectorState,
    gap_hours,
    has_gap,
    read_state,
    write_state,
)
from pulse_check.scraping import run_scrape
from pulse_check.scraping.discovered_urls import load_approved_discovered_urls
from pulse_check.storage.session import session_scope

log = logging.getLogger("pulse_check.scripts.daily_collect")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pulse-check daily-collect",
        description="Run a daily ingestion collection (scrape-only, no LLM).",
    )
    parser.add_argument(
        "--run-config",
        type=Path,
        required=True,
        help="Path to a run YAML (e.g. configs/run_wave5_v1.yaml).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    configure_logging()

    # Gap detection runs before the scrape so the warning is emitted even if the
    # collection itself later fails.
    prior = read_state()
    if has_gap(prior):
        hours = gap_hours(prior)
        log.warning(
            "daily-collector GAP detected: %.1fh since last run (last_run_at=%s, "
            "last_run_id=%s) — perishable Reddit data in the gap is unrecoverable",
            hours,
            prior.last_run_at.isoformat() if prior.last_run_at else None,
            prior.last_run_id,
        )
    elif prior.last_run_at is None:
        log.info("daily-collector cold start: no prior run recorded")

    run_config, product_set, _pair_plan, rss_sources = load_run(args.run_config)
    discovered_urls = (
        load_approved_discovered_urls(run_config.discovered_urls_sources)
        if run_config.discovered_urls_sources is not None
        else None
    )
    log.info(
        "starting daily collection: run_id=%s products=%d rss_sources=%s "
        "discovered_urls=%s",
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

    # Persist state only after a successful collection, so a crash mid-run does
    # not advance the timestamp and the next run still reports the gap.
    write_state(
        DailyCollectorState(
            last_run_at=datetime.now(UTC),
            last_run_id=run_config.run_id,
            last_new_mentions=ingest_stats.new_mentions,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
