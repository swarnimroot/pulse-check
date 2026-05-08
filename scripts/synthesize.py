"""CLI: full A1 synthesis pipeline for one (product, run) — bite 10.4.

Persists a `Brief` row with the §6.3 BriefNarrative shape plus
`flagged_citation_issues` from the citation validator. Soft-warn policy: the
brief is persisted even when the validator flags issues.

Usage::

    python scripts/synthesize.py --product-id alienware_16_aurora --run-id smoke_test
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from pulse_check.logging_config import configure_logging
from pulse_check.settings import get_settings
from pulse_check.storage.session import session_scope
from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.synthesis.orchestrator import synthesize_a1

log = logging.getLogger("pulse_check.scripts.synthesize")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="synthesize")
    parser.add_argument(
        "--product-id",
        required=True,
        help="Product ID from the products table (e.g. alienware_16_aurora)",
    )
    parser.add_argument(
        "--run-id",
        required=True,
        help="Run ID matching the aggregates_aspect_sku rows to synthesize",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    configure_logging()
    settings = get_settings()
    if not settings.anthropic_api_key:
        log.error("ANTHROPIC_API_KEY is not set; cannot call Anthropic.")
        return 2

    client = AnthropicClient(api_key=settings.anthropic_api_key)

    with session_scope() as session:
        try:
            brief = synthesize_a1(
                session,
                client=client,
                run_id=args.run_id,
                product_id=args.product_id,
            )
        except ValueError as exc:
            log.error("%s", exc)
            return 1
        narrative_dict = dict(brief.narrative)
        brief_id = brief.brief_id
        prompt_version = brief.prompt_version

    flags = narrative_dict.get("flagged_citation_issues", {}) or {}
    title = narrative_dict.get("brief_title", "")
    sections = narrative_dict.get("sections", []) or []

    log.info(
        "brief persisted: brief_id=%s prompt_version=%s sections=%d",
        brief_id,
        prompt_version,
        len(sections),
    )
    log.info(
        "validation: is_valid=%s fabricated=%d out_of_context=%d drift=%d empty=%d",
        flags.get("is_valid"),
        len(flags.get("fabricated_ids") or []),
        len(flags.get("out_of_context_ids") or []),
        len(flags.get("numerical_drift") or []),
        len(flags.get("empty_claims") or []),
    )

    print()
    print(f"Brief title: {title}")
    print(f"Sections: {len(sections)}")
    for i, section in enumerate(sections, 1):
        heading = section.get("heading", "?")
        claim_count = len(section.get("claims") or [])
        print(f"  {i}. {heading} ({claim_count} claim{'s' if claim_count != 1 else ''})")
    print()
    print("Validation:")
    print(json.dumps(flags, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
