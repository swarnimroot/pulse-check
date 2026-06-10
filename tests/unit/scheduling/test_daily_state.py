"""Unit tests for the daily-collector state module."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pulse_check.scheduling.daily_state import (
    GAP_THRESHOLD_HOURS,
    SCHEMA_VERSION,
    DailyCollectorState,
    gap_hours,
    has_gap,
    read_state,
    write_state,
)

# --------------------------------------------------------------------------- #
# read_state / write_state
# --------------------------------------------------------------------------- #


class TestReadState:
    def test_missing_file_returns_never(self, tmp_path: Path) -> None:
        result = read_state(tmp_path / "nope.json")
        assert result == DailyCollectorState.never()
        assert result.last_run_at is None
        assert result.last_run_id is None
        assert result.last_new_mentions is None

    def test_reads_v1_payload(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        ts = "2026-06-10T08:00:00+00:00"
        target.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "last_run_at": ts,
                    "last_run_id": "wave5_v1",
                    "last_new_mentions": 42,
                }
            ),
            encoding="utf-8",
        )

        result = read_state(target)
        assert result.last_run_at == datetime.fromisoformat(ts)
        assert result.last_run_id == "wave5_v1"
        assert result.last_new_mentions == 42

    def test_null_timestamp_round_trips_as_never(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        target.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "last_run_at": None,
                    "last_run_id": None,
                    "last_new_mentions": None,
                }
            ),
            encoding="utf-8",
        )

        assert read_state(target) == DailyCollectorState.never()

    def test_unknown_schema_version_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        target.write_text(
            json.dumps(
                {
                    "schema_version": 99,
                    "last_run_at": "2026-06-10T08:00:00+00:00",
                    "last_run_id": "x",
                    "last_new_mentions": 1,
                }
            ),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="schema_version"):
            read_state(target)


class TestWriteState:
    def test_round_trip(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        state = DailyCollectorState(
            last_run_at=datetime(2026, 6, 10, 8, 0, 0, tzinfo=UTC),
            last_run_id="wave5_v1",
            last_new_mentions=17,
        )

        write_state(state, target)

        assert read_state(target) == state

    def test_creates_parent_dir(self, tmp_path: Path) -> None:
        target = tmp_path / "nested" / "dir" / "state.json"
        write_state(DailyCollectorState.never(), target)

        assert target.exists()

    def test_payload_is_versioned(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        write_state(DailyCollectorState.never(), target)

        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["schema_version"] == SCHEMA_VERSION

    def test_no_temp_file_left_behind_after_success(self, tmp_path: Path) -> None:
        target = tmp_path / "state.json"
        write_state(DailyCollectorState.never(), target)

        leftovers = [
            p for p in tmp_path.iterdir() if p.name.startswith(".daily_collector_state_")
        ]
        assert leftovers == []


# --------------------------------------------------------------------------- #
# gap_hours
# --------------------------------------------------------------------------- #


class TestGapHours:
    def test_never_returns_none(self) -> None:
        assert gap_hours(DailyCollectorState.never()) is None

    def test_counts_fractional_hours(self) -> None:
        now = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
        state = DailyCollectorState(
            last_run_at=now - timedelta(hours=25, minutes=30),
            last_run_id="r",
            last_new_mentions=0,
        )
        assert gap_hours(state, now=now) == pytest.approx(25.5)


# --------------------------------------------------------------------------- #
# has_gap
# --------------------------------------------------------------------------- #


class TestHasGap:
    def test_never_run_is_not_a_gap(self) -> None:
        assert has_gap(DailyCollectorState.never()) is False

    def test_healthy_daily_cadence_no_gap(self) -> None:
        now = datetime(2026, 6, 10, 8, 0, tzinfo=UTC)
        state = DailyCollectorState(
            last_run_at=now - timedelta(hours=24),
            last_run_id="r",
            last_new_mentions=5,
        )
        assert has_gap(state, now=now) is False

    def test_missed_day_is_a_gap(self) -> None:
        now = datetime(2026, 6, 10, 8, 0, tzinfo=UTC)
        state = DailyCollectorState(
            last_run_at=now - timedelta(hours=49),
            last_run_id="r",
            last_new_mentions=5,
        )
        assert has_gap(state, now=now) is True

    def test_exactly_threshold_is_not_a_gap(self) -> None:
        now = datetime(2026, 6, 10, 8, 0, tzinfo=UTC)
        state = DailyCollectorState(
            last_run_at=now - timedelta(hours=GAP_THRESHOLD_HOURS),
            last_run_id="r",
            last_new_mentions=5,
        )
        # Strictly greater-than threshold counts as a gap, so exactly-threshold does not.
        assert has_gap(state, now=now) is False

    def test_custom_threshold_honored(self) -> None:
        now = datetime(2026, 6, 10, 8, 0, tzinfo=UTC)
        state = DailyCollectorState(
            last_run_at=now - timedelta(hours=12),
            last_run_id="r",
            last_new_mentions=5,
        )
        assert has_gap(state, now=now, threshold_hours=6) is True
        assert has_gap(state, now=now, threshold_hours=24) is False
