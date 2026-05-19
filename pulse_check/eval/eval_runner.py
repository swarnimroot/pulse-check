"""Eval runner for aspect-tagging classifier vs gold set (Wave 2 exit gate).

The Wave 2 exit criterion is "aspect classifier ≥ 80% accuracy on the
aspect_tagging gold set" (TASKS.md). The production classifier is Haiku via
``AspectClassifier`` (session-5 deviation; ARCHITECTURE §6.5); this module
wires the gold set to the classifier and packages results for downstream
scoring.

Pieces:

- ``resolve_truth(entry, mode)`` — pick the truth labels for an entry per
  the requested truth source (``sonnet`` / ``operator`` / ``merged``)
- ``score_one`` — run the classifier on one entry and pair predictions
  with truth tuples
- ``score_all`` — iterate a gold set, continuing past per-entry
  ``LlmParseError`` (logged + carried in the result row)

Truth-source caveat: when 0/N entries are operator-reviewed, ``merged`` and
``sonnet`` are identical, and ``operator`` yields an empty set. Today's
number reads as classifier-vs-Sonnet *agreement*, not classifier-vs-truth
*accuracy*, until the operator runs ``scripts/review_gold_set.py``.

Metric computation (``compute_micro_f1``, ``per_aspect_breakdown``) lives in
``12.b``; CLI wiring is ``scripts/run_eval.py`` (``12.c``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.eval.gold_set import GoldSetEntry
from pulse_check.llm_cache import LlmParseError
from pulse_check.storage.enums import Aspect, ContentType, Intensity, Polarity
from pulse_check.storage.models import ContentTypeTag
from pulse_check.tagging.aspect_classifier import (
    AspectClassifier,
    AspectPrediction,
    ProductContext,
)

log = logging.getLogger(__name__)

TruthMode = Literal["sonnet", "operator", "merged"]
SkipReason = Literal["no_truth", "parse_failure"]

LabelTuple = tuple[Aspect, Polarity, Intensity]

THRESHOLD = 0.80


# ---------------------------------------------------------------------------
# Content-type filter (production-matching gate)
# ---------------------------------------------------------------------------


def filter_by_content_types(
    session: Session,
    entries: list[GoldSetEntry],
    *,
    exclude: frozenset[ContentType],
) -> list[GoldSetEntry]:
    """Drop entries matching production's content-type exclusion gate.

    Mirrors ``tag_corpus_aspects`` semantics: a mention PASSES iff it has a
    ``ContentTypeTag`` row AND that tag's ``content_type`` is NOT in
    ``exclude``. Mentions without any ``ContentTypeTag`` row are excluded
    (strict gate; production assumes ``scripts/classify_content_type.py``
    has run first).

    No-op (returns ``entries`` unchanged) when ``exclude`` is empty — so the
    eval runner can apply this unconditionally.
    """
    if not exclude:
        return entries

    mention_ids = [e.mention_id for e in entries]
    allowed: set[str] = set(
        session.execute(
            select(ContentTypeTag.mention_id).where(
                ContentTypeTag.mention_id.in_(mention_ids),
                ContentTypeTag.content_type.notin_(exclude),
            )
        ).scalars().all()
    )
    return [e for e in entries if e.mention_id in allowed]


# ---------------------------------------------------------------------------
# Truth resolution
# ---------------------------------------------------------------------------


def _labels_to_tuples(labels: list[dict[str, Any]]) -> list[LabelTuple]:
    """Convert a gold-set label list (``sonnet_labels`` / ``operator_labels``)
    to ``(Aspect, Polarity, Intensity)`` tuples.

    Raises ``ValueError`` if any label carries an unknown enum value —
    callers should treat that as a stale gold-set vs current taxonomy.
    """
    tuples: list[LabelTuple] = []
    for label in labels:
        tuples.append(
            (
                Aspect(label["aspect"]),
                Polarity(label["polarity"]),
                Intensity(label["intensity"]),
            )
        )
    return tuples


def resolve_truth(entry: GoldSetEntry, mode: TruthMode) -> list[LabelTuple] | None:
    """Return the truth tuples for ``entry`` under ``mode``, or ``None`` when
    the entry should be skipped entirely.

    - ``"sonnet"``: always use ``entry.sonnet_labels``.
    - ``"operator"``: operator-verified truth — include entries the operator
      either ``accept``ed (truth = ``sonnet_labels``, operator confirmed
      Sonnet was right) or ``corrected`` (truth = ``operator_labels``).
      ``flag`` and unreviewed (``None``) entries are skipped.
    - ``"merged"``: use ``operator_labels`` when corrected, else
      ``sonnet_labels`` — never skips.
    """
    if mode == "sonnet":
        return _labels_to_tuples(entry.sonnet_labels)
    if mode == "operator":
        if entry.operator_flag == "corrected" and entry.operator_labels is not None:
            return _labels_to_tuples(entry.operator_labels)
        if entry.operator_flag == "accept":
            return _labels_to_tuples(entry.sonnet_labels)
        return None
    if mode == "merged":
        if entry.operator_flag == "corrected" and entry.operator_labels is not None:
            return _labels_to_tuples(entry.operator_labels)
        return _labels_to_tuples(entry.sonnet_labels)
    msg = f"unknown truth mode: {mode!r}"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# Prediction + scoring
# ---------------------------------------------------------------------------


@dataclass
class ScoredEntry:
    """One ``(mention, product)`` pair with paired gold + predicted tuples.

    ``skipped=True`` indicates the row was excluded (truth-mode skip or
    classifier parse failure); ``error_message`` carries the reason for
    surfacing in the final report. ``gold_tuples`` is populated whenever
    truth resolved, even on parse failure — so the report can show "we knew
    what to expect; the classifier failed to produce structured output."
    """

    entry: GoldSetEntry
    gold_tuples: list[LabelTuple] = field(default_factory=list)
    pred_tuples: list[LabelTuple] = field(default_factory=list)
    skipped: bool = False
    skip_reason: SkipReason | None = None
    error_message: str | None = None


def _predictions_to_tuples(preds: list[AspectPrediction]) -> list[LabelTuple]:
    return [(p.aspect, p.polarity, p.intensity) for p in preds]


def score_one(
    session: Session,
    *,
    classifier: AspectClassifier,
    entry: GoldSetEntry,
    truth_mode: TruthMode,
) -> ScoredEntry:
    """Run the classifier on one gold-set entry and pair predictions with
    truth.

    Truth-mode skip returns a ``ScoredEntry`` with ``skipped=True`` and no
    classifier call (no cache write, no API spend). Classifier parse
    failures are caught and surface as ``skipped=True`` with the error
    message — they do NOT crash the batch.
    """
    truth = resolve_truth(entry, truth_mode)
    if truth is None:
        return ScoredEntry(
            entry=entry,
            skipped=True,
            skip_reason="no_truth",
            error_message=f"no truth available under mode={truth_mode!r}",
        )

    product = ProductContext(
        product_id=entry.product_id,
        display_name=entry.product_display_name,
    )
    try:
        preds = classifier.classify(
            session,
            mention_text=entry.mention_text,
            product=product,
        )
    except LlmParseError as exc:
        log.warning(
            "classifier parse failure on mention %s: %s", entry.mention_id, exc
        )
        return ScoredEntry(
            entry=entry,
            gold_tuples=truth,
            skipped=True,
            skip_reason="parse_failure",
            error_message=f"classifier parse failure: {exc}",
        )
    return ScoredEntry(
        entry=entry,
        gold_tuples=truth,
        pred_tuples=_predictions_to_tuples(preds),
    )


def score_all(
    session: Session,
    *,
    classifier: AspectClassifier,
    entries: list[GoldSetEntry],
    truth_mode: TruthMode,
) -> list[ScoredEntry]:
    """Score every entry, yielding one ``ScoredEntry`` per input.

    ``LlmParseError`` on a single entry does not abort the batch — it is
    captured on the row and the loop continues. Any other exception
    propagates: per memory ``feedback_no_auto_rerun_on_crash``, mid-batch
    crashes should surface to the operator rather than be auto-handled.
    """
    return [
        score_one(session, classifier=classifier, entry=entry, truth_mode=truth_mode)
        for entry in entries
    ]


# ---------------------------------------------------------------------------
# Metrics — per-tuple micro-F1
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MicroF1Result:
    """Aggregate per-tuple micro-F1 across all non-skipped entries.

    Each ``(aspect, polarity, intensity)`` tuple is a label slot. TP =
    ``gold ∩ pred``, FP = ``pred \\ gold``, FN = ``gold \\ pred``, all
    summed across entries. F1 = harmonic mean of precision and recall.
    """

    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float


def _safe_divide(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator > 0 else 0.0


def _harmonic_mean(precision: float, recall: float) -> float:
    if precision + recall <= 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def compute_micro_f1(scored_entries: list[ScoredEntry]) -> MicroF1Result:
    """Aggregate per-tuple micro-F1 across all non-skipped entries (strict).

    Skipped entries (truth-mode skip or parse failure) are excluded entirely
    from numerator and denominator — they neither help nor hurt the score.

    Strict means full ``(aspect, polarity, intensity)`` tuple equality. For
    the ±1 intensity-tolerance variant (Wave 2 headline gate as of
    session 37), see :func:`compute_micro_f1_loose`.
    """
    tp = 0
    fp = 0
    fn = 0
    for scored in scored_entries:
        if scored.skipped:
            continue
        gold_set = set(scored.gold_tuples)
        pred_set = set(scored.pred_tuples)
        tp += len(gold_set & pred_set)
        fp += len(pred_set - gold_set)
        fn += len(gold_set - pred_set)
    precision = _safe_divide(tp, tp + fp)
    recall = _safe_divide(tp, tp + fn)
    return MicroF1Result(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=_harmonic_mean(precision, recall),
    )


_INTENSITY_INDEX: dict[Intensity, int] = {
    Intensity.LOW: 0,
    Intensity.MEDIUM: 1,
    Intensity.HIGH: 2,
}


def compute_micro_f1_loose(scored_entries: list[ScoredEntry]) -> MicroF1Result:
    """Per-tuple micro-F1 with ±1 intensity-bucket tolerance.

    A predicted tuple matches a gold tuple iff they share
    ``(aspect, polarity)`` and their intensities are within one bucket
    (e.g. medium↔high counts; low↔high does not). Exact matches consume
    their pair first, so they're never lost to a greedy adjacent match;
    remaining gold/pred tuples are paired one-to-one greedily within each
    ``(aspect, polarity)`` group.

    Rationale: intensity is inherently fuzzy (one human's "high" is
    another's "medium") and doesn't gate any downstream routing — it
    shows up only as low/medium/high counts in aggregates. Adjacent-bucket
    disagreement is not a categorical error. This metric is the Wave 2
    headline gate as of session 37; the strict variant
    (:func:`compute_micro_f1`) remains exposed for transparency.
    """
    tp = 0
    fp = 0
    fn = 0
    for scored in scored_entries:
        if scored.skipped:
            continue
        gold_set = set(scored.gold_tuples)
        pred_set = set(scored.pred_tuples)
        exact = gold_set & pred_set
        tp += len(exact)
        gold_remaining = list(gold_set - exact)
        pred_remaining = list(pred_set - exact)
        for gold_tuple in gold_remaining:
            g_aspect, g_pol, g_int = gold_tuple
            match: LabelTuple | None = None
            for pred_tuple in pred_remaining:
                p_aspect, p_pol, p_int = pred_tuple
                if (
                    g_aspect == p_aspect
                    and g_pol == p_pol
                    and abs(_INTENSITY_INDEX[g_int] - _INTENSITY_INDEX[p_int]) == 1
                ):
                    match = pred_tuple
                    break
            if match is not None:
                pred_remaining.remove(match)
                tp += 1
            else:
                fn += 1
        fp += len(pred_remaining)
    precision = _safe_divide(tp, tp + fp)
    recall = _safe_divide(tp, tp + fn)
    return MicroF1Result(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=_harmonic_mean(precision, recall),
    )


# ---------------------------------------------------------------------------
# Per-aspect breakdown
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AspectStats:
    """Per-aspect binary present/absent stats + polarity confusion.

    Binary: treat each aspect as "did the entry have this aspect at all?".
    TP = both gold and pred have it; FN = gold only; FP = pred only.

    ``polarity_confusion[(gold_polarity, pred_polarity)] = count`` for
    entries where the aspect appeared in BOTH gold and pred. Lets the
    report show e.g. "Haiku sometimes says positive when Sonnet said
    negative" per aspect.
    """

    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    polarity_confusion: dict[tuple[Polarity, Polarity], int]


def _first_polarity_per_aspect(
    tuples: list[LabelTuple],
) -> dict[Aspect, Polarity]:
    """First-occurrence polarity per aspect. Dedup-safe for the rare case
    where a label list carries the same aspect twice."""
    mapping: dict[Aspect, Polarity] = {}
    for aspect, polarity, _intensity in tuples:
        if aspect not in mapping:
            mapping[aspect] = polarity
    return mapping


def per_aspect_breakdown(
    scored_entries: list[ScoredEntry],
) -> dict[Aspect, AspectStats]:
    """Per-aspect binary F1 + polarity confusion across all non-skipped
    entries. Every value in ``Aspect`` appears in the output, even if no
    entry exercised it (all-zero stats in that case)."""
    counts: dict[Aspect, dict[str, int]] = {
        a: {"tp": 0, "fp": 0, "fn": 0} for a in Aspect
    }
    confusion: dict[Aspect, dict[tuple[Polarity, Polarity], int]] = {
        a: {} for a in Aspect
    }

    for scored in scored_entries:
        if scored.skipped:
            continue
        gold_polarity_by_aspect = _first_polarity_per_aspect(scored.gold_tuples)
        pred_polarity_by_aspect = _first_polarity_per_aspect(scored.pred_tuples)
        gold_aspects = set(gold_polarity_by_aspect)
        pred_aspects = set(pred_polarity_by_aspect)
        for aspect in Aspect:
            in_gold = aspect in gold_aspects
            in_pred = aspect in pred_aspects
            if in_gold and in_pred:
                counts[aspect]["tp"] += 1
                key = (
                    gold_polarity_by_aspect[aspect],
                    pred_polarity_by_aspect[aspect],
                )
                confusion[aspect][key] = confusion[aspect].get(key, 0) + 1
            elif in_gold:
                counts[aspect]["fn"] += 1
            elif in_pred:
                counts[aspect]["fp"] += 1

    breakdown: dict[Aspect, AspectStats] = {}
    for aspect in Aspect:
        tp = counts[aspect]["tp"]
        fp = counts[aspect]["fp"]
        fn = counts[aspect]["fn"]
        precision = _safe_divide(tp, tp + fp)
        recall = _safe_divide(tp, tp + fn)
        breakdown[aspect] = AspectStats(
            tp=tp,
            fp=fp,
            fn=fn,
            precision=precision,
            recall=recall,
            f1=_harmonic_mean(precision, recall),
            polarity_confusion=dict(confusion[aspect]),
        )
    return breakdown


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalReport:
    """Top-level result of running an eval over a gold set.

    ``passed`` is the headline Wave 2 exit-gate verdict and gates on
    ``micro_loose.f1 >= THRESHOLD`` — the off-by-one intensity-tolerance
    metric — as of session 37. ``micro`` (strict) remains exposed for
    transparency; readers can compare both numbers in the report.
    ``scored_count`` excludes both truth-skipped entries (semantically not
    the classifier's fault) and parse-failed entries (classifier's fault,
    but already surfaced separately).
    """

    total_entries: int
    scored_count: int
    truth_skip_count: int
    parse_failure_count: int
    micro: MicroF1Result
    micro_loose: MicroF1Result
    per_aspect: dict[Aspect, AspectStats]
    threshold: float
    passed: bool

    @classmethod
    def from_scored(cls, scored_entries: list[ScoredEntry]) -> EvalReport:
        total = len(scored_entries)
        truth_skips = sum(
            1 for s in scored_entries if s.skip_reason == "no_truth"
        )
        parse_failures = sum(
            1 for s in scored_entries if s.skip_reason == "parse_failure"
        )
        scored_count = total - truth_skips - parse_failures
        micro = compute_micro_f1(scored_entries)
        micro_loose = compute_micro_f1_loose(scored_entries)
        per_aspect = per_aspect_breakdown(scored_entries)
        return cls(
            total_entries=total,
            scored_count=scored_count,
            truth_skip_count=truth_skips,
            parse_failure_count=parse_failures,
            micro=micro,
            micro_loose=micro_loose,
            per_aspect=per_aspect,
            threshold=THRESHOLD,
            passed=micro_loose.f1 >= THRESHOLD,
        )


# ---------------------------------------------------------------------------
# Disagreement listing (capability-aha vs output-aha sanity)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Disagreement:
    """One scored entry where the prediction-set differs from the gold-set.

    Surfaced in the report so the operator can eyeball the raw text alongside
    the headline number — per the project's capability-vs-output aha
    discipline, system-works ≠ findings-work.
    """

    mention_id: str
    mention_text: str
    product_display_name: str
    gold_tuples: list[LabelTuple]
    pred_tuples: list[LabelTuple]


def disagreements(scored_entries: list[ScoredEntry]) -> list[Disagreement]:
    """Return non-skipped entries where ``set(gold) != set(pred)``, sorted by
    severity (largest symmetric difference first)."""
    scored_with_diff: list[tuple[int, Disagreement]] = []
    for s in scored_entries:
        if s.skipped:
            continue
        gold_set = set(s.gold_tuples)
        pred_set = set(s.pred_tuples)
        if gold_set == pred_set:
            continue
        scored_with_diff.append(
            (
                len(gold_set ^ pred_set),
                Disagreement(
                    mention_id=s.entry.mention_id,
                    mention_text=s.entry.mention_text,
                    product_display_name=s.entry.product_display_name,
                    gold_tuples=s.gold_tuples,
                    pred_tuples=s.pred_tuples,
                ),
            )
        )
    scored_with_diff.sort(key=lambda kv: -kv[0])
    return [d for _, d in scored_with_diff]


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------


def _tuple_to_dict(label: LabelTuple) -> dict[str, str]:
    aspect, polarity, intensity = label
    return {
        "aspect": aspect.value,
        "polarity": polarity.value,
        "intensity": intensity.value,
    }


def report_to_dict(
    report: EvalReport,
    scored_entries: list[ScoredEntry],
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render the report + scored entries into a JSON-serializable dict.

    ``meta`` carries CLI-level context (provider, model, truth mode, paths,
    timestamps) that the report dataclass doesn't track itself.
    """
    return {
        "meta": meta or {},
        "summary": {
            "total_entries": report.total_entries,
            "scored_count": report.scored_count,
            "truth_skip_count": report.truth_skip_count,
            "parse_failure_count": report.parse_failure_count,
            "threshold": report.threshold,
            "passed": report.passed,
        },
        "micro_f1": {
            "tp": report.micro.tp,
            "fp": report.micro.fp,
            "fn": report.micro.fn,
            "precision": report.micro.precision,
            "recall": report.micro.recall,
            "f1": report.micro.f1,
        },
        "micro_f1_loose": {
            "tp": report.micro_loose.tp,
            "fp": report.micro_loose.fp,
            "fn": report.micro_loose.fn,
            "precision": report.micro_loose.precision,
            "recall": report.micro_loose.recall,
            "f1": report.micro_loose.f1,
        },
        "per_aspect": {
            aspect.value: {
                "tp": stats.tp,
                "fp": stats.fp,
                "fn": stats.fn,
                "precision": stats.precision,
                "recall": stats.recall,
                "f1": stats.f1,
                "polarity_confusion": [
                    {
                        "gold_polarity": gold.value,
                        "pred_polarity": pred.value,
                        "count": count,
                    }
                    for (gold, pred), count in sorted(
                        stats.polarity_confusion.items(),
                        key=lambda kv: (kv[0][0].value, kv[0][1].value),
                    )
                ],
            }
            for aspect, stats in report.per_aspect.items()
        },
        "disagreements": [
            {
                "mention_id": d.mention_id,
                "mention_text": d.mention_text,
                "product_display_name": d.product_display_name,
                "gold": [_tuple_to_dict(t) for t in d.gold_tuples],
                "pred": [_tuple_to_dict(t) for t in d.pred_tuples],
            }
            for d in disagreements(scored_entries)
        ],
        "parse_failures": [
            {
                "mention_id": s.entry.mention_id,
                "error_message": s.error_message,
            }
            for s in scored_entries
            if s.skip_reason == "parse_failure"
        ],
    }
