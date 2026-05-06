"""Batch content-type classifier tests.

Coverage priorities:
- Happy path: in-scope mentions get classified into content_type_tags rows
- Idempotent re-run: mentions already classified at the same prompt_version skip
- Out-of-scope mentions (no attribution to any in-scope product) skipped
- Empty product set is a no-op
- Each unique mention is classified once per pass (mention-scoped, not pair-scoped)
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
from sqlalchemy.orm import Session

from pulse_check.storage.enums import (
    AttributionMethod,
    AttributionType,
    ContentType,
    SourceType,
)
from pulse_check.storage.models import (
    ContentTypeTag,
    Mention,
    MentionAttribution,
    Product,
)
from pulse_check.tagging.content_type_batch import classify_corpus_content_type
from pulse_check.tagging.content_type_classifier import (
    PROMPT_VERSION,
    ContentTypeClassifier,
)
from pulse_check.tagging.ollama import OllamaClient


def _ollama(handler: Callable[[httpx.Request], httpx.Response]) -> OllamaClient:
    return OllamaClient(
        client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://mock")
    )


def _canned(body: dict[str, object]) -> dict[str, object]:
    return {"response": json.dumps(body), "done": True}


def _make_product(session: Session, product_id: str) -> Product:
    p = Product(product_id=product_id, display_name=product_id, brand="x")
    session.add(p)
    return p


def _make_mention(session: Session, mention_id: str, text: str) -> Mention:
    m = Mention(
        mention_id=mention_id,
        source_type=SourceType.REDDIT_POST,
        source_url=f"https://reddit.com/{mention_id}",
        raw_text=text,
        metadata_={},
    )
    session.add(m)
    return m


def _attach(
    session: Session,
    mention_id: str,
    product_id: str,
    attribution_type: AttributionType = AttributionType.PRIMARY,
) -> None:
    session.add(
        MentionAttribution(
            mention_id=mention_id,
            product_id=product_id,
            attribution_type=attribution_type,
            attribution_method=AttributionMethod.REGEX,
        )
    )


def _fixture(session: Session) -> None:
    _make_product(session, "aw16")
    _make_product(session, "strix_g16")
    _make_mention(session, "m1", "two weeks with the alienware. keys feel mushy.")
    _make_mention(session, "m2", "best deal of the year: alienware $899 at BB!")
    _attach(session, "m1", "aw16")
    _attach(session, "m2", "aw16")
    session.flush()


def _classifier(handler: Callable[[httpx.Request], httpx.Response]) -> ContentTypeClassifier:
    return ContentTypeClassifier(_ollama(handler), model="qwen2.5:7b-q4_K_M")


def test_happy_path_classifies_in_scope_mentions(session: Session) -> None:
    _fixture(session)

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if "two weeks" in body:
            return httpx.Response(200, json=_canned({"content_type": "review", "confidence": 0.9}))
        return httpx.Response(200, json=_canned({"content_type": "deal", "confidence": 0.95}))

    stats = classify_corpus_content_type(
        session, classifier=_classifier(handler), product_ids=["aw16"]
    )
    session.commit()

    assert stats.mentions_seen == 2
    assert stats.mentions_classified == 2
    assert stats.tags_inserted == 2

    rows = session.query(ContentTypeTag).all()
    by_id = {r.mention_id: r.content_type for r in rows}
    assert by_id == {"m1": ContentType.REVIEW, "m2": ContentType.DEAL}
    assert rows[0].prompt_version == PROMPT_VERSION


def test_idempotent_rerun_skips_existing(session: Session) -> None:
    _fixture(session)

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=_canned({"content_type": "review"}))

    classify_corpus_content_type(
        session, classifier=_classifier(handler), product_ids=["aw16"]
    )
    session.commit()
    first = call_count

    stats = classify_corpus_content_type(
        session, classifier=_classifier(handler), product_ids=["aw16"]
    )
    session.commit()

    assert call_count == first
    assert stats.mentions_skipped_existing == 2
    assert stats.mentions_classified == 0
    assert stats.tags_inserted == 0


def test_out_of_scope_mentions_skipped(session: Session) -> None:
    _fixture(session)
    _make_product(session, "legion_7i")
    _make_mention(session, "m3", "legion is great")
    _attach(session, "m3", "legion_7i")
    session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_canned({"content_type": "review"}))

    stats = classify_corpus_content_type(
        session, classifier=_classifier(handler), product_ids=["aw16"]
    )
    session.commit()

    assert stats.mentions_seen == 2  # m3/legion not seen
    rows = session.query(ContentTypeTag).filter_by(mention_id="m3").count()
    assert rows == 0


def test_empty_products_is_noop(session: Session) -> None:
    _fixture(session)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("classifier should not be called")

    stats = classify_corpus_content_type(
        session, classifier=_classifier(handler), product_ids=[]
    )
    assert stats == type(stats)(0, 0, 0, 0, 0)


def test_unique_mention_classified_once_per_pass(session: Session) -> None:
    """A mention attributed to multiple products should still be classified once
    (content type is mention-scoped)."""
    _fixture(session)
    # Add a secondary attribution: m1 → strix_g16 (so m1 is in scope via two products)
    _attach(session, "m1", "strix_g16", attribution_type=AttributionType.SECONDARY)
    session.flush()

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=_canned({"content_type": "review"}))

    stats = classify_corpus_content_type(
        session, classifier=_classifier(handler), product_ids=["aw16", "strix_g16"]
    )
    session.commit()

    # m1 + m2 both in scope; m1 classified once despite attribution to two products.
    assert stats.mentions_seen == 2
    assert stats.mentions_classified == 2
    assert call_count == 2
    assert session.query(ContentTypeTag).filter_by(mention_id="m1").count() == 1
