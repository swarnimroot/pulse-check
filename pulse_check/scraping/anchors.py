"""Build scrapers-lib `Anchor` values from our product configs.

Each `ProductConfig` becomes one `Anchor`:
- `anchor_id` = `product_id`
- `attribution_regex.primary` = product's primary patterns (alias list is
  informational; scrapers-lib only uses the regex list for matching)
- `source_urls` = per-source product page URLs for URL-map attribution
  (BestBuy reviews, Amazon reviews exact-URL match via `attribute_url`)

A product with no primary patterns cannot produce a valid Anchor (scrapers-lib
requires `min_length=1` on `AttributionRegex.primary`). Such products are
skipped with a warning — common on Wave 5 demo placeholders that haven't had
patterns filled in yet.

scrapers-lib's `AttributionRegex` treats tokens as *literal strings* by default
and expects a `re:` prefix for regex interpretation. Our configs store regex
patterns (validated via `re.compile` at load time), so every pattern is wrapped
with `re:` before being handed to scrapers-lib.
"""

from __future__ import annotations

import logging

from scrapers_lib import Anchor, AttributionRegex

from pulse_check.config.models import ProductConfig, ProductSet

log = logging.getLogger(__name__)


def _as_regex_tokens(patterns: list[str]) -> list[str]:
    """Wrap each pattern with scrapers-lib's `re:` prefix for regex interpretation."""
    return [f"re:{p}" for p in patterns]


def to_anchor(product: ProductConfig) -> Anchor | None:
    """Convert one ProductConfig to a scrapers-lib Anchor, or None if not buildable."""
    primary_patterns = _as_regex_tokens(list(product.attribution_patterns.primary))
    if not primary_patterns:
        log.warning(
            "product %s has no primary attribution patterns; skipping anchor build",
            product.product_id,
        )
        return None

    source_urls: dict[str, str] = {}
    if product.urls.bestbuy is not None:
        source_urls["bestbuy"] = product.urls.bestbuy
    if product.urls.amazon is not None:
        source_urls["amazon"] = product.urls.amazon
    if product.urls.manufacturer is not None:
        source_urls["manufacturer"] = product.urls.manufacturer

    return Anchor(
        anchor_id=product.product_id,
        anchor_type="product",
        name=product.display_name,
        aliases=product.aliases,
        attribution_regex=AttributionRegex(primary=primary_patterns),
        source_urls=source_urls,
    )


def to_anchors(product_set: ProductSet) -> list[Anchor]:
    """Build Anchors for every buildable product in a product set."""
    anchors: list[Anchor] = []
    for product in product_set.products:
        anchor = to_anchor(product)
        if anchor is not None:
            anchors.append(anchor)
    return anchors


def to_anchor_with_secondary(product: ProductConfig) -> Anchor | None:
    """Like `to_anchor` but primary = primary + secondary patterns combined.

    Used by the post-fetch secondary attribution sweep (ARCHITECTURE §5):
    we want any mention whose text matches *either* the primary anchor regex
    or the looser secondary regex to surface as a secondary-attribution
    candidate against the stored corpus.
    """
    combined = list(product.attribution_patterns.primary) + list(
        product.attribution_patterns.secondary
    )
    if not combined:
        return None
    return Anchor(
        anchor_id=product.product_id,
        anchor_type="product",
        name=product.display_name,
        aliases=product.aliases,
        attribution_regex=AttributionRegex(primary=_as_regex_tokens(combined)),
    )
