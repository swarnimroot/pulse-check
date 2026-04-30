"""Converter tests: source_type mapping, metadata rollup, attribution method."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from scrapers_lib import RawMention
from scrapers_lib.core.schemas import Attribution

from pulse_check.scraping.converter import (
    attribution_to_row,
    raw_mention_to_mention,
    resolve_source_type,
)
from pulse_check.storage.enums import AttributionMethod, AttributionType, SourceType

# ---------------------------------------------------------------------------
# resolve_source_type
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "source_type", "expected"),
    [
        ("reddit", "post", SourceType.REDDIT_POST),
        ("reddit", "comment", SourceType.REDDIT_COMMENT),
        ("reddit_comments", "post", SourceType.REDDIT_POST),
        ("reddit_comments", "comment", SourceType.REDDIT_COMMENT),
        ("bestbuy_reviews", "comment", SourceType.BESTBUY_REVIEW),
        ("amazon_reviews", "comment", SourceType.AMAZON_REVIEW),
        ("youtube", "transcript_chunk", SourceType.YOUTUBE_CHUNK),
        # Article fetcher uses hostname slug; any source string + "article" works.
        ("notebookcheck.net", "article", SourceType.ARTICLE),
        ("some.news.site", "article", SourceType.ARTICLE),
    ],
)
def test_resolve_source_type_known_pairs(
    source: str, source_type: str, expected: SourceType
) -> None:
    assert resolve_source_type(source, source_type) is expected


def test_resolve_source_type_unknown_pair_raises() -> None:
    with pytest.raises(ValueError, match="unknown scrapers-lib"):
        resolve_source_type("tiktok", "post")


# ---------------------------------------------------------------------------
# raw_mention_to_mention
# ---------------------------------------------------------------------------


def _reddit_post_mention(mention_id: str = "reddit_post_abc") -> RawMention:
    return RawMention(
        mention_id=mention_id,
        source="reddit",
        source_type="post",
        source_url="https://reddit.com/r/GamingLaptops/comments/abc",
        source_title="Alienware 16 Aurora thermals",
        author="user_1",
        author_id="t2_author_abc",
        channel="GamingLaptops",
        parent_id=None,
        published_at=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
        raw_text="The Alienware 16 Aurora runs hot under load.",
        attribution=Attribution(
            anchor_id="alienware_16_aurora",
            confidence=1.0,
            method="regex",
            matched_tokens=["Alienware 16 Aurora"],
        ),
        raw={"upvotes": 42, "verified": False},
    )


def test_raw_mention_to_mention_fields() -> None:
    rm = _reddit_post_mention()
    row = raw_mention_to_mention(rm)

    assert row.mention_id == "reddit_post_abc"
    assert row.source_type is SourceType.REDDIT_POST
    assert row.source_url == rm.source_url
    assert row.published_at == datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
    assert row.author == "user_1"
    assert row.channel == "GamingLaptops"
    assert row.raw_text == rm.raw_text
    assert row.first_seen_at.tzinfo is not None


def test_raw_mention_metadata_rollup_includes_opaque_fields() -> None:
    rm = _reddit_post_mention()
    row = raw_mention_to_mention(rm)

    meta = row.metadata_
    assert meta["source_title"] == "Alienware 16 Aurora thermals"
    assert meta["author_id"] == "t2_author_abc"
    assert meta["raw"] == {"upvotes": 42, "verified": False}
    assert meta["scrapers_lib_source"] == "reddit"
    assert "fetched_at" in meta  # library auto-populates


def test_raw_mention_metadata_omits_null_fields() -> None:
    rm = RawMention(
        mention_id="article_123",
        source="notebookcheck.net",
        source_type="article",
        source_url="https://notebookcheck.net/alienware-review",
        raw_text="A long enough body for the extraction gate to pass.",
    )
    row = raw_mention_to_mention(rm)

    assert "source_title" not in row.metadata_
    assert "author_id" not in row.metadata_
    assert "parent_id" not in row.metadata_
    assert "raw" not in row.metadata_
    # But scrapers_lib_source is always recorded.
    assert row.metadata_["scrapers_lib_source"] == "notebookcheck.net"


# ---------------------------------------------------------------------------
# attribution_to_row
# ---------------------------------------------------------------------------


def test_attribution_to_row_regex_method() -> None:
    attr = Attribution(anchor_id="alienware_16_aurora", confidence=1.0, method="regex")
    row = attribution_to_row("m_1", attr)

    assert row.mention_id == "m_1"
    assert row.product_id == "alienware_16_aurora"
    assert row.attribution_type is AttributionType.PRIMARY
    assert row.attribution_method is AttributionMethod.REGEX


def test_attribution_to_row_url_map_method() -> None:
    attr = Attribution(anchor_id="alienware_16_aurora", confidence=1.0, method="url_map")
    row = attribution_to_row("m_1", attr)

    assert row.attribution_method is AttributionMethod.URL


def test_attribution_to_row_rejects_manual_method() -> None:
    attr = Attribution(anchor_id="p", confidence=1.0, method="manual")
    with pytest.raises(ValueError, match="not supported"):
        attribution_to_row("m_1", attr)
