"""Batch content-type classifier.

Runs ``ContentTypeClassifier.classify`` over every distinct mention that
has at least one attribution to an in-scope product. Idempotent per
``(mention_id, prompt_version)`` — matches the unique constraint on
``content_type_tags``.

Mirrors the structure of ``aspect`` batch tagging (error isolation +
infra-failure circuit breaker).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmConnectionError, LlmParseError, LlmResponseError
from pulse_check.storage.models import ContentTypeTag, Mention, MentionAttribution
from pulse_check.tagging.content_type_classifier import ContentTypeClassifier

log = logging.getLogger(__name__)

_MAX_CONSECUTIVE_INFRA_FAILURES = 3


@dataclass(frozen=True)
class BatchContentTypeStats:
    mentions_seen: int
    mentions_skipped_existing: int
    mentions_classified: int
    tags_inserted: int
    parse_failures: int


def classify_corpus_content_type(
    session: Session,
    *,
    classifier: ContentTypeClassifier,
    product_ids: Iterable[str],
) -> BatchContentTypeStats:
    """Classify content-type for every distinct in-scope mention.

    Arguments
    ---------
    session:
        Open SQLAlchemy session. Flushes but does not commit; caller owns
        the transaction boundary.
    classifier:
        Configured ``ContentTypeClassifier``. Its ``prompt_version`` +
        ``model`` + ``temperature`` are stamped on every inserted row and
        contribute to the uniqueness key.
    product_ids:
        Only mentions with at least one attribution to one of these
        product_ids are classified. Mention-scoped: each unique mention
        is classified once, regardless of how many products it references.
    """
    pid_set = set(product_ids)
    if not pid_set:
        log.warning("classify_corpus_content_type: empty product set; nothing to do")
        return BatchContentTypeStats(0, 0, 0, 0, 0)

    in_scope_mention_ids: list[str] = list(
        session.execute(
            select(MentionAttribution.mention_id)
            .where(MentionAttribution.product_id.in_(pid_set))
            .distinct()
        )
        .scalars()
        .all()
    )

    already_tagged: set[str] = set(
        session.execute(
            select(ContentTypeTag.mention_id)
            .where(ContentTypeTag.prompt_version == classifier.prompt_version)
            .distinct()
        )
        .scalars()
        .all()
    )

    seen = 0
    skipped = 0
    classified = 0
    inserted = 0
    parse_failures = 0
    consecutive_infra_failures = 0

    for mention_id in in_scope_mention_ids:
        seen += 1
        if mention_id in already_tagged:
            skipped += 1
            continue

        mention = session.get(Mention, mention_id)
        if mention is None:
            log.warning(
                "classify_corpus_content_type: missing mention_id=%s; skipping",
                mention_id,
            )
            continue

        try:
            pred = classifier.classify(session, mention_text=mention.raw_text)
        except LlmParseError as exc:
            log.warning(
                "content_type parse failure on mention_id=%s: %s",
                mention_id,
                exc,
            )
            parse_failures += 1
            already_tagged.add(mention_id)
            consecutive_infra_failures = 0
            continue
        except (LlmConnectionError, LlmResponseError) as exc:
            consecutive_infra_failures += 1
            log.warning(
                "content_type infra failure (%d/%d consecutive) on mention_id=%s: %s",
                consecutive_infra_failures,
                _MAX_CONSECUTIVE_INFRA_FAILURES,
                mention_id,
                exc,
            )
            already_tagged.add(mention_id)
            if consecutive_infra_failures >= _MAX_CONSECUTIVE_INFRA_FAILURES:
                log.error(
                    "halting batch after %d consecutive infra failures",
                    consecutive_infra_failures,
                )
                break
            continue

        consecutive_infra_failures = 0
        classified += 1

        if pred is None:
            # parseable JSON but content_type was unrecognized — log already
            # emitted in parse_response. Don't insert; mark already-seen so
            # we don't re-classify in this pass on a duplicate.
            already_tagged.add(mention_id)
            continue

        session.add(
            ContentTypeTag(
                mention_id=mention_id,
                content_type=pred.content_type,
                classifier_confidence=pred.confidence,
                prompt_version=classifier.prompt_version,
                model=classifier.model,
                temperature=classifier.temperature,
            )
        )
        inserted += 1
        already_tagged.add(mention_id)

    session.flush()
    return BatchContentTypeStats(
        mentions_seen=seen,
        mentions_skipped_existing=skipped,
        mentions_classified=classified,
        tags_inserted=inserted,
        parse_failures=parse_failures,
    )
