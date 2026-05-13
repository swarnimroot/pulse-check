"""CLI: interactively review the deliberation gold-set JSONL — bite 13.c.4.

Mirror of ``scripts/review_gold_set.py`` but for ``DeliberationGoldEntry``:
the per-entry display renders the thread (title + body + OP / OTHER
top-level comments) and Sonnet's deliberation prediction, then prompts:

    [a] accept     mark as verified
    [f] flag       mark as flagged, with optional note
    [c] correct    supply corrected labels (JSON object — see below)
    [s] skip       leave entry unchanged, move on
    [q] quit       save progress + exit

Corrected labels schema (JSON object — mirrors DeliberationPrediction)::

    {
      "is_deliberation": true,
      "is_resolved": false,
      "products_discussed": ["rog_strix_g16"],
      "chosen_product_id": null,
      "chosen_external_name": null,
      "confidence": 0.85
    }

Usage::

    python scripts/review_deliberation_gold_set.py data/gold_sets/deliberation_v1.jsonl

Already-reviewed entries (``operator_flag is not None``) are skipped so the
operator can resume partial reviews. Text fields are truncated to
``--max-chars-per-field`` (default 2000) per field for terminal sanity;
operator can inspect the raw JSONL for full text.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import TextIO

from pulse_check.eval.deliberation_gold_set import (
    DeliberationGoldEntry,
    read_deliberation_gold_jsonl,
    write_deliberation_gold_jsonl,
)
from pulse_check.logging_config import configure_logging

log = logging.getLogger("pulse_check.scripts.review_deliberation_gold_set")

_VALID_ACTIONS = {"a", "f", "c", "s", "q"}
_DEFAULT_MAX_CHARS_PER_FIELD = 2000


def _truncate(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n... [truncated; {len(text) - max_chars} more chars]"


def _format_comments_block(label: str, comments: list[str], max_chars: int) -> list[str]:
    if not comments:
        return [f"{label} (0): —"]
    lines = [f"{label} ({len(comments)}):"]
    for i, comment in enumerate(comments, start=1):
        lines.append(f"  [{i}] {_truncate(comment, max_chars)}")
    return lines


def _format_entry(
    entry: DeliberationGoldEntry,
    *,
    idx: int,
    total: int,
    max_chars: int,
) -> str:
    pred = entry.sonnet_prediction or {}
    rule = entry.force_include_rule
    rule_line = f"force_include_rule: {rule}" if rule else "force_include_rule: (none)"
    lines = [
        f"=== entry {idx}/{total} — thread_mention_id={entry.thread_mention_id} ===",
        rule_line,
        f"product_universe: {', '.join(entry.product_universe_ids) or '(empty)'}",
        f"attributed_primary: {', '.join(entry.attributed_primary_product_ids) or '(empty)'}",
        "",
        f"title: {entry.op_post_title}",
        "",
        "op_post_text:",
        _truncate(entry.op_post_text, max_chars),
        "",
    ]
    lines.extend(
        _format_comments_block(
            "op_top_level_comments", entry.op_top_level_comments, max_chars
        )
    )
    lines.append("")
    lines.extend(
        _format_comments_block(
            "other_top_level_comments", entry.other_top_level_comments, max_chars
        )
    )
    lines.extend([
        "",
        "sonnet prediction:",
        f"  is_deliberation:      {pred.get('is_deliberation')}",
        f"  is_resolved:          {pred.get('is_resolved')}",
        f"  products_discussed:   {pred.get('products_discussed')}",
        f"  chosen_product_id:    {pred.get('chosen_product_id')}",
        f"  chosen_external_name: {pred.get('chosen_external_name')}",
        f"  confidence:           {pred.get('confidence')}",
        "",
        "[a]ccept  [f]lag  [c]orrect  [s]kip  [q]uit",
    ])
    return "\n".join(lines)


def _read_action(inp: TextIO) -> str:
    while True:
        choice = inp.readline().strip().lower()
        if choice in _VALID_ACTIONS:
            return choice
        print(f"unknown action {choice!r}; use one of {sorted(_VALID_ACTIONS)}")


def _read_corrected_labels(inp: TextIO) -> dict[str, object] | None:
    print(
        "corrected labels as JSON object (e.g. "
        '{"is_deliberation":true,"is_resolved":true,'
        '"products_discussed":["rog_strix_g16"],'
        '"chosen_product_id":"rog_strix_g16",'
        '"chosen_external_name":null,"confidence":0.9}):'
    )
    raw = inp.readline().strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"JSON parse error: {exc}; leaving entry unchanged")
        return None
    if not isinstance(parsed, dict):
        print("expected a JSON object (dict); leaving entry unchanged")
        return None
    if "is_deliberation" not in parsed:
        print("expected at least 'is_deliberation' key; leaving entry unchanged")
        return None
    return parsed


def _review_entry(entry: DeliberationGoldEntry, *, inp: TextIO) -> bool:
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
            return True
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
    entries: list[DeliberationGoldEntry],
    *,
    inp: TextIO = sys.stdin,
    max_chars_per_field: int = _DEFAULT_MAX_CHARS_PER_FIELD,
) -> int:
    """Walk entries, prompting for an action per unreviewed one.

    Returns the count of newly-actioned entries (accept + flag + correct).
    """
    actioned = 0
    for idx, entry in enumerate(entries, start=1):
        if entry.operator_flag is not None:
            continue
        print(_format_entry(entry, idx=idx, total=len(entries), max_chars=max_chars_per_field))
        pre_flag = entry.operator_flag
        keep_going = _review_entry(entry, inp=inp)
        if entry.operator_flag != pre_flag:
            actioned += 1
        if not keep_going:
            break
    return actioned


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pulse-check review-deliberation-gold-set",
        description="Interactively review a deliberation gold-set JSONL file.",
    )
    parser.add_argument("path", type=Path, help="Path to the JSONL gold set.")
    parser.add_argument(
        "--max-chars-per-field",
        type=int,
        default=_DEFAULT_MAX_CHARS_PER_FIELD,
        help=(
            "Truncate each text field (op_post_text + per-comment text) to this "
            "many chars. 0 disables truncation. Default: %(default)s."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    configure_logging()

    if not args.path.exists():
        log.error("gold set not found: %s", args.path)
        return 1

    entries = read_deliberation_gold_jsonl(args.path)
    unreviewed = sum(1 for e in entries if e.operator_flag is None)
    print(f"loaded {len(entries)} entries from {args.path} ({unreviewed} unreviewed)")

    actioned = review(entries, max_chars_per_field=args.max_chars_per_field)

    write_deliberation_gold_jsonl(entries, args.path)
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
