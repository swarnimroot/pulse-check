"""Unit tests for the deliberation-gold-set sampler.

Coverage priorities (bite 13.c.2):
- Heuristic (b) ∪ (c) selects the right reddit_post mention_ids, mirrors
  production's strict content-type gate, and caps deterministically.
- Thread reconstruction partitions OP / OTHER top-level comments and
  excludes nested + cross-post comments.
- Stratify-and-sample evenly draws across 3 confidence bands, force-includes
  B / C / D with priority B > C > D, never double-counts, and is reproducible
  for a given seed.
- Reason-candidate selection is polarity-agnostic with NEG-toward-winner
  force-include up to the configured quota.

No LLM client is involved — the sampler operates on pre-labeled inputs.
"""

from __future__ import annotations

import random

from sqlalchemy.orm import Session

from pulse_check.eval.sampler import (
    CandidateThread,
    LabeledCandidate,
    LabeledComment,
    build_candidate_thread,
    select_candidate_thread_ids,
    select_reason_candidates,
    stratify_and_sample_threads,
)
from pulse_check.storage.enums import (
    AttributionMethod,
    AttributionType,
    ContentType,
    Intensity,
    Polarity,
    ReasonBucket,
    SourceType,
)
from pulse_check.storage.models import (
    ContentTypeTag,
    Mention,
    MentionAttribution,
)
from pulse_check.tagging.deliberation_classifier import DeliberationPrediction
from pulse_check.tagging.reason_tagger import ReasonPrediction

# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_post(
    session: Session,
    *,
    mention_id: str,
    title: str = "",
    body: str = "neutral body without keywords",
    author: str = "op_user",
    content_type: ContentType | None = ContentType.REVIEW,
) -> None:
    session.add(
        Mention(
            mention_id=mention_id,
            source_type=SourceType.REDDIT_POST,
            source_url="https://reddit.com/r/test/abc",
            author=author,
            raw_text=body,
            metadata_={"source_title": title},
        )
    )
    if content_type is not None:
        session.add(
            ContentTypeTag(
                mention_id=mention_id,
                content_type=content_type,
                prompt_version="content_type_v1",
                model="claude-haiku-4-5-20251001",
                temperature=0.0,
            )
        )


def _seed_primary(session: Session, *, mention_id: str, product_id: str) -> None:
    session.add(
        MentionAttribution(
            mention_id=mention_id,
            product_id=product_id,
            attribution_type=AttributionType.PRIMARY,
            attribution_method=AttributionMethod.REGEX,
        )
    )


def _seed_comment(
    session: Session,
    *,
    mention_id: str,
    parent_id: str,
    body: str = "",
    author: str = "commenter",
) -> None:
    session.add(
        Mention(
            mention_id=mention_id,
            source_type=SourceType.REDDIT_COMMENT,
            source_url="https://reddit.com/r/test/abc/comment",
            author=author,
            raw_text=body,
            metadata_={"parent_id": parent_id},
        )
    )


def _make_labeled(
    thread_id: str,
    *,
    is_deliberation: bool = True,
    is_resolved: bool = True,
    products_discussed: tuple[str, ...] = ("alienware_16_aurora", "rog_strix_g16"),
    chosen_product_id: str | None = "alienware_16_aurora",
    confidence: float | None = 0.9,
) -> LabeledCandidate:
    return LabeledCandidate(
        candidate=CandidateThread(
            thread_mention_id=thread_id,
            op_author="u",
            op_post_title="",
            op_post_text="",
            op_top_level_comments=(),
            other_top_level_comments=(),
            attributed_primary_product_ids=(),
        ),
        prediction=DeliberationPrediction(
            is_deliberation=is_deliberation,
            is_resolved=is_resolved,
            products_discussed=products_discussed,
            chosen_product_id=chosen_product_id,
            confidence=confidence,
        ),
    )


def _make_labeled_comment(
    mention_id: str,
    *,
    polarity: Polarity = Polarity.POSITIVE,
    n_reasons: int = 1,
) -> LabeledComment:
    reasons = tuple(
        ReasonPrediction(
            reason_bucket=ReasonBucket.THERMALS,
            polarity=polarity,
            intensity=Intensity.MEDIUM,
        )
        for _ in range(n_reasons)
    )
    return LabeledComment(
        mention_id=mention_id,
        comment_text="x",
        thread_mention_id="t1",
        winning_product_id="alienware_16_aurora",
        reason_predictions=reasons,
    )


# ---------------------------------------------------------------------------
# select_candidate_thread_ids — heuristic + content-type gate + cap
# ---------------------------------------------------------------------------


def test_select_candidate_thread_ids_empty_corpus(session: Session) -> None:
    assert select_candidate_thread_ids(session, rng=random.Random(0)) == []


def test_select_candidate_thread_ids_includes_post_with_two_primary_attributions(
    session: Session,
) -> None:
    """Heuristic (b): post with ≥2 distinct PRIMARY attributions."""
    _seed_post(session, mention_id="reddit_post_a_x")
    _seed_primary(session, mention_id="reddit_post_a_x", product_id="alienware_16_aurora")
    _seed_primary(session, mention_id="reddit_post_a_x", product_id="rog_strix_g16")
    session.flush()
    ids = select_candidate_thread_ids(session, rng=random.Random(0))
    assert ids == ["reddit_post_a_x"]


def test_select_candidate_thread_ids_excludes_post_with_single_primary_attribution(
    session: Session,
) -> None:
    """Single PRIMARY attribution + no keyword → not selected."""
    _seed_post(session, mention_id="reddit_post_a_x", body="my new laptop is great")
    _seed_primary(session, mention_id="reddit_post_a_x", product_id="alienware_16_aurora")
    session.flush()
    assert select_candidate_thread_ids(session, rng=random.Random(0)) == []


def test_select_candidate_thread_ids_includes_post_with_keyword_in_title(
    session: Session,
) -> None:
    """Heuristic (c) hits via title."""
    _seed_post(session, mention_id="reddit_post_a_x", title="Alienware vs ROG")
    session.flush()
    assert select_candidate_thread_ids(session, rng=random.Random(0)) == ["reddit_post_a_x"]


def test_select_candidate_thread_ids_includes_post_with_keyword_in_body(
    session: Session,
) -> None:
    """Heuristic (c) hits via body."""
    _seed_post(session, mention_id="reddit_post_a_x", body="help me decide between two laptops")
    session.flush()
    assert select_candidate_thread_ids(session, rng=random.Random(0)) == ["reddit_post_a_x"]


def test_select_candidate_thread_ids_keyword_match_is_case_insensitive(
    session: Session,
) -> None:
    _seed_post(session, mention_id="reddit_post_a_x", title="HELP ME DECIDE today")
    session.flush()
    assert select_candidate_thread_ids(session, rng=random.Random(0)) == ["reddit_post_a_x"]


def test_select_candidate_thread_ids_dedupes_when_both_heuristics_match(
    session: Session,
) -> None:
    _seed_post(session, mention_id="reddit_post_a_x", title="Alienware vs ROG")
    _seed_primary(session, mention_id="reddit_post_a_x", product_id="alienware_16_aurora")
    _seed_primary(session, mention_id="reddit_post_a_x", product_id="rog_strix_g16")
    session.flush()
    ids = select_candidate_thread_ids(session, rng=random.Random(0))
    assert ids == ["reddit_post_a_x"]


def test_select_candidate_thread_ids_excludes_deal_content_type(session: Session) -> None:
    """Strict gate: deal content_type → excluded even if heuristic matches."""
    _seed_post(
        session,
        mention_id="reddit_post_a_x",
        title="Alienware vs ROG",
        content_type=ContentType.DEAL,
    )
    session.flush()
    assert select_candidate_thread_ids(session, rng=random.Random(0)) == []


def test_select_candidate_thread_ids_includes_other_content_type(session: Session) -> None:
    """Only DEAL is excluded by default; OTHER passes the gate."""
    _seed_post(
        session,
        mention_id="reddit_post_a_x",
        title="Alienware vs ROG",
        content_type=ContentType.OTHER,
    )
    session.flush()
    assert select_candidate_thread_ids(session, rng=random.Random(0)) == ["reddit_post_a_x"]


def test_select_candidate_thread_ids_excludes_post_without_content_type_tag(
    session: Session,
) -> None:
    """Strict gate: no ContentTypeTag row → excluded."""
    _seed_post(
        session,
        mention_id="reddit_post_a_x",
        title="Alienware vs ROG",
        content_type=None,
    )
    session.flush()
    assert select_candidate_thread_ids(session, rng=random.Random(0)) == []


def test_select_candidate_thread_ids_respects_hard_cap(session: Session) -> None:
    for i in range(15):
        _seed_post(session, mention_id=f"reddit_post_{i:02d}_x", title="Alienware vs ROG")
    session.flush()
    ids = select_candidate_thread_ids(session, rng=random.Random(0), candidate_cap=10)
    assert len(ids) == 10


def test_select_candidate_thread_ids_cap_deterministic_with_seed(session: Session) -> None:
    for i in range(15):
        _seed_post(session, mention_id=f"reddit_post_{i:02d}_x", title="Alienware vs ROG")
    session.flush()
    ids_a = select_candidate_thread_ids(session, rng=random.Random(42), candidate_cap=10)
    ids_b = select_candidate_thread_ids(session, rng=random.Random(42), candidate_cap=10)
    assert ids_a == ids_b


def test_select_candidate_thread_ids_sorted_output(session: Session) -> None:
    _seed_post(session, mention_id="reddit_post_z_x", title="Alienware vs ROG")
    _seed_post(session, mention_id="reddit_post_a_x", title="Alienware vs ROG")
    session.flush()
    ids = select_candidate_thread_ids(session, rng=random.Random(0))
    assert ids == ["reddit_post_a_x", "reddit_post_z_x"]


# ---------------------------------------------------------------------------
# build_candidate_thread — thread reconstruction
# ---------------------------------------------------------------------------


def test_build_candidate_thread_returns_none_for_missing_mention(session: Session) -> None:
    assert build_candidate_thread(session, thread_mention_id="missing") is None


def test_build_candidate_thread_returns_none_for_non_post_mention(session: Session) -> None:
    _seed_comment(session, mention_id="reddit_comment_1", parent_id="t3_abc")
    session.flush()
    assert build_candidate_thread(session, thread_mention_id="reddit_comment_1") is None


def test_build_candidate_thread_partitions_op_vs_other_comments(session: Session) -> None:
    _seed_post(session, mention_id="reddit_post_abc_x", body="post body", author="op_user")
    _seed_comment(
        session,
        mention_id="reddit_comment_1",
        parent_id="t3_abc",
        body="op reply",
        author="op_user",
    )
    _seed_comment(
        session,
        mention_id="reddit_comment_2",
        parent_id="t3_abc",
        body="other reply",
        author="other_user",
    )
    session.flush()
    thread = build_candidate_thread(session, thread_mention_id="reddit_post_abc_x")
    assert thread is not None
    assert thread.op_top_level_comments == ("op reply",)
    assert thread.other_top_level_comments == ("other reply",)


def test_build_candidate_thread_excludes_nested_comments(session: Session) -> None:
    """Comments with parent ``t1_...`` are nested, not top-level."""
    _seed_post(session, mention_id="reddit_post_abc_x", author="op_user")
    _seed_comment(
        session, mention_id="reddit_comment_1", parent_id="t1_xyz", body="nested", author="other"
    )
    session.flush()
    thread = build_candidate_thread(session, thread_mention_id="reddit_post_abc_x")
    assert thread is not None
    assert thread.op_top_level_comments == ()
    assert thread.other_top_level_comments == ()


def test_build_candidate_thread_excludes_comments_under_other_posts(session: Session) -> None:
    _seed_post(session, mention_id="reddit_post_abc_x", author="op_user")
    _seed_comment(
        session,
        mention_id="reddit_comment_1",
        parent_id="t3_xyz",
        body="not under this post",
        author="other",
    )
    session.flush()
    thread = build_candidate_thread(session, thread_mention_id="reddit_post_abc_x")
    assert thread is not None
    assert thread.other_top_level_comments == ()


def test_build_candidate_thread_returns_primary_product_ids_sorted(session: Session) -> None:
    _seed_post(session, mention_id="reddit_post_abc_x", author="op_user")
    _seed_primary(session, mention_id="reddit_post_abc_x", product_id="rog_strix_g16")
    _seed_primary(session, mention_id="reddit_post_abc_x", product_id="alienware_16_aurora")
    session.flush()
    thread = build_candidate_thread(session, thread_mention_id="reddit_post_abc_x")
    assert thread is not None
    assert thread.attributed_primary_product_ids == (
        "alienware_16_aurora",
        "rog_strix_g16",
    )


def test_build_candidate_thread_carries_title_and_body(session: Session) -> None:
    _seed_post(
        session,
        mention_id="reddit_post_abc_x",
        title="My Title",
        body="Body text here",
        author="op_user",
    )
    session.flush()
    thread = build_candidate_thread(session, thread_mention_id="reddit_post_abc_x")
    assert thread is not None
    assert thread.op_post_title == "My Title"
    assert thread.op_post_text == "Body text here"
    assert thread.op_author == "op_user"


# ---------------------------------------------------------------------------
# stratify_and_sample_threads — bands + force-includes
# ---------------------------------------------------------------------------


def test_stratify_empty_returns_empty_selection() -> None:
    selection = stratify_and_sample_threads([], rng=random.Random(0))
    assert selection.selected == ()
    assert selection.force_include_rules_applied == {}


def test_stratify_distributes_evenly_across_three_populated_bands() -> None:
    """Default 3-band stratification gives equal counts when all bands have ≥quota."""
    labeled = (
        [_make_labeled(f"t{i:02d}", confidence=0.3) for i in range(10)]
        + [_make_labeled(f"u{i:02d}", confidence=0.65) for i in range(10)]
        + [_make_labeled(f"v{i:02d}", confidence=0.95) for i in range(10)]
    )
    selection = stratify_and_sample_threads(
        labeled, rng=random.Random(0), target_size=9, force_include_per_rule=0
    )
    assert len(selection.selected) == 9
    low = sum(1 for lc in selection.selected if (lc.prediction.confidence or 0) < 0.5)
    mid = sum(1 for lc in selection.selected if 0.5 <= (lc.prediction.confidence or 0) < 0.8)
    high = sum(1 for lc in selection.selected if (lc.prediction.confidence or 0) >= 0.8)
    assert low == 3
    assert mid == 3
    assert high == 3


def test_stratify_shortfall_band_is_not_redistributed() -> None:
    """Mirrors gold_set.py: a thin band contributes what it has, no redistribution."""
    labeled = (
        [_make_labeled("t01", confidence=0.3)]
        + [_make_labeled(f"u{i:02d}", confidence=0.65) for i in range(10)]
        + [_make_labeled(f"v{i:02d}", confidence=0.95) for i in range(10)]
    )
    selection = stratify_and_sample_threads(
        labeled, rng=random.Random(0), target_size=9, force_include_per_rule=0
    )
    # 9 / 3 = 3 per band; low has only 1 → 1+3+3 = 7
    assert len(selection.selected) == 7


def test_stratify_force_includes_rule_B() -> None:
    """Rule B: is_deliberation + chosen_product_id is None + high confidence."""
    labeled = [
        _make_labeled("b1", chosen_product_id=None, is_resolved=False, confidence=0.9),
        _make_labeled("b2", chosen_product_id=None, is_resolved=False, confidence=0.9),
        _make_labeled("h1", confidence=0.9),
        _make_labeled("h2", confidence=0.9),
    ]
    selection = stratify_and_sample_threads(
        labeled, rng=random.Random(0), target_size=4, force_include_per_rule=2
    )
    ids = {lc.candidate.thread_mention_id for lc in selection.selected}
    assert {"b1", "b2"} <= ids
    assert selection.force_include_rules_applied.get("b1") == "B"
    assert selection.force_include_rules_applied.get("b2") == "B"


def test_stratify_force_includes_rule_C() -> None:
    """Rule C: ≥3 distinct products_discussed."""
    labeled = [
        _make_labeled("c1", products_discussed=("p1", "p2", "p3")),
        _make_labeled("c2", products_discussed=("p1", "p2", "p3", "p4")),
        _make_labeled("h1", confidence=0.9),
        _make_labeled("h2", confidence=0.9),
    ]
    selection = stratify_and_sample_threads(
        labeled, rng=random.Random(0), target_size=4, force_include_per_rule=2
    )
    ids = {lc.candidate.thread_mention_id for lc in selection.selected}
    assert {"c1", "c2"} <= ids
    assert selection.force_include_rules_applied.get("c1") == "C"


def test_stratify_force_includes_rule_D() -> None:
    """Rule D: is_deliberation=True with confidence < 0.6 (default)."""
    labeled = [
        _make_labeled("d1", confidence=0.4),
        _make_labeled("d2", confidence=0.55),
        _make_labeled("h1", confidence=0.9),
        _make_labeled("h2", confidence=0.9),
    ]
    selection = stratify_and_sample_threads(
        labeled, rng=random.Random(0), target_size=4, force_include_per_rule=2
    )
    ids = {lc.candidate.thread_mention_id for lc in selection.selected}
    assert {"d1", "d2"} <= ids
    assert selection.force_include_rules_applied.get("d1") == "D"


def test_stratify_force_include_priority_B_over_C() -> None:
    """A thread fitting both B and C is counted under B (priority)."""
    bc_thread = _make_labeled(
        "bc1",
        products_discussed=("p1", "p2", "p3"),
        chosen_product_id=None,
        is_resolved=False,
        confidence=0.95,
    )
    labeled = [
        bc_thread,
        _make_labeled("c1", products_discussed=("p1", "p2", "p3")),
        _make_labeled("h1", confidence=0.9),
        _make_labeled("h2", confidence=0.9),
    ]
    selection = stratify_and_sample_threads(
        labeled, rng=random.Random(0), target_size=4, force_include_per_rule=2
    )
    assert selection.force_include_rules_applied.get("bc1") == "B"


def test_stratify_force_include_per_rule_caps_count() -> None:
    """force_include_per_rule limits how many entries each rule's pool contributes."""
    labeled = [
        _make_labeled(f"c{i:02d}", products_discussed=("p1", "p2", "p3"), confidence=0.9)
        for i in range(10)
    ]
    selection = stratify_and_sample_threads(
        labeled, rng=random.Random(0), target_size=10, force_include_per_rule=2
    )
    forced_count = sum(1 for v in selection.force_include_rules_applied.values() if v == "C")
    assert forced_count == 2


def test_stratify_force_includes_removed_from_band_pool() -> None:
    """A rule-forced thread is NOT also drawn in the band stratification step."""
    labeled = [
        _make_labeled(
            "c1", products_discussed=("p1", "p2", "p3"), confidence=0.95
        ),
        _make_labeled("h1", confidence=0.95),
        _make_labeled("h2", confidence=0.95),
    ]
    selection = stratify_and_sample_threads(
        labeled, rng=random.Random(0), target_size=2, force_include_per_rule=1
    )
    ids = [lc.candidate.thread_mention_id for lc in selection.selected]
    assert ids.count("c1") == 1
    assert len(selection.selected) == 2


def test_stratify_reproducible_with_same_seed() -> None:
    labeled = [_make_labeled(f"t{i:02d}", confidence=0.65) for i in range(10)]
    a = stratify_and_sample_threads(
        labeled, rng=random.Random(42), target_size=5, force_include_per_rule=0
    )
    b = stratify_and_sample_threads(
        labeled, rng=random.Random(42), target_size=5, force_include_per_rule=0
    )
    ids_a = [lc.candidate.thread_mention_id for lc in a.selected]
    ids_b = [lc.candidate.thread_mention_id for lc in b.selected]
    assert ids_a == ids_b


def test_stratify_pools_none_confidence_into_low_band() -> None:
    """confidence=None pools into the low band as edge-case."""
    labeled = [_make_labeled(f"t{i:02d}", confidence=None) for i in range(3)]
    selection = stratify_and_sample_threads(
        labeled, rng=random.Random(0), target_size=3, force_include_per_rule=0
    )
    assert len(selection.selected) == 3


def test_stratify_force_includes_can_exceed_target_size() -> None:
    """If force-includes alone exceed target_size, they all still ship."""
    labeled = [
        _make_labeled("b1", chosen_product_id=None, is_resolved=False, confidence=0.95),
        _make_labeled("b2", chosen_product_id=None, is_resolved=False, confidence=0.95),
        _make_labeled("c1", products_discussed=("p1", "p2", "p3")),
        _make_labeled("c2", products_discussed=("p1", "p2", "p3")),
        _make_labeled("d1", confidence=0.3),
        _make_labeled("d2", confidence=0.3),
        _make_labeled("h1", confidence=0.9),
    ]
    selection = stratify_and_sample_threads(
        labeled, rng=random.Random(0), target_size=4, force_include_per_rule=2
    )
    # 6 force-includes (2 B + 2 C + 2 D) ≥ target_size=4 → all 6 ship, no band fill
    assert len(selection.selected) == 6
    rules = set(selection.force_include_rules_applied.values())
    assert rules == {"B", "C", "D"}


# ---------------------------------------------------------------------------
# select_reason_candidates — polarity-agnostic + NEG force-include
# ---------------------------------------------------------------------------


def test_select_reason_candidates_empty() -> None:
    sel = select_reason_candidates(labeled_comments=[], rng=random.Random(0))
    assert sel.selected == ()
    assert sel.force_included_mention_ids == ()


def test_select_reason_candidates_polarity_agnostic_random_fill() -> None:
    """Without NEG comments, fill is polarity-agnostic to target_per_thread."""
    comments = [
        _make_labeled_comment(f"c{i:02d}", polarity=Polarity.POSITIVE) for i in range(10)
    ]
    sel = select_reason_candidates(
        labeled_comments=comments, rng=random.Random(0), target_per_thread=5
    )
    assert len(sel.selected) == 5
    assert sel.force_included_mention_ids == ()


def test_select_reason_candidates_force_includes_neg() -> None:
    """NEG-toward-winner comments are force-included up to quota."""
    comments = [
        _make_labeled_comment("n1", polarity=Polarity.NEGATIVE),
        _make_labeled_comment("n2", polarity=Polarity.NEGATIVE),
        _make_labeled_comment("p1", polarity=Polarity.POSITIVE),
        _make_labeled_comment("p2", polarity=Polarity.POSITIVE),
        _make_labeled_comment("p3", polarity=Polarity.POSITIVE),
    ]
    sel = select_reason_candidates(
        labeled_comments=comments,
        rng=random.Random(0),
        target_per_thread=4,
        forced_negative_quota=2,
    )
    ids = {lc.mention_id for lc in sel.selected}
    assert {"n1", "n2"} <= ids
    assert set(sel.force_included_mention_ids) == {"n1", "n2"}


def test_select_reason_candidates_skips_force_when_no_neg() -> None:
    comments = [
        _make_labeled_comment(f"p{i:02d}", polarity=Polarity.POSITIVE) for i in range(5)
    ]
    sel = select_reason_candidates(
        labeled_comments=comments,
        rng=random.Random(0),
        target_per_thread=5,
        forced_negative_quota=2,
    )
    assert sel.force_included_mention_ids == ()


def test_select_reason_candidates_caps_force_at_quota() -> None:
    """More NEG comments than quota → force-include only the quota."""
    comments = [
        _make_labeled_comment(f"n{i:02d}", polarity=Polarity.NEGATIVE) for i in range(5)
    ]
    sel = select_reason_candidates(
        labeled_comments=comments,
        rng=random.Random(0),
        target_per_thread=10,
        forced_negative_quota=2,
    )
    assert len(sel.force_included_mention_ids) == 2


def test_select_reason_candidates_no_double_count_with_random_fill() -> None:
    """A force-included NEG is excluded from the random-fill pool."""
    comments = [_make_labeled_comment("n1", polarity=Polarity.NEGATIVE)]
    sel = select_reason_candidates(
        labeled_comments=comments,
        rng=random.Random(0),
        target_per_thread=5,
        forced_negative_quota=2,
    )
    ids = [lc.mention_id for lc in sel.selected]
    assert ids.count("n1") == 1


def test_select_reason_candidates_reproducible_with_seed() -> None:
    comments = [_make_labeled_comment(f"c{i:02d}", polarity=Polarity.NEUTRAL) for i in range(10)]
    a = select_reason_candidates(
        labeled_comments=comments, rng=random.Random(42), target_per_thread=4
    )
    b = select_reason_candidates(
        labeled_comments=comments, rng=random.Random(42), target_per_thread=4
    )
    assert [lc.mention_id for lc in a.selected] == [lc.mention_id for lc in b.selected]


def test_select_reason_candidates_mixed_polarity_with_any_neg_qualifies() -> None:
    """A comment with any NEG reason label counts as NEG-toward-winner."""
    mixed = LabeledComment(
        mention_id="mixed",
        comment_text="x",
        thread_mention_id="t1",
        winning_product_id="alienware_16_aurora",
        reason_predictions=(
            ReasonPrediction(
                reason_bucket=ReasonBucket.THERMALS,
                polarity=Polarity.POSITIVE,
                intensity=Intensity.LOW,
            ),
            ReasonPrediction(
                reason_bucket=ReasonBucket.KEYBOARD,
                polarity=Polarity.NEGATIVE,
                intensity=Intensity.HIGH,
            ),
        ),
    )
    pos = _make_labeled_comment("p1", polarity=Polarity.POSITIVE)
    sel = select_reason_candidates(
        labeled_comments=[mixed, pos],
        rng=random.Random(0),
        target_per_thread=2,
        forced_negative_quota=2,
    )
    assert "mixed" in sel.force_included_mention_ids
