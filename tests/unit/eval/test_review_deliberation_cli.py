"""Interactive review CLI tests for the deliberation gold set — bite 13.c.4.

Mirrors `tests/unit/eval/test_review_cli.py` for the aspect review CLI.
The CLI prompts on stdin and writes to stdout; we drive it with an in-memory
StringIO so we can assert on state transitions deterministically.
"""

from __future__ import annotations

import io

from pulse_check.eval.deliberation_gold_set import DeliberationGoldEntry

# scripts.review_deliberation_gold_set imports cleanly when scripts has an
# __init__.py (it does, per scripts.review_gold_set test convention).
from scripts.review_deliberation_gold_set import review


def _entry(thread_mention_id: str = "reddit_post_a_x") -> DeliberationGoldEntry:
    return DeliberationGoldEntry(
        thread_mention_id=thread_mention_id,
        op_post_title="Alienware vs ROG",
        op_post_text="help me decide between these two laptops",
        op_top_level_comments=["OP follow-up"],
        other_top_level_comments=["someone else replying"],
        product_universe_ids=["alienware_16_aurora", "rog_strix_g16"],
        attributed_primary_product_ids=["alienware_16_aurora"],
        sonnet_prediction={
            "is_deliberation": True,
            "is_resolved": False,
            "products_discussed": ["alienware_16_aurora", "rog_strix_g16"],
            "chosen_product_id": None,
            "confidence": 0.85,
        },
        force_include_rule=None,
    )


def test_review_accept_sets_flag() -> None:
    entries = [_entry()]
    actioned = review(entries, inp=io.StringIO("a\n"))
    assert actioned == 1
    assert entries[0].operator_flag == "accept"
    assert entries[0].operator_labels is None


def test_review_flag_captures_optional_note() -> None:
    entries = [_entry()]
    actioned = review(entries, inp=io.StringIO("f\nSonnet should have resolved this one\n"))
    assert actioned == 1
    assert entries[0].operator_flag == "flag"
    assert entries[0].operator_notes == "Sonnet should have resolved this one"


def test_review_flag_blank_note_stays_none() -> None:
    entries = [_entry()]
    actioned = review(entries, inp=io.StringIO("f\n\n"))
    assert actioned == 1
    assert entries[0].operator_flag == "flag"
    assert entries[0].operator_notes is None


def test_review_correct_captures_labels_and_note() -> None:
    entries = [_entry()]
    corrected = (
        '{"is_deliberation":true,"is_resolved":true,'
        '"products_discussed":["alienware_16_aurora"],'
        '"chosen_product_id":"alienware_16_aurora","confidence":0.95}'
    )
    actioned = review(
        entries,
        inp=io.StringIO(f"c\n{corrected}\nOP picked Alienware in comment 1\n"),
    )
    assert actioned == 1
    assert entries[0].operator_flag == "corrected"
    assert entries[0].operator_labels == {
        "is_deliberation": True,
        "is_resolved": True,
        "products_discussed": ["alienware_16_aurora"],
        "chosen_product_id": "alienware_16_aurora",
        "confidence": 0.95,
    }
    assert entries[0].operator_notes == "OP picked Alienware in comment 1"


def test_review_correct_with_bad_json_leaves_entry_unchanged() -> None:
    entries = [_entry()]
    actioned = review(entries, inp=io.StringIO("c\nnot-valid-json\n"))
    assert actioned == 0
    assert entries[0].operator_flag is None


def test_review_correct_with_non_dict_json_leaves_unchanged() -> None:
    entries = [_entry()]
    actioned = review(entries, inp=io.StringIO('c\n["a", "list"]\n'))
    assert actioned == 0
    assert entries[0].operator_flag is None


def test_review_correct_without_is_deliberation_key_rejected() -> None:
    """A corrected JSON missing the 'is_deliberation' key is rejected to avoid silent dummies."""
    entries = [_entry()]
    actioned = review(entries, inp=io.StringIO('c\n{"is_resolved":true}\n'))
    assert actioned == 0
    assert entries[0].operator_flag is None


def test_review_skip_does_nothing() -> None:
    entries = [_entry()]
    actioned = review(entries, inp=io.StringIO("s\n"))
    assert actioned == 0
    assert entries[0].operator_flag is None


def test_review_quit_stops_iteration() -> None:
    entries = [_entry("t1"), _entry("t2"), _entry("t3")]
    actioned = review(entries, inp=io.StringIO("a\nq\n"))
    assert actioned == 1
    assert entries[0].operator_flag == "accept"
    assert entries[1].operator_flag is None
    assert entries[2].operator_flag is None


def test_review_skips_already_reviewed_entries() -> None:
    entries = [_entry("t1"), _entry("t2")]
    entries[0].operator_flag = "accept"
    actioned = review(entries, inp=io.StringIO("f\n\n"))
    assert actioned == 1
    assert entries[0].operator_flag == "accept"
    assert entries[1].operator_flag == "flag"


def test_review_invalid_action_reprompts() -> None:
    entries = [_entry()]
    actioned = review(entries, inp=io.StringIO("x\na\n"))
    assert actioned == 1
    assert entries[0].operator_flag == "accept"


def test_review_truncation_does_not_alter_entry_text() -> None:
    """The display truncates long text, but the entry's stored text is unchanged."""
    entries = [_entry()]
    long_text = "x" * 5000
    entries[0].op_post_text = long_text
    review(entries, inp=io.StringIO("a\n"), max_chars_per_field=100)
    assert entries[0].op_post_text == long_text
