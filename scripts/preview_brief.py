"""CLI: A1 exec one-pager preview brief for a single product (Path A throwaway).

Path A is a fast aha checkpoint before the full Wave 2 synthesis layer is
built. Pulls a product's aspect aggregates + capped per-aspect verbatim
excerpts from the DB, asks Sonnet for a 3-finding + headline + watchout
exec brief in JSON, renders to markdown, writes to ``data/preview_briefs/``.

Informal citation contract: Sonnet cites mention IDs in [M:<id>] form; the
script flags any cited ID not present in the in-scope verbatim pool so the
operator can eyeball-check fabrication. Not a substitute for the real
citation validator (Wave 2 synthesis tasks).

Usage::

    python scripts/preview_brief.py --product-id alienware_16_aurora
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from pulse_check.llm_cache import call_with_cache
from pulse_check.logging_config import configure_logging
from pulse_check.settings import get_settings
from pulse_check.storage.models import (
    AggregateAspectSku,
    Mention,
    Product,
)
from pulse_check.storage.session import session_scope
from pulse_check.synthesis.anthropic_client import AnthropicClient

log = logging.getLogger("pulse_check.scripts.preview_brief")

PROMPT_VERSION = "preview_a1_v1"
MAX_RAW_TEXT_CHARS = 1500
MAX_VERBATIMS_PER_ASPECT = 4
OUT_DIR = Path("data/preview_briefs")


def _enum_value(v: Any) -> str:
    return v.value if hasattr(v, "value") else str(v)


def _build_prompts(
    product: Product,
    aggregates: list[AggregateAspectSku],
    verbatims_by_aspect: dict[str, list[dict[str, str]]],
) -> tuple[str, str]:
    system = (
        "You are a product-listening analyst writing a one-page exec brief "
        f"for {product.brand} hardware product leadership on consumer "
        f"reception of the {product.display_name}. Audience: senior PMs and "
        "engineering leads who already know the product. Goal: surface the "
        "highest-signal findings in <= ~300 words.\n\n"
        "Cite verbatim mention IDs in [M:<id>] form for every concrete claim. "
        "Use ONLY mention IDs supplied in the verbatim corpus below — do NOT "
        "invent IDs. Pick the 3 highest-signal findings (positive or negative). "
        "watchout = the single most important risk or unanswered question.\n\n"
        "Return ONLY a JSON object with this exact shape:\n"
        "{\n"
        '  "headline": "<one-sentence top-line takeaway>",\n'
        '  "findings": [\n'
        '    {"aspect": "<aspect_id>", "summary": "<2–3 sentence finding>", '
        '"citations": ["<mention_id>", ...]},\n'
        "    ... (3 entries)\n"
        "  ],\n"
        '  "watchout": "<single most important risk or open question>"\n'
        "}"
    )

    aggregates_payload = [
        {
            "aspect": _enum_value(agg.aspect),
            "total_mentions": agg.total_mentions,
            "polarity_counts": agg.polarity_counts,
            "net_sentiment": round(agg.net_sentiment, 3),
            "intensity_counts": agg.intensity_counts,
            "verified_share": round(agg.verified_share, 3),
            "by_source": agg.by_source,
        }
        for agg in aggregates
    ]

    user = (
        "Product:\n"
        + json.dumps(
            {
                "product_id": product.product_id,
                "display_name": product.display_name,
                "brand": product.brand,
            },
            indent=2,
        )
        + "\n\nAspect aggregates (descending by volume):\n"
        + json.dumps(aggregates_payload, indent=2)
        + "\n\nVerbatim excerpts grouped by aspect. Cite these mention_ids in "
        "your findings:\n"
        + json.dumps(verbatims_by_aspect, indent=2)
    )
    return system, user


def _collect_verbatims(
    session: Any, aggregates: list[AggregateAspectSku]
) -> tuple[dict[str, list[dict[str, str]]], set[str]]:
    by_aspect: dict[str, list[dict[str, str]]] = {}
    in_scope_ids: set[str] = set()
    for agg in aggregates:
        aspect = _enum_value(agg.aspect)
        verbatims: list[dict[str, str]] = []
        for mid in list(agg.mention_ids)[:MAX_VERBATIMS_PER_ASPECT]:
            mention = session.get(Mention, mid)
            if mention is None:
                continue
            in_scope_ids.add(mid)
            verbatims.append(
                {
                    "mention_id": mid,
                    "source_type": _enum_value(mention.source_type),
                    "excerpt": mention.raw_text[:MAX_RAW_TEXT_CHARS],
                }
            )
        by_aspect[aspect] = verbatims
    return by_aspect, in_scope_ids


def _render_markdown(product: Product, brief: dict[str, Any]) -> str:
    lines: list[str] = [
        f"# A1 preview brief — {product.display_name}",
        f"_Generated: {datetime.now(UTC).isoformat()}_",
        "",
    ]
    headline = brief.get("headline", "").strip()
    if headline:
        lines += [f"**Headline:** {headline}", ""]
    for i, finding in enumerate(brief.get("findings", []), 1):
        aspect = finding.get("aspect", "?")
        summary = finding.get("summary", "").strip()
        cites = finding.get("citations", []) or []
        cite_str = " ".join(f"[M:{c}]" for c in cites) if cites else "_(no citations)_"
        lines += [
            f"### {i}. {aspect}",
            summary,
            "",
            f"_Citations:_ {cite_str}",
            "",
        ]
    watchout = brief.get("watchout", "").strip()
    if watchout:
        lines += [f"**Watchout:** {watchout}", ""]
    return "\n".join(lines)


def _check_citations(brief: dict[str, Any], in_scope_ids: set[str]) -> tuple[int, list[str]]:
    cited: list[str] = []
    for finding in brief.get("findings", []):
        cited.extend(finding.get("citations", []) or [])
    fabricated = [c for c in cited if c not in in_scope_ids]
    return len(cited), fabricated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="preview-brief")
    parser.add_argument(
        "--product-id",
        required=True,
        help="Product ID from the products table (e.g. alienware_16_aurora)",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    configure_logging()
    settings = get_settings()
    if not settings.anthropic_api_key:
        log.error("ANTHROPIC_API_KEY is not set; cannot call Sonnet.")
        return 2

    with session_scope() as session:
        product = session.get(Product, args.product_id)
        if product is None:
            log.error("product not found: %s", args.product_id)
            return 1

        aggregates = list(
            session.execute(
                select(AggregateAspectSku)
                .where(AggregateAspectSku.product_id == args.product_id)
                .order_by(AggregateAspectSku.total_mentions.desc())
            ).scalars()
        )
        if not aggregates:
            log.error("no aggregates_aspect_sku rows for product %s", args.product_id)
            return 1

        verbatims_by_aspect, in_scope_ids = _collect_verbatims(session, aggregates)
        system, user_prompt = _build_prompts(product, aggregates, verbatims_by_aspect)

        client = AnthropicClient(api_key=settings.anthropic_api_key)
        model = settings.anthropic_sonnet_model

        cache_payload = {
            "system": system,
            "user": user_prompt,
            "product_id": args.product_id,
        }

        def _compute() -> Any:
            return client.generate_json(
                model=model,
                prompt=user_prompt,
                system=system,
                temperature=0.0,
                max_tokens=1500,
            )

        log.info(
            "calling Sonnet (model=%s) for preview brief — %s aggregates, %d verbatims",
            model,
            len(aggregates),
            sum(len(v) for v in verbatims_by_aspect.values()),
        )
        response = call_with_cache(
            session,
            task="preview_brief_a1",
            input_payload=cache_payload,
            prompt_version=PROMPT_VERSION,
            model=model,
            temperature=0.0,
            compute=_compute,
        )

        parsed = response.parsed_output

    if not isinstance(parsed, dict):
        log.error("unexpected Sonnet output shape: %s", type(parsed).__name__)
        return 1

    md = _render_markdown(product, parsed)
    cited_count, fabricated = _check_citations(parsed, in_scope_ids)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUT_DIR / f"{args.product_id}_{ts}.md"
    out_path.write_text(md, encoding="utf-8")

    log.info("wrote %s", out_path)
    log.info(
        "citation integrity: %d cited, %d fabricated (not in supplied corpus)",
        cited_count,
        len(fabricated),
    )
    if fabricated:
        log.warning("fabricated mention IDs: %s", fabricated)

    print()
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
