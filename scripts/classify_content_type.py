"""CLI: classify every in-scope mention as review | deal | other.

Usage::

    python scripts/classify_content_type.py --run-config configs/run_smoke_test.yaml

Wires the Anthropic client (Haiku) and runs the content-type batch over
every mention attributed to any product in the run config. Idempotent
per ``(mention_id, prompt_version)``.

Used as a gate before aspect tagging — pass
``--exclude-content-types deal`` to ``scripts/tag.py`` after this runs to
suppress deal-roundup contamination from aspect aggregates.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pulse_check.config import load_run
from pulse_check.logging_config import configure_logging
from pulse_check.settings import get_settings
from pulse_check.storage.session import session_scope
from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.tagging.content_type_batch import classify_corpus_content_type
from pulse_check.tagging.content_type_classifier import ContentTypeClassifier

log = logging.getLogger("pulse_check.scripts.classify_content_type")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pulse-check classify-content-type",
        description="Triage every in-scope mention as review | deal | other.",
    )
    parser.add_argument(
        "--run-config",
        type=Path,
        required=True,
        help="Path to a run YAML (e.g. configs/run_smoke_test.yaml).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    configure_logging()

    settings = get_settings()
    if not settings.anthropic_api_key:
        log.error("ANTHROPIC_API_KEY is not set; cannot call Haiku.")
        return 2

    _run_config, product_set, _pair_plan = load_run(args.run_config)
    product_ids = [p.product_id for p in product_set.products]
    log.info(
        "starting content-type classification: products=%d model=%s",
        len(product_ids),
        settings.anthropic_haiku_model,
    )

    client = AnthropicClient(api_key=settings.anthropic_api_key, timeout=300.0)
    classifier = ContentTypeClassifier(client, model=settings.anthropic_haiku_model)

    with session_scope() as session:
        stats = classify_corpus_content_type(
            session,
            classifier=classifier,
            product_ids=product_ids,
        )

    log.info(
        "done: seen=%d skipped=%d classified=%d inserted=%d parse_failures=%d",
        stats.mentions_seen,
        stats.mentions_skipped_existing,
        stats.mentions_classified,
        stats.tags_inserted,
        stats.parse_failures,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
