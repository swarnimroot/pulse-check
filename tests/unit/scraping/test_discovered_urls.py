"""Unit tests for pulse_check.scraping.discovered_urls.

Exercises the read side of the catalog-discovery pipeline: glob YAMLs in a
directory, filter to operator-approved entries, build `DiscoveredUrlEntry`
records. Defensive against malformed YAML, missing product_id, and the
`_dropped_*` quarantine convention.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from pulse_check.scraping.discovered_urls import (
    DiscoveredUrlEntry,
    load_approved_discovered_urls,
)


def _write_yaml(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _approved_entry(url: str, title: str, published_at: str | None = None) -> dict[str, object]:
    return {
        "url": url,
        "title": title,
        "published_at": published_at,
        "rating_pct": 87,
        "review_type": "editorial",
        "approved": True,
    }


def _unapproved_entry(url: str, title: str) -> dict[str, object]:
    return {
        "url": url,
        "title": title,
        "published_at": "2025-04-27",
        "rating_pct": None,
        "review_type": "editorial",
        "approved": False,
    }


def test_loads_only_approved_entries(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "rog_strix_g16.yaml",
        {
            "product_id": "rog_strix_g16",
            "search_term": "ROG Strix G16",
            "discovered_at": "2026-05-13T10:00:26",
            "total_found": 18,
            "editorial_count": 1,
            "reviews": [
                _approved_entry("https://nb.net/A-review.1.0.html", "A", "2025-04-27"),
                _unapproved_entry("https://nb.net/B-review.2.0.html", "B"),
            ],
        },
    )

    entries = load_approved_discovered_urls(tmp_path)

    assert len(entries) == 1
    assert entries[0].product_id == "rog_strix_g16"
    assert entries[0].url == "https://nb.net/A-review.1.0.html"
    assert entries[0].title == "A"
    assert entries[0].published_at == date(2025, 4, 27)


def test_returns_empty_when_directory_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"
    assert load_approved_discovered_urls(missing) == []


def test_returns_empty_when_directory_has_no_yamls(tmp_path: Path) -> None:
    (tmp_path / "_dropped_28a").mkdir()
    (tmp_path / "README.md").write_text("not yaml")
    assert load_approved_discovered_urls(tmp_path) == []


def test_ignores_subdirectory_yamls(tmp_path: Path) -> None:
    """Quarantine convention: `_dropped_*/` subdirs MUST NOT be loaded."""
    quarantine = tmp_path / "_dropped_28a"
    quarantine.mkdir()
    _write_yaml(
        quarantine / "asus_tuf_14.yaml",
        {
            "product_id": "asus_tuf_14",
            "reviews": [_approved_entry("https://nb.net/X.html", "X", "2025-01-01")],
        },
    )
    _write_yaml(
        tmp_path / "rog_strix_g16.yaml",
        {
            "product_id": "rog_strix_g16",
            "reviews": [_approved_entry("https://nb.net/Y.html", "Y", "2025-04-27")],
        },
    )

    entries = load_approved_discovered_urls(tmp_path)

    assert len(entries) == 1
    assert entries[0].product_id == "rog_strix_g16"


def test_sorted_by_product_then_url(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "zog.yaml",
        {
            "product_id": "zog",
            "reviews": [
                _approved_entry("https://nb.net/B-review.html", "B", "2025-01-01"),
                _approved_entry("https://nb.net/A-review.html", "A", "2025-02-01"),
            ],
        },
    )
    _write_yaml(
        tmp_path / "aog.yaml",
        {
            "product_id": "aog",
            "reviews": [_approved_entry("https://nb.net/C-review.html", "C", "2025-01-01")],
        },
    )

    entries = load_approved_discovered_urls(tmp_path)

    assert [(e.product_id, e.url) for e in entries] == [
        ("aog", "https://nb.net/C-review.html"),
        ("zog", "https://nb.net/A-review.html"),
        ("zog", "https://nb.net/B-review.html"),
    ]


def test_skips_yaml_without_product_id(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "broken.yaml",
        {"reviews": [_approved_entry("https://nb.net/A.html", "A", "2025-01-01")]},
    )
    _write_yaml(
        tmp_path / "ok.yaml",
        {
            "product_id": "ok",
            "reviews": [_approved_entry("https://nb.net/B.html", "B", "2025-01-01")],
        },
    )

    entries = load_approved_discovered_urls(tmp_path)

    assert len(entries) == 1
    assert entries[0].product_id == "ok"


def test_skips_review_with_empty_url(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "rog_strix_g16.yaml",
        {
            "product_id": "rog_strix_g16",
            "reviews": [
                {
                    "url": "",
                    "title": "no url",
                    "review_type": "editorial",
                    "approved": True,
                },
                _approved_entry("https://nb.net/A-review.html", "A", "2025-04-27"),
            ],
        },
    )

    entries = load_approved_discovered_urls(tmp_path)

    assert len(entries) == 1
    assert entries[0].url == "https://nb.net/A-review.html"


def test_handles_unparseable_date_gracefully(tmp_path: Path) -> None:
    _write_yaml(
        tmp_path / "rog_strix_g16.yaml",
        {
            "product_id": "rog_strix_g16",
            "reviews": [
                _approved_entry("https://nb.net/A-review.html", "A", "bogus-date"),
            ],
        },
    )

    entries = load_approved_discovered_urls(tmp_path)

    assert len(entries) == 1
    assert entries[0].published_at is None


def test_handles_yaml_native_date_object(tmp_path: Path) -> None:
    # PyYAML auto-parses YYYY-MM-DD into datetime.date; the loader must accept it.
    yaml_text = """
product_id: rog_strix_g16
reviews:
- url: https://nb.net/A-review.html
  title: A
  published_at: 2025-04-27
  review_type: editorial
  approved: true
"""
    (tmp_path / "rog_strix_g16.yaml").write_text(yaml_text, encoding="utf-8")

    entries = load_approved_discovered_urls(tmp_path)

    assert len(entries) == 1
    assert entries[0].published_at == date(2025, 4, 27)


def test_source_file_points_at_originating_yaml(tmp_path: Path) -> None:
    path = tmp_path / "rog_strix_g16.yaml"
    _write_yaml(
        path,
        {
            "product_id": "rog_strix_g16",
            "reviews": [_approved_entry("https://nb.net/A.html", "A", "2025-04-27")],
        },
    )

    entries = load_approved_discovered_urls(tmp_path)

    assert len(entries) == 1
    assert entries[0].source_file == path


def test_dataclass_is_hashable_and_frozen() -> None:
    e = DiscoveredUrlEntry(
        product_id="p",
        url="u",
        title="t",
        published_at=None,
        source_file=Path("x.yaml"),
    )
    assert {e} == {e}  # hashable / set membership
    import dataclasses

    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        e.url = "z"  # type: ignore[misc]
