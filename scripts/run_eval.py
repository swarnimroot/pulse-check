"""CLI: run the aspect-tagging classifier eval against a gold set.

Usage::

    python scripts/run_eval.py
    python scripts/run_eval.py --truth operator
    python scripts/run_eval.py --provider qwen --gold-set data/gold_sets/aspect_tagging_v2.jsonl

Loads the gold set, runs the production aspect classifier (Haiku per
session-5 deviation; ``--provider qwen`` falls back to Ollama+Qwen for
symmetry with ``scripts/tag.py``), computes per-tuple micro-F1 (both
strict and ±1 intensity-tolerance) + per-aspect breakdown, writes a JSON
report to ``data/eval_results/{timestamp}_aspect_tagging.json``, and
prints a PASS/FAIL summary versus the 80% Wave 2 exit threshold (gated
on the loose metric as of session 37).

Truth modes:
- ``sonnet``: compare to Sonnet's labels as-is (treats Sonnet as oracle)
- ``operator``: compare only to operator-corrected entries (skips others)
- ``merged`` (default): operator_labels where corrected, else sonnet_labels
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

from pulse_check.eval.eval_runner import (
    EvalReport,
    TruthMode,
    disagreements,
    filter_by_content_types,
    report_to_dict,
    score_all,
)
from pulse_check.eval.gold_set import read_jsonl
from pulse_check.logging_config import configure_logging
from pulse_check.settings import get_settings
from pulse_check.storage.enums import ContentType
from pulse_check.storage.session import session_scope
from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.tagging.aspect_classifier import AspectClassifier
from pulse_check.tagging.ollama import OllamaClient

log = logging.getLogger("pulse_check.scripts.run_eval")

_DEFAULT_GOLD_SET = Path("data/gold_sets/aspect_tagging_v2.jsonl")
_DEFAULT_OUTPUT_DIR = Path("data/eval_results")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pulse-check run-eval",
        description=(
            "Score the production aspect classifier (Haiku by default) "
            "against a gold-set JSONL. Outputs per-tuple micro-F1, "
            "per-aspect breakdown, and a JSON report."
        ),
    )
    parser.add_argument(
        "--gold-set",
        type=Path,
        default=_DEFAULT_GOLD_SET,
        help=f"Path to gold-set JSONL. Default: {_DEFAULT_GOLD_SET}",
    )
    parser.add_argument(
        "--truth",
        choices=("sonnet", "operator", "merged"),
        default="merged",
        help=(
            "Truth source: 'sonnet' (Sonnet labels as oracle), "
            "'operator' (only operator-corrected entries), "
            "'merged' (operator where corrected, else Sonnet). Default: merged."
        ),
    )
    parser.add_argument(
        "--provider",
        choices=("haiku", "qwen"),
        default="haiku",
        help="Classifier provider. Default: haiku (production).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output JSON path. Default: "
            f"{_DEFAULT_OUTPUT_DIR}/{{timestamp}}_aspect_tagging.json"
        ),
    )
    parser.add_argument(
        "--exclude-content-types",
        nargs="+",
        choices=[ct.value for ct in ContentType],
        default=[ContentType.DEAL.value],
        metavar="TYPE",
        help=(
            "Drop gold-set entries whose ContentTypeTag matches any of these "
            "values. Mirrors scripts/run_stage_b.py production gate (default: "
            "'deal'). Pass an empty list (e.g. via shell trickery) to disable. "
            "Mentions without a ContentTypeTag row are also excluded "
            "(strict gate)."
        ),
    )
    return parser.parse_args(argv)


def _truth_caveat(
    truth_mode: str,
    *,
    provider: str,
    operator_corrected_count: int,
    total_entries: int,
) -> list[str] | None:
    """Multi-line truth-source caveat, or ``None`` if no caveat applies.

    - ``operator`` mode is never caveated (we're scoring real operator truth).
    - ``sonnet`` mode is always caveated (treating Sonnet as oracle).
    - ``merged`` mode is caveated unless all entries are operator-corrected.
    """
    if truth_mode == "operator":
        return None
    if truth_mode == "sonnet":
        return [
            "",
            "Truth-source caveat: comparing to Sonnet labels as oracle.",
            f"Headline reads as {provider}-vs-Sonnet AGREEMENT, not accuracy.",
            "For Wave 2 exit, run scripts/review_gold_set.py "
            "and re-run --truth operator.",
        ]
    # merged
    if operator_corrected_count == 0:
        return [
            "",
            "Truth-source caveat: 0 entries are operator-corrected; "
            "merged mode falls back entirely to Sonnet labels.",
            f"Headline reads as {provider}-vs-Sonnet AGREEMENT, not accuracy.",
            "For Wave 2 exit, run scripts/review_gold_set.py "
            "and re-run --truth operator.",
        ]
    if operator_corrected_count < total_entries:
        return [
            "",
            f"Truth-source caveat: {operator_corrected_count}/{total_entries} "
            "operator-corrected; the rest fall back to Sonnet labels.",
        ]
    return None  # 100% corrected under merged ≈ operator mode


def _format_summary(
    report: EvalReport,
    *,
    provider: str,
    model: str,
    truth_mode: str,
    gold_set_path: Path,
    operator_touched_count: int,
    operator_corrected_count: int,
    total_entries: int,
    pre_filter_count: int,
    exclude_content_types: list[str],
    output_path: Path,
) -> str:
    """Multi-line stdout summary with PASS/FAIL banner + truth caveat."""
    bar = "=" * 60
    verdict = "PASS" if report.passed else "FAIL"
    lines = [
        bar,
        "Aspect-tagging eval — Wave 2 exit gate",
        bar,
        f"Gold set:     {gold_set_path} ({pre_filter_count} entries; "
        f"{operator_touched_count} reviewed, "
        f"{operator_corrected_count} corrected)",
    ]
    if exclude_content_types:
        lines.append(
            f"Filter:       exclude={','.join(exclude_content_types)}  ->  "
            f"{total_entries} entries after content-type filter"
        )
    lines.extend(
        [
            f"Provider:     {provider} ({model})",
            f"Truth mode:   {truth_mode}",
            bar,
            f"Scored:       {report.scored_count} / {report.total_entries}  "
            f"(truth-skipped: {report.truth_skip_count}, "
            f"parse failures: {report.parse_failure_count})",
            f"Micro F1 (strict):  {report.micro.f1:.4f}  "
            f"(TP={report.micro.tp}, FP={report.micro.fp}, "
            f"FN={report.micro.fn})",
            f"Micro F1 (loose):   {report.micro_loose.f1:.4f}  "
            f"(TP={report.micro_loose.tp}, "
            f"FP={report.micro_loose.fp}, "
            f"FN={report.micro_loose.fn})  <- gate",
            f"Precision (loose):  {report.micro_loose.precision:.4f}",
            f"Recall (loose):     {report.micro_loose.recall:.4f}",
            f"Threshold:          {report.threshold:.2f}",
            f"Result:             {verdict}",
            bar,
        ]
    )
    caveat = _truth_caveat(
        truth_mode,
        provider=provider,
        operator_corrected_count=operator_corrected_count,
        total_entries=total_entries,
    )
    if caveat is not None:
        lines.extend(caveat)
    return "\n".join(lines) + f"\n\nFull report: {output_path}\n"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    configure_logging()
    settings = get_settings()

    if args.provider == "haiku" and not settings.anthropic_api_key:
        log.error("--provider haiku requires ANTHROPIC_API_KEY in env/.env")
        return 2

    if not args.gold_set.exists():
        log.error("gold set not found: %s", args.gold_set)
        return 2

    entries = read_jsonl(args.gold_set)
    if not entries:
        log.warning("gold set is empty: %s", args.gold_set)
        return 1

    truth_mode: TruthMode = args.truth
    exclude_content_types: frozenset[ContentType] = frozenset(
        ContentType(v) for v in args.exclude_content_types
    )
    pre_filter_count = len(entries)

    if args.provider == "haiku":
        client = AnthropicClient(api_key=settings.anthropic_api_key)
        model = settings.anthropic_haiku_model
        classifier = AspectClassifier(client, model=model)
        with session_scope() as session:
            entries = filter_by_content_types(
                session, entries, exclude=exclude_content_types
            )
            if exclude_content_types:
                log.info(
                    "content-type filter %s: %d → %d entries",
                    sorted(ct.value for ct in exclude_content_types),
                    pre_filter_count,
                    len(entries),
                )
            if not entries:
                log.warning("no entries remain after content-type filter")
                return 1
            log.info(
                "running eval: provider=haiku model=%s truth=%s entries=%d",
                model, truth_mode, len(entries),
            )
            scored = score_all(
                session,
                classifier=classifier,
                entries=entries,
                truth_mode=truth_mode,
            )
    else:
        with OllamaClient(host=settings.ollama_host) as ollama_client:
            model = settings.ollama_model
            classifier = AspectClassifier(ollama_client, model=model)
            with session_scope() as session:
                entries = filter_by_content_types(
                    session, entries, exclude=exclude_content_types
                )
                if exclude_content_types:
                    log.info(
                        "content-type filter %s: %d → %d entries",
                        sorted(ct.value for ct in exclude_content_types),
                        pre_filter_count,
                        len(entries),
                    )
                if not entries:
                    log.warning("no entries remain after content-type filter")
                    return 1
                log.info(
                    "running eval: provider=qwen model=%s truth=%s entries=%d",
                    model, truth_mode, len(entries),
                )
                scored = score_all(
                    session,
                    classifier=classifier,
                    entries=entries,
                    truth_mode=truth_mode,
                )

    report = EvalReport.from_scored(scored)

    if args.output is None:
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = _DEFAULT_OUTPUT_DIR / f"{timestamp}_aspect_tagging.json"
    else:
        out_path = args.output

    operator_touched_count = sum(
        1 for e in entries if e.operator_flag is not None
    )
    operator_corrected_count = sum(
        1 for e in entries if e.operator_flag == "corrected"
    )
    meta = {
        "provider": args.provider,
        "model": model,
        "truth_mode": truth_mode,
        "gold_set_path": str(args.gold_set),
        "timestamp": dt.datetime.now().isoformat(),
        "operator_touched_count": operator_touched_count,
        "operator_corrected_count": operator_corrected_count,
        "disagreement_count": len(disagreements(scored)),
        "pre_filter_count": pre_filter_count,
        "post_filter_count": len(entries),
        "exclude_content_types": sorted(args.exclude_content_types),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report_to_dict(report, scored, meta=meta), indent=2),
        encoding="utf-8",
    )
    log.info("wrote eval report: %s", out_path)

    print(
        _format_summary(
            report,
            provider=args.provider,
            model=model,
            truth_mode=truth_mode,
            gold_set_path=args.gold_set,
            operator_touched_count=operator_touched_count,
            operator_corrected_count=operator_corrected_count,
            total_entries=len(entries),
            pre_filter_count=pre_filter_count,
            exclude_content_types=sorted(args.exclude_content_types),
            output_path=out_path,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
