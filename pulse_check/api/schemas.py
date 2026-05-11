"""Pydantic response models for the public API.

Bite 11.1 — Wave 2 finish. Shapes here are what the React frontend codes
against; backend handlers in `main.py` build these out of ORM rows.

Design choices (locked at session-13 start):
- `AspectRow` carries both PRIMARY and SECONDARY halves in a single object.
  Frontend bins rows into Section A (top-3 PRIMARY) → B (top-3 SECONDARY) → C
  (long tail) per scroller; that bucketing is a UI concern, not a backend one.
- `MentionView` exposes `upvotes` and `rating` (when present in `Mention.metadata_`)
  but not `ownership` or `tombstone` (deferred — see SESSION_LOG session-13 locks).
- `RunMeta` fields are non-jargon: total mentions + window + last-refreshed date.
  Run-id and taxonomy-version are intentionally excluded.
- Brief responses pass `BriefNarrative` through unchanged — the §6.3 four-quadrant
  contract from session 11/12 is preserved end-to-end.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProductSummary(BaseModel):
    """Lightweight product card returned by `/api/products`."""

    product_id: str
    display_name: str
    brand: str
    aliases: list[str] = Field(default_factory=list)


class ProductsResponse(BaseModel):
    products: list[ProductSummary]


class AspectRow(BaseModel):
    """One row per (product, aspect). Carries PRIMARY + SECONDARY halves.

    `intensity_counts` keys are the canonical Intensity enum values
    (`"high"`, `"medium"`, `"low"`); empty dict if zero mentions in that bucket.
    `sources` is the list of source-type strings present in the bucket
    (e.g., `["reddit_post", "amazon_review"]`); frontend formats display labels.
    `verified_pct` is `verified_share * 100`, rounded one decimal.
    """

    aspect: str

    total_mentions: int
    net_sentiment: float
    intensity_counts: dict[str, int]
    verified_pct: float
    sources: list[str]
    mention_ids: list[str]

    total_mentions_secondary: int
    net_sentiment_secondary: float
    intensity_counts_secondary: dict[str, int]
    verified_pct_secondary: float
    sources_secondary: list[str]
    mention_ids_secondary: list[str]


class RunMeta(BaseModel):
    """Top-of-page provenance strip — non-jargon labels only."""

    total_mentions: int
    window_label: str
    last_refreshed: datetime


class ProductDetail(BaseModel):
    """Payload behind `/api/product/{product_id}`.

    `latest_brief_id` is the highest `brief_id` whose `scope_type == aspect_1_sku`
    and `scope_id == product_id`; `None` when no A1 brief has been generated for
    this product yet. Lets the Standalone page navigate product → brief in one
    hop without a separate lookup endpoint.
    """

    product_id: str
    display_name: str
    brand: str
    aliases: list[str]
    aspects: list[AspectRow]
    run_meta: RunMeta
    latest_brief_id: int | None = None


class MentionView(BaseModel):
    """Verbatim card for the EvidenceDrawer / CitationPanel.

    `aspect_tags` lists every (aspect, polarity, intensity) tag attached to
    this mention so a single mention can carry multiple per-product aspects.
    `verified` reads from `metadata_.verified_purchase` for retailer reviews;
    Reddit mentions are unverified by definition.
    """

    mention_id: str
    source_type: str
    channel: str | None
    author: str | None
    published_at: datetime | None
    raw_text: str
    url: str
    verified: bool
    upvotes: int | None
    rating: float | None
    aspect_tags: list[dict[str, str]]


class MentionsResponse(BaseModel):
    mentions: list[MentionView]


class BriefView(BaseModel):
    """Persisted brief + metadata. `narrative` is the §6.3 BriefNarrative shape
    plus the top-level `flagged_citation_issues` key injected by the orchestrator.
    """

    brief_id: int
    run_id: str
    scope_type: str
    scope_id: str
    prompt_version: str
    model: str
    generated_at: datetime
    narrative: dict[str, Any]
