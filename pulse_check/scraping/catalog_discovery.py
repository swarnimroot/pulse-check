"""Programmatic Notebookcheck catalog discovery via POST search.

POSTs `{"model": <display_name>}` to Notebookcheck's `Laptop_Search.8223.0.html`
endpoint, parses the results HTML, and returns the discovered review URLs
(both editorial reviews and spec/aggregation pages). Each result is a
`DiscoveredReview` with the URL, title, published date, Notebookcheck
aggregated rating (if present), and a `review_type` ("editorial" | "spec")
classified from the URL slug.

Notebookcheck protects article paths with Cloudflare's managed challenge.
The default fetcher uses `curl_cffi` Chrome120 impersonation (transitive
via scrapers-lib >=1.4.0) to bypass it. A one-time warmup GET to the
home page seeds the session before the search POST.

Architectural seam: the public surface accepts an injected `HtmlPostFetcher`
callable so tests can stub the HTTP layer without a live network call.

Downstream flow: the CLI (`scripts/discover_notebookcheck.py`) loops a
product_set, calls `search_notebookcheck` for each product, filters to
editorial reviews, and writes per-product YAMLs with `approved: false` on
every entry for operator curation before any scrape ingest.
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

log = logging.getLogger(__name__)

HOME_URL = "https://www.notebookcheck.net/"
SEARCH_URL = "https://www.notebookcheck.net/Laptop_Search.8223.0.html"

# Editorial reviews have "-review" in the URL slug; spec/aggregation pages
# are plain `<Model>.<NNNNNN>.0.html` with no quality cue in the slug.
_EDITORIAL_SLUG_RE = re.compile(r"-review[a-z0-9-]*\.\d+\.0\.html$", re.IGNORECASE)

# Notebookcheck renders each result as a pair of <tr> rows: an empty
# header row with `id="modelidN"`, then a data row. This pattern matches
# the data row only — the header row has no `<span>` inside its <td>, so
# it never satisfies the date-span subpattern.
_DATA_ROW_RE = re.compile(
    r"<tr[^>]*?>\s*"
    r"<td[^>]*?>\s*<span[^>]*?>\s*(?P<date>\d{2}\.\d{2}\.\d{4})\s*</span>\s*</td>\s*"
    r"<td[^>]*?>\s*"
    r'(?:<span[^>]*?class="rating"[^>]*?>\s*'
    r'<span[^>]*?class="average">\s*(?P<rating>\d+)%\s*</span>\s*</span>\s*)?'
    r"</td>\s*"
    r'<td[^>]*?>\s*<a\s+href="(?P<url>[^"]+)"[^>]*?>(?P<title>[^<]+)</a>',
    re.IGNORECASE | re.DOTALL,
)


ReviewType = Literal["editorial", "spec"]


class DiscoveredReview(BaseModel):
    """One review entry discovered via Notebookcheck catalog search.

    Serialized to per-product YAML for operator curation; `approved`
    defaults to False and must be flipped manually before downstream
    scrape ingests the URL.
    """

    model_config = ConfigDict(extra="forbid")

    url: str
    title: str
    published_at: date | None = None
    rating_pct: int | None = None
    review_type: ReviewType
    approved: bool = False


class DiscoveryResult(BaseModel):
    """Per-product discovery output. One YAML file per product."""

    model_config = ConfigDict(extra="forbid")

    product_id: str
    search_term: str
    discovered_at: datetime
    total_found: int
    editorial_count: int
    reviews: list[DiscoveredReview] = Field(default_factory=list)


# Injectable POST helper: (url, post_data) -> response body text. Allows
# tests to stub the curl_cffi layer without a live network call.
HtmlPostFetcher = Callable[[str, dict[str, str]], str]


def _classify_review_type(url: str) -> ReviewType:
    return "editorial" if _EDITORIAL_SLUG_RE.search(url) else "spec"


def _parse_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw, "%d.%m.%Y").date()
    except ValueError:
        return None


def parse_results(response_html: str) -> list[DiscoveredReview]:
    """Parse a Notebookcheck Laptop_Search response into reviews.

    Returns one `DiscoveredReview` per result row (both editorial and
    spec/aggregation pages). `approved` defaults to False.
    """
    reviews: list[DiscoveredReview] = []
    for m in _DATA_ROW_RE.finditer(response_html):
        url = m.group("url").strip()
        title = html.unescape(m.group("title")).strip()
        published_at = _parse_date(m.group("date"))
        rating_raw = m.group("rating")
        rating_pct = int(rating_raw) if rating_raw else None
        reviews.append(
            DiscoveredReview(
                url=url,
                title=title,
                published_at=published_at,
                rating_pct=rating_pct,
                review_type=_classify_review_type(url),
            )
        )
    return reviews


def _default_post_fetcher() -> HtmlPostFetcher:
    """Build the default curl_cffi-impersonated POST fetcher with home warmup.

    Lazy-imports curl_cffi so tests that inject a stub fetcher don't pay the
    import cost (and so import of this module doesn't fail in environments
    where curl_cffi is absent).
    """
    from curl_cffi.requests import Session

    session: Any = Session(impersonate="chrome120")
    session.get(HOME_URL, timeout=30)

    def _post(url: str, data: dict[str, str]) -> str:
        r = session.post(url, data=data, timeout=30)
        r.raise_for_status()
        return str(r.text)

    return _post


def search_notebookcheck(
    model_name: str,
    *,
    manufacturer: str | int | None = None,
    fetcher: HtmlPostFetcher | None = None,
) -> list[DiscoveredReview]:
    """POST a model search to Notebookcheck and return ALL discovered reviews.

    Returns editorial and spec entries unfiltered; the caller filters as
    needed (the CLI filters to editorials before writing per-product YAMLs).

    ``manufacturer`` accepts the numeric manufacturer ID from Notebookcheck's
    search form (e.g. Acer=18, Alienware=19, ASUS=11, HP=9, Lenovo=35, MSI=15).
    When supplied, results are restricted to that brand on the server side —
    the fix for generic model names ("Legion 7", "TUF 15") that previously
    pulled phones / tablets / unrelated SKUs into the 500-result cap.
    Defaults to ``None`` (unfiltered substring match — original behavior).
    """
    f = fetcher if fetcher is not None else _default_post_fetcher()
    payload: dict[str, str] = {"model": model_name}
    if manufacturer is not None:
        payload["manufacturer"] = str(manufacturer)
    response = f(SEARCH_URL, payload)
    reviews = parse_results(response)
    editorial_count = sum(1 for r in reviews if r.review_type == "editorial")
    log.info(
        "notebookcheck search model=%r manufacturer=%s total=%d editorial=%d",
        model_name,
        manufacturer if manufacturer is not None else "any",
        len(reviews),
        editorial_count,
    )
    return reviews


def filter_by_min_date(
    reviews: list[DiscoveredReview],
    min_published_date: date,
) -> list[DiscoveredReview]:
    """Drop reviews older than ``min_published_date`` (and those with no date).

    Notebookcheck's catalog search is a substring match on display names, so
    generic names ("ASUS TUF 14") sweep in prior-generation reviews. This
    helper applies a recency cutoff at discovery time so the per-product
    curation surface stays tractable. Entries with ``published_at is None``
    (date couldn't be parsed) are dropped under an active filter — they're
    unverifiable for a recency-based decision.
    """
    return [
        r
        for r in reviews
        if r.published_at is not None and r.published_at >= min_published_date
    ]


def build_discovery_result(
    *,
    product_id: str,
    search_term: str,
    reviews: list[DiscoveredReview],
    total_found: int,
    now: datetime | None = None,
) -> DiscoveryResult:
    """Bundle reviews + metadata into a YAML-serializable DiscoveryResult."""
    return DiscoveryResult(
        product_id=product_id,
        search_term=search_term,
        discovered_at=now if now is not None else datetime.now(),
        total_found=total_found,
        editorial_count=sum(1 for r in reviews if r.review_type == "editorial"),
        reviews=reviews,
    )
