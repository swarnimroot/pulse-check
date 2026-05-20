"""Unit tests for the refresh-cadence state module."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pulse_check.scheduling.state import (
    DEFAULT_REFRESH_INTERVAL_DAYS,
    SCHEMA_VERSION,
    RefreshState,
    days_since_refresh,
    is_due,
    read_state,
    write_state,
)

# --------------------------------------------------------------------------- #
# read_state / write_state
# --------------------------------------------------------------------------- #


class TestReadState:
    def test_missing_file_returns_never(self, tmp_path: Path) -> None:
        result = read_state(tmp_path / "nope.json")
        assert result == RefreshState.never()
        assert result.last_refresh_at is None
        assert result.last_refresh_run_id is None

    def test_reads_v1_payload(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        ts = "2026-02-15T21:43:56.123456+00:00"
        target.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "last_refresh_at": ts,
                    "last_refresh_run_id": "run_wave5_v1",
                }
            ),
            encoding="utf-8",
        )

        result = read_state(target)
        assert result.last_refresh_at == datetime.fromisoformat(ts)
        assert result.last_refresh_run_id == "run_wave5_v1"

    def test_null_timestamp_round_trips_as_never(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        target.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "last_refresh_at": None,
                    "last_refresh_run_id": None,
                }
            ),
            encoding="utf-8",
        )

        assert read_state(target) == RefreshState.never()

    def test_unknown_schema_version_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        target.write_text(
            json.dumps(
                {
                    "schema_version": 99,
                    "last_refresh_at": "2026-02-15T21:43:56+00:00",
                    "last_refresh_run_id": "x",
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="schema_version"):
            read_state(target)


class TestWriteState:
    def test_round_trip(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        state = RefreshState(
            last_refresh_at=datetime(2026, 2, 15, 21, 43, 56, tzinfo=UTC),
            last_refresh_run_id="run_wave5_v1",
        )

        write_state(state, target)

        assert read_state(target) == state

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "dir" / "state.json"
        write_state(RefreshState.never(), target)

        assert target.exists()

    def test_payload_is_versioned(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        write_state(RefreshState.never(), target)

        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["schema_version"] == SCHEMA_VERSION

    def test_no_temp_file_left_behind_after_success(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        write_state(RefreshState.never(), target)

        leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".refresh_state_")]
        assert leftovers == []


# --------------------------------------------------------------------------- #
# is_due
# --------------------------------------------------------------------------- #


class TestIsDue:
    def test_never_refreshed_is_due(self) -> None:
        assert is_due(RefreshState.never()) is True

    def test_just_refreshed_not_due(self) -> None:
        now = datetime(2026, 5, 20, tzinfo=UTC)
        state = RefreshState(
            last_refresh_at=now - timedelta(days=1),
            last_refresh_run_id="r",
        )
        assert is_due(state, now=now) is False

    def test_exactly_threshold_is_due(self) -> None:
        now = datetime(2026, 5, 20, tzinfo=UTC)
        state = RefreshState(
            last_refresh_at=now - timedelta(days=DEFAULT_REFRESH_INTERVAL_DAYS),
            last_refresh_run_id="r",
        )
        assert is_due(state, now=now) is True

    def test_overdue_is_due(self) -> None:
        now = datetime(2026, 5, 20, tzinfo=UTC)
        state = RefreshState(
            last_refresh_at=now - timedelta(days=120),
            last_refresh_run_id="r",
        )
        assert is_due(state, now=now) is True

    def test_custom_interval_honored(self) -> None:
        now = datetime(2026, 5, 20, tzinfo=UTC)
        state = RefreshState(
            last_refresh_at=now - timedelta(days=10),
            last_refresh_run_id="r",
        )
        assert is_due(state, now=now, interval_days=7) is True
        assert is_due(state, now=now, interval_days=30) is False


# --------------------------------------------------------------------------- #
# days_since_refresh
# --------------------------------------------------------------------------- #


class TestDaysSinceRefresh:
    def test_never_returns_none(self) -> None:
        assert days_since_refresh(RefreshState.never()) is None

    def test_counts_whole_days(self) -> None:
        now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
        state = RefreshState(
            last_refresh_at=now - timedelta(days=5, hours=3),
            last_refresh_run_id="r",
        )
        assert days_since_refresh(state, now=now) == 5
