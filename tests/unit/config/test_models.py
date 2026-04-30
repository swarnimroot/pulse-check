"""Pydantic model validation for ProductSet / PairPlan / RunConfig.

Coverage per TESTING §3: malformed shapes, missing fields, invalid regex,
unknown product_ids referenced by pair_plan, slug constraints.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pulse_check.config.models import (
    AttributionPatterns,
    PairConfig,
    PairPlan,
    ProductConfig,
    ProductSet,
    RedditWindow,
    RunConfig,
    SourceWindows,
)

# ---------------------------------------------------------------------------
# ProductSet
# ---------------------------------------------------------------------------


def _product(product_id: str = "alienware_16_aurora") -> dict[str, object]:
    return {
        "product_id": product_id,
        "display_name": "Alienware 16 Aurora",
        "brand": "Alienware",
    }


def test_product_set_happy_path() -> None:
    ps = ProductSet.model_validate({"products": [_product("a"), _product("b")]})
    assert ps.product_ids() == {"a", "b"}


def test_product_set_rejects_empty_products_list() -> None:
    with pytest.raises(ValidationError):
        ProductSet.model_validate({"products": []})


def test_product_set_rejects_duplicate_product_ids() -> None:
    with pytest.raises(ValidationError) as err:
        ProductSet.model_validate({"products": [_product("same"), _product("same")]})
    assert "duplicate product_id" in str(err.value)


def test_product_config_rejects_bad_slug() -> None:
    with pytest.raises(ValidationError):
        ProductConfig.model_validate(_product("Has Spaces"))
    with pytest.raises(ValidationError):
        ProductConfig.model_validate(_product("UPPERCASE"))
    with pytest.raises(ValidationError):
        ProductConfig.model_validate(_product("has-dashes"))


def test_product_config_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError) as err:
        ProductConfig.model_validate({**_product(), "unknown_field": 1})
    assert "Extra inputs are not permitted" in str(err.value) or "extra_forbidden" in str(err.value)


def test_attribution_patterns_rejects_invalid_regex() -> None:
    with pytest.raises(ValidationError) as err:
        AttributionPatterns.model_validate({"primary": ["valid", "["]})
    assert "invalid attribution regex" in str(err.value)


def test_attribution_patterns_accepts_empty_and_compiles_valid() -> None:
    ap = AttributionPatterns.model_validate({"primary": [r"\balienware\s+16\s*aurora\b"]})
    assert ap.primary == [r"\balienware\s+16\s*aurora\b"]
    assert ap.secondary == []


# ---------------------------------------------------------------------------
# PairPlan
# ---------------------------------------------------------------------------


def test_pair_plan_happy_path() -> None:
    pp = PairPlan.model_validate(
        {"pairs": [{"pair_id": "a_vs_b", "primary": "a", "comparator": "b"}]}
    )
    assert pp.pairs[0].primary == "a"


def test_pair_plan_rejects_primary_equals_comparator() -> None:
    with pytest.raises(ValidationError) as err:
        PairConfig.model_validate({"pair_id": "same_vs_same", "primary": "x", "comparator": "x"})
    assert "must differ" in str(err.value)


def test_pair_plan_rejects_duplicate_pair_ids() -> None:
    with pytest.raises(ValidationError) as err:
        PairPlan.model_validate(
            {
                "pairs": [
                    {"pair_id": "p", "primary": "a", "comparator": "b"},
                    {"pair_id": "p", "primary": "c", "comparator": "d"},
                ]
            }
        )
    assert "duplicate pair_id" in str(err.value)


def test_pair_plan_rejects_empty_pairs_list() -> None:
    with pytest.raises(ValidationError):
        PairPlan.model_validate({"pairs": []})


# ---------------------------------------------------------------------------
# SourceWindows
# ---------------------------------------------------------------------------


def test_source_windows_absent_sources_default_to_none() -> None:
    sw = SourceWindows.model_validate({})
    assert sw.reddit is None
    assert sw.bestbuy_reviews is None


def test_source_windows_rejects_unknown_source_key() -> None:
    with pytest.raises(ValidationError):
        SourceWindows.model_validate({"tiktok": {"enabled": True}})


def test_reddit_window_accepts_source_specific_fields() -> None:
    rw = RedditWindow.model_validate(
        {"enabled": True, "backfill_months": 6, "subreddits": ["GamingLaptops"]}
    )
    assert rw.subreddits == ["GamingLaptops"]


def test_source_window_rejects_negative_backfill() -> None:
    with pytest.raises(ValidationError):
        RedditWindow.model_validate({"backfill_months": -1})


def test_source_window_rejects_huge_backfill() -> None:
    with pytest.raises(ValidationError):
        RedditWindow.model_validate({"backfill_months": 200})


# ---------------------------------------------------------------------------
# RunConfig
# ---------------------------------------------------------------------------


def test_run_config_happy_path() -> None:
    rc = RunConfig.model_validate(
        {
            "run_id": "demo_2026_04",
            "product_set": "product_set.yaml",
            "pair_plan": "pair_plan.yaml",
            "taxonomy_version": "v0",
        }
    )
    assert rc.run_id == "demo_2026_04"


def test_run_config_rejects_missing_taxonomy_version() -> None:
    with pytest.raises(ValidationError):
        RunConfig.model_validate(
            {
                "run_id": "x",
                "product_set": "a.yaml",
                "pair_plan": "b.yaml",
            }
        )


def test_run_id_length_cap() -> None:
    with pytest.raises(ValidationError):
        RunConfig.model_validate(
            {
                "run_id": "x" * 65,
                "product_set": "a.yaml",
                "pair_plan": "b.yaml",
                "taxonomy_version": "v0",
            }
        )
