"""CLI entry point: run aspect tagging over the DB corpus.

Usage::

    python scripts/tag.py --run-config configs/run_smoke_test.yaml

Reads the run config to pick up the product set + taxonomy_version, wires an
``OllamaClient`` against the configured host + model, then iterates every
attribution and writes ``aspect_tags`` rows. Idempotent: re-running tags only
the pairs that don't already have rows under the same
``(taxonomy_version, prompt_version)``.
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
from pulse_check.tagging import AspectClassifier, ProductContext
from pulse_check.tagging.batch import tag_corpus_aspects
from pulse_check.tagging.ollama import OllamaClient

log = logging.getLogger("pulse_check.scripts.tag")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="pulse-check tag",
        description="Tag every attributed (mention, product) pair with aspect tags.",
    )
    parser.add_argument(
        "--run-config",
        type=Path,
        required=True,
        help="Path to a run YAML (e.g. configs/run_smoke_test.yaml).",
    )
    parser.add_argument(
        "--provider",
        choices=("ollama", "anthropic"),
        default="ollama",
        help=(
            "Which LLM provider drives classification. 'ollama' (default) runs"
            " Qwen locally; 'anthropic' runs Haiku via the Anthropic API as a"
            " fallback when Qwen misses the gold-set threshold (CLAUDE.md)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    configure_logging()

    settings = get_settings()
    run_config, product_set, _pair_plan = load_run(args.run_config)

    products = [
        ProductContext(product_id=p.product_id, display_name=p.display_name)
        for p in product_set.products
    ]
    log.info(
        "starting aspect tagging: run_id=%s products=%d taxonomy=%s provider=%s",
        run_config.run_id,
        len(products),
        run_config.taxonomy_version,
        args.provider,
    )

    if args.provider == "anthropic":
        if not settings.anthropic_api_key:
            log.error(
                "--provider anthropic requires ANTHROPIC_API_KEY in env/.env"
            )
            return 1
        anthropic_client = AnthropicClient(
            api_key=settings.anthropic_api_key, timeout=300.0
        )
        model = settings.anthropic_haiku_model
        log.info("anthropic classifier model=%s", model)
        classifier = AspectClassifier(anthropic_client, model=model)
        with session_scope() as session:
            stats = tag_corpus_aspects(
                session,
                classifier=classifier,
                products=products,
                taxonomy_version=run_config.taxonomy_version,
            )
    else:
        with OllamaClient(host=settings.ollama_host) as ollama_client:
            classifier = AspectClassifier(
                ollama_client, model=settings.ollama_model
            )
            with session_scope() as session:
                stats = tag_corpus_aspects(
                    session,
                    classifier=classifier,
                    products=products,
                    taxonomy_version=run_config.taxonomy_version,
                )

    log.info(
        "done: seen=%d skipped=%d classified=%d inserted=%d",
        stats.attributions_seen,
        stats.attributions_skipped_existing,
        stats.attributions_classified,
        stats.aspect_tags_inserted,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
