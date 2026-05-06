"""Content-type classifier tests.

Coverage priorities:
- Prompt is deterministic, embeds mention text, advertises 3 buckets
- parse_response: happy / missing-content_type / case canon / bad shape
- ContentTypeClassifier: cache miss calls client + stores row; cache hit does not
- Cache scoped per mention_text only (no product context)
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmParseError
from pulse_check.storage.enums import ContentType
from pulse_check.storage.models import LlmCache
from pulse_check.tagging.content_type_classifier import (
    PROMPT_VERSION,
    ContentTypeClassifier,
    ContentTypePrediction,
    build_prompt,
    parse_response,
)
from pulse_check.tagging.ollama import OllamaClient


def _ollama_with(handler: Callable[[httpx.Request], httpx.Response]) -> OllamaClient:
    transport = httpx.MockTransport(handler)
    return OllamaClient(client=httpx.Client(transport=transport, base_url="http://mock"))


def _canned(body: dict[str, object]) -> dict[str, object]:
    return {"response": json.dumps(body), "done": True}


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_prompt_version_is_v1_shape() -> None:
    assert PROMPT_VERSION.startswith("content_type_classifier_v")


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------


def test_build_prompt_advertises_all_three_buckets() -> None:
    prompt = build_prompt(mention_text="x")
    for ct in ContentType:
        assert ct.value in prompt, f"missing bucket {ct.value}"


def test_build_prompt_embeds_mention_text() -> None:
    prompt = build_prompt(mention_text="fans are loud and the price was great")
    assert "fans are loud and the price was great" in prompt


def test_build_prompt_is_deterministic() -> None:
    p1 = build_prompt(mention_text="same input")
    p2 = build_prompt(mention_text="same input")
    assert p1 == p2


def test_build_prompt_clips_long_text() -> None:
    long_text = "abc " * 2000  # 8000 chars, exceeds 3000 cap
    prompt = build_prompt(mention_text=long_text)
    assert len(prompt) < len(long_text) + 2000  # prompt overhead bounded


# ---------------------------------------------------------------------------
# parse_response
# ---------------------------------------------------------------------------


def test_parse_response_happy_path() -> None:
    payload = {"content_type": "review", "confidence": 0.85, "rationale": "first-person eval"}
    pred = parse_response(payload)
    assert pred == ContentTypePrediction(
        content_type=ContentType.REVIEW, confidence=0.85, rationale="first-person eval"
    )


def test_parse_response_canonicalizes_case() -> None:
    pred = parse_response({"content_type": "DEAL", "confidence": 0.9})
    assert pred is not None
    assert pred.content_type is ContentType.DEAL


def test_parse_response_missing_confidence_is_allowed() -> None:
    pred = parse_response({"content_type": "other"})
    assert pred is not None
    assert pred.content_type is ContentType.OTHER
    assert pred.confidence is None
    assert pred.rationale is None


def test_parse_response_unknown_content_type_returns_none() -> None:
    assert parse_response({"content_type": "spam", "confidence": 0.7}) is None


def test_parse_response_missing_content_type_returns_none() -> None:
    assert parse_response({"confidence": 0.7}) is None


def test_parse_response_drops_confidence_out_of_range() -> None:
    pred = parse_response({"content_type": "review", "confidence": 1.5})
    assert pred is not None
    assert pred.confidence is None


def test_parse_response_drops_confidence_bool() -> None:
    pred = parse_response({"content_type": "review", "confidence": True})
    assert pred is not None
    assert pred.confidence is None


def test_parse_response_raises_on_non_dict() -> None:
    with pytest.raises(LlmParseError):
        parse_response([])


# ---------------------------------------------------------------------------
# ContentTypeClassifier — cache integration
# ---------------------------------------------------------------------------


def test_classify_cache_miss_calls_client_and_stores_row(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200, json=_canned({"content_type": "review", "confidence": 0.9})
        )

    classifier = ContentTypeClassifier(_ollama_with(handler), model="qwen2.5:7b-q4_K_M")
    pred = classifier.classify(session, mention_text="two weeks with the laptop")
    session.commit()

    assert pred == ContentTypePrediction(
        content_type=ContentType.REVIEW, confidence=0.9, rationale=None
    )
    assert len(calls) == 1

    rows = session.query(LlmCache).all()
    assert len(rows) == 1
    assert rows[0].prompt_version == PROMPT_VERSION
    assert rows[0].temperature == 0.0


def test_classify_cache_hit_does_not_call_client(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_canned({"content_type": "deal"}))

    classifier = ContentTypeClassifier(_ollama_with(handler), model="qwen2.5:7b-q4_K_M")
    classifier.classify(session, mention_text="x")
    session.commit()
    classifier.classify(session, mention_text="x")

    assert len(calls) == 1


def test_classify_cache_scoped_per_mention_text(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_canned({"content_type": "review"}))

    classifier = ContentTypeClassifier(_ollama_with(handler), model="qwen2.5:7b-q4_K_M")
    classifier.classify(session, mention_text="text a")
    classifier.classify(session, mention_text="text b")
    session.commit()

    assert len(calls) == 2
    assert session.query(LlmCache).count() == 2


def test_prompt_version_bump_invalidates_cache(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_canned({"content_type": "other"}))

    client = _ollama_with(handler)
    v1 = ContentTypeClassifier(
        client, model="qwen2.5:7b-q4_K_M", prompt_version="content_type_classifier_v1"
    )
    v2 = ContentTypeClassifier(
        client, model="qwen2.5:7b-q4_K_M", prompt_version="content_type_classifier_v2"
    )

    v1.classify(session, mention_text="x")
    session.commit()
    v2.classify(session, mention_text="x")
    session.commit()

    assert len(calls) == 2
    rows = session.query(LlmCache).order_by(LlmCache.prompt_version).all()
    assert [r.prompt_version for r in rows] == [
        "content_type_classifier_v1",
        "content_type_classifier_v2",
    ]
