"""Opus-adjudicated weak-bucket gold scrub for aspect_tagging_v2 (session 31).

Per ARCH §6.6 (Opus carve-out): runs Opus 4.7 as an independent adjudicator
on (mention, weak-aspect) pairs surfaced as false-negatives in
``data/eval_results/{ts}_aspect_tagging.json`` — cases where Sonnet labeled
software_experience / aesthetics / support_warranty and Haiku did not.
Opus arbitrates whether the Sonnet label is substantive or merely a passing
mention.

Two phases via CLI flags:

- default (adjudicate)::

    python scripts/adjudicate_weak_bucket_gold.py \\
        --eval-report data/eval_results/20260513_184513_aspect_tagging.json

  Calls Opus per disagreement, writes verdicts to
  ``data/eval_results/{ts}_opus_adjudication_verdicts.jsonl`` (append-mode,
  one verdict per line — partial output survives crashes).

- apply::

    python scripts/adjudicate_weak_bucket_gold.py \\
        --apply data/eval_results/{ts}_opus_adjudication_verdicts.jsonl

  For each "over-labeled" or "wrong" verdict, updates the matching gold
  entry: sets ``operator_flag='corrected'``, sets ``operator_labels`` to
  ``sonnet_labels`` minus the over-labeled tuple, appends to
  ``operator_notes`` a one-line trace. ``.bak`` sibling written first.

Cache: ``call_with_cache`` keys each Opus call on
``(mention_id, aspect, polarity, intensity)`` × ``aspect_adjudication_v1`` ×
``claude-opus-4-7`` × ``0.0``. Re-running adjudicate mode is free after
the first pass (cache hits).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from pulse_check.eval.gold_set import read_jsonl, write_jsonl
from pulse_check.llm_cache import LlmResponse, call_with_cache
from pulse_check.logging_config import configure_logging
from pulse_check.settings import get_settings
from pulse_check.storage.enums import Aspect
from pulse_check.storage.session import session_scope
from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.tagging.aspect_classifier import _ASPECT_DEFS

log = logging.getLogger("pulse_check.scripts.adjudicate_weak_bucket_gold")

ADJUDICATION_PROMPT_VERSION = "aspect_adjudication_v1"
OPUS_MODEL = "claude-opus-4-7"
WEAK_BUCKETS = {"software_experience", "aesthetics", "support_warranty"}
VALID_VERDICTS = {"valid", "over-labeled", "wrong", "ambiguous"}

_PROMPT_TEMPLATE = """You are an independent quality-control adjudicator for product-review aspect \
tagging.

A previous labeler claimed that this product-review mention discusses the aspect "{aspect}" \
with polarity "{polarity}" and intensity "{intensity}".

Your task: decide if the claim is defensible. Be strict — over-labeling (tagging a passing \
word as a real signal) is the most common error to catch.

Aspect being audited: {aspect}
- Definition: {aspect_definition}
- Claimed polarity: {polarity}
- Claimed intensity: {intensity}

Mention text:
\"\"\"
{mention_text}
\"\"\"

Verdicts (choose exactly one):
- "valid": the mention substantively discusses {aspect} (at least one full sentence \
dedicated to this aspect), and the polarity + intensity are reasonable.
- "over-labeled": {aspect} is mentioned only as a passing word or brief phrase, NOT a \
real signal. The labeler over-labeled.
- "wrong": the mention discusses {aspect}, but the polarity or intensity is materially \
incorrect.
- "ambiguous": borderline — either "valid" or "over-labeled" is defensible.

Output JSON only, no prose, no markdown fences:
{{"verdict": "valid" | "over-labeled" | "wrong" | "ambiguous", \
"reasoning": "<1-2 sentence justification, <=30 words>"}}
"""


def build_prompt(
    *, mention_text: str, aspect: str, polarity: str, intensity: str
) -> str:
    return _PROMPT_TEMPLATE.format(
        aspect=aspect,
        aspect_definition=_ASPECT_DEFS[Aspect(aspect)],
        polarity=polarity,
        intensity=intensity,
        mention_text=mention_text,
    )


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="adjudicate-weak-bucket-gold")
    p.add_argument(
        "--eval-report",
        type=Path,
        help="Path to the aspect-tagging eval JSON report (adjudicate mode).",
    )
    p.add_argument(
        "--gold-set",
        type=Path,
        default=Path("data/gold_sets/aspect_tagging_v2.jsonl"),
        help="Path to the gold-set JSONL (apply mode writes back here).",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/eval_results"),
        help="Directory for the verdicts JSONL (adjudicate mode).",
    )
    p.add_argument(
        "--apply",
        type=Path,
        help="Apply mode: path to a verdicts JSONL produced by a prior run.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Print one line per Opus call (default: progress every 5 calls).",
    )
    return p.parse_args(argv)


def _collect_weak_fn_pairs(
    eval_report: dict[str, Any],
) -> list[dict[str, Any]]:
    """Pull weak-bucket FN cases out of the eval-runner JSON report.

    Returns one row per (mention, weak-aspect) FN tuple — multiple per
    mention if Sonnet added more than one weak-bucket label.
    """
    pairs: list[dict[str, Any]] = []
    for d in eval_report["disagreements"]:
        gold_by_aspect = {t["aspect"]: t for t in d["gold"]}
        pred_aspects = {t["aspect"] for t in d["pred"]}
        for aspect in WEAK_BUCKETS:
            if aspect in gold_by_aspect and aspect not in pred_aspects:
                t = gold_by_aspect[aspect]
                pairs.append(
                    {
                        "mention_id": d["mention_id"],
                        "product_display_name": d["product_display_name"],
                        "mention_text": d["mention_text"],
                        "aspect": aspect,
                        "polarity": t["polarity"],
                        "intensity": t["intensity"],
                    }
                )
    return pairs


def _adjudicate_one(
    client: AnthropicClient,
    session: Session,
    pair: dict[str, Any],
) -> dict[str, Any]:
    """Run Opus on one (mention, weak-aspect) pair via the cached-call contract."""
    input_payload: dict[str, Any] = {
        "mention_id": pair["mention_id"],
        "aspect": pair["aspect"],
        "polarity": pair["polarity"],
        "intensity": pair["intensity"],
    }

    def _compute() -> LlmResponse:
        prompt = build_prompt(
            mention_text=pair["mention_text"],
            aspect=pair["aspect"],
            polarity=pair["polarity"],
            intensity=pair["intensity"],
        )
        return client.generate_json(
            model=OPUS_MODEL,
            prompt=prompt,
            temperature=0.0,
            max_tokens=512,
        )

    response = call_with_cache(
        session,
        task="aspect_adjudication",
        input_payload=input_payload,
        prompt_version=ADJUDICATION_PROMPT_VERSION,
        model=OPUS_MODEL,
        temperature=0.0,
        compute=_compute,
    )
    parsed = response.parsed_output
    if not isinstance(parsed, dict):
        msg = f"adjudicator returned non-object: {type(parsed).__name__}"
        raise ValueError(msg)
    verdict = parsed.get("verdict")
    reasoning = parsed.get("reasoning", "")
    if verdict not in VALID_VERDICTS:
        msg = f"adjudicator returned unknown verdict: {verdict!r}"
        raise ValueError(msg)
    return {
        "mention_id": pair["mention_id"],
        "product_display_name": pair["product_display_name"],
        "aspect": pair["aspect"],
        "polarity": pair["polarity"],
        "intensity": pair["intensity"],
        "verdict": verdict,
        "reasoning": reasoning,
    }


def run_adjudicate(args: argparse.Namespace) -> int:
    if args.eval_report is None:
        log.error("--eval-report is required in adjudicate mode")
        return 2
    if not args.eval_report.exists():
        log.error("eval report not found: %s", args.eval_report)
        return 2

    settings = get_settings()
    if not settings.anthropic_api_key:
        log.error("ANTHROPIC_API_KEY not set in environment")
        return 2

    report = json.loads(args.eval_report.read_text(encoding="utf-8"))
    pairs = _collect_weak_fn_pairs(report)
    log.info("weak-bucket FN pairs: %d", len(pairs))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = args.output_dir / f"{ts}_opus_adjudication_verdicts.jsonl"

    client = AnthropicClient(api_key=settings.anthropic_api_key, timeout=180.0)
    succeeded = 0
    failed: list[tuple[dict[str, Any], str]] = []
    verdict_counts: dict[str, int] = {v: 0 for v in VALID_VERDICTS}

    with out_path.open("w", encoding="utf-8") as fh, session_scope() as session:
        for i, pair in enumerate(pairs, 1):
            try:
                verdict_row = _adjudicate_one(client, session, pair)
                fh.write(json.dumps(verdict_row, ensure_ascii=False) + "\n")
                fh.flush()
                verdict_counts[verdict_row["verdict"]] += 1
                succeeded += 1
                if args.verbose or i % 5 == 0 or i == len(pairs):
                    log.info(
                        "[%d/%d] %s · %s → %s",
                        i,
                        len(pairs),
                        pair["mention_id"][:50],
                        pair["aspect"],
                        verdict_row["verdict"],
                    )
            except Exception as exc:
                log.warning(
                    "[%d/%d] %s · %s FAILED: %s",
                    i,
                    len(pairs),
                    pair["mention_id"][:50],
                    pair["aspect"],
                    exc,
                )
                failed.append((pair, str(exc)))

    print("=" * 60)
    print("Opus weak-bucket adjudication complete")
    print("=" * 60)
    print(f"Pairs:      {len(pairs)}")
    print(f"Succeeded:  {succeeded}")
    print(f"Failed:     {len(failed)}")
    print("Verdicts:")
    for v in ("valid", "over-labeled", "wrong", "ambiguous"):
        print(f"  {v:>14}: {verdict_counts[v]}")
    print(f"Output:     {out_path}")
    print("=" * 60)
    if failed:
        print("Failures (first 5):")
        for pair, err in failed[:5]:
            print(f"  {pair['mention_id']} · {pair['aspect']}: {err}")
        return 1
    return 0


def run_apply(args: argparse.Namespace) -> int:
    verdicts_path = args.apply
    if not verdicts_path.exists():
        log.error("verdicts file not found: %s", verdicts_path)
        return 2
    if not args.gold_set.exists():
        log.error("gold set not found: %s", args.gold_set)
        return 2

    verdicts: list[dict[str, Any]] = []
    with verdicts_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if line:
                verdicts.append(json.loads(line))
    log.info("loaded %d verdicts from %s", len(verdicts), verdicts_path)

    # Index "remove" verdicts by (mention_id, aspect)
    removals: dict[tuple[str, str], dict[str, Any]] = {}
    for v in verdicts:
        if v["verdict"] in ("over-labeled", "wrong"):
            removals[(v["mention_id"], v["aspect"])] = v
    log.info("removals (over-labeled + wrong): %d", len(removals))

    entries = read_jsonl(args.gold_set)
    log.info("loaded %d gold entries", len(entries))

    # .bak sibling
    bak_path = args.gold_set.with_suffix(args.gold_set.suffix + ".session31_bak")
    shutil.copy2(args.gold_set, bak_path)
    log.info("backup written: %s", bak_path)

    n_modified = 0
    for entry in entries:
        if entry.operator_flag == "flag":
            continue
        per_entry_removals = [
            v
            for (mid, _), v in removals.items()
            if mid == entry.mention_id
        ]
        if not per_entry_removals:
            continue
        aspects_to_drop = {v["aspect"] for v in per_entry_removals}
        kept = [
            t for t in entry.sonnet_labels if t.get("aspect") not in aspects_to_drop
        ]
        entry.operator_flag = "corrected"
        entry.operator_labels = kept
        notes_prefix = entry.operator_notes or ""
        trace = (
            "; ".join(
                f"opus-31:{v['aspect']}={v['verdict']}" for v in per_entry_removals
            )
        )
        entry.operator_notes = (notes_prefix + " | " + trace).strip(" |") if notes_prefix else trace
        n_modified += 1

    write_jsonl(entries, args.gold_set)
    print("=" * 60)
    print("Apply complete")
    print("=" * 60)
    print(f"Verdicts loaded:   {len(verdicts)}")
    print(f"Removals to apply: {len(removals)}")
    print(f"Entries modified:  {n_modified}")
    print(f"Backup:            {bak_path}")
    print(f"Gold rewritten:    {args.gold_set}")
    print("=" * 60)
    return 0


def main(argv: list[str]) -> int:
    configure_logging()
    args = _parse_args(argv)
    if args.apply is not None:
        return run_apply(args)
    return run_adjudicate(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
