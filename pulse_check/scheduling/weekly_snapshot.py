"""Weekly-snapshot identity + Run-row helper.

The weekly-analysis tier (step 2 of the daily-ingestion cadence — see
``docs/DAILY_INGESTION_DESIGN.md``) writes one ``aggregates_aspect_sku``
snapshot per ISO week, keyed by a time-stamped ``run_id``. The sequence of
these snapshots *is* the trend (Option A — no schema migration; the existing
``runs.run_id`` key is reused).

``snapshot_run_id`` derives the deterministic id (e.g. ``run_2026_w24``) from a
datetime's ISO calendar. Re-running in the same week reuses the same id, so the
aggregator's delete-then-insert overwrites that week in place (idempotent) and
leaves prior weeks untouched.

``ensure_run_row`` inserts the backing ``runs`` row if absent. ``aggregates``
carries a FK to ``runs.run_id``; SQLite doesn't enforce it by default but
Postgres (the future cloud target) will, so the row is created up front.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from pulse_check.storage.models import Run


def snapshot_run_id(when: datetime) -> str:
    """Deterministic weekly-snapshot run id, e.g. ``run_2026_w24``.

    Uses the ISO calendar so the week number matches ``isocalendar()`` — note
    the ISO *year* can differ from the calendar year in the first/last days of
    a year (e.g. 2027-01-01 falls in ISO week 53 of 2026). That edge is
    intentional: it keeps every snapshot id unique and monotonic by week.
    """
    iso = when.isocalendar()
    return f"run_{iso.year}_w{iso.week:02d}"


def ensure_run_row(
    session: Session,
    *,
    run_id: str,
    taxonomy_version: str,
    prompt_version: str,
    config_snapshot: dict[str, Any] | None = None,
) -> bool:
    """Insert the ``runs`` row for ``run_id`` if it doesn't exist yet.

    Returns ``True`` when a row was inserted, ``False`` when one already
    existed. Flushes but does not commit — the caller owns the transaction.
    Mirrors the ``_ensure_run_row`` pattern in ``scripts/run_stage_a.py``.
    """
    if session.get(Run, run_id) is not None:
        return False
    session.add(
        Run(
            run_id=run_id,
            config_snapshot=config_snapshot or {"cadence": "weekly"},
            taxonomy_version=taxonomy_version,
            prompt_versions={"aspect_classifier": prompt_version},
        )
    )
    session.flush()
    return True
