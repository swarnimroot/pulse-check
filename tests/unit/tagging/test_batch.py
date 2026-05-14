"""Batch aspect tagger tests.

Coverage priorities:
- Happy path: each attributed (mention, product) pair gets classified and
  produces aspect_tags rows
- Idempotent re-run: pairs already tagged under (taxonomy_version, prompt_version)
  are skipped without calling the classifier
- Out-of-scope attributions (product not in products set) are skipped
- Primary + secondary attributions for the same (mention, product) pair → one
  classify call + one set of tags (dedup inside the pass)
- Empty product set → no work
- Multiple aspects per mention are all stored with correct metadata
  (taxonomy_version, prompt_version, model, temperature)
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
    AspectTag,
    ContentTypeTag,
    Mention,
    MentionAttribution,
    Product,
)
from pulse_check.tagging import AspectClassifier, ProductContext
from pulse_check.tagging.aspect_classifier import PROMPT_VERSION
from pulse_check.tagging.batch import tag_corpus_aspects
from pulse_check.tagging.ollama import OllamaClient


def _ollama(handler: Callable[[httpx.Request], httpx.Response]) -> OllamaClient:
    return OllamaClient(
        client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://mock")
    )


def _canned_tags(*tags: dict[str, object]) -> dict[str, object]:
    return {"response": json.dumps({"tags": list(tags)}), "done": True}


def _make_product(session: Session, product_id: str, display_name: str) -> Product:
    p = Product(
        product_id=product_id,
        display_name=display_name,
        brand="alienware" if product_id.startswith("aw") else "other",
    )
    session.add(p)
    return p


def _make_mention(session: Session, mention_id: str, text: str) -> Mention:
    m = Mention(
        mention_id=mention_id,
        source_type=SourceType.REDDIT_POST,
        source_url=f"https://reddit.com/r/GamingLaptops/{mention_id}",
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
) -> MentionAttribution:
    a = MentionAttribution(
        mention_id=mention_id,
        product_id=product_id,
        attribution_type=attribution_type,
        attribution_method=AttributionMethod.REGEX,
    )
    session.add(a)
    return a


def _fixture(session: Session) -> None:
    _make_product(session, "aw16", "Alienware 16 Aurora")
    _make_product(session, "strix_g16", "ROG Strix G16")
    _make_mention(session, "m1", "fans are loud and it runs hot under load")
    _make_mention(session, "m2", "4090 crushes everything at 1440p")
    _attach(session, "m1", "aw16")
    _attach(session, "m2", "strix_g16")
    session.flush()


_AW16 = ProductContext(product_id="aw16", display_name="Alienware 16 Aurora")
_STRIX = ProductContext(product_id="strix_g16", display_name="ROG Strix G16")


# ---------------------------------------------------------------------------
# Happy path + metadata
# ---------------------------------------------------------------------------


def test_tag_corpus_produces_aspect_tag_rows(session: Session) -> None:
    _fixture(session)

    ollama_calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        ollama_calls.append(request)
        # Both mentions receive a single thermals/performance tag respectively.
        body = request.content.decode()
        if "fans are loud" in body:
            return httpx.Response(
                200,
                json=_canned_tags(
                    {
                        "aspect": "thermals",
                        "polarity": "negative",
                        "intensity": "high",
                        "confidence": 0.9,
                    }
                ),
            )
        return httpx.Response(
            200,
            json=_canned_tags(
                {
                    "aspect": "performance",
                    "polarity": "positive",
                    "intensity": "high",
                    "confidence": 0.85,
                }
            ),
        )

    classifier = AspectClassifier(_ollama(handler))
    stats = tag_corpus_aspects(session, classifier=classifier, products=[_AW16, _STRIX])
    session.commit()

    assert stats.attributions_seen == 2
    assert stats.attributions_skipped_existing == 0
    assert stats.attributions_classified == 2
    assert stats.aspect_tags_inserted == 2

    rows = session.query(AspectTag).all()
    assert {(r.mention_id, r.product_id, r.aspect.value) for r in rows} == {
        ("m1", "aw16", "thermals"),
        ("m2", "strix_g16", "performance"),
    }
    # Check one row for the stamped metadata.
    m1_row = next(r for r in rows if r.mention_id == "m1")
    assert m1_row.taxonomy_version == "v0"
    assert m1_row.prompt_version == PROMPT_VERSION
    assert m1_row.model == "qwen2.5:7b-q4_K_M"
    assert m1_row.temperature == 0.0
    assert m1_row.classifier_confidence == 0.9


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_tag_corpus_idempotent_reruns_skip_already_tagged(session: Session) -> None:
    _fixture(session)

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json=_canned_tags({"aspect": "thermals", "polarity": "negative", "intensity": "low"}),
        )

    classifier = AspectClassifier(_ollama(handler))

    # First pass tags both mentions.
    tag_corpus_aspects(session, classifier=classifier, products=[_AW16, _STRIX])
    session.commit()
    first_call_count = call_count
    assert first_call_count == 2

    # Second pass should hit zero classifier calls — both pairs already have
    # rows under the same (taxonomy_version, prompt_version).
    stats = tag_corpus_aspects(session, classifier=classifier, products=[_AW16, _STRIX])
    session.commit()

    assert call_count == first_call_count  # no new Ollama calls
    assert stats.attributions_seen == 2
    assert stats.attributions_skipped_existing == 2
    assert stats.attributions_classified == 0
    assert stats.aspect_tags_inserted == 0
    assert session.query(AspectTag).count() == 2


# ---------------------------------------------------------------------------
# Scope filtering
# ---------------------------------------------------------------------------


def test_tag_corpus_skips_attributions_outside_product_scope(session: Session) -> None:
    _fixture(session)  # aw16 + strix_g16 products
    # Attribute a mention to a product not in the scope.
    _make_product(session, "legion_7i", "Legion 7i")
    _make_mention(session, "m3", "display is fantastic")
    _attach(session, "m3", "legion_7i")
    session.flush()

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_canned_tags())

    classifier = AspectClassifier(_ollama(handler))
    # Only aw16 + strix are in scope.
    stats = tag_corpus_aspects(session, classifier=classifier, products=[_AW16, _STRIX])
    session.commit()

    assert stats.attributions_seen == 2  # m3/legion not seen
    assert session.query(AspectTag).filter_by(product_id="legion_7i").count() == 0


# ---------------------------------------------------------------------------
# Primary + secondary dedup
# ---------------------------------------------------------------------------


def test_tag_corpus_dedupes_primary_and_secondary_for_same_pair(session: Session) -> None:
    _fixture(session)
    # Add a secondary attribution for (m1, aw16) — same pair, different type.
    _attach(session, "m1", "aw16", attribution_type=AttributionType.SECONDARY)
    session.flush()

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=_canned_tags({"aspect": "thermals", "polarity": "negative", "intensity": "high"}),
        )

    classifier = AspectClassifier(_ollama(handler))
    stats = tag_corpus_aspects(session, classifier=classifier, products=[_AW16, _STRIX])
    session.commit()

    # attributions_seen counts both primary + secondary for m1/aw16 + m2/strix.
    assert stats.attributions_seen == 3
    # But we only classify the unique pair once per run.
    assert stats.attributions_classified == 2
    assert stats.aspect_tags_inserted == 2  # one tag per unique (mention, product)
    # Exactly one aspect_tag row for (m1, aw16, thermals) — not two.
    assert session.query(AspectTag).filter_by(mention_id="m1", product_id="aw16").count() == 1


# ---------------------------------------------------------------------------
# Empty corpus / no-op
# ---------------------------------------------------------------------------


def test_tag_corpus_empty_products_is_noop(session: Session) -> None:
    _fixture(session)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("classifier should not be called with empty product set")

    classifier = AspectClassifier(_ollama(handler))
    stats = tag_corpus_aspects(session, classifier=classifier, products=[])

    assert stats == type(stats)(0, 0, 0, 0)
    assert session.query(AspectTag).count() == 0


# ---------------------------------------------------------------------------
# Content-type filter (review/deal/other gate)
# ---------------------------------------------------------------------------


def _add_content_type_tag(
    session: Session, mention_id: str, content_type: ContentType
) -> None:
    session.add(
        ContentTypeTag(
            mention_id=mention_id,
            content_type=content_type,
            prompt_version="content_type_classifier_v1",
            model="claude-haiku-4-5-20251001",
            temperature=0.0,
        )
    )


def test_tag_corpus_filter_skips_excluded_content_types(session: Session) -> None:
    _fixture(session)
    _add_content_type_tag(session, "m1", ContentType.REVIEW)
    _add_content_type_tag(session, "m2", ContentType.DEAL)
    session.flush()

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=_canned_tags({"aspect": "thermals", "polarity": "negative", "intensity": "low"}),
        )

    classifier = AspectClassifier(_ollama(handler))
    stats = tag_corpus_aspects(
        session,
        classifier=classifier,
        products=[_AW16, _STRIX],
        exclude_content_types=frozenset({ContentType.DEAL}),
    )
    session.commit()

    # m2 is a DEAL → filtered. m1 is REVIEW → tagged.
    assert stats.attributions_seen == 2
    assert stats.attributions_skipped_content_filter == 1
    assert stats.attributions_classified == 1
    assert len(calls) == 1
    assert session.query(AspectTag).filter_by(mention_id="m2").count() == 0
    assert session.query(AspectTag).filter_by(mention_id="m1").count() == 1


def test_tag_corpus_filter_skips_unclassified_mentions_strictly(session: Session) -> None:
    _fixture(session)
    # Only m1 has a content_type_tag; m2 has none.
    _add_content_type_tag(session, "m1", ContentType.REVIEW)
    session.flush()

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=_canned_tags({"aspect": "thermals", "polarity": "negative", "intensity": "low"}),
        )

    classifier = AspectClassifier(_ollama(handler))
    stats = tag_corpus_aspects(
        session,
        classifier=classifier,
        products=[_AW16, _STRIX],
        exclude_content_types=frozenset({ContentType.DEAL}),
    )
    session.commit()

    # m2 has no content_type tag → strict gate skips it.
    assert stats.attributions_skipped_content_filter == 1
    assert stats.attributions_classified == 1
    assert len(calls) == 1


def test_tag_corpus_no_filter_does_not_skip(session: Session) -> None:
    _fixture(session)
    # Even with deal-tagged content, no filter means everything is tagged.
    _add_content_type_tag(session, "m1", ContentType.DEAL)
    _add_content_type_tag(session, "m2", ContentType.DEAL)
    session.flush()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_canned_tags({"aspect": "thermals", "polarity": "negative", "intensity": "low"}),
        )

    classifier = AspectClassifier(_ollama(handler))
    stats = tag_corpus_aspects(
        session, classifier=classifier, products=[_AW16, _STRIX]
    )
    session.commit()

    assert stats.attributions_skipped_content_filter == 0
    assert stats.attributions_classified == 2


def test_tag_corpus_multiple_aspects_per_mention(session: Session) -> None:
    _fixture(session)

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        if "fans are loud" in body:
            return httpx.Response(
                200,
                json=_canned_tags(
                    {"aspect": "thermals", "polarity": "negative", "intensity": "high"},
                    {"aspect": "performance", "polarity": "negative", "intensity": "medium"},
                ),
            )
        return httpx.Response(200, json=_canned_tags())

    classifier = AspectClassifier(_ollama(handler))
    stats = tag_corpus_aspects(session, classifier=classifier, products=[_AW16, _STRIX])
    session.commit()

    assert stats.aspect_tags_inserted == 2
    m1_aspects = {r.aspect.value for r in session.query(AspectTag).filter_by(mention_id="m1").all()}
    assert m1_aspects == {"thermals", "performance"}


def test_commit_every_fires_periodic_commits(session: Session, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """commit_every>0 should fire session.commit() at the configured cadence."""
    _fixture(session)

    commits: list[str] = []
    original = session.commit

    def spy() -> None:
        commits.append("commit")
        original()

    monkeypatch.setattr(session, "commit", spy)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_canned_tags({"aspect": "thermals", "polarity": "negative", "intensity": "low"}),
        )

    classifier = AspectClassifier(_ollama(handler))
    stats = tag_corpus_aspects(
        session,
        classifier=classifier,
        products=[_AW16, _STRIX],
        commit_every=1,
    )

    # 2 attributions classified at commit_every=1 → 2 mid-loop commits + 1 end-of-loop commit
    assert stats.attributions_classified == 2
    assert stats.aspect_tags_inserted == 2
    assert len(commits) == 3
