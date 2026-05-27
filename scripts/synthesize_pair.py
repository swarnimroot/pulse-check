"""CLI: pair-brief synthesis for one product pair OR a batch from a pair-plan YAML.

Persists a `Brief` row with the §6.4 PairBriefNarrative shape plus
`flagged_citation_issues` from the citation validator. Soft-warn policy: the
brief is persisted even when the validator flags issues.

Usage::

    # one pair (lookup primary/comparator from pair_plan)
    python scripts/synthesize_pair.py \\
        --pair-plan configs/pair_plan_alienware_vs_all.yaml \\
        --pair-id alienware_16_aurora_vs_rog_strix_g16 \\
        --run-id run_wave5_v1

    # smoke a subset
    python scripts/synthesize_pair.py \\
        --pair-plan configs/pair_plan_alienware_vs_all.yaml \\
        --run-id run_wave5_v1 \\
        --limit 2

    # batch all pairs in the plan
    python scripts/synthesize_pair.py \\
        --pair-plan configs/pair_plan_alienware_vs_all.yaml \\
        --run-id run_wave5_v1

A `--commit-every N` knob commits between pairs so a mid-batch crash doesn't
discard paid LLM rows (mirrors `feedback_long_llm_batch_commits`). Default
commit-every is 1 (commit after each pair) since pairs are independent and
inexpensive.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from pulse_check.config.loader import load_pair_plan
from pulse_check.config.models import PairConfig
from pulse_check.logging_config import configure_logging
from pulse_check.settings import get_settings
from pulse_check.storage.session import get_sessionmaker
from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.synthesis.orchestrator import synthesize_pair

log = logging.getLogger("pulse_check.scripts.synthesize_pair")


def _select_pairs(
    all_pairs: list[PairConfig], *, only_pair_id: str | None, limit: int | None
) -> list[PairConfig]:
    if only_pair_id is not None:
        matches = [p for p in all_pairs if p.pair_id == only_pair_id]
        if not matches:
            msg = f"pair_id {only_pair_id!r} not found in pair plan"
            raise ValueError(msg)
        return matches
    if limit is not None and limit >= 0:
        return all_pairs[:limit]
    return list(all_pairs)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="synthesize_pair")
    parser.add_argument(
        "--pair-plan",
        required=True,
        type=Path,
        help="Path to pair-plan YAML (e.g. configs/pair_plan_alienware_vs_all.yaml)",
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="Run ID matching the aggregates_aspect_sku rows to synthesize against",
    )
    parser.add_argument(
        "--pair-id",
        default=None,
        help="Optional: synthesize only this pair_id (must exist in --pair-plan)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional: cap batch size to first N pairs in the plan",
    )
    parser.add_argument(
        "--commit-every",
        type=int,
        default=1,
        help="Commit DB session after every N pairs (default 1)",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    configure_logging()
    settings = get_settings()
    if not settings.anthropic_api_key:
        log.error("ANTHROPIC_API_KEY is not set; cannot call Anthropic.")
        return 2

    try:
        pair_plan = load_pair_plan(args.pair_plan)
    except Exception as exc:
        log.error("could not load pair plan: %s", exc)
        return 1

    try:
        targets = _select_pairs(
            list(pair_plan.pairs), only_pair_id=args.pair_id, limit=args.limit
        )
    except ValueError as exc:
        log.error("%s", exc)
        return 1

    if not targets:
        log.error("no pairs selected; nothing to do")
        return 1

    log.info(
        "synthesizing %d pair(s) against run_id=%s (commit-every=%d)",
        len(targets),
        args.run_id,
        args.commit_every,
    )

    client = AnthropicClient(api_key=settings.anthropic_api_key)
    factory = get_sessionmaker()
    session = factory()
    completed = 0
    flagged = 0
    try:
        for idx, pair in enumerate(targets, 1):
            try:
                brief = synthesize_pair(
                    session,
                    client=client,
                    run_id=args.run_id,
                    pair_id=pair.pair_id,
                    primary_product_id=pair.primary,
                    comparator_product_id=pair.comparator,
                )
            except ValueError as exc:
                log.error("pair %s skipped: %s", pair.pair_id, exc)
                continue

            narrative_dict = dict(brief.narrative)
            flags = narrative_dict.get("flagged_citation_issues", {}) or {}
            title = narrative_dict.get("brief_title", "")
            contrast = narrative_dict.get("contrast", {}) or {}
            contrast_text = contrast.get("text", "")
            cited = contrast.get("cited_mention_ids", []) or []
            is_valid = flags.get("is_valid")
            if not is_valid:
                flagged += 1
            log.info(
                "[%d/%d] pair=%s brief_id=%s prompt_version=%s is_valid=%s "
                "fabricated=%d out_of_context=%d empty=%d cites=%d title=%r",
                idx,
                len(targets),
                pair.pair_id,
                brief.brief_id,
                brief.prompt_version,
                is_valid,
                len(flags.get("fabricated_ids") or []),
                len(flags.get("out_of_context_ids") or []),
                len(flags.get("empty_claims") or []),
                len(cited),
                title,
            )
            print()
            print(f"Pair: {pair.pair_id}")
            print(f"Title: {title}")
            print(f"Contrast: {contrast_text}")
            print(f"Cited: {cited}")
            print(f"Validation: {json.dumps(flags)}")

            completed += 1
            if args.commit_every > 0 and completed % args.commit_every == 0:
                session.commit()
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    log.info(
        "done: %d/%d pair(s) synthesized; %d flagged by validator",
        completed,
        len(targets),
        flagged,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
