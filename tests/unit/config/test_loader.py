"""YAML loader + cross-reference validation tests.

Every failure path should raise `ConfigError` with a message that names the
offending file. The happy paths cover loading the real smoke-test configs
shipped in `configs/`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pulse_check.config import (
    ConfigError,
    load_pair_plan,
    load_product_set,
    load_run,
    load_run_config,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SMOKE_RUN = _REPO_ROOT / "configs" / "run_smoke_test.yaml"
_SMOKE_PRODUCTS = _REPO_ROOT / "configs" / "product_set_smoke_test.yaml"
_SMOKE_PAIRS = _REPO_ROOT / "configs" / "pair_plan_smoke_test.yaml"


# ---------------------------------------------------------------------------
# Happy paths on the real smoke configs
# ---------------------------------------------------------------------------


def test_load_smoke_product_set() -> None:
    ps = load_product_set(_SMOKE_PRODUCTS)
    assert ps.product_ids() == {"alienware_16_aurora", "rog_strix_g16"}


def test_load_smoke_pair_plan() -> None:
    pp = load_pair_plan(_SMOKE_PAIRS)
    assert len(pp.pairs) == 1
    assert pp.pairs[0].primary == "alienware_16_aurora"


def test_load_run_config_resolves_relative_paths() -> None:
    rc = load_run_config(_SMOKE_RUN)
    assert rc.run_id == "smoke_test"
    assert rc.product_set.is_absolute()
    assert rc.pair_plan.is_absolute()
    assert rc.product_set.name == "product_set_smoke_test.yaml"


def test_load_run_end_to_end_on_smoke_configs() -> None:
    run, product_set, pair_plan = load_run(_SMOKE_RUN)
    assert run.run_id == "smoke_test"
    assert product_set.product_ids() == {"alienware_16_aurora", "rog_strix_g16"}
    assert pair_plan.pairs[0].primary == "alienware_16_aurora"


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_loader_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as err:
        load_product_set(tmp_path / "does_not_exist.yaml")
    assert "not found" in str(err.value)


def test_loader_raises_for_malformed_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("products:\n  - product_id: [unclosed\n", encoding="utf-8")
    with pytest.raises(ConfigError) as err:
        load_product_set(bad)
    assert "invalid YAML" in str(err.value)


def test_loader_raises_when_top_level_is_not_mapping(tmp_path: Path) -> None:
    bad = tmp_path / "list.yaml"
    bad.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ConfigError) as err:
        load_product_set(bad)
    assert "top-level must be a mapping" in str(err.value)


def test_loader_raises_clean_error_for_validation_failure(tmp_path: Path) -> None:
    bad = tmp_path / "empty_products.yaml"
    bad.write_text("products: []\n", encoding="utf-8")
    with pytest.raises(ConfigError) as err:
        load_product_set(bad)
    msg = str(err.value)
    assert "invalid ProductSet" in msg
    assert str(bad) in msg


def test_load_run_rejects_unknown_product_in_pair_plan(tmp_path: Path) -> None:
    products = tmp_path / "products.yaml"
    pairs = tmp_path / "pairs.yaml"
    run = tmp_path / "run.yaml"
    products.write_text(
        "products:\n"
        "  - product_id: a\n"
        "    display_name: A\n"
        "    brand: X\n"
        "  - product_id: b\n"
        "    display_name: B\n"
        "    brand: X\n",
        encoding="utf-8",
    )
    pairs.write_text(
        "pairs:\n"
        "  - pair_id: a_vs_c\n"
        "    primary: a\n"
        "    comparator: c\n",  # c is not in product set
        encoding="utf-8",
    )
    run.write_text(
        "run_id: test_run\n"
        "product_set: products.yaml\n"
        "pair_plan: pairs.yaml\n"
        "taxonomy_version: v0\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError) as err:
        load_run(run)
    assert "unknown product_id" in str(err.value)
    assert "'c'" in str(err.value)


# ---------------------------------------------------------------------------
# Placeholder demo configs should at least parse structurally (cross-ref validation
# requires URLs so we only lint the shape — ensures TODOs don't break loading).
# ---------------------------------------------------------------------------


def test_demo_configs_parse_structurally() -> None:
    demo_run = _REPO_ROOT / "configs" / "run_demo_2026_04.yaml"
    run, product_set, pair_plan = load_run(demo_run)
    assert run.run_id == "demo_2026_04"
    assert len(product_set.products) == 59
    assert len(pair_plan.pairs) == 10
