"""CLI: interactively review a gold set.

For each un-reviewed entry, prints the mention text + Sonnet labels and
prompts the operator for an action:

    [a] accept     mark as verified
    [f] flag       mark as flagged, with optional note
    [c] correct    supply corrected labels (JSON list of tag objects)
    [s] skip       leave entry unchanged, move on
    [q] quit       save progress + exit

Usage::

    python scripts/review_gold_set.py data/gold_sets/aspect_tagging_v1.jsonl

Already-reviewed entries (``operator_flag is not None``) are skipped
automatically so the operator can resume partial reviews.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import TextIO

from pulse_check.eval.gold_set import GoldSetEntry, read_jsonl, write_jsonl
from pulse_check.logging_config import configure_logging

log = logging.getLogger("pulse_check.scripts.review_gold_set")

_VALID_ACTIONS = {"a", "f", "c", "s", "q"}


def _format_entry(entry: GoldSetEntry, idx: int, total: int) -> str:
    lines = [
        f"=== entry {idx}/{total} — mention_id={entry.mention_id} ===",
        f"product: {entry.product_display_name} ({entry.product_id})",
        f"source:  {entry.source_type.value}",
        "",
        "text:",
        entry.mention_text,
        "",
        "sonnet labels:",
    ]
    if not entry.sonnet_labels:
        lines.append("  (no aspects)")
    else:
        for tag in entry.sonnet_labels:
            lines.append(
                "  - aspect={aspect} polarity={polarity} intensity={intensity}"
                " confidence={confidence}".format(**tag)
            )
    lines.append("")
    lines.append("[a]ccept  [f]lag  [c]orrect  [s]kip  [q]uit")
    return "\n".join(lines)


def _read_action(inp: TextIO) -> str:
    while True:
        choice = inp.readline().strip().lower()
        if choice in _VALID_ACTIONS:
            return choice
        print(f"unknown action {choice!r}; use one of {sorted(_VALID_ACTIONS)}")


def _read_corrected_labels(inp: TextIO) -> list[dict[str, object]] | None:
    print(
        "corrected labels as JSON list (e.g. "
        '[{"aspect":"thermals","polarity":"negative","intensity":"high","confidence":0.9}]'
        "):"
    )
    raw = inp.readline().strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"JSON parse error: {exc}; leaving entry unchanged")
        return None
    if not isinstance(parsed, list) or not all(isinstance(item, dict) for item in parsed):
        print("expected a JSON list of tag objects; leaving entry unchanged")
        return None
    return parsed


def _review_entry(entry: GoldSetEntry, *, inp: TextIO) -> bool:
    """Prompt for one action. Returns False to signal 'quit'."""
    action = _read_action(inp)
    if action == "a":
        entry.operator_flag = "accept"
    elif action == "f":
        entry.operator_flag = "flag"
        print("note (optional):")
        entry.operator_notes = inp.readline().strip() or None
    elif action == "c":
        corrected = _read_corrected_labels(inp)
        if corrected is None:
            return True  # leave unchanged, keep going
        entry.operator_flag = "corrected"
        entry.operator_labels = corrected
        print("note (optional):")
        entry.operator_notes = inp.readline().strip() or None
    elif action == "s":
        pass
    elif action == "q":
        return False
    return True


def review(
    entries: list[GoldSetEntry],
    *,
    inp: TextIO = sys.stdin,
) -> int:
    """Walk entries in order, prompting for an action per unreviewed one.

    Returns the count of newly-actioned entries (accept + flag + correct).
    """
    actioned = 0
    for idx, entry in enumerate(entries, start=1):
        if entry.operator_flag is not None:
            continue
        print(_format_entry(entry, idx=idx, total=len(entries)))
        pre_flag = entry.operator_flag
        keep_going = _review_entry(entry, inp=inp)
        if entry.operator_flag != pre_flag:
            actioned += 1
        if not keep_going:
            break
    return actioned


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pulse-check review-gold-set",
        description="Interactively review a gold-set JSONL file.",
    )
    parser.add_argument("path", type=Path, help="Path to the JSONL gold set.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    configure_logging()

    if not args.path.exists():
        log.error("gold set not found: %s", args.path)
        return 1

    entries = read_jsonl(args.path)
    unreviewed = sum(1 for e in entries if e.operator_flag is None)
    print(f"loaded {len(entries)} entries from {args.path} ({unreviewed} unreviewed)")

    actioned = review(entries)

    write_jsonl(entries, args.path)
    accepted = sum(1 for e in entries if e.operator_flag == "accept")
    flagged = sum(1 for e in entries if e.operator_flag == "flag")
    corrected = sum(1 for e in entries if e.operator_flag == "corrected")
    print(
        f"saved {len(entries)} entries to {args.path} "
        f"(actioned this session: {actioned}; "
        f"total accepted={accepted} flagged={flagged} corrected={corrected})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
