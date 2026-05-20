"""Quarterly-cadence refresh orchestrator (skeleton).

Default mode is DRY-RUN: prints the plan, "is due" verdict, and estimated
LLM spend without firing any subprocess or writing state. Use ``--execute``
to actually fire the pipeline; a keypress confirmation is still required.

Pipeline (subprocess chain, in order):
    1. scripts/scrape.py                 -- ingest new mentions
    2. scripts/run_stage_b.py            -- tag + aggregate + brief
    3. scripts/verify_mention_links.py   -- tombstone dead links

Discipline:
- State (``data/refresh_state.json``) is written ONLY after every step in
  the chain exits 0. A crash mid-chain leaves ``last_refresh_at`` unchanged
  so the next invocation re-proposes the run.
- ``--force`` bypasses the 90-day is_due gate. Keypress confirmation is
  still required.
- The Windows Task Scheduler template (``scripts/refresh_quarterly.xml``)
  fires this script WITHOUT ``--execute`` on purpose: the scheduled job
  surfaces a dry-run plan into the operator's log, and the operator chooses
  whether to manually fire ``--execute``.

Usage:
    python scripts/refresh.py                    # default: dry-run plan
    python scripts/refresh.py --execute          # fire chain (asks y/n)
    python scripts/refresh.py --execute --force  # ignore is_due, ask y/n
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from pulse_check.logging_config import configure_logging
from pulse_check.scheduling.state import (
    DEFAULT_REFRESH_INTERVAL_DAYS,
    RefreshState,
    days_since_refresh,
    is_due,
    read_state,
    write_state,
)
from pulse_check.settings import get_settings

log = logging.getLogger("pulse_check.scripts.refresh")

# scripts/refresh.py lives at <repo>/scripts/refresh.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUN_ID = "run_wave5_v1"

# Subprocess chain. Each entry is (script-relative-to-scripts/, extra args).
# Extra args are kept minimal here; per-script tuning lives in each script's
# own CLI (operator can run them directly with non-default flags for repair
# passes outside the quarterly cadence).
PIPELINE: list[tuple[str, list[str]]] = [
    ("scrape.py", []),
    ("run_stage_b.py", []),
    ("verify_mention_links.py", []),
]

COST_ESTIMATE_PER_QUARTER = "~$5-25 (quarterly slice of ~$60-100/year cadence)"
WALL_TIME_ESTIMATE = "30-120 min (corpus-growth + cache-hit dependent)"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="refresh",
        description=(
            "Quarterly refresh orchestrator. Defaults to dry-run; opt in "
            "with --execute to fire the pipeline."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually fire the pipeline (requires y/n keypress confirmation).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass the 90-day is_due gate. Confirmation still required.",
    )
    parser.add_argument(
        "--interval-days",
        type=int,
        default=DEFAULT_REFRESH_INTERVAL_DAYS,
        help="Override the is_due threshold (default 90).",
    )
    parser.add_argument(
        "--refresh-state-path",
        type=Path,
        default=None,
        help="Override the refresh-state JSON path (testing / catch-up runs).",
    )
    return parser.parse_args(argv)


def _format_plan(
    state: RefreshState,
    *,
    state_path: Path,
    now: datetime,
    interval_days: int,
    force: bool,
) -> str:
    if state.last_refresh_at is None:
        last_line = "(never -- first run)"
        days_line = "N/A"
    else:
        last_line = state.last_refresh_at.isoformat()
        days_line = f"{days_since_refresh(state, now=now)}"

    due = is_due(state, now=now, interval_days=interval_days)
    if due and state.last_refresh_at is None:
        due_line = "YES (no prior refresh recorded)"
    elif due:
        overdue = (days_since_refresh(state, now=now) or 0) - interval_days
        due_line = f"YES ({overdue} days overdue)"
    else:
        remaining = interval_days - (days_since_refresh(state, now=now) or 0)
        due_line = f"NO ({remaining} days remaining)"

    plan_lines = "\n".join(
        f"  {i}. scripts/{script} {' '.join(extra)}".rstrip()
        for i, (script, extra) in enumerate(PIPELINE, 1)
    )

    forced = " (--force will override)" if not due and not force else ""

    return (
        f"State file:        {state_path}\n"
        f"Last refresh:      {last_line}\n"
        f"Days since:        {days_line}\n"
        f"Threshold:         {interval_days} days\n"
        f"Due?               {due_line}{forced}\n"
        f"Run ID (continues): {RUN_ID}\n"
        f"\n"
        f"Planned chain (subprocess, in order):\n"
        f"{plan_lines}\n"
        f"\n"
        f"Estimated LLM spend: {COST_ESTIMATE_PER_QUARTER}\n"
        f"Estimated wall time: {WALL_TIME_ESTIMATE}\n"
    )


def _confirm() -> bool:
    """Blocking prompt; returns True only on 'y' or 'Y'."""
    try:
        answer = input("Continue? [y/N]: ").strip()
    except EOFError:
        return False
    return answer in {"y", "Y"}


def _run_pipeline() -> int:
    """Invoke each subprocess in order. Returns 0 on success, non-zero on first failure."""
    for i, (script, args) in enumerate(PIPELINE, 1):
        cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / script), *args]
        log.info(
            "[%d/%d] invoking: %s", i, len(PIPELINE), " ".join(cmd)
        )
        proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=False)
        if proc.returncode != 0:
            log.error(
                "[%d/%d] %s exited %d -- aborting chain; state NOT updated",
                i,
                len(PIPELINE),
                script,
                proc.returncode,
            )
            return proc.returncode
        log.info("[%d/%d] %s exited 0", i, len(PIPELINE), script)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    configure_logging()

    state_path = args.refresh_state_path or Path(get_settings().refresh_state_path)
    state = read_state(state_path)
    now = datetime.now(UTC)
    plan = _format_plan(
        state,
        state_path=state_path,
        now=now,
        interval_days=args.interval_days,
        force=args.force,
    )

    if not args.execute:
        sys.stdout.write("\n=== Quarterly refresh: DRY-RUN ===\n")
        sys.stdout.write(plan)
        sys.stdout.write("\nTo execute: python scripts/refresh.py --execute\n")
        return 0

    due = is_due(state, now=now, interval_days=args.interval_days)
    if not due and not args.force:
        sys.stdout.write("\n=== Quarterly refresh: NOT DUE ===\n")
        sys.stdout.write(plan)
        sys.stdout.write("\nNo action. Use --force to override.\n")
        return 0

    sys.stdout.write("\n=== Quarterly refresh: EXECUTE ===\n")
    sys.stdout.write(plan)
    sys.stdout.write("\n")
    if not _confirm():
        sys.stdout.write("Aborted.\n")
        return 0

    log.info("=== quarterly refresh: start ===")
    rc = _run_pipeline()
    if rc != 0:
        log.error("=== quarterly refresh: FAILED (rc=%d) ===", rc)
        return rc

    completed_at = datetime.now(UTC)
    new_state = RefreshState(
        last_refresh_at=completed_at, last_refresh_run_id=RUN_ID
    )
    write_state(new_state, state_path)
    log.info(
        "=== quarterly refresh: COMPLETE at %s (state written) ===",
        completed_at.isoformat(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
