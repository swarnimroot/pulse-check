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
        "starting aspect tagging: run_id=%s products=%d taxonomy=%s",
        run_config.run_id,
        len(products),
        run_config.taxonomy_version,
    )

    with OllamaClient(host=settings.ollama_host) as client:
        classifier = AspectClassifier(client, model=settings.ollama_model)
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
