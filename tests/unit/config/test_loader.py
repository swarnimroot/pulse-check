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
    load_rss_sources,
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
    run, product_set, pair_plan, rss_sources = load_run(_SMOKE_RUN)
    assert run.run_id == "smoke_test"
    assert product_set.product_ids() == {"alienware_16_aurora", "rog_strix_g16"}
    assert pair_plan.pairs[0].primary == "alienware_16_aurora"
    assert rss_sources is None  # smoke run does not reference an RSS sources file


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
    run, product_set, pair_plan, rss_sources = load_run(demo_run)
    assert run.run_id == "demo_2026_04"
    # 60 since session 48 (alienware_15 added going-forward via add_product.py).
    assert len(product_set.products) == 60
    assert len(pair_plan.pairs) == 10
    assert rss_sources is None


def test_load_wave5_rss_sources_yaml_parses() -> None:
    path = _REPO_ROOT / "configs" / "wave5_rss_sources.yaml"
    rss = load_rss_sources(path)
    assert len(rss.youtube_channels) == 7
    # Session 26: LaptopMag article feed removed (stale, no posts since
    # 2025-11-28); RTINGS disabled (HTML auto-discovery fallback yielded no
    # laptop-keyword feed link in the session-26 dry-run).
    assert len(rss.article_rss_feeds) == 8
    assert sum(1 for f in rss.article_rss_feeds if f.enabled) == 7
    # title_keywords seeded with the operator's filter list. Session 27:
    # tightened from bare "review"/"best" (admitted phones/tablets from
    # Notebookcheck's mixed-category feed) to "laptop review" / "best laptop"
    # compound phrases.
    assert "gaming laptop" in rss.title_keywords
    assert "laptop review" in rss.title_keywords
    assert "best laptop" in rss.title_keywords
    assert "review" not in rss.title_keywords
    assert "best" not in rss.title_keywords
    # RTINGS entry retains its index-page URL; disabled at config level.
    rtings = next(f for f in rss.article_rss_feeds if f.site == "RTINGS")
    assert rtings.rss_url.endswith("/rss-feeds")
    assert rtings.status == "RED"
    assert rtings.enabled is False
    # LaptopMag article feed no longer present (YouTube channel still active).
    assert not any(f.site == "LaptopMag" for f in rss.article_rss_feeds)


def test_load_run_config_resolves_discovered_urls_sources_relative_path(
    tmp_path: Path,
) -> None:
    """The new `discovered_urls_sources` field mirrors `rss_sources` path
    resolution: relative values are resolved against the run config's
    parent directory; absolute paths pass through unchanged.
    """
    # Build a self-contained run config + product/pair stubs alongside it,
    # plus a discovered-urls directory referenced relatively.
    products_path = tmp_path / "ps.yaml"
    products_path.write_text(
        "products:\n  - product_id: p1\n    display_name: P1\n    brand: x\n",
        encoding="utf-8",
    )
    pairs_path = tmp_path / "pp.yaml"
    pairs_path.write_text("pairs: []\n", encoding="utf-8")
    disc_dir = tmp_path / "disc"
    disc_dir.mkdir()
    run_yaml = tmp_path / "run.yaml"
    run_yaml.write_text(
        (
            "run_id: t_run\n"
            "product_set: ps.yaml\n"
            "pair_plan: pp.yaml\n"
            "discovered_urls_sources: disc\n"
            "taxonomy_version: v1\n"
        ),
        encoding="utf-8",
    )

    rc = load_run_config(run_yaml)
    assert rc.discovered_urls_sources is not None
    assert rc.discovered_urls_sources.is_absolute()
    assert rc.discovered_urls_sources.name == "disc"
    assert rc.discovered_urls_sources.parent == tmp_path.resolve()


def test_load_run_config_discovered_urls_sources_defaults_to_none() -> None:
    """Smoke run config omits `discovered_urls_sources` → loader returns None."""
    rc = load_run_config(_SMOKE_RUN)
    assert rc.discovered_urls_sources is None


def test_load_run_wave5_v1_threads_rss_sources_through_load_run() -> None:
    path = _REPO_ROOT / "configs" / "run_wave5_v1.yaml"
    run, _ps, _pp, rss = load_run(path)
    assert run.run_id == "wave5_v1"
    assert run.rss_sources is not None
    assert run.rss_sources.name == "wave5_rss_sources.yaml"
    # Full Wave 5 posture: reddit + rss both enabled at 6-month backfill;
    # operator-curated discovered_urls_sources flipped on; article window
    # enabled (required by the discovered-URLs orchestrator guard).
    assert run.source_windows.rss is not None
    assert run.source_windows.rss.enabled is True
    assert run.source_windows.rss.backfill_months == 6
    assert run.source_windows.reddit is not None
    assert run.source_windows.reddit.enabled is True
    assert run.source_windows.reddit.backfill_months == 6
    assert run.source_windows.article is not None
    assert run.source_windows.article.enabled is True
    assert run.discovered_urls_sources is not None
    assert run.discovered_urls_sources.name == "notebookcheck"
    assert rss is not None
    assert len(rss.youtube_channels) == 7
