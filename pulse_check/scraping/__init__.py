"""scrapers-lib integration and scrape orchestration.

Public entry points:
- `run_scrape(session, run_config, product_set)` — full end-to-end scrape.
- `ingest_batch(session, results)` — result_sink-compatible ingester.
- `apply_secondary_attribution(session, product_set)` — post-fetch sweep.
- `apply_comment_inheritance(session)` — Reddit comment attribution inheritance.
- `to_anchor` / `to_anchors` — ProductConfig → scrapers-lib Anchor.
"""

from pulse_check.scraping.anchors import to_anchor, to_anchors
from pulse_check.scraping.attribution import (
    SecondaryAttributionStats,
    apply_secondary_attribution,
)
from pulse_check.scraping.comment_inheritance import (
    CommentInheritanceStats,
    apply_comment_inheritance,
)
from pulse_check.scraping.converter import (
    attribution_to_row,
    raw_mention_to_mention,
    resolve_source_type,
)
from pulse_check.scraping.discovered_urls import (
    DiscoveredUrlEntry,
    load_approved_discovered_urls,
)
from pulse_check.scraping.ingester import IngestStats, ingest_batch
from pulse_check.scraping.orchestrator import run_scrape
from pulse_check.scraping.rss_discovery import (
    DiscoveredItem,
    DiscoveryStats,
    discover,
)

__all__ = [
    "CommentInheritanceStats",
    "DiscoveredItem",
    "DiscoveredUrlEntry",
    "DiscoveryStats",
    "IngestStats",
    "SecondaryAttributionStats",
    "apply_comment_inheritance",
    "apply_secondary_attribution",
    "attribution_to_row",
    "discover",
    "ingest_batch",
    "load_approved_discovered_urls",
    "raw_mention_to_mention",
    "resolve_source_type",
    "run_scrape",
    "to_anchor",
    "to_anchors",
]
