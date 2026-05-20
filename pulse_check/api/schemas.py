"""Pydantic response models for the public API.

Bite 11.1 — Wave 2 finish. Shapes here are what the React frontend codes
against; backend handlers in `main.py` build these out of ORM rows.

Design choices (locked at session-13 start):
- `AspectRow` carries both PRIMARY and SECONDARY halves in a single object.
  Frontend bins rows into Section A (top-3 PRIMARY) → B (top-3 SECONDARY) → C
  (long tail) per scroller; that bucketing is a UI concern, not a backend one.
- `MentionView` exposes `upvotes` and `rating` (when present in `Mention.metadata_`)
  plus `tombstoned_at` for the link-rot badge; `ownership` stays deferred.
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
    tombstoned_at: datetime | None
    tombstone_reason: str | None


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


# ---------------------------------------------------------------------------
# Compare (cross-product heatmap) — bite 32.a
# ---------------------------------------------------------------------------


class CompareCell(BaseModel):
    """One cell of the cross-product heatmap.

    `mention_ids` is capped server-side so the bulk response stays bounded;
    the EvidenceDrawer fetches verbatim text via `/api/mentions` from this
    same list.
    """

    aspect: str
    total_mentions: int
    net_sentiment: float
    mention_ids: list[str]


class CompareProductRow(BaseModel):
    """One row in the heatmap. `cells` is sparse — only aspects with at
    least one tagged mention are present; the frontend renders empty
    cells for missing aspects against the canonical column order.
    """

    product_id: str
    display_name: str
    brand: str
    cells: list[CompareCell]


class CompareResponse(BaseModel):
    """Payload behind `/api/compare`.

    `aspects` is the canonical column order (Aspect enum declaration order).
    `run_id` is the run picked to populate the grid; `None` only when zero
    runs have any aggregate rows yet.
    """

    products: list[CompareProductRow]
    aspects: list[str]
    run_id: str | None
    generated_at: datetime


# ---------------------------------------------------------------------------
# Home page summary + pair comparison — bite 32.b
# ---------------------------------------------------------------------------


class PipelineStageStat(BaseModel):
    """One stage in the plain-English "Under the hood" pipeline explainer.

    `chips` are name/value pairs surfaced as small metric pills on the stage
    card. Order is preserved and rendered left-to-right.
    """

    key: str  # stable id used by the frontend for keys + iconography
    label: str  # short uppercase tag (PULL / NARROW / TAG / SCORE / ...)
    title: str  # human-readable stage title
    description: str  # plain-English sentence shown beneath the title
    ai: bool = False  # whether this stage involves an LLM call (badge on the card)
    chips: list[dict[str, str | int | float]] = Field(default_factory=list)


class HomeSummary(BaseModel):
    """Payload behind `/api/home`.

    Drives the top-of-page summary strip plus the "Under the hood" panel.
    `products_tracked` is the count of products with at least one aggregate
    row in the chosen run. `mentions_analyzed` is the total distinct
    mentions in the corpus (across all sources).
    """

    run_id: str | None
    products_tracked: int
    mentions_analyzed: int
    pipeline: list[PipelineStageStat]
    generated_at: datetime


class PairAspectCell(BaseModel):
    """One product's data for one aspect, in the head-to-head context."""

    total_mentions: int
    net_sentiment: float
    mention_ids: list[str]


class PairAspectRow(BaseModel):
    """One side-by-side row in the head-to-head scorecard.

    `delta` = primary.net_sentiment - competitor.net_sentiment. Positive
    means the primary leads on this aspect; negative means the competitor
    leads. `leader` is a stable string (`"primary"` / `"competitor"` /
    `"tie"`) so the frontend doesn't have to re-derive the same comparison.
    """

    aspect: str
    primary: PairAspectCell | None
    competitor: PairAspectCell | None
    delta: float
    leader: str  # "primary" | "competitor" | "tie"


class PairProductRef(BaseModel):
    product_id: str
    display_name: str
    brand: str


class PairResponse(BaseModel):
    """Payload behind `/api/pair`.

    Returns a paired aspect-by-aspect comparison plus a small summary
    (aspects each side leads on). `aspects` carries the canonical column
    order so the frontend renders consistently with the heatmap.
    """

    primary: PairProductRef
    competitor: PairProductRef
    aspects: list[str]
    rows: list[PairAspectRow]
    primary_leads_count: int  # aspects where primary > competitor net sentiment
    competitor_leads_count: int
    ties_count: int  # both sides equal or both sides missing data
    run_id: str | None
    generated_at: datetime


# ---------------------------------------------------------------------------
# /api/sources — operator-curated source list shown in the home page
# "Under the hood" accordion.
# ---------------------------------------------------------------------------


class SourceEntry(BaseModel):
    """One source surface (a subreddit, a YouTube channel, an article feed)."""

    name: str  # display label — e.g. "r/GamingLaptops" or "Tom's Hardware"
    detail: str  # secondary line — URL, handle, or note


class SourcesResponse(BaseModel):
    """Payload behind `/api/sources`.

    Surfaces the operator-curated source set for the active run by reading
    the YAML configs at request time. `review_sites` is the article-RSS
    list filtered to `enabled` entries.
    """

    reddit: list[SourceEntry]
    youtube: list[SourceEntry]
    review_sites: list[SourceEntry]
    generated_at: datetime
