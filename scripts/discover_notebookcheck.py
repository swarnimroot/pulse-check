"""CLI: search Notebookcheck per-product and write discovered-URL YAMLs.

For each product in a `product_set` YAML, POSTs `{"model": display_name}` to
Notebookcheck's `Laptop_Search.8223.0.html`, filters results to editorial
reviews (URL slug contains `-review`), and writes a per-product YAML at
`data/discovered_urls/notebookcheck/<product_id>.yaml` with `approved: false`
on every entry. Operator flips `approved: true` on legitimate matches before
any downstream scrape ingests the URL.

Example:
    .venv/Scripts/python.exe scripts/discover_notebookcheck.py \\
        --product-set configs/product_set_gaming_laptops_2026.yaml \\
        --product-id rog_strix_g16 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

from pulse_check.config.loader import load_product_set
from pulse_check.scraping.catalog_discovery import (
    build_discovery_result,
    search_notebookcheck,
)

log = logging.getLogger("pulse_check.scripts.discover_notebookcheck")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Search Notebookcheck for each product in a product_set and "
            "write per-product discovered-URL YAMLs for operator curation."
        ),
    )
    parser.add_argument(
        "--product-set",
        type=Path,
        required=True,
        help="Path to the product_set YAML.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/discovered_urls/notebookcheck"),
        help="Directory for per-product output YAMLs (default: %(default)s).",
    )
    parser.add_argument(
        "--pace",
        type=float,
        default=2.0,
        help="Seconds to sleep between products for politeness (default: %(default)s).",
    )
    parser.add_argument(
        "--product-id",
        type=str,
        default=None,
        help="If set, only process this single product_id.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print findings to logs without writing YAML files.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    product_set = load_product_set(args.product_set)
    products = product_set.products
    if args.product_id is not None:
        products = [p for p in products if p.product_id == args.product_id]
        if not products:
            log.error("product_id %r not found in %s", args.product_id, args.product_set)
            return 1

    if not args.dry_run:
        args.out_dir.mkdir(parents=True, exist_ok=True)

    for i, product in enumerate(products):
        search_term = product.display_name
        log.info(
            "[%d/%d] %s — searching %r",
            i + 1,
            len(products),
            product.product_id,
            search_term,
        )
        try:
            all_reviews = search_notebookcheck(search_term)
        except Exception as exc:
            log.warning("  search failed: %s", exc, exc_info=True)
            if i < len(products) - 1:
                time.sleep(args.pace)
            continue

        editorial = [r for r in all_reviews if r.review_type == "editorial"]
        result = build_discovery_result(
            product_id=product.product_id,
            search_term=search_term,
            reviews=editorial,
            total_found=len(all_reviews),
            now=datetime.now(),
        )
        log.info(
            "  total=%d editorial_kept=%d",
            result.total_found,
            result.editorial_count,
        )

        if args.dry_run:
            for r in editorial:
                log.info(
                    "    %s [%s, %s%%] %s",
                    r.url,
                    r.published_at.isoformat() if r.published_at else "no-date",
                    r.rating_pct if r.rating_pct is not None else "—",
                    r.title,
                )
        else:
            out_path = args.out_dir / f"{product.product_id}.yaml"
            out_path.write_text(
                yaml.safe_dump(
                    result.model_dump(mode="json"),
                    sort_keys=False,
                    allow_unicode=True,
                ),
                encoding="utf-8",
            )
            log.info("  wrote %s", out_path)

        if i < len(products) - 1:
            time.sleep(args.pace)

    return 0


if __name__ == "__main__":
    sys.exit(main())
