"""Unit tests for ``pulse_check.eval.eval_runner`` — truth resolution + scoring.

Coverage priorities:
- ``_labels_to_tuples`` round-trips valid labels and raises on unknown enum values
- ``resolve_truth`` honors all three modes (sonnet / operator / merged) incl.
  operator-mode-skips-uncorrected and merged-falls-back-to-sonnet
- ``score_one`` happy path pairs gold + pred; truth-skip avoids classifier call;
  ``LlmParseError`` surfaces as ``skipped=True`` without crashing
- ``score_all`` continues past per-entry parse failures
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from pulse_check.eval.eval_runner import (
    THRESHOLD,
    AspectStats,
    Disagreement,
    EvalReport,
    MicroF1Result,
    ScoredEntry,
    _labels_to_tuples,
    compute_micro_f1,
    compute_micro_f1_loose,
    disagreements,
    filter_by_content_types,
    per_aspect_breakdown,
    report_to_dict,
    resolve_truth,
    score_all,
    score_one,
)
from pulse_check.eval.gold_set import GoldSetEntry
from pulse_check.llm_cache import LlmParseError
from pulse_check.storage.enums import (
    Aspect,
    ContentType,
    Intensity,
    Polarity,
    SourceType,
)
from pulse_check.storage.models import ContentTypeTag, Mention
from pulse_check.tagging.aspect_classifier import (
    AspectClassifier,
    AspectPrediction,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    *,
    sonnet_labels: list[dict[str, Any]] | None = None,
    operator_flag: str | None = None,
    operator_labels: list[dict[str, Any]] | None = None,
) -> GoldSetEntry:
    if sonnet_labels is None:
        sonnet_labels = [
            {
                "aspect": "thermals",
                "polarity": "negative",
                "intensity": "high",
                "confidence": 0.9,
            }
        ]
    return GoldSetEntry(
        mention_id="m1",
        product_id="p1",
        mention_text="Temps hit 95C under load",
        source_type=SourceType.REDDIT_POST,
        product_display_name="Alienware 16 Aurora",
        sonnet_labels=sonnet_labels,
        operator_flag=operator_flag,  # type: ignore[arg-type]
        operator_labels=operator_labels,
    )


def _pred(
    aspect: Aspect, polarity: Polarity, intensity: Intensity
) -> AspectPrediction:
    return AspectPrediction(
        aspect=aspect, polarity=polarity, intensity=intensity, confidence=None
    )


# ---------------------------------------------------------------------------
# _labels_to_tuples
# ---------------------------------------------------------------------------


class TestLabelsToTuples:
    def test_valid_labels_round_trip_to_enum_tuples(self) -> None:
        labels = [
            {"aspect": "thermals", "polarity": "negative", "intensity": "high"},
            {"aspect": "performance", "polarity": "positive", "intensity": "medium"},
        ]
        assert _labels_to_tuples(labels) == [
            (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH),
            (Aspect.PERFORMANCE, Polarity.POSITIVE, Intensity.MEDIUM),
        ]

    def test_empty_list_returns_empty(self) -> None:
        assert _labels_to_tuples([]) == []

    def test_unknown_aspect_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            _labels_to_tuples(
                [
                    {
                        "aspect": "made_up_aspect",
                        "polarity": "neutral",
                        "intensity": "low",
                    }
                ]
            )


# ---------------------------------------------------------------------------
# resolve_truth
# ---------------------------------------------------------------------------


class TestResolveTruth:
    def test_sonnet_mode_always_uses_sonnet_labels(self) -> None:
        entry = _make_entry(
            sonnet_labels=[
                {"aspect": "thermals", "polarity": "negative", "intensity": "high"}
            ],
            operator_flag="corrected",
            operator_labels=[
                {"aspect": "battery", "polarity": "positive", "intensity": "low"}
            ],
        )
        assert resolve_truth(entry, "sonnet") == [
            (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)
        ]

    def test_operator_mode_uses_operator_labels_when_corrected(self) -> None:
        entry = _make_entry(
            operator_flag="corrected",
            operator_labels=[
                {"aspect": "battery", "polarity": "positive", "intensity": "low"}
            ],
        )
        assert resolve_truth(entry, "operator") == [
            (Aspect.BATTERY, Polarity.POSITIVE, Intensity.LOW)
        ]

    def test_operator_mode_returns_none_when_uncorrected(self) -> None:
        entry = _make_entry(operator_flag=None)
        assert resolve_truth(entry, "operator") is None

    def test_operator_mode_uses_sonnet_labels_when_flag_is_accept(self) -> None:
        # "accept" means operator verified Sonnet was right — sonnet_labels are
        # the operator-verified truth.
        entry = _make_entry(
            sonnet_labels=[
                {"aspect": "thermals", "polarity": "negative", "intensity": "high"}
            ],
            operator_flag="accept",
        )
        assert resolve_truth(entry, "operator") == [
            (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)
        ]

    def test_operator_mode_returns_none_when_flag_is_flag(self) -> None:
        # "flag" means operator is uncertain — exclude from scoring.
        entry = _make_entry(operator_flag="flag")
        assert resolve_truth(entry, "operator") is None

    def test_merged_mode_uses_operator_when_corrected(self) -> None:
        entry = _make_entry(
            operator_flag="corrected",
            operator_labels=[
                {"aspect": "display", "polarity": "neutral", "intensity": "medium"}
            ],
        )
        assert resolve_truth(entry, "merged") == [
            (Aspect.DISPLAY, Polarity.NEUTRAL, Intensity.MEDIUM)
        ]

    def test_merged_mode_falls_back_to_sonnet_when_uncorrected(self) -> None:
        entry = _make_entry(operator_flag=None)
        assert resolve_truth(entry, "merged") == [
            (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)
        ]

    def test_merged_mode_falls_back_to_sonnet_when_flag_is_accept(self) -> None:
        entry = _make_entry(operator_flag="accept")
        assert resolve_truth(entry, "merged") == [
            (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)
        ]

    def test_unknown_mode_raises_value_error(self) -> None:
        entry = _make_entry()
        with pytest.raises(ValueError):
            resolve_truth(entry, "bogus")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# score_one
# ---------------------------------------------------------------------------


class TestScoreOne:
    def test_happy_path_pairs_gold_and_pred_tuples(self) -> None:
        entry = _make_entry()
        classifier = MagicMock(spec=AspectClassifier)
        classifier.classify.return_value = [
            _pred(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH),
            _pred(Aspect.PERFORMANCE, Polarity.POSITIVE, Intensity.MEDIUM),
        ]
        session = MagicMock(spec=Session)

        scored = score_one(
            session, classifier=classifier, entry=entry, truth_mode="merged"
        )

        assert scored.skipped is False
        assert scored.error_message is None
        assert scored.gold_tuples == [
            (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)
        ]
        assert scored.pred_tuples == [
            (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH),
            (Aspect.PERFORMANCE, Polarity.POSITIVE, Intensity.MEDIUM),
        ]
        classifier.classify.assert_called_once()

    def test_no_truth_skips_without_calling_classifier(self) -> None:
        entry = _make_entry(operator_flag=None)
        classifier = MagicMock(spec=AspectClassifier)
        session = MagicMock(spec=Session)

        scored = score_one(
            session, classifier=classifier, entry=entry, truth_mode="operator"
        )

        assert scored.skipped is True
        assert scored.skip_reason == "no_truth"
        assert "no truth available" in (scored.error_message or "")
        classifier.classify.assert_not_called()

    def test_parse_error_skips_gracefully(self) -> None:
        entry = _make_entry()
        classifier = MagicMock(spec=AspectClassifier)
        classifier.classify.side_effect = LlmParseError(
            "model returned malformed JSON"
        )
        session = MagicMock(spec=Session)

        scored = score_one(
            session, classifier=classifier, entry=entry, truth_mode="merged"
        )

        assert scored.skipped is True
        assert scored.skip_reason == "parse_failure"
        assert "parse failure" in (scored.error_message or "")
        # gold still resolved — report can show "we knew what to expect"
        assert scored.gold_tuples == [
            (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)
        ]
        assert scored.pred_tuples == []


# ---------------------------------------------------------------------------
# score_all
# ---------------------------------------------------------------------------


class TestScoreAll:
    def test_returns_one_scored_entry_per_input(self) -> None:
        entries = [_make_entry(), _make_entry()]
        classifier = MagicMock(spec=AspectClassifier)
        classifier.classify.return_value = []
        session = MagicMock(spec=Session)

        results: list[ScoredEntry] = score_all(
            session, classifier=classifier, entries=entries, truth_mode="merged"
        )

        assert len(results) == 2
        assert classifier.classify.call_count == 2

    def test_continues_past_individual_parse_failures(self) -> None:
        entries = [_make_entry(), _make_entry()]
        classifier = MagicMock(spec=AspectClassifier)
        classifier.classify.side_effect = [
            LlmParseError("first failed"),
            [_pred(Aspect.DISPLAY, Polarity.POSITIVE, Intensity.LOW)],
        ]
        session = MagicMock(spec=Session)

        results = score_all(
            session, classifier=classifier, entries=entries, truth_mode="merged"
        )

        assert results[0].skipped is True
        assert results[0].skip_reason == "parse_failure"
        assert results[1].skipped is False
        assert results[1].pred_tuples == [
            (Aspect.DISPLAY, Polarity.POSITIVE, Intensity.LOW)
        ]


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------


def _scored(
    gold_tuples: list[tuple[Aspect, Polarity, Intensity]],
    pred_tuples: list[tuple[Aspect, Polarity, Intensity]],
    *,
    skipped: bool = False,
    skip_reason: str | None = None,
) -> ScoredEntry:
    return ScoredEntry(
        entry=_make_entry(),
        gold_tuples=gold_tuples,
        pred_tuples=pred_tuples,
        skipped=skipped,
        skip_reason=skip_reason,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# compute_micro_f1
# ---------------------------------------------------------------------------


class TestComputeMicroF1:
    def test_empty_scored_list_returns_zero_f1(self) -> None:
        result = compute_micro_f1([])
        assert result == MicroF1Result(
            tp=0, fp=0, fn=0, precision=0.0, recall=0.0, f1=0.0
        )

    def test_perfect_match_returns_f1_one(self) -> None:
        result = compute_micro_f1(
            [
                _scored(
                    gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                    pred_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                )
            ]
        )
        assert result.tp == 1
        assert result.fp == 0
        assert result.fn == 0
        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1 == 1.0

    def test_complete_miss_returns_f1_zero(self) -> None:
        result = compute_micro_f1(
            [
                _scored(
                    gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                    pred_tuples=[(Aspect.BATTERY, Polarity.POSITIVE, Intensity.LOW)],
                )
            ]
        )
        assert result.tp == 0
        assert result.fp == 1
        assert result.fn == 1
        assert result.f1 == 0.0

    def test_partial_overlap_computes_expected_micro_f1(self) -> None:
        # E1 gold {A1, A2} pred {A1} → TP=1, FN=1
        # E2 gold {A3} pred {A3, A4} → TP=1, FP=1
        # totals: TP=2, FP=1, FN=1
        # P = R = 2/3 ; F1 = 2/3
        entries = [
            _scored(
                gold_tuples=[
                    (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH),
                    (Aspect.BATTERY, Polarity.POSITIVE, Intensity.MEDIUM),
                ],
                pred_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
            ),
            _scored(
                gold_tuples=[(Aspect.DISPLAY, Polarity.NEUTRAL, Intensity.LOW)],
                pred_tuples=[
                    (Aspect.DISPLAY, Polarity.NEUTRAL, Intensity.LOW),
                    (Aspect.KEYBOARD, Polarity.POSITIVE, Intensity.MEDIUM),
                ],
            ),
        ]
        result = compute_micro_f1(entries)
        assert result.tp == 2
        assert result.fp == 1
        assert result.fn == 1
        assert result.precision == pytest.approx(2 / 3)
        assert result.recall == pytest.approx(2 / 3)
        assert result.f1 == pytest.approx(2 / 3)

    def test_skipped_entries_excluded_from_counts(self) -> None:
        # Truth-skip + parse-failure both excluded entirely
        result = compute_micro_f1(
            [
                _scored(
                    gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                    pred_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                ),
                _scored(
                    gold_tuples=[(Aspect.BATTERY, Polarity.POSITIVE, Intensity.LOW)],
                    pred_tuples=[],
                    skipped=True,
                    skip_reason="parse_failure",
                ),
            ]
        )
        # Only the un-skipped row counts — perfect match
        assert result.tp == 1
        assert result.fn == 0
        assert result.f1 == 1.0


# ---------------------------------------------------------------------------
# compute_micro_f1_loose (±1 intensity tolerance)
# ---------------------------------------------------------------------------


class TestComputeMicroF1Loose:
    def test_exact_match_still_counts(self) -> None:
        # Loose is a superset of strict — exact matches remain matches
        result = compute_micro_f1_loose(
            [
                _scored(
                    gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                    pred_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                )
            ]
        )
        assert result.tp == 1
        assert result.fp == 0
        assert result.fn == 0
        assert result.f1 == 1.0

    def test_adjacent_intensity_counts_as_match(self) -> None:
        # gold HIGH, pred MEDIUM — off-by-one bucket, same aspect + polarity
        result = compute_micro_f1_loose(
            [
                _scored(
                    gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                    pred_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.MEDIUM)],
                )
            ]
        )
        assert result.tp == 1
        assert result.fp == 0
        assert result.fn == 0
        assert result.f1 == 1.0

    def test_two_buckets_apart_does_not_match(self) -> None:
        # gold LOW, pred HIGH — 2 buckets apart, treated as miss
        result = compute_micro_f1_loose(
            [
                _scored(
                    gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.LOW)],
                    pred_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                )
            ]
        )
        assert result.tp == 0
        assert result.fp == 1
        assert result.fn == 1
        assert result.f1 == 0.0

    def test_polarity_mismatch_blocks_match_even_at_adjacent_intensity(self) -> None:
        # Same aspect, intensities adjacent, but polarity differs — no match
        result = compute_micro_f1_loose(
            [
                _scored(
                    gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                    pred_tuples=[(Aspect.THERMALS, Polarity.POSITIVE, Intensity.MEDIUM)],
                )
            ]
        )
        assert result.tp == 0
        assert result.fp == 1
        assert result.fn == 1

    def test_aspect_mismatch_blocks_match(self) -> None:
        # Different aspects can never match under loose either
        result = compute_micro_f1_loose(
            [
                _scored(
                    gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                    pred_tuples=[(Aspect.BATTERY, Polarity.NEGATIVE, Intensity.MEDIUM)],
                )
            ]
        )
        assert result.tp == 0
        assert result.fp == 1
        assert result.fn == 1

    def test_exact_match_consumed_before_adjacent(self) -> None:
        # gold = {(T,N,H), (T,N,M)}; pred = {(T,N,H)}.
        # Greedy must NOT consume (T,N,H) with adjacent (T,N,M) and leave
        # the exact (T,N,H) gold unmatched. Exact-first ordering gives
        # 1 TP, 1 FN; bad ordering would give 1 TP, 1 FN too here but
        # the assertion guards against regression on the ordering rule.
        result = compute_micro_f1_loose(
            [
                _scored(
                    gold_tuples=[
                        (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH),
                        (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.MEDIUM),
                    ],
                    pred_tuples=[
                        (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH),
                    ],
                )
            ]
        )
        assert result.tp == 1
        assert result.fp == 0
        assert result.fn == 1

    def test_one_pred_does_not_double_count_for_two_gold(self) -> None:
        # gold = {(T,N,L), (T,N,H)}; pred = {(T,N,M)} — medium is adjacent to
        # both, but a single pred can absorb at most one gold. 1 TP, 1 FN.
        result = compute_micro_f1_loose(
            [
                _scored(
                    gold_tuples=[
                        (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.LOW),
                        (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH),
                    ],
                    pred_tuples=[
                        (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.MEDIUM),
                    ],
                )
            ]
        )
        assert result.tp == 1
        assert result.fn == 1
        assert result.fp == 0

    def test_skipped_entries_excluded_from_loose_counts(self) -> None:
        result = compute_micro_f1_loose(
            [
                _scored(
                    gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                    pred_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                ),
                _scored(
                    gold_tuples=[(Aspect.BATTERY, Polarity.POSITIVE, Intensity.LOW)],
                    pred_tuples=[],
                    skipped=True,
                    skip_reason="parse_failure",
                ),
            ]
        )
        assert result.tp == 1
        assert result.fn == 0
        assert result.f1 == 1.0


# ---------------------------------------------------------------------------
# per_aspect_breakdown
# ---------------------------------------------------------------------------


class TestPerAspectBreakdown:
    def test_all_aspects_present_in_output_even_with_empty_input(self) -> None:
        result = per_aspect_breakdown([])
        assert set(result.keys()) == set(Aspect)
        for stats in result.values():
            assert stats.tp == 0
            assert stats.fp == 0
            assert stats.fn == 0
            assert stats.f1 == 0.0
            assert stats.polarity_confusion == {}

    def test_binary_aspect_counts_independent_of_polarity_intensity(self) -> None:
        # Gold has THERMALS-NEG-HIGH; pred has THERMALS-POS-HIGH
        # → aspect THERMALS counts as TP (present in both), regardless of disagreement
        entries = [
            _scored(
                gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                pred_tuples=[(Aspect.THERMALS, Polarity.POSITIVE, Intensity.HIGH)],
            )
        ]
        result = per_aspect_breakdown(entries)
        thermals = result[Aspect.THERMALS]
        assert thermals.tp == 1
        assert thermals.fp == 0
        assert thermals.fn == 0
        assert thermals.f1 == 1.0
        # But polarity confusion captures the disagreement
        assert thermals.polarity_confusion == {
            (Polarity.NEGATIVE, Polarity.POSITIVE): 1
        }

    def test_aspect_in_gold_only_counts_as_fn(self) -> None:
        entries = [
            _scored(
                gold_tuples=[(Aspect.BATTERY, Polarity.POSITIVE, Intensity.LOW)],
                pred_tuples=[],
            )
        ]
        result = per_aspect_breakdown(entries)
        assert result[Aspect.BATTERY].fn == 1
        assert result[Aspect.BATTERY].tp == 0

    def test_aspect_in_pred_only_counts_as_fp(self) -> None:
        entries = [
            _scored(
                gold_tuples=[],
                pred_tuples=[(Aspect.DISPLAY, Polarity.NEUTRAL, Intensity.MEDIUM)],
            )
        ]
        result = per_aspect_breakdown(entries)
        assert result[Aspect.DISPLAY].fp == 1
        assert result[Aspect.DISPLAY].tp == 0

    def test_polarity_confusion_aggregates_across_entries(self) -> None:
        entries = [
            _scored(
                gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                pred_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
            ),
            _scored(
                gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.MEDIUM)],
                pred_tuples=[(Aspect.THERMALS, Polarity.POSITIVE, Intensity.MEDIUM)],
            ),
        ]
        result = per_aspect_breakdown(entries)
        assert result[Aspect.THERMALS].polarity_confusion == {
            (Polarity.NEGATIVE, Polarity.NEGATIVE): 1,
            (Polarity.NEGATIVE, Polarity.POSITIVE): 1,
        }


# ---------------------------------------------------------------------------
# EvalReport
# ---------------------------------------------------------------------------


class TestEvalReport:
    def test_from_scored_aggregates_counts_correctly(self) -> None:
        entries = [
            _scored(
                gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                pred_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
            ),
            _scored(
                gold_tuples=[],
                pred_tuples=[],
                skipped=True,
                skip_reason="no_truth",
            ),
            _scored(
                gold_tuples=[],
                pred_tuples=[],
                skipped=True,
                skip_reason="parse_failure",
            ),
        ]
        report = EvalReport.from_scored(entries)
        assert report.total_entries == 3
        assert report.truth_skip_count == 1
        assert report.parse_failure_count == 1
        assert report.scored_count == 1
        assert report.threshold == THRESHOLD

    def test_passed_true_when_f1_meets_threshold(self) -> None:
        # One perfect match → f1=1.0 ≥ 0.80
        entries = [
            _scored(
                gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                pred_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
            )
        ]
        report = EvalReport.from_scored(entries)
        assert report.passed is True
        assert report.micro.f1 == 1.0

    def test_passed_false_when_f1_below_threshold(self) -> None:
        # Complete miss → f1=0.0 < 0.80
        entries = [
            _scored(
                gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                pred_tuples=[(Aspect.BATTERY, Polarity.POSITIVE, Intensity.LOW)],
            )
        ]
        report = EvalReport.from_scored(entries)
        assert report.passed is False
        assert report.micro.f1 == 0.0

    def test_per_aspect_dict_includes_all_aspects(self) -> None:
        report = EvalReport.from_scored([])
        assert set(report.per_aspect.keys()) == set(Aspect)
        for stats in report.per_aspect.values():
            assert isinstance(stats, AspectStats)

    def test_passed_gate_is_loose_not_strict(self) -> None:
        # gold HIGH, pred MEDIUM — strict f1 = 0.0, loose f1 = 1.0.
        # Gate is loose, so passed must be True even though strict misses.
        entries = [
            _scored(
                gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                pred_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.MEDIUM)],
            )
        ]
        report = EvalReport.from_scored(entries)
        assert report.micro.f1 == 0.0
        assert report.micro_loose.f1 == 1.0
        assert report.passed is True


# ---------------------------------------------------------------------------
# disagreements
# ---------------------------------------------------------------------------


class TestDisagreements:
    def test_empty_list_returns_empty(self) -> None:
        assert disagreements([]) == []

    def test_identical_sets_excluded(self) -> None:
        entries = [
            _scored(
                gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                pred_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
            )
        ]
        assert disagreements(entries) == []

    def test_skipped_entries_excluded(self) -> None:
        entries = [
            _scored(
                gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                pred_tuples=[(Aspect.BATTERY, Polarity.POSITIVE, Intensity.LOW)],
                skipped=True,
                skip_reason="parse_failure",
            )
        ]
        assert disagreements(entries) == []

    def test_differing_sets_included(self) -> None:
        entries = [
            _scored(
                gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                pred_tuples=[(Aspect.BATTERY, Polarity.POSITIVE, Intensity.LOW)],
            )
        ]
        result = disagreements(entries)
        assert len(result) == 1
        assert isinstance(result[0], Disagreement)
        assert result[0].mention_id == "m1"

    def test_sorted_by_symmetric_difference_size(self) -> None:
        # Small disagreement: 1 sym-diff
        small = _scored(
            gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
            pred_tuples=[
                (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH),
                (Aspect.BATTERY, Polarity.POSITIVE, Intensity.LOW),
            ],
        )
        # Large disagreement: 4 sym-diff
        large = _scored(
            gold_tuples=[
                (Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH),
                (Aspect.BATTERY, Polarity.POSITIVE, Intensity.LOW),
            ],
            pred_tuples=[
                (Aspect.DISPLAY, Polarity.NEUTRAL, Intensity.MEDIUM),
                (Aspect.KEYBOARD, Polarity.POSITIVE, Intensity.HIGH),
            ],
        )
        result = disagreements([small, large])
        assert len(result) == 2
        # Larger sym-diff comes first
        assert result[0].gold_tuples == large.gold_tuples
        assert result[1].gold_tuples == small.gold_tuples


# ---------------------------------------------------------------------------
# report_to_dict
# ---------------------------------------------------------------------------


class TestReportToDict:
    def test_round_trips_through_json(self) -> None:
        import json

        entries = [
            _scored(
                gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                pred_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
            )
        ]
        report = EvalReport.from_scored(entries)
        rendered = report_to_dict(report, entries, meta={"provider": "haiku"})
        # JSON-serializable end-to-end
        encoded = json.dumps(rendered)
        decoded = json.loads(encoded)
        assert decoded["meta"]["provider"] == "haiku"
        assert decoded["summary"]["passed"] is True
        assert decoded["micro_f1"]["f1"] == 1.0

    def test_includes_all_top_level_keys(self) -> None:
        report = EvalReport.from_scored([])
        rendered = report_to_dict(report, [], meta=None)
        assert set(rendered.keys()) == {
            "meta",
            "summary",
            "micro_f1",
            "micro_f1_loose",
            "per_aspect",
            "disagreements",
            "parse_failures",
        }
        assert rendered["meta"] == {}

    def test_micro_f1_loose_serialized_alongside_strict(self) -> None:
        # Adjacent intensity: strict 0.0, loose 1.0 — both must surface
        entries = [
            _scored(
                gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                pred_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.MEDIUM)],
            )
        ]
        report = EvalReport.from_scored(entries)
        rendered = report_to_dict(report, entries, meta=None)
        assert rendered["micro_f1"]["f1"] == 0.0
        assert rendered["micro_f1_loose"]["f1"] == 1.0
        assert rendered["summary"]["passed"] is True

    def test_per_aspect_keyed_by_enum_value_strings(self) -> None:
        report = EvalReport.from_scored([])
        rendered = report_to_dict(report, [], meta=None)
        # All keys are string aspect values, not enum instances
        for key in rendered["per_aspect"]:
            assert isinstance(key, str)
        assert "thermals" in rendered["per_aspect"]

    def test_polarity_confusion_serialized_as_list(self) -> None:
        entries = [
            _scored(
                gold_tuples=[(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH)],
                pred_tuples=[(Aspect.THERMALS, Polarity.POSITIVE, Intensity.HIGH)],
            )
        ]
        report = EvalReport.from_scored(entries)
        rendered = report_to_dict(report, entries, meta=None)
        confusion = rendered["per_aspect"]["thermals"]["polarity_confusion"]
        assert confusion == [
            {"gold_polarity": "negative", "pred_polarity": "positive", "count": 1}
        ]

    def test_parse_failures_surfaced_in_report(self) -> None:
        entry = _scored(
            gold_tuples=[],
            pred_tuples=[],
            skipped=True,
            skip_reason="parse_failure",
        )
        entry.error_message = "model returned malformed JSON"
        report = EvalReport.from_scored([entry])
        rendered = report_to_dict(report, [entry], meta=None)
        assert len(rendered["parse_failures"]) == 1
        assert rendered["parse_failures"][0]["mention_id"] == "m1"
        assert "malformed" in rendered["parse_failures"][0]["error_message"]


# ---------------------------------------------------------------------------
# filter_by_content_types
# ---------------------------------------------------------------------------


def _seed_mention_with_content_type(
    session: Session,
    *,
    mention_id: str,
    content_type: ContentType | None,
) -> None:
    """Seed a Mention row (FK target) and optionally a ContentTypeTag."""
    session.add(
        Mention(
            mention_id=mention_id,
            source_type=SourceType.REDDIT_POST,
            source_url=f"https://example.com/{mention_id}",
            raw_text="text",
            metadata_={},
        )
    )
    if content_type is not None:
        session.add(
            ContentTypeTag(
                mention_id=mention_id,
                content_type=content_type,
                prompt_version="v1",
                model="claude-haiku-4-5",
                temperature=0.0,
            )
        )
    session.flush()


def _gold_entry(mention_id: str) -> GoldSetEntry:
    return GoldSetEntry(
        mention_id=mention_id,
        product_id="p1",
        mention_text="text",
        source_type=SourceType.REDDIT_POST,
        product_display_name="Alienware 16 Aurora",
        sonnet_labels=[],
    )


class TestFilterByContentTypes:
    def test_empty_exclude_returns_entries_unchanged(self, session: Session) -> None:
        entries = [_gold_entry("m1"), _gold_entry("m2")]
        result = filter_by_content_types(session, entries, exclude=frozenset())
        assert result == entries

    def test_excluded_type_dropped(self, session: Session) -> None:
        _seed_mention_with_content_type(
            session, mention_id="m1", content_type=ContentType.DEAL
        )
        result = filter_by_content_types(
            session, [_gold_entry("m1")], exclude=frozenset({ContentType.DEAL})
        )
        assert result == []

    def test_non_excluded_type_kept(self, session: Session) -> None:
        _seed_mention_with_content_type(
            session, mention_id="m1", content_type=ContentType.REVIEW
        )
        result = filter_by_content_types(
            session, [_gold_entry("m1")], exclude=frozenset({ContentType.DEAL})
        )
        assert len(result) == 1
        assert result[0].mention_id == "m1"

    def test_no_content_type_tag_excluded_strict_gate(self, session: Session) -> None:
        # Seed mention but NO ContentTypeTag — production strict gate excludes
        _seed_mention_with_content_type(session, mention_id="m1", content_type=None)
        result = filter_by_content_types(
            session, [_gold_entry("m1")], exclude=frozenset({ContentType.DEAL})
        )
        assert result == []

    def test_mixed_corpus_filters_correctly(self, session: Session) -> None:
        _seed_mention_with_content_type(
            session, mention_id="m_deal", content_type=ContentType.DEAL
        )
        _seed_mention_with_content_type(
            session, mention_id="m_review", content_type=ContentType.REVIEW
        )
        _seed_mention_with_content_type(
            session, mention_id="m_other", content_type=ContentType.OTHER
        )
        _seed_mention_with_content_type(
            session, mention_id="m_untagged", content_type=None
        )
        entries = [
            _gold_entry("m_deal"),
            _gold_entry("m_review"),
            _gold_entry("m_other"),
            _gold_entry("m_untagged"),
        ]
        # Exclude deal only — review + other survive, untagged dropped (strict)
        result = filter_by_content_types(
            session, entries, exclude=frozenset({ContentType.DEAL})
        )
        survivors = {e.mention_id for e in result}
        assert survivors == {"m_review", "m_other"}

    def test_multi_type_exclude(self, session: Session) -> None:
        _seed_mention_with_content_type(
            session, mention_id="m_deal", content_type=ContentType.DEAL
        )
        _seed_mention_with_content_type(
            session, mention_id="m_review", content_type=ContentType.REVIEW
        )
        _seed_mention_with_content_type(
            session, mention_id="m_other", content_type=ContentType.OTHER
        )
        entries = [
            _gold_entry("m_deal"),
            _gold_entry("m_review"),
            _gold_entry("m_other"),
        ]
        result = filter_by_content_types(
            session,
            entries,
            exclude=frozenset({ContentType.DEAL, ContentType.OTHER}),
        )
        survivors = {e.mention_id for e in result}
        assert survivors == {"m_review"}
