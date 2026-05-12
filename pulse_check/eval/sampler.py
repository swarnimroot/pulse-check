"""Deliberation gold-set sampler — bite 13.c.2.

Pure-logic helpers that produce gold-set selections for Wave 3 classifiers.
No LLM calls — the orchestration layer feeds pre-labeled inputs in.

Public surface:

    select_candidate_thread_ids(session, ...) -> list[str]
        Apply heuristic (b) ∪ (c) to the corpus, capped.

    build_candidate_thread(session, *, thread_mention_id) -> CandidateThread | None
        Reconstruct a thread (OP/OTHER top-level comment partitioning).

    stratify_and_sample_threads(labeled, ...) -> GoldThreadSelection
        3-band stratified sample with B/C/D force-includes.

    select_reason_candidates(*, labeled_comments, ...) -> ReasonGoldSelection
        Per-thread polarity-agnostic random sample with NEG-toward-winner
        force-include.

Heuristic (operator-locked, session 23):

    (b) reddit_post mentions with ≥2 distinct PRIMARY product attributions
    UNION
    (c) reddit_post mentions whose title or body matches the deliberation
        keyword pattern (case-insensitive). The pattern is noisy by design —
        false positives at candidate stage are filtered by Sonnet labeling
        downstream. Operator-approved keywords:
        ``vs | or | between | help me decide | choose | deciding | recommend``

Production filter mirror (per ``feedback_eval_must_mirror_production_filters``):
mentions without a ContentTypeTag row, OR whose tag's ``content_type`` is in
``excluded_content_types`` (default ``ContentType.DEAL``), are excluded — same
strict gate as ``pulse_check.tagging.batch``.

Stratification: 3 bands by Sonnet confidence at thresholds (0.5, 0.8).
``DeliberationPrediction.confidence is None`` pools into the low band.

Force-include rules (priority B → C → D; a thread fitting multiple rules is
counted once under the highest-priority rule it matches):

    B: is_deliberation=True AND chosen_product_id is None
       AND confidence >= rule_b_min_confidence (default 0.8)
    C: len(set(products_discussed)) >= 3
    D: is_deliberation=True AND confidence < rule_d_max_confidence (default 0.6)

Force-includes ship even if their total exceeds ``target_size`` — the rules
exist because stratification alone won't surface these shapes.

Reason-comment selection (per resolved thread): up to
``forced_negative_quota`` comments whose any reason label has
``polarity == NEGATIVE`` are force-included first; the remainder of
``target_per_thread`` is filled polarity-agnostically.
"""

from __future__ import annotations

import logging
import random
import re
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.storage.enums import (
    AttributionType,
    ContentType,
    Polarity,
    SourceType,
)
from pulse_check.storage.models import (
    ContentTypeTag,
    Mention,
    MentionAttribution,
)
from pulse_check.tagging.deliberation_classifier import DeliberationPrediction
from pulse_check.tagging.reason_tagger import ReasonPrediction

log = logging.getLogger(__name__)


DEFAULT_KEYWORD_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:vs|or|between|help me decide|choose|deciding|recommend)\b",
    re.IGNORECASE,
)
DEFAULT_CANDIDATE_CAP = 100
DEFAULT_BAND_THRESHOLDS: tuple[float, float] = (0.5, 0.8)
DEFAULT_RULE_B_MIN_CONFIDENCE = 0.8
DEFAULT_RULE_D_MAX_CONFIDENCE = 0.6
DEFAULT_TARGET_SIZE = 40
DEFAULT_FORCE_INCLUDE_PER_RULE = 2
DEFAULT_REASON_TARGET_PER_THREAD = 5
DEFAULT_FORCED_NEGATIVE_QUOTA = 2


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateThread:
    """A reddit_post + reconstructed top-level thread for the labeler.

    ``attributed_primary_product_ids`` is the set of PRIMARY product
    attributions on the POST itself (the (b) heuristic input). It is NOT
    the deliberation classifier's product universe — callers pass the
    run's full tracked product set at label time per ARCH §6.1.

    OP edits are not captured today — scrapers-lib's reddit fetcher does
    not emit them separately. ``op_edit_text`` is therefore omitted from
    this dataclass and the labeler call will pass ``op_edit_text=None``.
    """

    thread_mention_id: str
    op_author: str | None
    op_post_title: str
    op_post_text: str
    op_top_level_comments: tuple[str, ...]
    other_top_level_comments: tuple[str, ...]
    attributed_primary_product_ids: tuple[str, ...]


@dataclass(frozen=True)
class LabeledCandidate:
    """Candidate thread + Sonnet deliberation prediction."""

    candidate: CandidateThread
    prediction: DeliberationPrediction


@dataclass(frozen=True)
class GoldThreadSelection:
    """Output of ``stratify_and_sample_threads``.

    ``force_include_rules_applied`` maps thread_mention_id → "B"|"C"|"D"
    for force-included threads (omitted for stratified-random picks).
    """

    selected: tuple[LabeledCandidate, ...]
    force_include_rules_applied: dict[str, str]


@dataclass(frozen=True)
class LabeledComment:
    """Comment under a resolved thread + Sonnet reason labels."""

    mention_id: str
    comment_text: str
    thread_mention_id: str
    winning_product_id: str
    reason_predictions: tuple[ReasonPrediction, ...]


@dataclass(frozen=True)
class ReasonGoldSelection:
    """Output of ``select_reason_candidates`` (per-thread).

    ``force_included_mention_ids`` is the subset whose any reason label has
    ``polarity == NEGATIVE`` and which were claimed by the force-include
    quota.
    """

    selected: tuple[LabeledComment, ...]
    force_included_mention_ids: tuple[str, ...]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _post_id_from_post_mention_id(mention_id: str) -> str | None:
    """Recover the Reddit post_id from a ``reddit_post_<post_id>_<anchor_id>``.

    Mirrors ``pulse_check.scraping.comment_inheritance._post_id_from_post_mention_id``;
    duplicated here so the eval package does not import from scraping.
    """
    if not mention_id.startswith("reddit_post_"):
        return None
    rest = mention_id[len("reddit_post_") :]
    if not rest:
        return None
    head, _sep, _tail = rest.partition("_")
    return head or None


def _matches_keyword(post: Mention, pattern: re.Pattern[str]) -> bool:
    title = post.metadata_.get("source_title") if isinstance(post.metadata_, dict) else None
    if isinstance(title, str) and pattern.search(title):
        return True
    return bool(pattern.search(post.raw_text))


def _is_top_level_under(comment: Mention, parent_post_id: str) -> bool:
    """A reddit_comment is top-level iff its parent_id is ``t3_<post_id>``."""
    meta = comment.metadata_ if isinstance(comment.metadata_, dict) else None
    parent_link_id = meta.get("parent_id") if meta is not None else None
    if not isinstance(parent_link_id, str):
        return False
    return parent_link_id == f"t3_{parent_post_id}"


# ---------------------------------------------------------------------------
# Candidate selection (heuristic (b) ∪ (c) + content-type strict gate)
# ---------------------------------------------------------------------------


def select_candidate_thread_ids(
    session: Session,
    *,
    rng: random.Random,
    candidate_cap: int = DEFAULT_CANDIDATE_CAP,
    keyword_pattern: re.Pattern[str] = DEFAULT_KEYWORD_PATTERN,
    excluded_content_types: Sequence[ContentType] = (ContentType.DEAL,),
) -> list[str]:
    """Return ``reddit_post`` mention_ids passing the heuristic, capped.

    Output is sorted by mention_id. When the union exceeds ``candidate_cap``,
    the selection is determined by ``rng.shuffle`` over the sorted union
    before slicing — same seed yields the same subset.

    Strict content-type gate: a mention is allowed iff it has at least one
    ``ContentTypeTag`` row whose ``content_type`` is NOT in
    ``excluded_content_types``. Mentions without any tag are excluded.
    """
    allowed_mention_ids = set(
        session.execute(
            select(ContentTypeTag.mention_id)
            .where(ContentTypeTag.content_type.notin_(excluded_content_types))
            .distinct()
        )
        .scalars()
        .all()
    )

    primary_rows = session.execute(
        select(MentionAttribution.mention_id, MentionAttribution.product_id)
        .join(Mention, Mention.mention_id == MentionAttribution.mention_id)
        .where(
            Mention.source_type == SourceType.REDDIT_POST,
            MentionAttribution.attribution_type == AttributionType.PRIMARY,
        )
    ).all()
    primary_products_by_post: dict[str, set[str]] = {}
    for mention_id, product_id in primary_rows:
        primary_products_by_post.setdefault(mention_id, set()).add(product_id)
    heuristic_b: set[str] = {
        mid for mid, prods in primary_products_by_post.items() if len(prods) >= 2
    }

    reddit_posts: list[Mention] = list(
        session.execute(
            select(Mention).where(Mention.source_type == SourceType.REDDIT_POST)
        ).scalars()
    )
    heuristic_c: set[str] = {
        post.mention_id for post in reddit_posts if _matches_keyword(post, keyword_pattern)
    }

    union = (heuristic_b | heuristic_c) & allowed_mention_ids
    sorted_union = sorted(union)
    if len(sorted_union) <= candidate_cap:
        return sorted_union

    pool = list(sorted_union)
    rng.shuffle(pool)
    return sorted(pool[:candidate_cap])


# ---------------------------------------------------------------------------
# Thread reconstruction
# ---------------------------------------------------------------------------


def fetch_top_level_comments(
    session: Session,
    *,
    thread_mention_id: str,
) -> list[Mention]:
    """Return the top-level ``reddit_comment`` Mentions under a ``reddit_post``.

    Top-level = ``metadata_["parent_id"] == "t3_<post_id>"`` where ``post_id``
    is recovered from the post's ``reddit_post_<post_id>_<anchor_id>`` form.
    Nested comments (parent ``t1_...``) are excluded. Results ordered by
    mention_id for determinism.

    Returns an empty list if the post is missing, not a reddit_post, or its
    mention_id does not decode (e.g. malformed). Used by the orchestrator
    to gather comments for reason-labeling.
    """
    post = session.execute(
        select(Mention).where(Mention.mention_id == thread_mention_id)
    ).scalar_one_or_none()
    if post is None or post.source_type != SourceType.REDDIT_POST:
        return []
    post_id = _post_id_from_post_mention_id(thread_mention_id)
    if post_id is None:
        return []
    comments = list(
        session.execute(
            select(Mention)
            .where(Mention.source_type == SourceType.REDDIT_COMMENT)
            .order_by(Mention.mention_id.asc())
        ).scalars()
    )
    return [c for c in comments if _is_top_level_under(c, post_id)]


def build_candidate_thread(
    session: Session,
    *,
    thread_mention_id: str,
) -> CandidateThread | None:
    """Reconstruct a ``CandidateThread`` from corpus state.

    Returns None if the mention does not exist or is not a ``reddit_post``.
    Top-level comments under the post are partitioned by author:
    OP-authored go into ``op_top_level_comments``; the rest go into
    ``other_top_level_comments``. Order within each list is by mention_id.
    Nested comments (parent ``t1_...``) and comments under other posts are
    excluded.
    """
    post = session.execute(
        select(Mention).where(Mention.mention_id == thread_mention_id)
    ).scalar_one_or_none()
    if post is None or post.source_type != SourceType.REDDIT_POST:
        return None

    op_top: list[str] = []
    other_top: list[str] = []
    for comment in fetch_top_level_comments(session, thread_mention_id=thread_mention_id):
        if post.author is not None and comment.author == post.author:
            op_top.append(comment.raw_text)
        else:
            other_top.append(comment.raw_text)

    primary_products = sorted(
        session.execute(
            select(MentionAttribution.product_id).where(
                MentionAttribution.mention_id == thread_mention_id,
                MentionAttribution.attribution_type == AttributionType.PRIMARY,
            )
        )
        .scalars()
        .all()
    )

    title_raw = post.metadata_.get("source_title") if isinstance(post.metadata_, dict) else None
    title = title_raw if isinstance(title_raw, str) else ""

    return CandidateThread(
        thread_mention_id=thread_mention_id,
        op_author=post.author,
        op_post_title=title,
        op_post_text=post.raw_text,
        op_top_level_comments=tuple(op_top),
        other_top_level_comments=tuple(other_top),
        attributed_primary_product_ids=tuple(primary_products),
    )


# ---------------------------------------------------------------------------
# Stratification + force-includes
# ---------------------------------------------------------------------------


def _classify_force_rule(
    pred: DeliberationPrediction,
    *,
    rule_b_min_confidence: float,
    rule_d_max_confidence: float,
) -> str | None:
    """Return ``"B"``, ``"C"``, ``"D"``, or None. Priority order B > C > D."""
    if (
        pred.is_deliberation
        and pred.chosen_product_id is None
        and pred.confidence is not None
        and pred.confidence >= rule_b_min_confidence
    ):
        return "B"
    if len(set(pred.products_discussed)) >= 3:
        return "C"
    if (
        pred.is_deliberation
        and pred.confidence is not None
        and pred.confidence < rule_d_max_confidence
    ):
        return "D"
    return None


def _band_for(pred: DeliberationPrediction, *, thresholds: tuple[float, float]) -> str:
    conf = pred.confidence
    if conf is None or conf < thresholds[0]:
        return "low"
    if conf < thresholds[1]:
        return "mid"
    return "high"


def stratify_and_sample_threads(
    labeled: Sequence[LabeledCandidate],
    *,
    rng: random.Random,
    target_size: int = DEFAULT_TARGET_SIZE,
    band_thresholds: tuple[float, float] = DEFAULT_BAND_THRESHOLDS,
    rule_b_min_confidence: float = DEFAULT_RULE_B_MIN_CONFIDENCE,
    rule_d_max_confidence: float = DEFAULT_RULE_D_MAX_CONFIDENCE,
    force_include_per_rule: int = DEFAULT_FORCE_INCLUDE_PER_RULE,
) -> GoldThreadSelection:
    """Sample a stratified gold set with B/C/D force-includes.

    Force-includes claim slots first (up to ``force_include_per_rule`` per
    rule). The remaining slots ``max(0, target_size - len(forced))`` are
    drawn evenly across the three confidence bands over the pool with
    force-included entries removed. A band with fewer entries than its
    even-quota share contributes everything it has; the shortfall is NOT
    redistributed to other bands (mirrors ``gold_set.sample_attributions_stratified``).

    If force-includes alone exceed ``target_size``, they all still ship —
    the rules exist precisely because stratification will not surface these
    shapes.
    """
    sorted_labeled = sorted(labeled, key=lambda lc: lc.candidate.thread_mention_id)

    rule_pools: dict[str, list[LabeledCandidate]] = {"B": [], "C": [], "D": []}
    for lc in sorted_labeled:
        rule = _classify_force_rule(
            lc.prediction,
            rule_b_min_confidence=rule_b_min_confidence,
            rule_d_max_confidence=rule_d_max_confidence,
        )
        if rule is not None:
            rule_pools[rule].append(lc)

    forced: list[LabeledCandidate] = []
    forced_ids: set[str] = set()
    forced_rules: dict[str, str] = {}
    for rule in ("B", "C", "D"):
        pool = list(rule_pools[rule])
        rng.shuffle(pool)
        taken = 0
        for lc in pool:
            if taken >= force_include_per_rule:
                break
            if lc.candidate.thread_mention_id in forced_ids:
                continue
            forced.append(lc)
            forced_ids.add(lc.candidate.thread_mention_id)
            forced_rules[lc.candidate.thread_mention_id] = rule
            taken += 1

    remaining_pool = [
        lc for lc in sorted_labeled if lc.candidate.thread_mention_id not in forced_ids
    ]
    by_band: dict[str, list[LabeledCandidate]] = {"low": [], "mid": [], "high": []}
    for lc in remaining_pool:
        by_band[_band_for(lc.prediction, thresholds=band_thresholds)].append(lc)

    remaining_size = max(target_size - len(forced), 0)
    sampled: list[LabeledCandidate] = []
    band_order = ("low", "mid", "high")
    non_empty_bands = [b for b in band_order if by_band[b]]
    if non_empty_bands and remaining_size > 0:
        per_band = remaining_size // len(non_empty_bands)
        remainder = remaining_size - per_band * len(non_empty_bands)
        for idx, band in enumerate(non_empty_bands):
            pool = list(by_band[band])
            rng.shuffle(pool)
            take = min(per_band + (1 if idx < remainder else 0), len(pool))
            sampled.extend(pool[:take])

    selected = forced + sampled
    selected.sort(key=lambda lc: lc.candidate.thread_mention_id)
    return GoldThreadSelection(
        selected=tuple(selected),
        force_include_rules_applied=forced_rules,
    )


# ---------------------------------------------------------------------------
# Reason-comment selection (per resolved thread)
# ---------------------------------------------------------------------------


def select_reason_candidates(
    *,
    labeled_comments: Sequence[LabeledComment],
    rng: random.Random,
    target_per_thread: int = DEFAULT_REASON_TARGET_PER_THREAD,
    forced_negative_quota: int = DEFAULT_FORCED_NEGATIVE_QUOTA,
) -> ReasonGoldSelection:
    """Per-thread polarity-agnostic random sample with NEG-toward-winner force-include.

    A comment is NEG-toward-winner iff any of its ``reason_predictions`` has
    ``polarity == Polarity.NEGATIVE``. Up to
    ``min(forced_negative_quota, target_per_thread, len(neg_pool))`` such
    comments are force-included first; the remaining slots are filled by
    polarity-agnostic random draw from the rest of the pool. Force-included
    comments are not eligible for the random-fill stage (no double-counting).
    """
    sorted_comments = sorted(labeled_comments, key=lambda lc: lc.mention_id)

    negative_pool: list[LabeledComment] = []
    for lc in sorted_comments:
        if any(rp.polarity == Polarity.NEGATIVE for rp in lc.reason_predictions):
            negative_pool.append(lc)

    n_forced = min(forced_negative_quota, target_per_thread, len(negative_pool))
    neg_shuffled = list(negative_pool)
    rng.shuffle(neg_shuffled)
    forced = neg_shuffled[:n_forced]
    forced_ids: set[str] = {lc.mention_id for lc in forced}

    remaining_pool = [lc for lc in sorted_comments if lc.mention_id not in forced_ids]
    rng.shuffle(remaining_pool)
    remaining_slots = max(target_per_thread - n_forced, 0)
    fill = remaining_pool[:remaining_slots]

    selected = sorted(forced + fill, key=lambda lc: lc.mention_id)
    return ReasonGoldSelection(
        selected=tuple(selected),
        force_included_mention_ids=tuple(sorted(forced_ids)),
    )
