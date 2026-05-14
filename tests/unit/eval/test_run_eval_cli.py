"""Unit tests for ``scripts/run_eval.py`` CLI helpers.

Coverage priorities:
- ``_parse_args`` defaults + custom flag values
- ``_truth_caveat`` fires/suppresses correctly across the (mode, corrected) cube
- ``_format_summary`` banner reflects PASS/FAIL and embeds the right counts

``main()`` integration is not exercised here — it's thin glue over already-tested
modules (``read_jsonl``, ``score_all``, ``EvalReport.from_scored``,
``report_to_dict``).
"""

from __future__ import annotations

from pathlib import Path

from pulse_check.eval.eval_runner import EvalReport, ScoredEntry
from pulse_check.eval.gold_set import GoldSetEntry
from pulse_check.storage.enums import Aspect, Intensity, Polarity, SourceType
from scripts.run_eval import _format_summary, _parse_args, _truth_caveat

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry() -> GoldSetEntry:
    return GoldSetEntry(
        mention_id="m1",
        product_id="p1",
        mention_text="example",
        source_type=SourceType.REDDIT_POST,
        product_display_name="Alienware 16 Aurora",
        sonnet_labels=[],
    )


def _scored_match() -> ScoredEntry:
    """A scored entry where gold == pred (one tuple match each side)."""
    return ScoredEntry(
        entry=_entry(),
        gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
        pred_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
    )


def _scored_miss() -> ScoredEntry:
    """A scored entry where gold and pred are disjoint."""
    return ScoredEntry(
        entry=_entry(),
        gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
        pred_tuples=[(Aspect.BATTERY, Polarity.POSITIVE, Intensity.LOW)],
    )


# ---------------------------------------------------------------------------
# _parse_args
# ---------------------------------------------------------------------------


class TestParseArgs:
    def test_defaults(self) -> None:
        args = _parse_args([])
        assert args.gold_set == Path("data/gold_sets/aspect_tagging_v2.jsonl")
        assert args.truth == "merged"
        assert args.provider == "haiku"
        assert args.output is None

    def test_custom_provider_and_truth(self) -> None:
        args = _parse_args(["--provider", "qwen", "--truth", "operator"])
        assert args.provider == "qwen"
        assert args.truth == "operator"

    def test_custom_paths(self) -> None:
        args = _parse_args(
            [
                "--gold-set",
                "data/other/gold.jsonl",
                "--output",
                "data/eval_results/out.json",
            ]
        )
        assert args.gold_set == Path("data/other/gold.jsonl")
        assert args.output == Path("data/eval_results/out.json")


# ---------------------------------------------------------------------------
# _truth_caveat
# ---------------------------------------------------------------------------


class TestTruthCaveat:
    def test_operator_mode_never_caveats(self) -> None:
        assert (
            _truth_caveat(
                "operator",
                provider="haiku",
                operator_corrected_count=0,
                total_entries=28,
            )
            is None
        )
        assert (
            _truth_caveat(
                "operator",
                provider="haiku",
                operator_corrected_count=28,
                total_entries=28,
            )
            is None
        )

    def test_sonnet_mode_always_caveats(self) -> None:
        caveat = _truth_caveat(
            "sonnet",
            provider="haiku",
            operator_corrected_count=0,
            total_entries=28,
        )
        assert caveat is not None
        assert any("Sonnet labels as oracle" in line for line in caveat)

    def test_merged_zero_corrected_caveats_strongly(self) -> None:
        caveat = _truth_caveat(
            "merged",
            provider="haiku",
            operator_corrected_count=0,
            total_entries=28,
        )
        assert caveat is not None
        assert any(
            "0 entries are operator-corrected" in line for line in caveat
        )
        assert any("haiku-vs-Sonnet AGREEMENT" in line for line in caveat)

    def test_merged_partial_corrected_caveats_with_count(self) -> None:
        caveat = _truth_caveat(
            "merged",
            provider="haiku",
            operator_corrected_count=10,
            total_entries=28,
        )
        assert caveat is not None
        assert any("10/28 operator-corrected" in line for line in caveat)

    def test_merged_fully_corrected_does_not_caveat(self) -> None:
        assert (
            _truth_caveat(
                "merged",
                provider="haiku",
                operator_corrected_count=28,
                total_entries=28,
            )
            is None
        )


# ---------------------------------------------------------------------------
# _format_summary
# ---------------------------------------------------------------------------


def _call_summary(
    report: EvalReport,
    *,
    truth_mode: str = "merged",
    operator_touched_count: int = 0,
    operator_corrected_count: int = 0,
    total_entries: int = 1,
    pre_filter_count: int | None = None,
    exclude_content_types: list[str] | None = None,
    output_path: Path = Path("data/eval_results/x.json"),
) -> str:
    return _format_summary(
        report,
        provider="haiku",
        model="claude-haiku-4-5",
        truth_mode=truth_mode,
        gold_set_path=Path("data/gold_sets/x.jsonl"),
        operator_touched_count=operator_touched_count,
        operator_corrected_count=operator_corrected_count,
        total_entries=total_entries,
        pre_filter_count=pre_filter_count
        if pre_filter_count is not None
        else total_entries,
        exclude_content_types=exclude_content_types or [],
        output_path=output_path,
    )


class TestFormatSummary:
    def test_pass_banner_present_on_perfect_match(self) -> None:
        report = EvalReport.from_scored([_scored_match()])
        summary = _call_summary(report)
        assert "Result:       PASS" in summary
        assert "Micro F1:     1.0000" in summary

    def test_fail_banner_present_on_complete_miss(self) -> None:
        report = EvalReport.from_scored([_scored_miss()])
        summary = _call_summary(report)
        assert "Result:       FAIL" in summary
        assert "Micro F1:     0.0000" in summary

    def test_caveat_appears_in_merged_zero_corrected(self) -> None:
        report = EvalReport.from_scored([_scored_match()])
        summary = _call_summary(report, total_entries=28)
        assert "0 entries are operator-corrected" in summary
        assert "scripts/review_gold_set.py" in summary

    def test_caveat_suppressed_in_operator_mode(self) -> None:
        report = EvalReport.from_scored([_scored_match()])
        summary = _call_summary(
            report,
            truth_mode="operator",
            operator_touched_count=5,
            operator_corrected_count=5,
            total_entries=28,
        )
        assert "Truth-source caveat" not in summary

    def test_summary_includes_output_path(self) -> None:
        report = EvalReport.from_scored([_scored_match()])
        output = Path("data/eval_results/20260511_123000_aspect_tagging.json")
        summary = _call_summary(report, total_entries=28, output_path=output)
        assert str(output) in summary

    def test_filter_line_appears_when_exclude_set_non_empty(self) -> None:
        report = EvalReport.from_scored([_scored_match()])
        summary = _call_summary(
            report,
            total_entries=8,
            pre_filter_count=28,
            exclude_content_types=["deal"],
        )
        assert "Filter:" in summary
        assert "exclude=deal" in summary
        assert "->" in summary
        assert "8 entries after content-type filter" in summary

    def test_filter_line_absent_when_exclude_set_empty(self) -> None:
        report = EvalReport.from_scored([_scored_match()])
        summary = _call_summary(report, total_entries=28, exclude_content_types=[])
        assert "Filter:" not in summary


class TestParseArgsContentTypeFlag:
    def test_default_is_empty_list(self) -> None:
        args = _parse_args([])
        assert args.exclude_content_types == []

    def test_single_exclude(self) -> None:
        args = _parse_args(["--exclude-content-types", "deal"])
        assert args.exclude_content_types == ["deal"]

    def test_multi_exclude(self) -> None:
        args = _parse_args(["--exclude-content-types", "deal", "other"])
        assert sorted(args.exclude_content_types) == ["deal", "other"]
