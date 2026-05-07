"""Post-ingest comment-attribution inheritance.

When `fetch_reddit_comments` runs with `emit_all_comments=True` (bite
6.2-revised follow-up), comments arrive in the DB with no attribution
unless their own text matches an anchor regex. The standard
`apply_secondary_attribution` sweep upgrades those whose text matches a
product's combined primary+secondary patterns. Many comments still slip
through with zero attributions because they don't re-name the product
("yeah, same issue", "+1 to OP", etc.) even though they're substantive
discussion under a primary-attributed Reddit POST.

This pass is the safety net: for every reddit_comment Mention with **zero**
attributions whose `metadata_["parent_id"]` (Reddit ``link_id``) matches a
primary-attributed reddit_post in the DB, write SECONDARY attribution rows
inheriting the parent's products. The attribution_method is REGEX since
the inheritance chain ultimately roots in the parent post's primary regex
match (not a brand-new method enum value).

Run this pass AFTER `apply_secondary_attribution` so comments whose own
text matched a regex don't also pick up an inherited row redundantly.
Idempotent: re-running on a corpus where every comment already has at
least one attribution is a no-op.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.storage.enums import AttributionMethod, AttributionType, SourceType
from pulse_check.storage.models import Mention, MentionAttribution

log = logging.getLogger(__name__)


@dataclass
class CommentInheritanceStats:
    comments_scanned: int = 0
    new_attributions: int = 0
    skipped_no_parent: int = 0
    skipped_parent_not_attributed: int = 0
    skipped_already_attributed: int = 0


def _post_id_from_post_mention_id(mention_id: str) -> str | None:
    """Recover the Reddit post_id from a `reddit_post_<post_id>_<anchor_id>`
    mention_id. Reddit post IDs are alphanumeric (base36) so we split on
    the first `_` after the prefix.
    """
    if not mention_id.startswith("reddit_post_"):
        return None
    rest = mention_id[len("reddit_post_") :]
    if not rest:
        return None
    head, _sep, _tail = rest.partition("_")
    return head or None


def apply_comment_inheritance(session: Session) -> CommentInheritanceStats:
    """Inherit parent-post primary attribution as SECONDARY on unattributed comments.

    Only operates on `reddit_comment` mentions with zero existing attributions.
    Caller owns the transaction (function flushes but does not commit).
    """
    stats = CommentInheritanceStats()

    parent_rows = session.execute(
        select(Mention.mention_id, MentionAttribution.product_id)
        .join(MentionAttribution, MentionAttribution.mention_id == Mention.mention_id)
        .where(
            Mention.source_type == SourceType.REDDIT_POST,
            MentionAttribution.attribution_type == AttributionType.PRIMARY,
        )
    ).all()
    parent_products: dict[str, set[str]] = {}
    for mention_id, product_id in parent_rows:
        post_id = _post_id_from_post_mention_id(mention_id)
        if post_id is None:
            continue
        parent_products.setdefault(post_id, set()).add(product_id)

    # Comments with zero attributions, evaluated via NOT EXISTS to keep the
    # query simple and survive multi-attribution comments cleanly.
    unattributed_comments = (
        session.execute(
            select(Mention).where(
                Mention.source_type == SourceType.REDDIT_COMMENT,
                ~select(MentionAttribution.attribution_id)
                .where(MentionAttribution.mention_id == Mention.mention_id)
                .exists(),
            )
        )
        .scalars()
        .all()
    )

    for comment in unattributed_comments:
        stats.comments_scanned += 1
        parent_link_id = comment.metadata_.get("parent_id")  # "t3_<post_id>"
        if not isinstance(parent_link_id, str) or not parent_link_id.startswith("t3_"):
            stats.skipped_no_parent += 1
            continue
        parent_post_id = parent_link_id[len("t3_") :]
        product_ids = parent_products.get(parent_post_id)
        if not product_ids:
            stats.skipped_parent_not_attributed += 1
            continue
        for product_id in product_ids:
            session.add(
                MentionAttribution(
                    mention_id=comment.mention_id,
                    product_id=product_id,
                    attribution_type=AttributionType.SECONDARY,
                    attribution_method=AttributionMethod.REGEX,
                )
            )
            stats.new_attributions += 1

    session.flush()
    log.info(
        "comment-inheritance: scanned=%d new=%d no_parent=%d parent_not_attributed=%d",
        stats.comments_scanned,
        stats.new_attributions,
        stats.skipped_no_parent,
        stats.skipped_parent_not_attributed,
    )
    return stats
