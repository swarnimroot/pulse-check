"""scrapers-lib integration and scrape orchestration.

Public entry points:
- `run_scrape(session, run_config, product_set)` — full end-to-end scrape.
- `ingest_batch(session, results)` — result_sink-compatible ingester.
- `apply_secondary_attribution(session, product_set)` — post-fetch sweep.
- `to_anchor` / `to_anchors` — ProductConfig → scrapers-lib Anchor.
"""

from pulse_check.scraping.anchors import to_anchor, to_anchors
from pulse_check.scraping.attribution import (
    SecondaryAttributionStats,
    apply_secondary_attribution,
)
from pulse_check.scraping.converter import (
    attribution_to_row,
    raw_mention_to_mention,
    resolve_source_type,
)
from pulse_check.scraping.ingester import IngestStats, ingest_batch
from pulse_check.scraping.orchestrator import run_scrape

__all__ = [
    "IngestStats",
    "SecondaryAttributionStats",
    "apply_secondary_attribution",
    "attribution_to_row",
    "ingest_batch",
    "raw_mention_to_mention",
    "resolve_source_type",
    "run_scrape",
    "to_anchor",
    "to_anchors",
]
