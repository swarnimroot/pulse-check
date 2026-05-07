"""Aspect classifier tests.

Coverage priorities:
- Prompt is deterministic and embeds the 11 v0 aspects + product + mention text
- parse_response: happy path, empty, case canonicalization, dropped unknowns
- parse_response: raises on top-level shape issues
- AspectClassifier: cache miss calls Ollama + stores row; cache hit does not
- AspectClassifier: cache key is scoped per (mention_text, product_id)
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmParseError
from pulse_check.storage.enums import Aspect, Intensity, Polarity
from pulse_check.storage.models import LlmCache
from pulse_check.tagging.aspect_classifier import (
    PROMPT_VERSION,
    TAXONOMY_VERSION,
    AspectClassifier,
    AspectPrediction,
    ProductContext,
    build_prompt,
    parse_response,
)
from pulse_check.tagging.ollama import OllamaClient

_AW16 = ProductContext(product_id="aw16", display_name="Alienware 16 Aurora")
_STRIX = ProductContext(product_id="strix_g16", display_name="ROG Strix G16")


def _ollama_with(handler: Callable[[httpx.Request], httpx.Response]) -> OllamaClient:
    transport = httpx.MockTransport(handler)
    return OllamaClient(client=httpx.Client(transport=transport, base_url="http://mock"))


def _canned(body: dict[str, object]) -> dict[str, object]:
    return {"response": json.dumps(body), "done": True}


# ---------------------------------------------------------------------------
# Taxonomy + version constants
# ---------------------------------------------------------------------------


def test_taxonomy_version_matches_run_config_default() -> None:
    assert TAXONOMY_VERSION == "v0"


def test_prompt_version_is_v1_shape() -> None:
    assert PROMPT_VERSION.startswith("aspect_classifier_v")


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------


def test_build_prompt_includes_all_eleven_aspects() -> None:
    prompt = build_prompt(mention_text="x", product=_AW16)
    for aspect in Aspect:
        assert aspect.value in prompt, f"missing aspect {aspect.value}"


def test_build_prompt_embeds_mention_and_product_name() -> None:
    prompt = build_prompt(mention_text="fans are loud", product=_AW16)
    assert "fans are loud" in prompt
    assert "Alienware 16 Aurora" in prompt


def test_build_prompt_is_deterministic() -> None:
    p1 = build_prompt(mention_text="same input", product=_AW16)
    p2 = build_prompt(mention_text="same input", product=_AW16)
    assert p1 == p2


def test_build_prompt_differs_per_product_name() -> None:
    p1 = build_prompt(mention_text="x", product=_AW16)
    p2 = build_prompt(mention_text="x", product=_STRIX)
    assert p1 != p2


# ---------------------------------------------------------------------------
# parse_response
# ---------------------------------------------------------------------------


def test_parse_response_happy_path_multi_tag() -> None:
    payload = {
        "tags": [
            {
                "aspect": "thermals",
                "polarity": "negative",
                "intensity": "high",
                "confidence": 0.9,
            },
            {
                "aspect": "performance",
                "polarity": "positive",
                "intensity": "medium",
                "confidence": 0.7,
            },
        ]
    }
    preds = parse_response(payload)
    assert preds == [
        AspectPrediction(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH, 0.9),
        AspectPrediction(Aspect.PERFORMANCE, Polarity.POSITIVE, Intensity.MEDIUM, 0.7),
    ]


def test_parse_response_empty_tags_returns_empty_list() -> None:
    assert parse_response({"tags": []}) == []


def test_parse_response_missing_confidence_is_allowed() -> None:
    preds = parse_response(
        {"tags": [{"aspect": "thermals", "polarity": "negative", "intensity": "low"}]}
    )
    assert preds == [AspectPrediction(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.LOW, None)]


def test_parse_response_canonicalizes_case() -> None:
    payload = {
        "tags": [{"aspect": "THERMALS", "polarity": "Negative", "intensity": "HIGH"}],
    }
    preds = parse_response(payload)
    assert preds == [AspectPrediction(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH, None)]


def test_parse_response_drops_unknown_aspect_keeps_others() -> None:
    payload = {
        "tags": [
            {"aspect": "bluetooth", "polarity": "negative", "intensity": "low"},
            {"aspect": "thermals", "polarity": "negative", "intensity": "low"},
        ]
    }
    preds = parse_response(payload)
    assert len(preds) == 1
    assert preds[0].aspect is Aspect.THERMALS


def test_parse_response_drops_tag_missing_required_field() -> None:
    # No intensity → tag is dropped entirely.
    payload = {"tags": [{"aspect": "thermals", "polarity": "negative"}]}
    assert parse_response(payload) == []


def test_parse_response_drops_tag_with_unknown_polarity() -> None:
    payload = {
        "tags": [{"aspect": "thermals", "polarity": "meh", "intensity": "low"}],
    }
    assert parse_response(payload) == []


def test_parse_response_raises_on_missing_tags_key() -> None:
    with pytest.raises(LlmParseError):
        parse_response({"aspects": []})


def test_parse_response_raises_on_non_dict() -> None:
    with pytest.raises(LlmParseError):
        parse_response([])


def test_parse_response_dedupes_repeated_aspect_within_response() -> None:
    # Haiku occasionally emits two entries for the same aspect on long
    # comments. Keep first; dropping the duplicate prevents the
    # aspect_tags UNIQUE constraint from failing the whole batch.
    payload = {
        "tags": [
            {"aspect": "aesthetics", "polarity": "negative", "intensity": "medium"},
            {"aspect": "aesthetics", "polarity": "positive", "intensity": "low"},
            {"aspect": "thermals", "polarity": "negative", "intensity": "high"},
        ]
    }
    preds = parse_response(payload)
    assert len(preds) == 2
    assert preds[0].aspect is Aspect.AESTHETICS
    assert preds[0].polarity is Polarity.NEGATIVE  # first wins
    assert preds[0].intensity is Intensity.MEDIUM
    assert preds[1].aspect is Aspect.THERMALS


def test_parse_response_raises_on_tags_not_list() -> None:
    with pytest.raises(LlmParseError):
        parse_response({"tags": "thermals"})


def test_parse_response_drops_confidence_out_of_range() -> None:
    preds = parse_response(
        {
            "tags": [
                {
                    "aspect": "thermals",
                    "polarity": "negative",
                    "intensity": "low",
                    "confidence": 1.5,
                }
            ]
        }
    )
    assert len(preds) == 1
    assert preds[0].confidence is None


def test_parse_response_drops_confidence_bool() -> None:
    # bool is an int subclass; we explicitly reject it.
    preds = parse_response(
        {
            "tags": [
                {
                    "aspect": "thermals",
                    "polarity": "negative",
                    "intensity": "low",
                    "confidence": True,
                }
            ]
        }
    )
    assert preds[0].confidence is None


# ---------------------------------------------------------------------------
# AspectClassifier — cache integration
# ---------------------------------------------------------------------------


def test_classify_cache_miss_calls_ollama_and_stores_row(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=_canned(
                {"tags": [{"aspect": "thermals", "polarity": "negative", "intensity": "high"}]}
            ),
        )

    classifier = AspectClassifier(_ollama_with(handler))
    preds = classifier.classify(session, mention_text="runs very hot", product=_AW16)
    session.commit()

    assert preds == [AspectPrediction(Aspect.THERMALS, Polarity.NEGATIVE, Intensity.HIGH, None)]
    assert len(calls) == 1

    rows = session.query(LlmCache).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.prompt_version == PROMPT_VERSION
    assert row.model == "qwen2.5:7b-q4_K_M"
    assert row.temperature == 0.0


def test_classify_cache_hit_does_not_call_ollama(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_canned({"tags": []}))

    classifier = AspectClassifier(_ollama_with(handler))
    classifier.classify(session, mention_text="x", product=_AW16)
    session.commit()
    classifier.classify(session, mention_text="x", product=_AW16)

    assert len(calls) == 1


def test_classify_cache_scoped_per_product(session: Session) -> None:
    """Same text, different product_id → two cache rows, two Ollama calls."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_canned({"tags": []}))

    classifier = AspectClassifier(_ollama_with(handler))
    classifier.classify(session, mention_text="runs hot", product=_AW16)
    classifier.classify(session, mention_text="runs hot", product=_STRIX)
    session.commit()

    assert len(calls) == 2
    assert session.query(LlmCache).count() == 2


def test_classify_cache_scoped_per_mention_text(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_canned({"tags": []}))

    classifier = AspectClassifier(_ollama_with(handler))
    classifier.classify(session, mention_text="text a", product=_AW16)
    classifier.classify(session, mention_text="text b", product=_AW16)
    session.commit()

    assert len(calls) == 2
    assert session.query(LlmCache).count() == 2


def test_classify_sends_temperature_zero_in_request_body(session: Session) -> None:
    bodies: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content.decode())
        return httpx.Response(200, json=_canned({"tags": []}))

    classifier = AspectClassifier(_ollama_with(handler))
    classifier.classify(session, mention_text="x", product=_AW16)

    assert len(bodies) == 1
    assert '"temperature":0.0' in bodies[0]
    assert '"format":"json"' in bodies[0]


def test_prompt_version_bump_invalidates_cache(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_canned({"tags": []}))

    client = _ollama_with(handler)
    v1 = AspectClassifier(client, prompt_version="aspect_classifier_v1")
    v2 = AspectClassifier(client, prompt_version="aspect_classifier_v2")

    v1.classify(session, mention_text="x", product=_AW16)
    session.commit()
    v2.classify(session, mention_text="x", product=_AW16)
    session.commit()

    assert len(calls) == 2
    rows = session.query(LlmCache).order_by(LlmCache.prompt_version).all()
    assert [r.prompt_version for r in rows] == ["aspect_classifier_v1", "aspect_classifier_v2"]
