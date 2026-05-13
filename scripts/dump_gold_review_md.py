"""Render aspect + deliberation v2 gold sets to markdown for bulk visual review.

Session 30 bite 30.b/30.c. Writes two markdown files alongside the JSONLs:

  data/gold_sets/aspect_tagging_v2_review.md
  data/gold_sets/deliberation_v2_review.md

Priority entries (per session-30 review-prioritization rules) are flagged
with a banner at the top of each entry so they're easy to scan for.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ASPECT_PATH = Path("data/gold_sets/aspect_tagging_v2.jsonl")
DELIB_PATH = Path("data/gold_sets/deliberation_v2.jsonl")
ASPECT_OUT = Path("data/gold_sets/aspect_tagging_v2_review.md")
DELIB_OUT = Path("data/gold_sets/deliberation_v2_review.md")

_TEXT_CAP = 600


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                entries.append(json.loads(line))
    return entries


def _trunc(text: str | None, cap: int = _TEXT_CAP) -> str:
    if not text:
        return ""
    if len(text) <= cap:
        return text
    return text[:cap] + "…"


def _render_aspect(entries: list[dict[str, Any]]) -> str:
    out: list[str] = []
    out.append(f"# Aspect gold set v2 — {len(entries)} entries\n")
    out.append(
        "Priority slice: entries with **no aspects** OR `source_type=reddit_comment` "
        "(thin bucket — 6 entries represent the whole source).\n"
    )
    for i, e in enumerate(entries, 1):
        is_zero = len(e.get("sonnet_labels") or []) == 0
        is_thin = e.get("source_type") == "reddit_comment"
        banner = ""
        if is_zero and is_thin:
            banner = " **[PRIORITY: zero-aspect + reddit_comment]**"
        elif is_zero:
            banner = " **[PRIORITY: zero-aspect]**"
        elif is_thin:
            banner = " **[PRIORITY: thin-bucket reddit_comment]**"
        reviewed = e.get("operator_flag")
        flag = f" *(operator_flag={reviewed})*" if reviewed else ""

        out.append(
            f"\n## {i}. `{e['mention_id']}` — "
            f"{e['product_display_name']} ({e['source_type']}){banner}{flag}\n"
        )
        out.append(f"**Text:** {_trunc(e.get('mention_text'))}\n")
        labels = e.get("sonnet_labels") or []
        if labels:
            out.append("**Sonnet labels:**\n")
            for t in labels:
                out.append(
                    f"- `{t.get('aspect')}` / {t.get('polarity')} / "
                    f"{t.get('intensity')} (conf={t.get('confidence')})"
                )
        else:
            out.append("**Sonnet labels:** *(none)*\n")
    return "\n".join(out)


def _render_deliberation(entries: list[dict[str, Any]]) -> str:
    out: list[str] = []
    out.append(f"# Deliberation gold set v2 — {len(entries)} entries\n")
    out.append(
        "Priority slice: entries where Sonnet said "
        "`is_deliberation=True AND is_resolved=False` (these answer the "
        "OP-strictness question), OR where `chosen_external_name` is set "
        "(the new v2 channel — should be 1 entry).\n"
    )
    for i, e in enumerate(entries, 1):
        pred = e.get("sonnet_prediction") or {}
        is_delib = pred.get("is_deliberation")
        is_resolved = pred.get("is_resolved")
        cpid = pred.get("chosen_product_id")
        cext = pred.get("chosen_external_name")
        banner = ""
        if cext is not None:
            banner = f" **[PRIORITY: chosen_external_name={cext!r}]**"
        elif is_delib and not is_resolved:
            banner = " **[PRIORITY: deliberation-not-resolved]**"
        reviewed = e.get("operator_flag")
        flag = f" *(operator_flag={reviewed})*" if reviewed else ""

        out.append(
            f"\n## {i}. `{e['thread_mention_id']}`{banner}{flag}\n"
        )
        out.append(
            f"**Sonnet says:** is_deliberation={is_delib}  "
            f"is_resolved={is_resolved}  "
            f"chosen_product_id={cpid!r}  "
            f"chosen_external_name={cext!r}\n"
        )
        title = e.get("op_post_title") or "*(no title)*"
        out.append(f"**OP title:** {title}\n")
        out.append(f"**OP post:** {_trunc(e.get('op_post_text'))}\n")
        attributed = e.get("attributed_primary_product_ids") or []
        out.append(f"**Tracked products primarily attributed:** {attributed}\n")
        comments_op = e.get("op_top_level_comments") or []
        comments_other = e.get("other_top_level_comments") or []
        out.append(
            f"**Comments:** OP top-level={len(comments_op)} · "
            f"other top-level={len(comments_other)}"
        )
    return "\n".join(out)


def main() -> int:
    aspect = _load_jsonl(ASPECT_PATH)
    delib = _load_jsonl(DELIB_PATH)
    ASPECT_OUT.write_text(_render_aspect(aspect), encoding="utf-8")
    DELIB_OUT.write_text(_render_deliberation(delib), encoding="utf-8")
    print(f"wrote {ASPECT_OUT} ({len(aspect)} entries)")
    print(f"wrote {DELIB_OUT} ({len(delib)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
