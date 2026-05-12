"""Pydantic v2 models for the three YAML configs a run consumes.

Shapes track ARCHITECTURE §4. `extra="forbid"` everywhere so typos in YAML
surface as validation errors rather than silently-ignored fields.

Public surface:
- `ProductSet`  — `configs/product_set_*.yaml`
- `PairPlan`    — `configs/pair_plan_*.yaml`
- `RunConfig`   — `configs/run_*.yaml`  (refs the two above)
- `SourceWindows` — per-source enable + backfill state, embedded in RunConfig

ID-length constraints match the storage schema (ARCHITECTURE §3):
- product_id: str(128)
- run_id:     str(64)
- pair_id:    str(256)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SLUG_PATTERN = r"^[a-z0-9_]+$"

ProductIdStr = Annotated[str, Field(pattern=_SLUG_PATTERN, min_length=1, max_length=128)]
RunIdStr = Annotated[str, Field(pattern=_SLUG_PATTERN, min_length=1, max_length=64)]
PairIdStr = Annotated[str, Field(pattern=_SLUG_PATTERN, min_length=1, max_length=256)]


# ---------------------------------------------------------------------------
# Product set
# ---------------------------------------------------------------------------


class AttributionPatterns(BaseModel):
    """Regex patterns that attribute mention text to this product.

    `primary` patterns are applied at fetch time against text from discovery
    sources (subreddit sweeps, article seeds). `secondary` patterns run on the
    post-fetch sweep and catch comparator mentions in reviews attributed to
    other products (ARCHITECTURE §5).
    """

    model_config = ConfigDict(extra="forbid")

    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)

    @field_validator("primary", "secondary")
    @classmethod
    def _must_compile(cls, patterns: list[str]) -> list[str]:
        for pattern in patterns:
            try:
                re.compile(pattern)
            except re.error as exc:
                msg = f"invalid attribution regex {pattern!r}: {exc}"
                raise ValueError(msg) from exc
        return patterns


class ProductUrls(BaseModel):
    """URLs used by fetchers for this product. All fields optional.

    `youtube_seeds` + `article_seeds` are lists of per-product curated URLs
    (hand-seeded, not discovered). `bestbuy`, `amazon`, `manufacturer` each
    point at a single product-page URL.
    """

    model_config = ConfigDict(extra="forbid")

    bestbuy: str | None = None
    amazon: str | None = None
    manufacturer: str | None = None
    youtube_seeds: list[str] = Field(default_factory=list)
    article_seeds: list[str] = Field(default_factory=list)


class ProductConfig(BaseModel):
    """One product in a product set."""

    model_config = ConfigDict(extra="forbid")

    product_id: ProductIdStr
    display_name: str = Field(min_length=1)
    brand: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    attribution_patterns: AttributionPatterns = Field(default_factory=AttributionPatterns)
    urls: ProductUrls = Field(default_factory=ProductUrls)


class ProductSet(BaseModel):
    """A list of products that form the anchor set for a run."""

    model_config = ConfigDict(extra="forbid")

    products: list[ProductConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_product_ids(self) -> Self:
        ids = [p.product_id for p in self.products]
        seen: set[str] = set()
        dupes: list[str] = []
        for pid in ids:
            if pid in seen:
                dupes.append(pid)
            seen.add(pid)
        if dupes:
            msg = f"duplicate product_id(s): {sorted(set(dupes))}"
            raise ValueError(msg)
        return self

    def product_ids(self) -> set[str]:
        return {p.product_id for p in self.products}


# ---------------------------------------------------------------------------
# Pair plan
# ---------------------------------------------------------------------------


class PairConfig(BaseModel):
    """One pair: primary vs comparator."""

    model_config = ConfigDict(extra="forbid")

    pair_id: PairIdStr
    primary: ProductIdStr
    comparator: ProductIdStr

    @model_validator(mode="after")
    def _primary_and_comparator_differ(self) -> Self:
        if self.primary == self.comparator:
            msg = f"pair {self.pair_id!r}: primary and comparator must differ"
            raise ValueError(msg)
        return self


class PairPlan(BaseModel):
    """List of 1v1 views to aggregate for a run."""

    model_config = ConfigDict(extra="forbid")

    pairs: list[PairConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_pair_ids(self) -> Self:
        ids = [p.pair_id for p in self.pairs]
        seen: set[str] = set()
        dupes: list[str] = []
        for pid in ids:
            if pid in seen:
                dupes.append(pid)
            seen.add(pid)
        if dupes:
            msg = f"duplicate pair_id(s): {sorted(set(dupes))}"
            raise ValueError(msg)
        return self


# ---------------------------------------------------------------------------
# Source windows
# ---------------------------------------------------------------------------


class SourceWindow(BaseModel):
    """Base per-source configuration. Specific sources extend this with
    source-specific fields (subreddits for reddit, paginate for bestbuy).

    Adding a new source in v1.5+ is a two-step change: add a subclass here
    and add a field on `SourceWindows`. The DB schema does not change
    (ARCHITECTURE §4.4).
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    backfill_months: int | None = Field(default=None, ge=0, le=120)


class RedditWindow(SourceWindow):
    subreddits: list[str] = Field(default_factory=list)


class BestBuyReviewsWindow(SourceWindow):
    paginate: bool = True


class AmazonReviewsWindow(SourceWindow):
    """Amazon PDP is snapshot-only (top ~10 inline); `backfill_months` not meaningful."""


class YouTubeWindow(SourceWindow):
    """`backfill_months` filters by video published_at."""


class ArticleWindow(SourceWindow):
    pass


class RSSWindow(SourceWindow):
    """RSS-discovery window. `backfill_months` filters feed entries by
    published_at; entries with no published_at pass through. Discovery runs
    BEFORE per-product YouTube/Article enqueues (coexists; per-product seed
    URLs still fire when their lists are non-empty)."""


class SourceWindows(BaseModel):
    """v1 sources. A source absent from the YAML defaults to None (fetcher not
    run); a source with `enabled: false` is explicit opt-out.

    `rss` toggles the RSS-discovery pass (see `pulse_check.scraping.rss_discovery`);
    the discovered URLs flow through the `youtube` / `article` fetchers, but the
    `rss` window is what gates whether discovery runs at all.
    """

    model_config = ConfigDict(extra="forbid")

    reddit: RedditWindow | None = None
    bestbuy_reviews: BestBuyReviewsWindow | None = None
    amazon_reviews: AmazonReviewsWindow | None = None
    youtube: YouTubeWindow | None = None
    article: ArticleWindow | None = None
    rss: RSSWindow | None = None


# ---------------------------------------------------------------------------
# Run config
# ---------------------------------------------------------------------------


class RunConfig(BaseModel):
    """A full pilot run configuration.

    `product_set`, `pair_plan`, and (optional) `rss_sources` are paths to
    YAML files; the loader resolves them against the run config's directory
    when relative.
    """

    model_config = ConfigDict(extra="forbid")

    run_id: RunIdStr
    product_set: Path
    pair_plan: Path
    rss_sources: Path | None = None
    source_windows: SourceWindows = Field(default_factory=SourceWindows)
    taxonomy_version: str = Field(min_length=1, max_length=32)


# ---------------------------------------------------------------------------
# RSS sources (operator-supplied feeds for the RSS-discovery pass)
# ---------------------------------------------------------------------------


class YouTubeChannelSource(BaseModel):
    """One YouTube channel whose atom feed is polled for video discovery.

    `channel_id` is the resolved canonical YouTube channel ID (e.g.
    `UCXuqSBlHAE6Xw-yeJA0Tunw`); `rss_url` is the corresponding atom feed
    (`https://www.youtube.com/feeds/videos.xml?channel_id=<channel_id>`).
    """

    model_config = ConfigDict(extra="forbid")

    handle: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    channel_id: str = Field(min_length=1)
    rss_url: str = Field(min_length=1)


class ArticleRSSFeedSource(BaseModel):
    """One review-site RSS feed polled for article discovery.

    `enabled: false` skips this feed without removing the entry.
    `status` / `notes` are operator-facing curation metadata (no business
    logic); kept here so the source file is self-describing.
    """

    model_config = ConfigDict(extra="forbid")

    site: str = Field(min_length=1)
    rss_url: str = Field(min_length=1)
    enabled: bool = True
    status: str | None = None
    notes: str | None = None


class RSSSources(BaseModel):
    """Operator-supplied RSS-discovery configuration.

    `title_keywords` are case-insensitive substring matches against entry
    titles; at least ONE must match for an entry to survive the filter.
    """

    model_config = ConfigDict(extra="forbid")

    title_keywords: list[str] = Field(min_length=1)
    youtube_channels: list[YouTubeChannelSource] = Field(default_factory=list)
    article_rss_feeds: list[ArticleRSSFeedSource] = Field(default_factory=list)
