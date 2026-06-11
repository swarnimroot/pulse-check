"""Add a new product to a product-set YAML, with a live corpus-match preview.

Onboarding a product is just appending a `ProductConfig` block to
`configs/product_set_*.yaml`; the next run's secondary-attribution pass then
back-attributes the existing corpus to it (see
`pulse_check/scraping/attribution.py`). This script removes the hand-editing:
it proposes collision-anchored regex patterns from the product NAME (plus any
SKU tokens found in the supplied product-page URLs), previews how many stored
mentions those patterns would match — so you catch over/under-matching BEFORE
committing — and on approval appends the validated block.

It does NOT scrape, tag, aggregate, or synthesize briefs. After approval, run
the normal pipeline (re-attribution + `scripts/run_stage_b.py`).

Usage:
    python scripts/add_product.py --name "Alienware 15" \
        --url https://www.dell.com/.../alienware-da15260-gaming-laptop \
        --url https://www.dell.com/.../alienware-da15265-gaming-laptop

    # non-interactive (skip the confirm prompt):
    python scripts/add_product.py --name "..." --brand "..." --yes
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from scrapers_lib.core.attribution import attribute_regex_all
from sqlalchemy import select

from pulse_check.config.loader import load_product_set
from pulse_check.config.models import (
    AttributionPatterns,
    ProductConfig,
    ProductSet,
    ProductUrls,
)
from pulse_check.logging_config import configure_logging
from pulse_check.scraping.anchors import to_anchor_with_secondary
from pulse_check.storage.models import Mention
from pulse_check.storage.session import session_scope

log = logging.getLogger("pulse_check.scripts.add_product")

DEFAULT_PRODUCT_SET = Path("configs/product_set_gaming_laptops_2026.yaml")
SAMPLE_LIMIT = 12  # match snippets to show in the preview
HIGH_MATCH_WARN = 400  # match count above this hints at an over-broad pattern
SKU_TOKEN = re.compile(r"[a-z]{2,4}\d{3,6}")  # e.g. da15260, ge76, gt77


def slugify(name: str) -> str:
    """'Alienware 15' -> 'alienware_15'."""
    tokens = re.findall(r"[a-z0-9]+", name.lower())
    return "_".join(tokens)


def name_to_primary_pattern(name: str) -> str:
    r"""'Alienware 15' -> r'\balienware\s+15\b' (lowercase, \b-anchored)."""
    tokens = re.findall(r"[a-z0-9]+", name.lower())
    if not tokens:
        raise SystemExit("error: --name has no alphanumeric content")
    return r"\b" + r"\s+".join(tokens) + r"\b"


def sku_secondary_patterns(urls: list[str]) -> list[str]:
    r"""Pull model-number tokens from URL paths -> [r'\bda15260\b', ...]."""
    skus: list[str] = []
    for url in urls:
        path = urlparse(url).path.lower()
        for tok in SKU_TOKEN.findall(path):
            if tok not in skus:
                skus.append(tok)
    return [rf"\b{s}\b" for s in skus]


def build_product(
    name: str, brand: str | None, product_id: str | None, urls: list[str]
) -> ProductConfig:
    """Assemble + validate a ProductConfig (Pydantic compiles the regexes)."""
    pid = product_id or slugify(name)
    resolved_brand = brand or name.split()[0]
    return ProductConfig(
        product_id=pid,
        display_name=name,
        brand=resolved_brand,
        aliases=[name],
        attribution_patterns=AttributionPatterns(
            primary=[name_to_primary_pattern(name)],
            secondary=sku_secondary_patterns(urls),
        ),
        urls=ProductUrls(),
    )


def render_block(p: ProductConfig) -> str:
    """Render a ProductConfig as a YAML list item matching the file's style."""

    def q(pattern: str) -> str:
        # Double backslashes so the double-quoted YAML scalar round-trips.
        return '"' + pattern.replace("\\", "\\\\") + '"'

    lines = [
        f"  - product_id: {p.product_id}",
        f'    display_name: "{p.display_name}"',
        f'    brand: "{p.brand}"',
        "    aliases:",
        *[f'      - "{a}"' for a in p.aliases],
        "    attribution_patterns:",
        "      primary:",
        *[f"        - {q(pat)}" for pat in p.attribution_patterns.primary],
    ]
    if p.attribution_patterns.secondary:
        lines.append("      secondary:")
        lines += [f"        - {q(pat)}" for pat in p.attribution_patterns.secondary]
    lines.append("    urls: {}")
    return "\n".join(lines) + "\n"


def preview_matches(product: ProductConfig) -> int:
    """Run the proposed patterns over the stored corpus exactly as the
    secondary-attribution pass does; print count + sample snippets. Returns
    the match count."""
    anchor = to_anchor_with_secondary(product)
    if anchor is None:
        raise SystemExit("error: product has no attribution patterns to preview")

    # Compiled copy for cosmetic snippet highlighting only; the count below is
    # authoritative via scrapers-lib's attribute_regex_all.
    compiled = [
        re.compile(pat, re.IGNORECASE)
        for pat in list(product.attribution_patterns.primary)
        + list(product.attribution_patterns.secondary)
    ]

    count = 0
    samples: list[str] = []
    with session_scope() as session:
        for mention in session.scalars(select(Mention)):
            if not attribute_regex_all(mention.raw_text, [anchor]):
                continue
            count += 1
            if len(samples) < SAMPLE_LIMIT:
                samples.append(_snippet(mention.raw_text, compiled))

    print(f"\n  Corpus matches: {count} existing mention(s) would attribute here.")
    if count == 0:
        print("  [!] ZERO matches - patterns may be too strict (or corpus empty).")
    elif count >= HIGH_MATCH_WARN:
        print(f"  [!] {count} is high - check the samples for over-matching.")
    for s in samples:
        print(f"    - {s}")
    return count


def _snippet(text: str, compiled: list[re.Pattern[str]], width: int = 70) -> str:
    """A short window around the first matching span, for eyeballing."""
    for rx in compiled:
        m = rx.search(text)
        if m:
            start = max(0, m.start() - width // 2)
            end = min(len(text), m.end() + width // 2)
            frag = text[start:end].replace("\n", " ").strip()
            return f"...{frag}..." if start > 0 else frag
    return text[:width].replace("\n", " ").strip()


def append_to_yaml(path: Path, block: str, expected_id: str) -> None:
    """Append the block, then reload to validate; restore the file on failure."""
    original = path.read_text(encoding="utf-8")
    suffix = "" if original.endswith("\n") else "\n"
    path.write_text(original + suffix + "\n" + block, encoding="utf-8")
    try:
        reloaded = load_product_set(path)
    except Exception as exc:
        path.write_text(original, encoding="utf-8")
        raise SystemExit(
            f"error: appended block failed validation, reverted: {exc}"
        ) from exc
    if expected_id not in {p.product_id for p in reloaded.products}:
        path.write_text(original, encoding="utf-8")
        raise SystemExit(f"error: {expected_id} not present after append, reverted")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="add-product")
    parser.add_argument("--name", required=True, help='e.g. "Alienware 15"')
    parser.add_argument(
        "--url", action="append", default=[], help="product-page URL (repeatable)"
    )
    parser.add_argument("--brand", default=None, help="defaults to first word of name")
    parser.add_argument("--id", default=None, help="product_id slug override")
    parser.add_argument("--product-set", type=Path, default=DEFAULT_PRODUCT_SET)
    parser.add_argument(
        "--yes", action="store_true", help="skip the confirm prompt (non-interactive)"
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    configure_logging()

    if not args.product_set.exists():
        raise SystemExit(f"error: product set not found: {args.product_set}")

    existing: ProductSet = load_product_set(args.product_set)
    product = build_product(args.name, args.brand, args.id, args.url)

    if product.product_id in {p.product_id for p in existing.products}:
        raise SystemExit(f"error: product_id '{product.product_id}' already exists")

    block = render_block(product)
    print(f"Proposed block for {args.product_set}:\n")
    print(block)
    preview_matches(product)

    if not args.yes:
        try:
            answer = input("\nAppend this product? [y/N] ").strip().lower()
        except EOFError:
            raise SystemExit(
                "\nNon-interactive shell: re-run with --yes to commit."
            ) from None
        if answer not in {"y", "yes"}:
            print("Aborted; no changes written.")
            return 1

    append_to_yaml(args.product_set, block, product.product_id)
    print(f"\n[ok] Added '{product.product_id}' to {args.product_set}")
    print(
        "  Next: re-attribute the corpus, then run the pipeline:\n"
        "    python -c \"from pulse_check.scraping import apply_secondary_attribution;"
        " from pulse_check.storage.session import session_scope;"
        " from pulse_check.config import load_product_set;"
        f" ps=load_product_set(r'{args.product_set}');"
        " s=session_scope().__enter__(); print(apply_secondary_attribution(s, ps)); s.commit()\"\n"
        f"    python scripts/run_stage_b.py --product-set {args.product_set}"
        "  (Sonnet briefs cost money - scope to the new product)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
