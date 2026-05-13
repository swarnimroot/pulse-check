"""Load operator-approved discovered URLs from per-product YAML files.

Each YAML under `<RunConfig.discovered_urls_sources>/*.yaml` is product-anchored
and lists candidate review URLs with `approved: <bool>`. The operator flips
`approved: true` on legitimate matches during the curation pass; this module
reads ONLY approved entries and exposes them as `DiscoveredUrlEntry` records
keyed by `product_id` for the orchestrator's single-anchor enqueue path.

This is the read side of the `catalog_discovery` pipeline (which is the write
side — it produces the per-product YAMLs via `scripts/discover_notebookcheck.py`).
The two halves are intentionally decoupled so operator curation sits cleanly
between them: discovery writes `approved: false`, operator flips legitimate
entries, orchestrator reads only the approved subset.

Only top-level `*.yaml` files in the directory are read; sub-directories are
skipped (the `_dropped_*` quarantine convention is honored automatically).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DiscoveredUrlEntry:
    """One operator-approved discovered URL anchored to a single product."""

    product_id: str
    url: str
    title: str
    published_at: date | None
    source_file: Path


def _coerce_published_at(raw: Any) -> date | None:
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw)
        except ValueError:
            return None
    return None


def load_approved_discovered_urls(directory: Path) -> list[DiscoveredUrlEntry]:
    """Load every `approved: true` entry from per-product YAMLs in `directory`.

    Skips files that fail to parse as a dict or are missing a `product_id`;
    logs a warning per skip. Returns entries sorted by ``(product_id, url)``
    for stable orchestrator enqueue order.
    """
    if not directory.exists():
        log.warning("discovered_urls: directory %s does not exist", directory)
        return []

    entries: list[DiscoveredUrlEntry] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            log.warning("discovered_urls: skipping %s (parse error: %s)", path, exc)
            continue
        if not isinstance(data, dict):
            log.warning("discovered_urls: skipping %s (root is not a mapping)", path)
            continue
        product_id = data.get("product_id")
        if not isinstance(product_id, str) or not product_id:
            log.warning("discovered_urls: skipping %s (missing product_id)", path)
            continue
        reviews = data.get("reviews", [])
        if not isinstance(reviews, list):
            log.warning("discovered_urls: skipping %s (reviews not a list)", path)
            continue
        for review in reviews:
            if not isinstance(review, dict):
                continue
            if not review.get("approved"):
                continue
            url = review.get("url")
            if not isinstance(url, str) or not url:
                continue
            title_raw = review.get("title", "")
            title = title_raw if isinstance(title_raw, str) else ""
            entries.append(
                DiscoveredUrlEntry(
                    product_id=product_id,
                    url=url,
                    title=title,
                    published_at=_coerce_published_at(review.get("published_at")),
                    source_file=path,
                )
            )
    entries.sort(key=lambda e: (e.product_id, e.url))
    log.info(
        "discovered_urls: loaded %d approved entries across %d products from %s",
        len(entries),
        len({e.product_id for e in entries}),
        directory,
    )
    return entries
