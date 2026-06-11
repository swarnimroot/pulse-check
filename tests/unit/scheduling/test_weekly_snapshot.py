"""Weekly-snapshot identity + Run-row helper tests.

Coverage priorities:
- snapshot_run_id formats ISO year + zero-padded week (run_YYYY_wNN)
- snapshot_run_id is deterministic / idempotent within a week
- snapshot_run_id uses the ISO calendar at year boundaries (ISO year != cal year)
- ensure_run_row inserts when absent (returns True) and is a no-op when present
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.scheduling.weekly_snapshot import ensure_run_row, snapshot_run_id
from pulse_check.storage.models import Run

_TAX = "v0"
_PROMPT = "aspect_classifier_v1"


def test_snapshot_run_id_formats_iso_year_and_padded_week() -> None:
    # 2026-06-08 is a Monday in ISO week 24.
    assert snapshot_run_id(datetime(2026, 6, 8, tzinfo=UTC)) == "run_2026_w24"


def test_snapshot_run_id_pads_single_digit_week() -> None:
    # 2026-01-05 is ISO week 2 → zero-padded.
    assert snapshot_run_id(datetime(2026, 1, 5, tzinfo=UTC)) == "run_2026_w02"


def test_snapshot_run_id_is_stable_within_a_week() -> None:
    monday = datetime(2026, 6, 8, 9, 0, tzinfo=UTC)
    sunday = datetime(2026, 6, 14, 23, 59, tzinfo=UTC)
    assert snapshot_run_id(monday) == snapshot_run_id(sunday) == "run_2026_w24"


def test_snapshot_run_id_uses_iso_year_at_boundary() -> None:
    # 2027-01-01 falls in ISO week 53 of ISO year 2026, not 2027.
    assert snapshot_run_id(datetime(2027, 1, 1, tzinfo=UTC)) == "run_2026_w53"


def test_ensure_run_row_inserts_when_absent(session: Session) -> None:
    inserted = ensure_run_row(
        session,
        run_id="run_2026_w24",
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
    )
    assert inserted is True
    row = session.get(Run, "run_2026_w24")
    assert row is not None
    assert row.taxonomy_version == _TAX
    assert row.prompt_versions == {"aspect_classifier": _PROMPT}


def test_ensure_run_row_is_noop_when_present(session: Session) -> None:
    ensure_run_row(
        session,
        run_id="run_2026_w24",
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        config_snapshot={"cadence": "weekly", "marker": "first"},
    )
    second = ensure_run_row(
        session,
        run_id="run_2026_w24",
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        config_snapshot={"cadence": "weekly", "marker": "second"},
    )
    assert second is False
    rows = list(session.execute(select(Run).where(Run.run_id == "run_2026_w24")).scalars())
    assert len(rows) == 1
    # The first row is untouched — no overwrite on the no-op path.
    assert rows[0].config_snapshot["marker"] == "first"
