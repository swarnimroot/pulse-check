"""Interactive review CLI tests.

The CLI prompts on stdin and writes to stdout; we drive it with an in-memory
``io.StringIO`` so we can assert on the state transitions deterministically.
"""

from __future__ import annotations

import io

from pulse_check.eval.gold_set import GoldSetEntry
from pulse_check.storage.enums import SourceType

# Importing from the `scripts/` module requires the scripts dir on sys.path;
# the test runner already has the repo root on sys.path, so
# `scripts.review_gold_set` imports cleanly as long as scripts has an
# `__init__.py` (it does).
from scripts.review_gold_set import review


def _entry(mention_id: str = "m1") -> GoldSetEntry:
    return GoldSetEntry(
        mention_id=mention_id,
        product_id="aw16",
        mention_text="example mention text",
        source_type=SourceType.REDDIT_POST,
        product_display_name="Alienware 16 Aurora",
        sonnet_labels=[
            {
                "aspect": "thermals",
                "polarity": "negative",
                "intensity": "high",
                "confidence": 0.9,
            }
        ],
    )


def test_review_accept_sets_flag() -> None:
    entries = [_entry()]
    actioned = review(entries, inp=io.StringIO("a\n"))
    assert actioned == 1
    assert entries[0].operator_flag == "accept"
    assert entries[0].operator_labels is None


def test_review_flag_captures_optional_note() -> None:
    entries = [_entry()]
    # 'f' then note text on next line
    actioned = review(entries, inp=io.StringIO("f\nSonnet missed intensity level\n"))
    assert actioned == 1
    assert entries[0].operator_flag == "flag"
    assert entries[0].operator_notes == "Sonnet missed intensity level"


def test_review_flag_blank_note_stays_none() -> None:
    entries = [_entry()]
    actioned = review(entries, inp=io.StringIO("f\n\n"))
    assert actioned == 1
    assert entries[0].operator_flag == "flag"
    assert entries[0].operator_notes is None


def test_review_correct_captures_labels_and_note() -> None:
    entries = [_entry()]
    labels = '[{"aspect":"thermals","polarity":"negative","intensity":"medium","confidence":0.7}]'
    # 'c' then labels JSON then note
    actioned = review(entries, inp=io.StringIO(f"c\n{labels}\nintensity is medium, not high\n"))
    assert actioned == 1
    assert entries[0].operator_flag == "corrected"
    assert entries[0].operator_labels == [
        {"aspect": "thermals", "polarity": "negative", "intensity": "medium", "confidence": 0.7}
    ]
    assert entries[0].operator_notes == "intensity is medium, not high"


def test_review_correct_with_bad_json_leaves_entry_unchanged() -> None:
    entries = [_entry()]
    actioned = review(entries, inp=io.StringIO("c\nnot-valid-json\n"))
    # Entry stays unflagged when the corrected JSON is unparseable.
    assert actioned == 0
    assert entries[0].operator_flag is None


def test_review_correct_with_non_list_json_leaves_unchanged() -> None:
    entries = [_entry()]
    actioned = review(entries, inp=io.StringIO('c\n{"not": "a list"}\n'))
    assert actioned == 0
    assert entries[0].operator_flag is None


def test_review_skip_does_nothing() -> None:
    entries = [_entry()]
    actioned = review(entries, inp=io.StringIO("s\n"))
    assert actioned == 0
    assert entries[0].operator_flag is None


def test_review_quit_stops_iteration() -> None:
    entries = [_entry("m1"), _entry("m2"), _entry("m3")]
    # Accept first, quit on second — third is untouched.
    actioned = review(entries, inp=io.StringIO("a\nq\n"))
    assert actioned == 1
    assert entries[0].operator_flag == "accept"
    assert entries[1].operator_flag is None
    assert entries[2].operator_flag is None


def test_review_skips_already_reviewed_entries() -> None:
    entries = [_entry("m1"), _entry("m2")]
    entries[0].operator_flag = "accept"  # pre-reviewed
    # Only one prompt because entry 0 is skipped.
    actioned = review(entries, inp=io.StringIO("f\n\n"))
    assert actioned == 1
    assert entries[0].operator_flag == "accept"  # unchanged
    assert entries[1].operator_flag == "flag"


def test_review_invalid_action_reprompts() -> None:
    entries = [_entry()]
    # 'x' is invalid; second token 'a' accepts.
    actioned = review(entries, inp=io.StringIO("x\na\n"))
    assert actioned == 1
    assert entries[0].operator_flag == "accept"
