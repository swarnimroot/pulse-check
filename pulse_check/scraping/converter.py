"""Convert scrapers-lib `RawMention` values to our `Mention` + `MentionAttribution` rows.

scrapers-lib's (source, source_type) vocabulary differs from our `SourceType`
enum — the mapping is in `_SOURCE_TYPE_MAP`. scrapers-lib's `Attribution.method`
vocabulary overlaps but we only use two of three values; `"manual"` is
rejected here because our fetcher pipeline never produces it.

The ingester calls `raw_mention_to_mention` for the Mention row and
`raw_mention_to_attribution` (possibly `None`) for the primary attribution —
split because one `RawMention` per matched anchor arrives with the same
`mention_id`, so the ingester upserts the mention once and appends
attributions per occurrence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from scrapers_lib import RawMention
from scrapers_lib.core.schemas import Attribution

from pulse_check.storage.enums import AttributionMethod, AttributionType, SourceType
from pulse_check.storage.models import Mention, MentionAttribution

# (scrapers-lib source, scrapers-lib source_type) → our SourceType
_SOURCE_TYPE_MAP: dict[tuple[str, str], SourceType] = {
    ("reddit", "post"): SourceType.REDDIT_POST,
    ("reddit", "comment"): SourceType.REDDIT_COMMENT,
    ("reddit_comments", "post"): SourceType.REDDIT_POST,
    ("reddit_comments", "comment"): SourceType.REDDIT_COMMENT,
    ("bestbuy_reviews", "comment"): SourceType.BESTBUY_REVIEW,
    ("amazon_reviews", "comment"): SourceType.AMAZON_REVIEW,
    ("youtube", "transcript_chunk"): SourceType.YOUTUBE_CHUNK,
}

_METHOD_MAP: dict[str, AttributionMethod] = {
    "regex": AttributionMethod.REGEX,
    "url_map": AttributionMethod.URL,
}


def resolve_source_type(source: str, source_type: str) -> SourceType:
    """Map scrapers-lib's (source, source_type) pair to our SourceType enum.

    Article mentions come from a per-publication `source` slug (hostname or
    operator-supplied), so the table keys on `source_type == "article"`.
    """
    if source_type == "article":
        return SourceType.ARTICLE
    try:
        return _SOURCE_TYPE_MAP[(source, source_type)]
    except KeyError as exc:
        msg = f"unknown scrapers-lib (source, source_type) = ({source!r}, {source_type!r})"
        raise ValueError(msg) from exc


def _method_to_enum(method: str) -> AttributionMethod:
    try:
        return _METHOD_MAP[method]
    except KeyError as exc:
        msg = (
            f"attribution method {method!r} not supported by pulse-check; "
            f"expected one of {list(_METHOD_MAP)}"
        )
        raise ValueError(msg) from exc


def _build_metadata(mention: RawMention) -> dict[str, Any]:
    """Fold scrapers-lib fields that don't map to columns into a metadata dict.

    Includes source_title, author_id, parent_id, the library's `fetched_at`,
    and the opaque `raw` payload (verified_purchase, upvotes, etc.).
    """
    meta: dict[str, Any] = {}
    if mention.source_title is not None:
        meta["source_title"] = mention.source_title
    if mention.author_id is not None:
        meta["author_id"] = mention.author_id
    if mention.parent_id is not None:
        meta["parent_id"] = mention.parent_id
    if mention.fetched_at is not None:
        meta["fetched_at"] = mention.fetched_at.isoformat()
    if mention.raw is not None:
        meta["raw"] = mention.raw
    # Record the library's source slug so article rows can be traced back to
    # their publication (hostname slug is lost once mapped to ARTICLE).
    meta["scrapers_lib_source"] = mention.source
    return meta


def raw_mention_to_mention(mention: RawMention) -> Mention:
    """Build a Mention ORM row (not added to a session) from a RawMention."""
    return Mention(
        mention_id=mention.mention_id,
        source_type=resolve_source_type(mention.source, mention.source_type),
        source_url=mention.source_url,
        published_at=mention.published_at,
        author=mention.author,
        raw_text=mention.raw_text,
        channel=mention.channel,
        metadata_=_build_metadata(mention),
        first_seen_at=datetime.now(UTC),
    )


def attribution_to_row(mention_id: str, attribution: Attribution) -> MentionAttribution:
    """Build a primary MentionAttribution row (not added) from a library Attribution."""
    return MentionAttribution(
        mention_id=mention_id,
        product_id=attribution.anchor_id,
        attribution_type=AttributionType.PRIMARY,
        attribution_method=_method_to_enum(attribution.method),
    )
