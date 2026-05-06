"""Batch aspect tagger.

Iterates every ``(mention, product)`` attribution pair and runs it through
``AspectClassifier.classify``. Per-pair idempotency: if an aspect tag row
already exists for ``(mention_id, product_id, taxonomy_version,
prompt_version)`` the pair is skipped. A pair with zero existing tags is
reclassified — but the ``llm_cache`` hit makes that a cheap no-op.

Scope: all attributions whose ``product_id`` is in the caller-supplied
product set. No run filter on the aspect_tags table itself — aggregation
uses ``taxonomy_version`` to select the right tags at rollup time.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmConnectionError, LlmParseError, LlmResponseError
from pulse_check.storage.models import AspectTag, Mention, MentionAttribution
from pulse_check.tagging.aspect_classifier import (
    TAXONOMY_VERSION,
    AspectClassifier,
    ProductContext,
)

log = logging.getLogger(__name__)

# Halt the batch after this many consecutive infrastructure failures
# (connection timeout / HTTP error). Parse failures are mention-specific
# and do not count toward this threshold.
_MAX_CONSECUTIVE_INFRA_FAILURES = 3


@dataclass(frozen=True)
class BatchTagStats:
    """Outcome summary of one batch tagging run."""

    attributions_seen: int
    attributions_skipped_existing: int
    attributions_classified: int
    aspect_tags_inserted: int


def tag_corpus_aspects(
    session: Session,
    *,
    classifier: AspectClassifier,
    products: Iterable[ProductContext],
    taxonomy_version: str = TAXONOMY_VERSION,
) -> BatchTagStats:
    """Tag every in-scope ``(mention, product)`` pair with aspects.

    Arguments
    ---------
    session:
        Open SQLAlchemy session. This function flushes but does not commit;
        the caller owns the transaction boundary.
    classifier:
        Configured ``AspectClassifier``. Its ``prompt_version`` + ``model`` +
        ``temperature`` are stamped onto each inserted ``AspectTag`` row and
        are part of the uniqueness key.
    products:
        Product set in scope for this tagging pass. Only attributions whose
        ``product_id`` appears here get classified.
    taxonomy_version:
        Written to each new aspect_tags row. Defaults to the classifier
        module's ``TAXONOMY_VERSION`` ("v0").
    """
    product_by_id: dict[str, ProductContext] = {p.product_id: p for p in products}
    if not product_by_id:
        log.warning("tag_corpus_aspects: empty product set; nothing to do")
        return BatchTagStats(0, 0, 0, 0)

    already_tagged: set[tuple[str, str]] = set(
        session.execute(
            select(AspectTag.mention_id, AspectTag.product_id)
            .where(
                AspectTag.taxonomy_version == taxonomy_version,
                AspectTag.prompt_version == classifier.prompt_version,
            )
            .distinct()
        )
        .tuples()
        .all()
    )

    attributions = (
        session.execute(
            select(MentionAttribution).where(
                MentionAttribution.product_id.in_(product_by_id.keys())
            )
        )
        .scalars()
        .all()
    )

    seen = 0
    skipped = 0
    classified = 0
    inserted = 0
    consecutive_infra_failures = 0

    for attribution in attributions:
        seen += 1
        key = (attribution.mention_id, attribution.product_id)
        if key in already_tagged:
            skipped += 1
            continue

        mention = session.get(Mention, attribution.mention_id)
        if mention is None:
            log.warning(
                "tag_corpus_aspects: attribution references missing mention_id=%s; skipping",
                attribution.mention_id,
            )
            continue

        product = product_by_id[attribution.product_id]
        try:
            preds = classifier.classify(
                session,
                mention_text=mention.raw_text,
                product=product,
            )
        except LlmParseError as exc:
            # Qwen produced a structurally invalid response for this mention.
            # Mention-specific; Ollama is healthy. Don't trip the circuit breaker.
            log.warning(
                "classify parse failure on mention_id=%s product_id=%s: %s",
                attribution.mention_id,
                attribution.product_id,
                exc,
            )
            already_tagged.add(key)
            consecutive_infra_failures = 0
            continue
        except (LlmConnectionError, LlmResponseError) as exc:
            # Infrastructure-level failure (timeout / HTTP error). Skip this
            # mention; halt the batch if too many in a row so we don't churn
            # for hours while Ollama is down.
            consecutive_infra_failures += 1
            log.warning(
                "classify infra failure (%d/%d consecutive) on mention_id=%s "
                "product_id=%s: %s",
                consecutive_infra_failures,
                _MAX_CONSECUTIVE_INFRA_FAILURES,
                attribution.mention_id,
                attribution.product_id,
                exc,
            )
            already_tagged.add(key)
            if consecutive_infra_failures >= _MAX_CONSECUTIVE_INFRA_FAILURES:
                log.error(
                    "halting batch after %d consecutive infra failures; "
                    "partial progress will be committed by the caller",
                    consecutive_infra_failures,
                )
                break
            continue
        classified += 1
        consecutive_infra_failures = 0

        for pred in preds:
            session.add(
                AspectTag(
                    mention_id=mention.mention_id,
                    product_id=product.product_id,
                    aspect=pred.aspect,
                    polarity=pred.polarity,
                    intensity=pred.intensity,
                    classifier_confidence=pred.confidence,
                    taxonomy_version=taxonomy_version,
                    prompt_version=classifier.prompt_version,
                    model=classifier.model,
                    temperature=classifier.temperature,
                )
            )
            inserted += 1

        # Block a duplicate-attribution (primary+secondary for same pair) from
        # running the classifier + insert a second time in this pass.
        already_tagged.add(key)

    session.flush()
    return BatchTagStats(
        attributions_seen=seen,
        attributions_skipped_existing=skipped,
        attributions_classified=classified,
        aspect_tags_inserted=inserted,
    )
