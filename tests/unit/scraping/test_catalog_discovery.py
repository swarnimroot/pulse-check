"""Unit tests for pulse_check.scraping.catalog_discovery.

The HTML fixture at `tests/fixtures/html/notebookcheck_search_rog_strix_g16.html`
is a real captured POST response from Notebookcheck for `{"model": "ROG Strix G16"}`
on 2026-05-12. Re-capture it if Notebookcheck's results-template HTML shifts.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from pulse_check.scraping.catalog_discovery import (
    SEARCH_URL,
    DiscoveredReview,
    DiscoveryResult,
    build_discovery_result,
    parse_results,
    search_notebookcheck,
)

_FIXTURE_PATH = (
    Path(__file__).parent.parent.parent
    / "fixtures"
    / "html"
    / "notebookcheck_search_rog_strix_g16.html"
)


@pytest.fixture
def rog_strix_html() -> str:
    return _FIXTURE_PATH.read_text(encoding="utf-8")


def test_parse_results_returns_expected_count(rog_strix_html: str) -> None:
    reviews = parse_results(rog_strix_html)
    assert len(reviews) == 18


def test_parse_results_classifies_editorial_count(rog_strix_html: str) -> None:
    reviews = parse_results(rog_strix_html)
    editorial = [r for r in reviews if r.review_type == "editorial"]
    assert len(editorial) == 2


def test_parse_results_extracts_known_editorial_url(rog_strix_html: str) -> None:
    reviews = parse_results(rog_strix_html)
    editorial_urls = {r.url for r in reviews if r.review_type == "editorial"}
    # Both editorial URLs in the captured fixture (operator-verified).
    assert (
        "https://www.notebookcheck.net/"
        "The-RTX-5080-Laptop-is-optimal-for-Gaming-in-WQHD-"
        "Asus-ROG-Strix-G16-G615-review.1005904.0.html"
    ) in editorial_urls


def test_parse_results_extracts_first_entry_metadata(rog_strix_html: str) -> None:
    reviews = parse_results(rog_strix_html)
    first = reviews[0]
    assert first.url == "https://www.notebookcheck.net/Asus-ROG-Strix-G16-G615.1070239.0.html"
    assert first.title == "Asus ROG Strix G16 G615"
    assert first.published_at == date(2026, 4, 26)
    assert first.rating_pct == 88
    assert first.review_type == "spec"
    assert first.approved is False


def test_parse_results_handles_entry_without_rating(rog_strix_html: str) -> None:
    # The 10.07.2025 G615JMR entry has no `<span class="rating">` block.
    reviews = parse_results(rog_strix_html)
    no_rating = [r for r in reviews if r.rating_pct is None]
    assert len(no_rating) >= 1
    # At least one no-rating entry should still have a valid date + URL.
    sample = no_rating[0]
    assert sample.url.startswith("https://www.notebookcheck.net/")
    assert sample.published_at is not None


def test_parse_results_parses_european_date_format(rog_strix_html: str) -> None:
    # Fixture has DD.MM.YYYY format. Confirm the latest entry parses to ISO date.
    reviews = parse_results(rog_strix_html)
    dates = [r.published_at for r in reviews if r.published_at]
    assert all(isinstance(d, date) for d in dates)
    # Latest date in fixture is 26.04.2026.
    assert date(2026, 4, 26) in dates


def test_parse_results_classifies_review_type_from_slug() -> None:
    editorial_html = (
        '<tr id="modelid1"><td></td></tr>'
        '<tr class="odd">'
        '<td><span style="color:foo">15.03.2025</span></td>'
        '<td><span class="rating"><span class="average">90%</span></span></td>'
        '<td><a href="https://www.notebookcheck.net/Foo-Bar-review.123.0.html">'
        "Foo Bar review</a></td>"
        "</tr>"
    )
    spec_html = (
        '<tr id="modelid1"><td></td></tr>'
        '<tr class="odd">'
        '<td><span style="color:foo">15.03.2025</span></td>'
        '<td><span class="rating"><span class="average">90%</span></span></td>'
        '<td><a href="https://www.notebookcheck.net/Foo-Bar.123.0.html">Foo Bar</a></td>'
        "</tr>"
    )
    assert parse_results(editorial_html)[0].review_type == "editorial"
    assert parse_results(spec_html)[0].review_type == "spec"


def test_parse_results_handles_empty_html() -> None:
    assert parse_results("") == []
    assert parse_results("<html><body>no results</body></html>") == []


def test_parse_results_unescapes_html_entities() -> None:
    sample = (
        '<tr id="modelid1"><td></td></tr>'
        '<tr class="odd">'
        '<td><span style="color:foo">15.03.2025</span></td>'
        '<td></td>'
        '<td><a href="https://www.notebookcheck.net/Foo.123.0.html">A &amp; B Review</a></td>'
        "</tr>"
    )
    out = parse_results(sample)
    assert out[0].title == "A & B Review"


def test_search_notebookcheck_invokes_fetcher_with_correct_args(rog_strix_html: str) -> None:
    fake_fetcher: MagicMock = MagicMock(return_value=rog_strix_html)
    reviews = search_notebookcheck("ROG Strix G16", fetcher=fake_fetcher)
    fake_fetcher.assert_called_once_with(SEARCH_URL, {"model": "ROG Strix G16"})
    assert len(reviews) == 18


def test_search_notebookcheck_returns_unfiltered_results(rog_strix_html: str) -> None:
    fake_fetcher = MagicMock(return_value=rog_strix_html)
    reviews = search_notebookcheck("ROG Strix G16", fetcher=fake_fetcher)
    types = {r.review_type for r in reviews}
    # Both editorial and spec are returned; filtering is the caller's job.
    assert types == {"editorial", "spec"}


def test_build_discovery_result_counts_editorials() -> None:
    reviews = [
        DiscoveredReview(
            url="https://www.notebookcheck.net/A-review.1.0.html",
            title="A",
            review_type="editorial",
        ),
        DiscoveredReview(
            url="https://www.notebookcheck.net/B.2.0.html",
            title="B",
            review_type="spec",
        ),
        DiscoveredReview(
            url="https://www.notebookcheck.net/C-review.3.0.html",
            title="C",
            review_type="editorial",
        ),
    ]
    fixed_now = datetime(2026, 5, 12, 21, 0, 0)
    result = build_discovery_result(
        product_id="foo",
        search_term="Foo",
        reviews=reviews,
        total_found=10,
        now=fixed_now,
    )
    assert result.product_id == "foo"
    assert result.search_term == "Foo"
    assert result.discovered_at == fixed_now
    assert result.total_found == 10
    assert result.editorial_count == 2
    assert result.reviews == reviews


def test_discovery_result_yaml_round_trips_via_pydantic() -> None:
    # Operator-curation hinges on YAML round-tripping cleanly through
    # `model_dump(mode="json")` -> yaml -> `model_validate` -> equal model.
    import yaml

    original = build_discovery_result(
        product_id="rog_strix_g16",
        search_term="ROG Strix G16",
        reviews=[
            DiscoveredReview(
                url="https://www.notebookcheck.net/X-review.1.0.html",
                title="X review",
                published_at=date(2026, 4, 26),
                rating_pct=88,
                review_type="editorial",
                approved=False,
            )
        ],
        total_found=1,
        now=datetime(2026, 5, 12, 21, 0, 0),
    )
    yaml_text = yaml.safe_dump(original.model_dump(mode="json"), sort_keys=False)
    parsed_dict = yaml.safe_load(yaml_text)
    restored = DiscoveryResult.model_validate(parsed_dict)
    assert restored == original


def test_discovered_review_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        DiscoveredReview.model_validate(
            {
                "url": "https://www.notebookcheck.net/X-review.1.0.html",
                "title": "X",
                "review_type": "editorial",
                "unexpected_field": True,
            }
        )


def test_discovered_review_rejects_invalid_review_type() -> None:
    with pytest.raises(ValidationError):
        DiscoveredReview.model_validate(
            {
                "url": "https://www.notebookcheck.net/X.1.0.html",
                "title": "X",
                "review_type": "lol_not_a_type",
            }
        )
