"""Bulk-accept non-priority gold-set entries so interactive review only shows the priority slice.

Session 30 bite 30.b/30.c. Mutates two v2 JSONLs in place (with a `.bak`
sibling created first):

  aspect_tagging_v2.jsonl   priority = zero-aspect entries OR reddit_comment source
  deliberation_v2.jsonl     priority = (is_deliberation=True AND is_resolved=False)
                                       OR chosen_external_name set

Non-priority entries are written back with `operator_flag = "accept"`.
Priority entries are left as-is so `scripts/review_gold_set.py` and
`scripts/review_deliberation_gold_set.py` show them on next launch.

Idempotent: entries that already have `operator_flag is not None` are
preserved untouched.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

ASPECT_PATH = Path("data/gold_sets/aspect_tagging_v2.jsonl")
DELIB_PATH = Path("data/gold_sets/deliberation_v2.jsonl")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                entries.append(json.loads(line))
    return entries


def _write_jsonl(path: Path, entries: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def _aspect_is_priority(entry: dict[str, Any]) -> bool:
    return (
        len(entry.get("sonnet_labels") or []) == 0
        or entry.get("source_type") == "reddit_comment"
    )


def _deliberation_is_priority(entry: dict[str, Any]) -> bool:
    pred = entry.get("sonnet_prediction") or {}
    is_delib = bool(pred.get("is_deliberation"))
    is_resolved = bool(pred.get("is_resolved"))
    chosen_external = pred.get("chosen_external_name")
    return (is_delib and not is_resolved) or chosen_external is not None


def _process(
    path: Path,
    predicate: Callable[[dict[str, Any]], bool],
) -> tuple[int, int, int]:
    """Return (accepted, priority_left, already_reviewed)."""
    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        shutil.copy(path, backup)

    entries = _load_jsonl(path)
    accepted = 0
    priority_left = 0
    already = 0

    for e in entries:
        if e.get("operator_flag") is not None:
            already += 1
            continue
        if predicate(e):
            priority_left += 1
        else:
            e["operator_flag"] = "accept"
            accepted += 1

    _write_jsonl(path, entries)
    return accepted, priority_left, already


def main() -> int:
    a_acc, a_pri, a_done = _process(ASPECT_PATH, _aspect_is_priority)
    print(f"{ASPECT_PATH.name}:")
    print(f"  bulk-accepted:    {a_acc}")
    print(f"  priority-left:    {a_pri}")
    print(f"  already-reviewed: {a_done}")

    d_acc, d_pri, d_done = _process(DELIB_PATH, _deliberation_is_priority)
    print(f"{DELIB_PATH.name}:")
    print(f"  bulk-accepted:    {d_acc}")
    print(f"  priority-left:    {d_pri}")
    print(f"  already-reviewed: {d_done}")

    print()
    print(f"TOTAL priority entries left for interactive review: {a_pri + d_pri}")
    print("Backups written to *.bak siblings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
