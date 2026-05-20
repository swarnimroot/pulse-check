"""Unit tests for the refresh.py CLI surface.

Subprocess execution is intentionally not exercised here -- the bite is a
skeleton and the chain is plain ``subprocess.run`` calls into already-tested
scripts. Coverage focuses on the dry-run plan formatter and the main()
exit-code semantics around state-file safety.
"""

from __future__ import annotations

# scripts/ is not on the package path; load refresh as a module via importlib.
import importlib.util
import io
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from pulse_check.scheduling.state import RefreshState, read_state, write_state

_SPEC = importlib.util.spec_from_file_location(
    "_refresh_cli_under_test",
    Path(__file__).resolve().parents[3] / "scripts" / "refresh.py",
)
assert _SPEC is not None and _SPEC.loader is not None
refresh = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(refresh)

# --------------------------------------------------------------------------- #
# _format_plan
# --------------------------------------------------------------------------- #


class TestFormatPlan:
    def test_never_refreshed(self, tmp_path: Path) -> None:
        out = refresh._format_plan(
            RefreshState.never(),
            state_path=tmp_path / "state.json",
            now=datetime(2026, 5, 20, tzinfo=UTC),
            interval_days=90,
            force=False,
        )
        assert "(never -- first run)" in out
        assert "YES (no prior refresh recorded)" in out

    def test_overdue_shows_days_over(self) -> None:
        now = datetime(2026, 5, 20, tzinfo=UTC)
        state = RefreshState(
            last_refresh_at=now - timedelta(days=120),
            last_refresh_run_id="run_wave5_v1",
        )
        out = refresh._format_plan(
            state, state_path=Path("x"), now=now, interval_days=90, force=False
        )
        assert "YES (30 days overdue)" in out

    def test_not_due_shows_days_remaining_and_force_hint(self) -> None:
        now = datetime(2026, 5, 20, tzinfo=UTC)
        state = RefreshState(
            last_refresh_at=now - timedelta(days=30),
            last_refresh_run_id="run_wave5_v1",
        )
        out = refresh._format_plan(
            state, state_path=Path("x"), now=now, interval_days=90, force=False
        )
        assert "NO (60 days remaining)" in out
        assert "--force will override" in out

    def test_not_due_with_force_suppresses_hint(self) -> None:
        now = datetime(2026, 5, 20, tzinfo=UTC)
        state = RefreshState(
            last_refresh_at=now - timedelta(days=30),
            last_refresh_run_id="run_wave5_v1",
        )
        out = refresh._format_plan(
            state, state_path=Path("x"), now=now, interval_days=90, force=True
        )
        assert "NO (60 days remaining)" in out
        assert "--force will override" not in out


# --------------------------------------------------------------------------- #
# main() exit-code + state-safety
# --------------------------------------------------------------------------- #


class TestMain:
    def test_default_is_dry_run_no_state_write(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        state_path = tmp_path / "state.json"
        rc = refresh.main(["--refresh-state-path", str(state_path)])
        captured = capsys.readouterr()
        assert rc == 0
        assert "DRY-RUN" in captured.out
        # Must not have created the state file.
        assert not state_path.exists()

    def test_execute_aborts_on_negative_confirm(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        state_path = tmp_path / "state.json"

        with patch.object(sys, "stdin", io.StringIO("n\n")):
            rc = refresh.main(["--execute", "--refresh-state-path", str(state_path)])

        captured = capsys.readouterr()
        assert rc == 0
        assert "Aborted." in captured.out
        # State must remain unwritten on abort.
        assert not state_path.exists()

    def test_execute_not_due_exits_clean_without_subprocess(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Seed a recent state so is_due is False.
        state_path = tmp_path / "state.json"
        now = datetime.now(UTC)
        write_state(
            RefreshState(
                last_refresh_at=now - timedelta(days=30),
                last_refresh_run_id="run_wave5_v1",
            ),
            state_path,
        )
        # Patch _run_pipeline to ensure it is NOT called.
        with patch.object(refresh, "_run_pipeline", side_effect=AssertionError("should not run")):
            rc = refresh.main(["--execute", "--refresh-state-path", str(state_path)])

        captured = capsys.readouterr()
        assert rc == 0
        assert "NOT DUE" in captured.out
        # State preserved (still the 30-day-old timestamp).
        round_trip = read_state(state_path)
        assert round_trip.last_refresh_run_id == "run_wave5_v1"

    def test_pipeline_failure_does_not_advance_state(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        state_path = tmp_path / "state.json"  # never-state

        with (
            patch.object(refresh, "_confirm", return_value=True),
            patch.object(refresh, "_run_pipeline", return_value=2),
        ):
            rc = refresh.main(["--execute", "--refresh-state-path", str(state_path)])

        assert rc == 2
        # No state file written when pipeline fails.
        assert not state_path.exists()

    def test_pipeline_success_writes_state(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state.json"

        with (
            patch.object(refresh, "_confirm", return_value=True),
            patch.object(refresh, "_run_pipeline", return_value=0),
        ):
            rc = refresh.main(["--execute", "--refresh-state-path", str(state_path)])

        assert rc == 0
        assert state_path.exists()
        result = read_state(state_path)
        assert result.last_refresh_at is not None
        assert result.last_refresh_run_id == "run_wave5_v1"
