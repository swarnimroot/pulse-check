"""Unit tests for the Sonnet deliberation labeler.

Coverage priorities:
- Constants are the new labeling-namespace values
- ``label()`` returns a ``DeliberationPrediction``; passes Sonnet model + T=0
  to the underlying client; reuses the classifier's ``build_prompt`` (same
  markers in the rendered prompt)
- Cache key is keyed on thread content + sorted product_ids; excludes
  ``thread_id`` and per-product ``display_name``; cache namespace is distinct
  from the classifier's so co-resident inputs don't collide
- Parse delegation: top-level shape failure raises ``LlmParseError``; the
  classifier's defensive consistency rules fire through the labeler too
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from pulse_check.eval.deliberation_labeler import (
    PROMPT_VERSION,
    DeliberationLabeler,
)
from pulse_check.llm_cache import LlmParseError, LlmResponse
from pulse_check.tagging.aspect_classifier import ProductContext
from pulse_check.tagging.deliberation_classifier import (
    DeliberationClassifier,
    DeliberationPrediction,
    DeliberationThread,
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
        "is_deliberation": True,
        "is_resolved": True,
        "products_discussed": ["alienware_16_aurora", "rog_strix_g16"],
        "chosen_product_id": "alienware_16_aurora",
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


def _make_client(*responses: dict[str, Any]) -> MagicMock:
    """MagicMock client returning the given parsed-JSON responses in order."""
    client = MagicMock()
    payloads = [
        LlmResponse(raw_output=json.dumps(r), parsed_output=r) for r in responses
    ]
    if len(payloads) == 1:
        client.generate_json.return_value = payloads[0]
    else:
        client.generate_json.side_effect = payloads
    return client


def _thread(**overrides: Any) -> DeliberationThread:
    base: dict[str, Any] = {
        "thread_id": "t1",
        "op_post_text": "Help me decide between Alienware 16 and ROG Strix G16",
        "op_edit_text": None,
        "op_top_level_comments": (),
        "other_top_level_comments": (),
    }
    base.update(overrides)
    return DeliberationThread(**base)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_prompt_version_is_deliberation_labeling_v2() -> None:
    assert PROMPT_VERSION == "deliberation_labeling_v2"


def test_default_model_is_sonnet() -> None:
    labeler = DeliberationLabeler(_make_client(_good_response()))
    assert labeler.model == "claude-sonnet-4-6"


def test_default_temperature_is_zero() -> None:
    labeler = DeliberationLabeler(_make_client(_good_response()))
    assert labeler.temperature == 0.0


# ---------------------------------------------------------------------------
# Happy path + arg flow into generate_json
# ---------------------------------------------------------------------------


def test_label_returns_deliberation_prediction(session: Session) -> None:
    client = _make_client(_good_response())
    pred = DeliberationLabeler(client).label(
        session, thread=_thread(), products=_PRODUCTS
    )
    assert isinstance(pred, DeliberationPrediction)
    assert pred.is_deliberation is True
    assert pred.is_resolved is True
    assert pred.products_discussed == ("alienware_16_aurora", "rog_strix_g16")
    assert pred.chosen_product_id == "alienware_16_aurora"
    assert pred.confidence == 0.9


def test_label_invokes_generate_json_with_sonnet_model(session: Session) -> None:
    client = _make_client(_good_response())
    DeliberationLabeler(client).label(session, thread=_thread(), products=_PRODUCTS)
    assert client.generate_json.call_args.kwargs["model"] == "claude-sonnet-4-6"


def test_label_invokes_generate_json_with_temperature_zero(session: Session) -> None:
    client = _make_client(_good_response())
    DeliberationLabeler(client).label(session, thread=_thread(), products=_PRODUCTS)
    assert client.generate_json.call_args.kwargs["temperature"] == 0.0


def test_label_passes_classifier_prompt_to_client(session: Session) -> None:
    """Labeler reuses classifier's build_prompt — markers + universe section present."""
    client = _make_client(_good_response())
    DeliberationLabeler(client).label(session, thread=_thread(), products=_PRODUCTS)
    prompt = client.generate_json.call_args.kwargs["prompt"]
    assert "[OP_POST]" in prompt
    assert "PRODUCT UNIVERSE" in prompt
    assert "alienware_16_aurora" in prompt


# ---------------------------------------------------------------------------
# Cache integration — identity + key composition
# ---------------------------------------------------------------------------


def test_label_caches_second_call_on_identical_input(session: Session) -> None:
    client = _make_client(_good_response())
    labeler = DeliberationLabeler(client)
    labeler.label(session, thread=_thread(), products=_PRODUCTS)
    labeler.label(session, thread=_thread(), products=_PRODUCTS)
    assert client.generate_json.call_count == 1


def test_label_cache_misses_on_different_op_post(session: Session) -> None:
    client = _make_client(_good_response(), _good_response())
    labeler = DeliberationLabeler(client)
    labeler.label(session, thread=_thread(op_post_text="A"), products=_PRODUCTS)
    labeler.label(session, thread=_thread(op_post_text="B"), products=_PRODUCTS)
    assert client.generate_json.call_count == 2


def test_label_cache_independent_of_thread_id(session: Session) -> None:
    """thread_id is for logging only; same content + different thread_id → cache hit."""
    client = _make_client(_good_response())
    labeler = DeliberationLabeler(client)
    labeler.label(session, thread=_thread(thread_id="t1"), products=_PRODUCTS)
    labeler.label(session, thread=_thread(thread_id="t2"), products=_PRODUCTS)
    assert client.generate_json.call_count == 1


def test_label_cache_independent_of_display_names(session: Session) -> None:
    """display_name strings render in the prompt but are NOT in the cache key."""
    client = _make_client(_good_response())
    labeler = DeliberationLabeler(client)
    products_renamed = (
        ProductContext(product_id="alienware_16_aurora", display_name="Old Name"),
        ProductContext(product_id="rog_strix_g16", display_name="Another Old Name"),
    )
    labeler.label(session, thread=_thread(), products=_PRODUCTS)
    labeler.label(session, thread=_thread(), products=products_renamed)
    assert client.generate_json.call_count == 1


def test_label_cache_independent_of_product_order(session: Session) -> None:
    """Cache key sorts product_ids; passing them reversed → cache hit."""
    client = _make_client(_good_response())
    labeler = DeliberationLabeler(client)
    labeler.label(session, thread=_thread(), products=_PRODUCTS)
    labeler.label(session, thread=_thread(), products=tuple(reversed(_PRODUCTS)))
    assert client.generate_json.call_count == 1


def test_label_cache_misses_on_different_product_universe(session: Session) -> None:
    client = _make_client(_good_response(), _good_response())
    labeler = DeliberationLabeler(client)
    only_alien = (ProductContext(product_id="alienware_16_aurora", display_name="A"),)
    only_rog = (ProductContext(product_id="rog_strix_g16", display_name="R"),)
    labeler.label(session, thread=_thread(), products=only_alien)
    labeler.label(session, thread=_thread(), products=only_rog)
    assert client.generate_json.call_count == 2


def test_label_cache_misses_on_different_op_edit(session: Session) -> None:
    client = _make_client(_good_response(), _good_response())
    labeler = DeliberationLabeler(client)
    labeler.label(session, thread=_thread(op_edit_text=None), products=_PRODUCTS)
    labeler.label(session, thread=_thread(op_edit_text="Edit added"), products=_PRODUCTS)
    assert client.generate_json.call_count == 2


def test_label_namespace_distinct_from_classifier(session: Session) -> None:
    """Same input via classifier + labeler produces TWO LLM calls (separate cache rows)."""
    classifier_client = _make_client(_good_response())
    labeler_client = _make_client(_good_response())
    DeliberationClassifier(classifier_client).classify(
        session, thread=_thread(), products=_PRODUCTS
    )
    DeliberationLabeler(labeler_client).label(
        session, thread=_thread(), products=_PRODUCTS
    )
    assert classifier_client.generate_json.call_count == 1
    assert labeler_client.generate_json.call_count == 1


# ---------------------------------------------------------------------------
# Parse delegation — classifier's defensive rules must fire via labeler too
# ---------------------------------------------------------------------------


def test_label_raises_LlmParseError_on_invalid_response(session: Session) -> None:
    client = _make_client({"missing": "fields"})
    with pytest.raises(LlmParseError):
        DeliberationLabeler(client).label(
            session, thread=_thread(), products=_PRODUCTS
        )


def test_label_demotes_chosen_when_not_in_discussed(session: Session) -> None:
    response = _good_response(
        products_discussed=["alienware_16_aurora"],
        chosen_product_id="rog_strix_g16",
    )
    pred = DeliberationLabeler(_make_client(response)).label(
        session, thread=_thread(), products=_PRODUCTS
    )
    assert pred.chosen_product_id is None
    assert pred.is_resolved is False


def test_label_drops_unknown_product_ids(session: Session) -> None:
    response = _good_response(
        products_discussed=["alienware_16_aurora", "unknown_product"],
        chosen_product_id="alienware_16_aurora",
    )
    pred = DeliberationLabeler(_make_client(response)).label(
        session, thread=_thread(), products=_PRODUCTS
    )
    assert "unknown_product" not in pred.products_discussed
    assert "alienware_16_aurora" in pred.products_discussed


def test_label_returns_confidence_field_when_present(session: Session) -> None:
    response = _good_response(confidence=0.42)
    pred = DeliberationLabeler(_make_client(response)).label(
        session, thread=_thread(), products=_PRODUCTS
    )
    assert pred.confidence == 0.42


def test_label_propagates_chosen_external_name(session: Session) -> None:
    """v2: external-winner payload flows through unchanged."""
    response = _good_response(
        chosen_product_id=None,
        chosen_external_name="Razer Blade 16",
    )
    pred = DeliberationLabeler(_make_client(response)).label(
        session, thread=_thread(), products=_PRODUCTS
    )
    assert pred.chosen_product_id is None
    assert pred.chosen_external_name == "Razer Blade 16"
    assert pred.is_resolved is True


def test_label_mutex_drops_external_when_chosen_set(session: Session) -> None:
    """v2: classifier's mutex coercion fires through the labeler too."""
    response = _good_response(
        chosen_external_name="Razer Blade 16",
    )
    # chosen_product_id stays "alienware_16_aurora" from _good_response default.
    pred = DeliberationLabeler(_make_client(response)).label(
        session, thread=_thread(), products=_PRODUCTS
    )
    assert pred.chosen_product_id == "alienware_16_aurora"
    assert pred.chosen_external_name is None


def test_label_full_thread_with_edit_and_comments(session: Session) -> None:
    """A populated thread (edit + OP + OTHER comments) flows end-to-end."""
    client = _make_client(_good_response())
    labeler = DeliberationLabeler(client)
    thread = _thread(
        op_edit_text="EDIT: leaning toward Alienware",
        op_top_level_comments=("Update from OP",),
        other_top_level_comments=("Have you considered the Aero X16?",),
    )
    pred = labeler.label(session, thread=thread, products=_PRODUCTS)
    assert isinstance(pred, DeliberationPrediction)
    prompt = client.generate_json.call_args.kwargs["prompt"]
    assert "[OP_EDIT]" in prompt
    assert "[OP_COMMENT 1]" in prompt
    assert "[OTHER_COMMENT 1]" in prompt
