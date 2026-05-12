"""Unit tests for the Sonnet reason labeler.

Coverage priorities:
- Constants are the new labeling-namespace values
- ``label()`` returns ``list[ReasonPrediction]``; passes Sonnet model + T=0
  to the underlying client; reuses the tagger's ``build_prompt`` (same
  markers + reason-bucket section in the rendered prompt)
- Cache key matches the tagger's discipline: comment + winning product_id +
  op_post + sorted products_discussed ids; excludes display-name strings and
  product order; cache namespace is distinct from the tagger's
- Parse delegation: top-level shape failure raises ``LlmParseError``; the
  tagger's defensive dedup + unknown-enum drop fire through the labeler too
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from pulse_check.eval.reason_labeler import (
    PROMPT_VERSION,
    ReasonLabeler,
)
from pulse_check.llm_cache import LlmParseError, LlmResponse
from pulse_check.storage.enums import Intensity, Polarity, ReasonBucket
from pulse_check.tagging.aspect_classifier import ProductContext
from pulse_check.tagging.reason_tagger import (
    ReasonPrediction,
    ReasonTagger,
    ThreadContext,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_PRODUCTS = (
    ProductContext(product_id="alienware_16_aurora", display_name="Alienware 16 Aurora"),
    ProductContext(product_id="rog_strix_g16", display_name="ROG Strix G16"),
)


def _good_response(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "reasons": [
            {"reason_bucket": "thermals", "polarity": "positive", "intensity": "high"},
        ],
    }
    base.update(overrides)
    return base


def _make_client(*responses: dict[str, Any]) -> MagicMock:
    client = MagicMock()
    payloads = [
        LlmResponse(raw_output=json.dumps(r), parsed_output=r) for r in responses
    ]
    if len(payloads) == 1:
        client.generate_json.return_value = payloads[0]
    else:
        client.generate_json.side_effect = payloads
    return client


def _context(**overrides: Any) -> ThreadContext:
    base: dict[str, Any] = {
        "winning_product_id": "alienware_16_aurora",
        "winning_product_display_name": "Alienware 16 Aurora",
        "op_post_text": "Help me decide between Alienware 16 and ROG Strix G16",
        "products_discussed": _PRODUCTS,
    }
    base.update(overrides)
    return ThreadContext(**base)


_COMMENT = "Thermals on the Alienware are way better under load."


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_prompt_version_is_reason_labeling_v1() -> None:
    assert PROMPT_VERSION == "reason_labeling_v1"


def test_default_model_is_sonnet() -> None:
    labeler = ReasonLabeler(_make_client(_good_response()))
    assert labeler.model == "claude-sonnet-4-6"


def test_default_temperature_is_zero() -> None:
    labeler = ReasonLabeler(_make_client(_good_response()))
    assert labeler.temperature == 0.0


# ---------------------------------------------------------------------------
# Happy path + arg flow into generate_json
# ---------------------------------------------------------------------------


def test_label_returns_list_of_reason_prediction(session: Session) -> None:
    client = _make_client(_good_response())
    out = ReasonLabeler(client).label(
        session, comment_text=_COMMENT, context=_context()
    )
    assert len(out) == 1
    assert isinstance(out[0], ReasonPrediction)
    assert out[0].reason_bucket == ReasonBucket.THERMALS
    assert out[0].polarity == Polarity.POSITIVE
    assert out[0].intensity == Intensity.HIGH


def test_label_invokes_generate_json_with_sonnet_model(session: Session) -> None:
    client = _make_client(_good_response())
    ReasonLabeler(client).label(session, comment_text=_COMMENT, context=_context())
    assert client.generate_json.call_args.kwargs["model"] == "claude-sonnet-4-6"


def test_label_invokes_generate_json_with_temperature_zero(session: Session) -> None:
    client = _make_client(_good_response())
    ReasonLabeler(client).label(session, comment_text=_COMMENT, context=_context())
    assert client.generate_json.call_args.kwargs["temperature"] == 0.0


def test_label_passes_tagger_prompt_to_client(session: Session) -> None:
    """Labeler reuses tagger's build_prompt — known markers + reason list present."""
    client = _make_client(_good_response())
    ReasonLabeler(client).label(session, comment_text=_COMMENT, context=_context())
    prompt = client.generate_json.call_args.kwargs["prompt"]
    assert "REASON BUCKETS" in prompt
    assert "WINNING product" in prompt
    assert "thermals" in prompt
    assert _COMMENT in prompt


# ---------------------------------------------------------------------------
# Cache integration — identity + key composition
# ---------------------------------------------------------------------------


def test_label_caches_second_call_on_identical_input(session: Session) -> None:
    client = _make_client(_good_response())
    labeler = ReasonLabeler(client)
    labeler.label(session, comment_text=_COMMENT, context=_context())
    labeler.label(session, comment_text=_COMMENT, context=_context())
    assert client.generate_json.call_count == 1


def test_label_cache_misses_on_different_comment(session: Session) -> None:
    client = _make_client(_good_response(), _good_response())
    labeler = ReasonLabeler(client)
    labeler.label(session, comment_text="A", context=_context())
    labeler.label(session, comment_text="B", context=_context())
    assert client.generate_json.call_count == 2


def test_label_cache_independent_of_winning_display_name(session: Session) -> None:
    """winning_product_display_name renders but is NOT in the cache key."""
    client = _make_client(_good_response())
    labeler = ReasonLabeler(client)
    labeler.label(
        session, comment_text=_COMMENT, context=_context(winning_product_display_name="Old")
    )
    labeler.label(
        session, comment_text=_COMMENT, context=_context(winning_product_display_name="New")
    )
    assert client.generate_json.call_count == 1


def test_label_cache_independent_of_per_product_display_names(session: Session) -> None:
    """display_name strings per product render but are NOT in the cache key."""
    client = _make_client(_good_response())
    labeler = ReasonLabeler(client)
    products_renamed = (
        ProductContext(product_id="alienware_16_aurora", display_name="Old A"),
        ProductContext(product_id="rog_strix_g16", display_name="Old R"),
    )
    labeler.label(session, comment_text=_COMMENT, context=_context())
    labeler.label(
        session, comment_text=_COMMENT, context=_context(products_discussed=products_renamed)
    )
    assert client.generate_json.call_count == 1


def test_label_cache_independent_of_products_discussed_order(session: Session) -> None:
    """Cache key sorts product_ids; passing them reversed → cache hit."""
    client = _make_client(_good_response())
    labeler = ReasonLabeler(client)
    labeler.label(session, comment_text=_COMMENT, context=_context())
    labeler.label(
        session,
        comment_text=_COMMENT,
        context=_context(products_discussed=tuple(reversed(_PRODUCTS))),
    )
    assert client.generate_json.call_count == 1


def test_label_cache_misses_on_different_winning_product_id(session: Session) -> None:
    client = _make_client(_good_response(), _good_response())
    labeler = ReasonLabeler(client)
    labeler.label(
        session, comment_text=_COMMENT, context=_context(winning_product_id="alienware_16_aurora")
    )
    labeler.label(
        session, comment_text=_COMMENT, context=_context(winning_product_id="rog_strix_g16")
    )
    assert client.generate_json.call_count == 2


def test_label_cache_misses_on_different_op_post(session: Session) -> None:
    client = _make_client(_good_response(), _good_response())
    labeler = ReasonLabeler(client)
    labeler.label(session, comment_text=_COMMENT, context=_context(op_post_text="A"))
    labeler.label(session, comment_text=_COMMENT, context=_context(op_post_text="B"))
    assert client.generate_json.call_count == 2


def test_label_namespace_distinct_from_tagger(session: Session) -> None:
    """Same input via tagger + labeler produces TWO LLM calls (separate cache rows)."""
    tagger_client = _make_client(_good_response())
    labeler_client = _make_client(_good_response())
    ReasonTagger(tagger_client).classify(
        session, comment_text=_COMMENT, context=_context()
    )
    ReasonLabeler(labeler_client).label(
        session, comment_text=_COMMENT, context=_context()
    )
    assert tagger_client.generate_json.call_count == 1
    assert labeler_client.generate_json.call_count == 1


# ---------------------------------------------------------------------------
# Parse delegation — tagger's defensive rules must fire via labeler too
# ---------------------------------------------------------------------------


def test_label_raises_LlmParseError_on_invalid_response(session: Session) -> None:
    client = _make_client({"missing": "reasons"})
    with pytest.raises(LlmParseError):
        ReasonLabeler(client).label(
            session, comment_text=_COMMENT, context=_context()
        )


def test_label_dedups_within_response_by_bucket(session: Session) -> None:
    response = {
        "reasons": [
            {"reason_bucket": "thermals", "polarity": "positive", "intensity": "high"},
            {"reason_bucket": "thermals", "polarity": "negative", "intensity": "low"},
        ],
    }
    out = ReasonLabeler(_make_client(response)).label(
        session, comment_text=_COMMENT, context=_context()
    )
    assert len(out) == 1
    assert out[0].polarity == Polarity.POSITIVE


def test_label_drops_unknown_bucket(session: Session) -> None:
    response = {
        "reasons": [
            {"reason_bucket": "thermals", "polarity": "positive", "intensity": "high"},
            {"reason_bucket": "unknown_bucket", "polarity": "positive", "intensity": "low"},
        ],
    }
    out = ReasonLabeler(_make_client(response)).label(
        session, comment_text=_COMMENT, context=_context()
    )
    assert len(out) == 1
    assert out[0].reason_bucket == ReasonBucket.THERMALS


def test_label_returns_empty_list_when_no_reasons(session: Session) -> None:
    out = ReasonLabeler(_make_client({"reasons": []})).label(
        session, comment_text=_COMMENT, context=_context()
    )
    assert out == []


def test_label_returns_multiple_buckets(session: Session) -> None:
    response = {
        "reasons": [
            {"reason_bucket": "thermals", "polarity": "positive", "intensity": "high"},
            {"reason_bucket": "price_value", "polarity": "positive", "intensity": "medium"},
            {"reason_bucket": "build_quality", "polarity": "negative", "intensity": "low"},
        ],
    }
    out = ReasonLabeler(_make_client(response)).label(
        session, comment_text=_COMMENT, context=_context()
    )
    assert len(out) == 3
    buckets = {p.reason_bucket for p in out}
    assert buckets == {
        ReasonBucket.THERMALS,
        ReasonBucket.PRICE_VALUE,
        ReasonBucket.BUILD_QUALITY,
    }
