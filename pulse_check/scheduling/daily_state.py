"""Daily-collector run-state tracking.

Mirrors ``scheduling/state.py`` (the quarterly-refresh cadence gate) but tracks
the *daily ingestion* tier introduced in session 45 — see
``docs/DAILY_INGESTION_DESIGN.md``. Persists the last successful daily
collection (timestamp, run id, new-mention count) in a single atomically
written JSON file at ``Settings.daily_collector_state_path`` (default
``data/daily_collector_state.json``).

The file is updated only after a collection completes successfully — a mid-run
crash does NOT advance the timestamp, matching the no-auto-rerun-on-crash
discipline.

State powers **gap detection**: the collector is expected to run roughly every
24h. A gap exceeding ``GAP_THRESHOLD_HOURS`` since the last successful run means
a day (or more) of perishable Reddit data was likely missed. Reddit has no
backfill, so the gap is logged loudly — it cannot be recovered.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pulse_check.settings import get_settings

SCHEMA_VERSION = 1

# A daily run that lands more than this many hours after the previous one means
# at least one expected daily collection was missed. 36h (1.5 days) tolerates
# normal run-time jitter without flagging a healthy daily cadence.
GAP_THRESHOLD_HOURS = 36.0


@dataclass(frozen=True)
class DailyCollectorState:
    """Snapshot of the last successful daily collection.

    All fields are ``None`` for a fresh system that has never collected (the
    state file does not exist yet).
    """

    last_run_at: datetime | None
    last_run_id: str | None
    last_new_mentions: int | None

    @classmethod
    def never(cls) -> DailyCollectorState:
        return cls(last_run_at=None, last_run_id=None, last_new_mentions=None)


def _resolve_path(path: Path | None) -> Path:
    return path if path is not None else Path(get_settings().daily_collector_state_path)


def read_state(path: Path | None = None) -> DailyCollectorState:
    """Load state from ``path`` (or settings default).

    Returns ``DailyCollectorState.never()`` when the file does not exist. Raises
    ``ValueError`` on schema-version mismatch so callers fail loud rather than
    silently treating a future-schema file as "never collected".
    """
    p = _resolve_path(path)
    if not p.exists():
        return DailyCollectorState.never()

    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported daily-collector-state schema_version "
            f"{data.get('schema_version')!r} at {p} "
            f"(this binary speaks v{SCHEMA_VERSION})"
        )

    ts = data.get("last_run_at")
    return DailyCollectorState(
        last_run_at=datetime.fromisoformat(ts) if ts else None,
        last_run_id=data.get("last_run_id"),
        last_new_mentions=data.get("last_new_mentions"),
    )


def write_state(state: DailyCollectorState, path: Path | None = None) -> None:
    """Atomically write state to ``path`` (or settings default).

    Writes to a sibling temp file then ``os.replace``s into place so a crash
    mid-write cannot leave a half-written state file.
    """
    p = _resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "last_run_at": state.last_run_at.isoformat() if state.last_run_at else None,
        "last_run_id": state.last_run_id,
        "last_new_mentions": state.last_new_mentions,
    }

    fd, tmp_path = tempfile.mkstemp(
        prefix=".daily_collector_state_", suffix=".json", dir=str(p.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, p)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def gap_hours(
    state: DailyCollectorState, *, now: datetime | None = None
) -> float | None:
    """Hours since the last successful collection, or ``None`` if never run."""
    if state.last_run_at is None:
        return None
    now_ts = now if now is not None else datetime.now(UTC)
    return (now_ts - state.last_run_at).total_seconds() / 3600.0


def has_gap(
    state: DailyCollectorState,
    *,
    now: datetime | None = None,
    threshold_hours: float = GAP_THRESHOLD_HOURS,
) -> bool:
    """True when a prior run exists and the gap since it exceeds the threshold.

    A never-run system returns ``False`` — the first collection is not a "gap",
    just a cold start.
    """
    hours = gap_hours(state, now=now)
    if hours is None:
        return False
    return hours > threshold_hours
