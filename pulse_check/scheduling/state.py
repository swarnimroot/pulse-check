"""Refresh-cadence state tracking.

Persists the "last successful quarterly refresh" timestamp in a single JSON
file at ``Settings.refresh_state_path`` (default ``data/refresh_state.json``).
The file is updated atomically (write-temp + os.replace) only after a refresh
completes successfully — a mid-run crash does NOT advance the timestamp,
which keeps the next ``is_due()`` call reporting overdue until the operator
intervenes. Matches the no-auto-rerun-on-crash discipline.

State lives on disk rather than in the DB because cadence reporting hasn't
yet graduated to the UI. Promote to a ``RefreshLog`` SQLAlchemy table if/when
cross-run history becomes a product surface.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pulse_check.settings import get_settings

SCHEMA_VERSION = 1
DEFAULT_REFRESH_INTERVAL_DAYS = 90


@dataclass(frozen=True)
class RefreshState:
    """Snapshot of the last successful refresh.

    Both fields are ``None`` for a fresh system that has never run a refresh
    (the state file does not exist yet).
    """

    last_refresh_at: datetime | None
    last_refresh_run_id: str | None

    @classmethod
    def never(cls) -> RefreshState:
        return cls(last_refresh_at=None, last_refresh_run_id=None)


def _resolve_path(path: Path | None) -> Path:
    return path if path is not None else Path(get_settings().refresh_state_path)


def read_state(path: Path | None = None) -> RefreshState:
    """Load state from ``path`` (or settings default).

    Returns ``RefreshState.never()`` when the file does not exist. Raises
    ``ValueError`` on schema-version mismatch so callers fail loud rather than
    silently treating a future-schema file as "never refreshed".
    """
    p = _resolve_path(path)
    if not p.exists():
        return RefreshState.never()

    data = json.loads(p.read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported refresh-state schema_version "
            f"{data.get('schema_version')!r} at {p} "
            f"(this binary speaks v{SCHEMA_VERSION})"
        )

    ts = data.get("last_refresh_at")
    return RefreshState(
        last_refresh_at=datetime.fromisoformat(ts) if ts else None,
        last_refresh_run_id=data.get("last_refresh_run_id"),
    )


def write_state(state: RefreshState, path: Path | None = None) -> None:
    """Atomically write state to ``path`` (or settings default).

    Writes to a sibling temp file then ``os.replace``s into place so a crash
    mid-write cannot leave a half-written state file.
    """
    p = _resolve_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "last_refresh_at": (
            state.last_refresh_at.isoformat() if state.last_refresh_at else None
        ),
        "last_refresh_run_id": state.last_refresh_run_id,
    }

    fd, tmp_path = tempfile.mkstemp(
        prefix=".refresh_state_", suffix=".json", dir=str(p.parent)
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


def is_due(
    state: RefreshState,
    *,
    now: datetime | None = None,
    interval_days: int = DEFAULT_REFRESH_INTERVAL_DAYS,
) -> bool:
    """True when no prior refresh exists or the gap meets ``interval_days``."""
    if state.last_refresh_at is None:
        return True
    now_ts = now if now is not None else datetime.now(UTC)
    return (now_ts - state.last_refresh_at) >= timedelta(days=interval_days)


def days_since_refresh(
    state: RefreshState, *, now: datetime | None = None
) -> int | None:
    """Whole days since the last successful refresh, or ``None`` if never."""
    if state.last_refresh_at is None:
        return None
    now_ts = now if now is not None else datetime.now(UTC)
    return (now_ts - state.last_refresh_at).days
