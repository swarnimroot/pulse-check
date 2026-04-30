"""Anchor builder tests."""

from __future__ import annotations

from pulse_check.config.models import (
    AttributionPatterns,
    ProductConfig,
    ProductSet,
    ProductUrls,
)
from pulse_check.scraping.anchors import (
    to_anchor,
    to_anchor_with_secondary,
    to_anchors,
)


def _product(
    *,
    product_id: str = "alienware_16_aurora",
    primary: list[str] | None = None,
    secondary: list[str] | None = None,
    bestbuy: str | None = None,
    amazon: str | None = None,
) -> ProductConfig:
    return ProductConfig(
        product_id=product_id,
        display_name="Alienware 16 Aurora",
        brand="Alienware",
        aliases=["16 Aurora"],
        attribution_patterns=AttributionPatterns(
            primary=primary if primary is not None else [r"\balienware\s+16\s+aurora\b"],
            secondary=secondary or [],
        ),
        urls=ProductUrls(bestbuy=bestbuy, amazon=amazon),
    )


def test_to_anchor_happy_path_includes_primary_only() -> None:
    product = _product()
    anchor = to_anchor(product)

    assert anchor is not None
    assert anchor.anchor_id == "alienware_16_aurora"
    assert anchor.name == "Alienware 16 Aurora"
    # Patterns are wrapped with scrapers-lib's `re:` prefix so they're interpreted
    # as regex rather than literal strings.
    assert anchor.attribution_regex.primary == [r"re:\balienware\s+16\s+aurora\b"]
    # Secondary patterns do NOT go into the primary anchor.
    assert anchor.attribution_regex.corroboration == []


def test_to_anchor_forwards_source_urls_when_present() -> None:
    product = _product(
        bestbuy="https://www.bestbuy.com/alienware-16-aurora",
        amazon="https://www.amazon.com/dp/AW16A",
    )
    anchor = to_anchor(product)

    assert anchor is not None
    assert anchor.source_urls["bestbuy"] == "https://www.bestbuy.com/alienware-16-aurora"
    assert anchor.source_urls["amazon"] == "https://www.amazon.com/dp/AW16A"


def test_to_anchor_omits_missing_urls() -> None:
    product = _product()  # no URLs
    anchor = to_anchor(product)

    assert anchor is not None
    assert anchor.source_urls == {}


def test_to_anchor_returns_none_when_primary_empty() -> None:
    product = _product(primary=[])
    assert to_anchor(product) is None


def test_to_anchors_skips_products_without_primary_patterns() -> None:
    ps = ProductSet(
        products=[
            _product(product_id="with_patterns"),
            _product(product_id="no_patterns", primary=[]),
        ]
    )
    anchors = to_anchors(ps)
    assert [a.anchor_id for a in anchors] == ["with_patterns"]


# ---------------------------------------------------------------------------
# to_anchor_with_secondary
# ---------------------------------------------------------------------------


def test_to_anchor_with_secondary_combines_patterns() -> None:
    product = _product(
        primary=[r"\balienware\s+16\s+aurora\b"],
        secondary=[r"\balienware\s+aurora\b"],
    )
    anchor = to_anchor_with_secondary(product)

    assert anchor is not None
    assert anchor.attribution_regex.primary == [
        r"re:\balienware\s+16\s+aurora\b",
        r"re:\balienware\s+aurora\b",
    ]


def test_to_anchor_with_secondary_works_with_only_secondary() -> None:
    product = _product(primary=[], secondary=[r"\balienware\b"])
    anchor = to_anchor_with_secondary(product)
    assert anchor is not None
    assert anchor.attribution_regex.primary == [r"re:\balienware\b"]


def test_to_anchor_with_secondary_returns_none_when_both_empty() -> None:
    product = _product(primary=[], secondary=[])
    assert to_anchor_with_secondary(product) is None
