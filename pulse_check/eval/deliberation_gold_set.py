"""Deliberation + reason gold-set JSONL IO and orchestration — bite 13.c.3.

Two artifacts, one orchestrator. The orchestrator wires:

    candidates  →  Sonnet deliberation label  →  stratify_and_sample_threads
                                                          │
                                            ┌─────────────┘
                                            ▼
                          resolved threads only → reason-label every top-level
                                                  comment → select_reason_candidates

and writes two JSONL files matching the aspect-gold-set entry shape (with
``operator_flag`` / ``operator_notes`` / ``operator_labels`` empty for the
13.c.4 review CLI to populate).

File layout::

    data/gold_sets/deliberation_v1.jsonl
    data/gold_sets/reason_tagging_v1.jsonl

Idempotency: every LLM call flows through ``call_with_cache`` so a re-run on
the same corpus + seed is free after the first pass. A mid-run crash recovers
the same way — re-run, cached labels hit, only the remaining work calls
Sonnet. JSONL files are plain overwrites on every run; partial files are not
written incrementally (commit comes from the surrounding ``session_scope``).
"""

from __future__ import annotations

import json
import logging
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from sqlalchemy.orm import Session

from pulse_check.eval.deliberation_labeler import DeliberationLabeler
from pulse_check.eval.reason_labeler import ReasonLabeler
from pulse_check.eval.sampler import (
    DEFAULT_CANDIDATE_CAP,
    DEFAULT_FORCE_INCLUDE_PER_RULE,
    DEFAULT_FORCED_NEGATIVE_QUOTA,
    DEFAULT_REASON_TARGET_PER_THREAD,
    DEFAULT_TARGET_SIZE,
    CandidateThread,
    LabeledCandidate,
    LabeledComment,
    build_candidate_thread,
    fetch_top_level_comments,
    select_candidate_thread_ids,
    select_reason_candidates,
    stratify_and_sample_threads,
)
from pulse_check.storage.enums import Intensity, Polarity, ReasonBucket
from pulse_check.tagging.aspect_classifier import ProductContext
from pulse_check.tagging.deliberation_classifier import (
    DeliberationPrediction,
    DeliberationThread,
)
from pulse_check.tagging.reason_tagger import ReasonPrediction, ThreadContext

log = logging.getLogger(__name__)

OperatorFlag = Literal["accept", "flag", "corrected"]


# ---------------------------------------------------------------------------
# Entry dataclasses (JSONL row schema)
# ---------------------------------------------------------------------------


@dataclass
class DeliberationGoldEntry:
    """One deliberation gold-set row. Mirrors the aspect-gold operator-review fields."""

    thread_mention_id: str
    op_post_title: str
    op_post_text: str
    op_top_level_comments: list[str]
    other_top_level_comments: list[str]
    product_universe_ids: list[str]
    attributed_primary_product_ids: list[str]
    sonnet_prediction: dict[str, Any]
    force_include_rule: str | None
    operator_flag: OperatorFlag | None = None
    operator_notes: str | None = None
    operator_labels: dict[str, Any] | None = None


@dataclass
class ReasonGoldEntry:
    """One reason gold-set row (one comment under one resolved thread)."""

    mention_id: str
    comment_text: str
    thread_mention_id: str
    winning_product_id: str
    products_discussed_ids: list[str]
    op_post_text: str
    sonnet_reason_labels: list[dict[str, Any]]
    force_included_negative: bool
    operator_flag: OperatorFlag | None = None
    operator_notes: str | None = None
    operator_labels: list[dict[str, Any]] | None = None


@dataclass
class BuildStats:
    """Observability for the orchestrator. Cheap to print at exit."""

    candidates_selected: int = 0
    candidates_built: int = 0
    candidates_labeled: int = 0
    deliberation_entries_written: int = 0
    force_include_b: int = 0
    force_include_c: int = 0
    force_include_d: int = 0
    resolved_threads: int = 0
    comments_labeled: int = 0
    reason_entries_written: int = 0
    skipped_candidates_unbuildable: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _prediction_to_dict(pred: DeliberationPrediction) -> dict[str, Any]:
    return {
        "is_deliberation": pred.is_deliberation,
        "is_resolved": pred.is_resolved,
        "products_discussed": list(pred.products_discussed),
        "chosen_product_id": pred.chosen_product_id,
        "confidence": pred.confidence,
    }


def _dict_to_prediction(data: dict[str, Any]) -> DeliberationPrediction:
    return DeliberationPrediction(
        is_deliberation=bool(data["is_deliberation"]),
        is_resolved=bool(data["is_resolved"]),
        products_discussed=tuple(data.get("products_discussed") or []),
        chosen_product_id=data.get("chosen_product_id"),
        confidence=data.get("confidence"),
    )


def _reason_pred_to_dict(pred: ReasonPrediction) -> dict[str, Any]:
    return {
        "reason_bucket": pred.reason_bucket.value,
        "polarity": pred.polarity.value,
        "intensity": pred.intensity.value,
    }


def _dict_to_reason_pred(data: dict[str, Any]) -> ReasonPrediction:
    return ReasonPrediction(
        reason_bucket=ReasonBucket(data["reason_bucket"]),
        polarity=Polarity(data["polarity"]),
        intensity=Intensity(data["intensity"]),
    )


def _coerce_operator_flag(value: Any) -> OperatorFlag | None:
    if value is None:
        return None
    if value not in ("accept", "flag", "corrected"):
        msg = f"unknown operator_flag: {value!r}"
        raise ValueError(msg)
    return cast(OperatorFlag, value)


def _deliberation_entry_to_dict(entry: DeliberationGoldEntry) -> dict[str, Any]:
    return {
        "thread_mention_id": entry.thread_mention_id,
        "op_post_title": entry.op_post_title,
        "op_post_text": entry.op_post_text,
        "op_top_level_comments": list(entry.op_top_level_comments),
        "other_top_level_comments": list(entry.other_top_level_comments),
        "product_universe_ids": list(entry.product_universe_ids),
        "attributed_primary_product_ids": list(entry.attributed_primary_product_ids),
        "sonnet_prediction": entry.sonnet_prediction,
        "force_include_rule": entry.force_include_rule,
        "operator_flag": entry.operator_flag,
        "operator_notes": entry.operator_notes,
        "operator_labels": entry.operator_labels,
    }


def _dict_to_deliberation_entry(data: dict[str, Any]) -> DeliberationGoldEntry:
    return DeliberationGoldEntry(
        thread_mention_id=data["thread_mention_id"],
        op_post_title=data.get("op_post_title", ""),
        op_post_text=data["op_post_text"],
        op_top_level_comments=list(data.get("op_top_level_comments") or []),
        other_top_level_comments=list(data.get("other_top_level_comments") or []),
        product_universe_ids=list(data.get("product_universe_ids") or []),
        attributed_primary_product_ids=list(data.get("attributed_primary_product_ids") or []),
        sonnet_prediction=dict(data.get("sonnet_prediction") or {}),
        force_include_rule=data.get("force_include_rule"),
        operator_flag=_coerce_operator_flag(data.get("operator_flag")),
        operator_notes=data.get("operator_notes"),
        operator_labels=data.get("operator_labels"),
    )


def _reason_entry_to_dict(entry: ReasonGoldEntry) -> dict[str, Any]:
    return {
        "mention_id": entry.mention_id,
        "comment_text": entry.comment_text,
        "thread_mention_id": entry.thread_mention_id,
        "winning_product_id": entry.winning_product_id,
        "products_discussed_ids": list(entry.products_discussed_ids),
        "op_post_text": entry.op_post_text,
        "sonnet_reason_labels": entry.sonnet_reason_labels,
        "force_included_negative": entry.force_included_negative,
        "operator_flag": entry.operator_flag,
        "operator_notes": entry.operator_notes,
        "operator_labels": entry.operator_labels,
    }


def _dict_to_reason_entry(data: dict[str, Any]) -> ReasonGoldEntry:
    return ReasonGoldEntry(
        mention_id=data["mention_id"],
        comment_text=data["comment_text"],
        thread_mention_id=data["thread_mention_id"],
        winning_product_id=data["winning_product_id"],
        products_discussed_ids=list(data.get("products_discussed_ids") or []),
        op_post_text=data.get("op_post_text", ""),
        sonnet_reason_labels=list(data.get("sonnet_reason_labels") or []),
        force_included_negative=bool(data.get("force_included_negative", False)),
        operator_flag=_coerce_operator_flag(data.get("operator_flag")),
        operator_notes=data.get("operator_notes"),
        operator_labels=data.get("operator_labels"),
    )


# ---------------------------------------------------------------------------
# JSONL IO
# ---------------------------------------------------------------------------


def write_deliberation_gold_jsonl(entries: Iterable[DeliberationGoldEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(_deliberation_entry_to_dict(entry), ensure_ascii=False) + "\n")


def read_deliberation_gold_jsonl(path: Path) -> list[DeliberationGoldEntry]:
    entries: list[DeliberationGoldEntry] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            entries.append(_dict_to_deliberation_entry(json.loads(line)))
    return entries


def write_reason_gold_jsonl(entries: Iterable[ReasonGoldEntry], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(_reason_entry_to_dict(entry), ensure_ascii=False) + "\n")


def read_reason_gold_jsonl(path: Path) -> list[ReasonGoldEntry]:
    entries: list[ReasonGoldEntry] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            entries.append(_dict_to_reason_entry(json.loads(line)))
    return entries


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _candidate_to_deliberation_thread(candidate: CandidateThread) -> DeliberationThread:
    return DeliberationThread(
        thread_id=candidate.thread_mention_id,
        op_post_text=candidate.op_post_text,
        op_edit_text=None,
        op_top_level_comments=candidate.op_top_level_comments,
        other_top_level_comments=candidate.other_top_level_comments,
    )


def _build_thread_context(
    *,
    op_post_text: str,
    winning_product_id: str,
    products_by_id: dict[str, ProductContext],
    products_discussed_ids: Sequence[str],
) -> ThreadContext:
    discussed = tuple(
        products_by_id[pid] for pid in products_discussed_ids if pid in products_by_id
    )
    winning = products_by_id[winning_product_id]
    return ThreadContext(
        winning_product_id=winning_product_id,
        winning_product_display_name=winning.display_name,
        op_post_text=op_post_text,
        products_discussed=discussed,
    )


def build_gold_sets(
    session: Session,
    *,
    deliberation_labeler: DeliberationLabeler,
    reason_labeler: ReasonLabeler,
    products: Sequence[ProductContext],
    rng: random.Random,
    deliberation_output_path: Path,
    reason_output_path: Path,
    candidate_cap: int = DEFAULT_CANDIDATE_CAP,
    target_size: int = DEFAULT_TARGET_SIZE,
    force_include_per_rule: int = DEFAULT_FORCE_INCLUDE_PER_RULE,
    reason_target_per_thread: int = DEFAULT_REASON_TARGET_PER_THREAD,
    forced_negative_quota: int = DEFAULT_FORCED_NEGATIVE_QUOTA,
) -> BuildStats:
    """Run the full deliberation + reason gold-set build.

    Stages:
        1. Heuristic selection → candidate_ids (capped at ``candidate_cap``).
        2. Reconstruct each candidate thread (skip + log any that fail to build).
        3. Sonnet deliberation labeling, full product universe per ARCH §6.1.
        4. ``stratify_and_sample_threads`` → final gold-set selection.
        5. Write deliberation JSONL.
        6. For each *resolved* thread in the selection: fetch top-level comments,
           Sonnet-reason-label every one, then ``select_reason_candidates`` to
           pick gold-set comments. NEG-toward-winner force-include is flagged
           on the entry.
        7. Write reason JSONL.

    All LLM calls flow through ``call_with_cache`` — a re-run with the same
    corpus + seed + cap + product universe is free.
    """
    products_tuple = tuple(products)
    products_by_id: dict[str, ProductContext] = {p.product_id: p for p in products_tuple}
    stats = BuildStats()

    candidate_ids = select_candidate_thread_ids(
        session, rng=rng, candidate_cap=candidate_cap
    )
    stats.candidates_selected = len(candidate_ids)
    log.info("candidates selected by heuristic: %d", len(candidate_ids))

    candidates: list[CandidateThread] = []
    for cid in candidate_ids:
        c = build_candidate_thread(session, thread_mention_id=cid)
        if c is None:
            stats.skipped_candidates_unbuildable.append(cid)
            log.warning("candidate %s unbuildable (no row / wrong source_type) — skipping", cid)
            continue
        candidates.append(c)
    stats.candidates_built = len(candidates)

    labeled: list[LabeledCandidate] = []
    for candidate in candidates:
        thread = _candidate_to_deliberation_thread(candidate)
        prediction = deliberation_labeler.label(session, thread=thread, products=products_tuple)
        labeled.append(LabeledCandidate(candidate=candidate, prediction=prediction))
    stats.candidates_labeled = len(labeled)
    log.info("deliberation-labeled %d threads", len(labeled))

    selection = stratify_and_sample_threads(
        labeled,
        rng=rng,
        target_size=target_size,
        force_include_per_rule=force_include_per_rule,
    )
    log.info(
        "stratified selection: %d threads (%d force-included)",
        len(selection.selected),
        len(selection.force_include_rules_applied),
    )

    deliberation_entries: list[DeliberationGoldEntry] = []
    for lc in selection.selected:
        rule = selection.force_include_rules_applied.get(lc.candidate.thread_mention_id)
        if rule == "B":
            stats.force_include_b += 1
        elif rule == "C":
            stats.force_include_c += 1
        elif rule == "D":
            stats.force_include_d += 1
        deliberation_entries.append(
            DeliberationGoldEntry(
                thread_mention_id=lc.candidate.thread_mention_id,
                op_post_title=lc.candidate.op_post_title,
                op_post_text=lc.candidate.op_post_text,
                op_top_level_comments=list(lc.candidate.op_top_level_comments),
                other_top_level_comments=list(lc.candidate.other_top_level_comments),
                product_universe_ids=sorted(p.product_id for p in products_tuple),
                attributed_primary_product_ids=list(lc.candidate.attributed_primary_product_ids),
                sonnet_prediction=_prediction_to_dict(lc.prediction),
                force_include_rule=rule,
            )
        )

    write_deliberation_gold_jsonl(deliberation_entries, deliberation_output_path)
    stats.deliberation_entries_written = len(deliberation_entries)
    log.info("wrote %s (%d entries)", deliberation_output_path, len(deliberation_entries))

    reason_entries: list[ReasonGoldEntry] = []
    for lc in selection.selected:
        pred = lc.prediction
        if not pred.is_resolved or pred.chosen_product_id is None:
            continue
        if pred.chosen_product_id not in products_by_id:
            log.warning(
                "resolved thread %s names chosen_product_id %r outside the product universe — "
                "skipping reason labeling",
                lc.candidate.thread_mention_id,
                pred.chosen_product_id,
            )
            continue
        stats.resolved_threads += 1
        context = _build_thread_context(
            op_post_text=lc.candidate.op_post_text,
            winning_product_id=pred.chosen_product_id,
            products_by_id=products_by_id,
            products_discussed_ids=pred.products_discussed,
        )
        comments = fetch_top_level_comments(
            session, thread_mention_id=lc.candidate.thread_mention_id
        )
        labeled_comments: list[LabeledComment] = []
        for comment in comments:
            reason_preds = reason_labeler.label(
                session, comment_text=comment.raw_text, context=context
            )
            stats.comments_labeled += 1
            labeled_comments.append(
                LabeledComment(
                    mention_id=comment.mention_id,
                    comment_text=comment.raw_text,
                    thread_mention_id=lc.candidate.thread_mention_id,
                    winning_product_id=pred.chosen_product_id,
                    reason_predictions=tuple(reason_preds),
                )
            )

        reason_sel = select_reason_candidates(
            labeled_comments=labeled_comments,
            rng=rng,
            target_per_thread=reason_target_per_thread,
            forced_negative_quota=forced_negative_quota,
        )
        forced_set = set(reason_sel.force_included_mention_ids)
        for picked in reason_sel.selected:
            reason_entries.append(
                ReasonGoldEntry(
                    mention_id=picked.mention_id,
                    comment_text=picked.comment_text,
                    thread_mention_id=picked.thread_mention_id,
                    winning_product_id=picked.winning_product_id,
                    products_discussed_ids=list(pred.products_discussed),
                    op_post_text=lc.candidate.op_post_text,
                    sonnet_reason_labels=[
                        _reason_pred_to_dict(rp) for rp in picked.reason_predictions
                    ],
                    force_included_negative=picked.mention_id in forced_set,
                )
            )

    write_reason_gold_jsonl(reason_entries, reason_output_path)
    stats.reason_entries_written = len(reason_entries)
    log.info("wrote %s (%d entries)", reason_output_path, len(reason_entries))

    return stats
