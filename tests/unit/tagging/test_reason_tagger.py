"""Reason tagger tests.

Coverage priorities:
- Prompt is deterministic and embeds the 15-value ReasonBucket taxonomy,
  the polarity-relative-to-winner rule, the OP post, the winning product,
  and the products_discussed list (sorted internally for order-independence).
- parse_response: happy paths (single / multi / empty); defensive coercion
  drops unknown buckets / polarity / intensity values and dedups duplicates;
  raises ``LlmParseError`` only on top-level shape failure.
- ReasonTagger: cache miss calls Ollama + stores a row; cache hit does not;
  cache key is scoped to comment text + winning product_id + op_post_text +
  sorted products_discussed ids and ignores display_names.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmParseError
from pulse_check.storage.enums import Intensity, Polarity, ReasonBucket
from pulse_check.storage.models import LlmCache
from pulse_check.tagging.aspect_classifier import ProductContext
from pulse_check.tagging.ollama import OllamaClient
from pulse_check.tagging.reason_tagger import (
    PROMPT_VERSION,
    ReasonPrediction,
    ReasonTagger,
    ThreadContext,
    build_prompt,
    parse_response,
)

_AW16 = ProductContext(product_id="aw16", display_name="Alienware 16 Aurora")
_STRIX = ProductContext(product_id="strix_g16", display_name="ROG Strix G16")
_BLADE = ProductContext(product_id="razer_blade_16", display_name="Razer Blade 16")
_PRODUCTS_DISCUSSED = (_AW16, _STRIX, _BLADE)


def _ollama_with(handler: Callable[[httpx.Request], httpx.Response]) -> OllamaClient:
    transport = httpx.MockTransport(handler)
    return OllamaClient(client=httpx.Client(transport=transport, base_url="http://mock"))


def _canned(body: dict[str, object]) -> dict[str, object]:
    return {"response": json.dumps(body), "done": True}


def _empty_canned() -> dict[str, object]:
    return _canned({"reasons": []})


def _basic_context() -> ThreadContext:
    return ThreadContext(
        winning_product_id="aw16",
        winning_product_display_name="Alienware 16 Aurora",
        op_post_text="Trying to pick between the AW16, Strix G16, and Blade 16 for college.",
        products_discussed=_PRODUCTS_DISCUSSED,
    )


# ---------------------------------------------------------------------------
# Version constants
# ---------------------------------------------------------------------------


def test_prompt_version_is_v1_shape() -> None:
    assert PROMPT_VERSION.startswith("reason_tagger_v")


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------


def test_build_prompt_lists_all_15_reason_buckets() -> None:
    prompt = build_prompt(comment_text="anything", context=_basic_context())
    for bucket in ReasonBucket:
        assert bucket.value in prompt, f"missing {bucket.value} from prompt"


def test_build_prompt_distinguishes_overlap_buckets() -> None:
    # Each of the 4 extras names its nearest aspect-aligned neighbor in its
    # definition so the model can disambiguate. Assert the disambiguation
    # phrasing landed.
    prompt = build_prompt(comment_text="anything", context=_basic_context())
    assert "distinct from" in prompt
    assert "support_warranty" in prompt
    assert "price_value" in prompt
    assert "brand_loyalty" in prompt


def test_build_prompt_embeds_op_post() -> None:
    context = _basic_context()
    prompt = build_prompt(comment_text="my comment", context=context)
    assert context.op_post_text in prompt


def test_build_prompt_embeds_winning_product() -> None:
    context = _basic_context()
    prompt = build_prompt(comment_text="my comment", context=context)
    assert context.winning_product_id in prompt
    assert context.winning_product_display_name in prompt


def test_build_prompt_renders_all_products_discussed() -> None:
    prompt = build_prompt(comment_text="anything", context=_basic_context())
    for product in _PRODUCTS_DISCUSSED:
        assert product.product_id in prompt
        assert product.display_name in prompt


def test_build_prompt_embeds_comment_text() -> None:
    prompt = build_prompt(
        comment_text="The thermals on the AW16 sealed it for me.",
        context=_basic_context(),
    )
    assert "The thermals on the AW16 sealed it for me." in prompt


def test_build_prompt_includes_polarity_relative_to_winner_rule() -> None:
    # The polarity guide must spell out that it's relative to the WINNING
    # product — so the model maps both "endorses winner" AND "praises a
    # non-winner as a knock against the winner" correctly.
    prompt = build_prompt(comment_text="x", context=_basic_context())
    assert "WINNING product" in prompt
    assert "knock against the winner" in prompt


def test_build_prompt_is_deterministic() -> None:
    context = _basic_context()
    p1 = build_prompt(comment_text="hi", context=context)
    p2 = build_prompt(comment_text="hi", context=context)
    assert p1 == p2


def test_build_prompt_is_order_independent_in_products_discussed() -> None:
    ctx_1 = ThreadContext(
        winning_product_id="aw16",
        winning_product_display_name="Alienware 16 Aurora",
        op_post_text="op",
        products_discussed=(_AW16, _STRIX, _BLADE),
    )
    ctx_2 = ThreadContext(
        winning_product_id="aw16",
        winning_product_display_name="Alienware 16 Aurora",
        op_post_text="op",
        products_discussed=(_BLADE, _AW16, _STRIX),
    )
    assert build_prompt(comment_text="x", context=ctx_1) == build_prompt(
        comment_text="x", context=ctx_2
    )


def test_build_prompt_differs_per_comment_text() -> None:
    context = _basic_context()
    p1 = build_prompt(comment_text="first comment", context=context)
    p2 = build_prompt(comment_text="totally different comment text", context=context)
    assert p1 != p2


# ---------------------------------------------------------------------------
# parse_response — happy paths
# ---------------------------------------------------------------------------


def test_parse_response_single_reason() -> None:
    payload = {
        "reasons": [
            {"reason_bucket": "thermals", "polarity": "positive", "intensity": "high"}
        ]
    }
    out = parse_response(payload)
    assert out == [
        ReasonPrediction(
            reason_bucket=ReasonBucket.THERMALS,
            polarity=Polarity.POSITIVE,
            intensity=Intensity.HIGH,
        )
    ]


def test_parse_response_multi_reason() -> None:
    payload = {
        "reasons": [
            {"reason_bucket": "thermals", "polarity": "positive", "intensity": "high"},
            {"reason_bucket": "price_value", "polarity": "positive", "intensity": "medium"},
            {"reason_bucket": "keyboard", "polarity": "negative", "intensity": "low"},
        ]
    }
    out = parse_response(payload)
    assert {r.reason_bucket for r in out} == {
        ReasonBucket.THERMALS,
        ReasonBucket.PRICE_VALUE,
        ReasonBucket.KEYBOARD,
    }


def test_parse_response_empty_reasons_list_is_valid() -> None:
    out = parse_response({"reasons": []})
    assert out == []


def test_parse_response_handles_all_four_extras() -> None:
    payload = {
        "reasons": [
            {"reason_bucket": "brand_loyalty", "polarity": "positive", "intensity": "medium"},
            {"reason_bucket": "value_deal", "polarity": "positive", "intensity": "high"},
            {"reason_bucket": "support_reputation", "polarity": "negative", "intensity": "medium"},
            {"reason_bucket": "prior_ownership", "polarity": "neutral", "intensity": "low"},
        ]
    }
    out = parse_response(payload)
    assert {r.reason_bucket for r in out} == {
        ReasonBucket.BRAND_LOYALTY,
        ReasonBucket.VALUE_DEAL,
        ReasonBucket.SUPPORT_REPUTATION,
        ReasonBucket.PRIOR_OWNERSHIP,
    }


def test_parse_response_preserves_input_order_for_distinct_buckets() -> None:
    payload = {
        "reasons": [
            {"reason_bucket": "thermals", "polarity": "positive", "intensity": "high"},
            {"reason_bucket": "battery", "polarity": "negative", "intensity": "medium"},
            {"reason_bucket": "display", "polarity": "neutral", "intensity": "low"},
        ]
    }
    out = parse_response(payload)
    assert [r.reason_bucket for r in out] == [
        ReasonBucket.THERMALS,
        ReasonBucket.BATTERY,
        ReasonBucket.DISPLAY,
    ]


# ---------------------------------------------------------------------------
# parse_response — defensive coercion
# ---------------------------------------------------------------------------


def test_parse_response_drops_unknown_reason_bucket() -> None:
    payload = {
        "reasons": [
            {"reason_bucket": "thermals", "polarity": "positive", "intensity": "high"},
            {"reason_bucket": "haptics", "polarity": "positive", "intensity": "low"},  # unknown
        ]
    }
    out = parse_response(payload)
    assert len(out) == 1
    assert out[0].reason_bucket == ReasonBucket.THERMALS


def test_parse_response_drops_unknown_polarity() -> None:
    payload = {
        "reasons": [
            {"reason_bucket": "thermals", "polarity": "ecstatic", "intensity": "high"},
        ]
    }
    assert parse_response(payload) == []


def test_parse_response_drops_unknown_intensity() -> None:
    payload = {
        "reasons": [
            {"reason_bucket": "thermals", "polarity": "positive", "intensity": "blistering"},
        ]
    }
    assert parse_response(payload) == []


def test_parse_response_drops_entry_with_missing_field() -> None:
    payload = {
        "reasons": [
            {"reason_bucket": "thermals", "polarity": "positive"},  # no intensity
            {"reason_bucket": "battery", "intensity": "low"},  # no polarity
            {"polarity": "positive", "intensity": "low"},  # no bucket
        ]
    }
    assert parse_response(payload) == []


def test_parse_response_skips_non_dict_entry() -> None:
    payload = {
        "reasons": [
            "not a dict",
            {"reason_bucket": "thermals", "polarity": "positive", "intensity": "high"},
            42,
        ]
    }
    out = parse_response(payload)
    assert len(out) == 1
    assert out[0].reason_bucket == ReasonBucket.THERMALS


def test_parse_response_dedups_duplicate_buckets_first_wins() -> None:
    payload = {
        "reasons": [
            {"reason_bucket": "thermals", "polarity": "positive", "intensity": "high"},
            {"reason_bucket": "thermals", "polarity": "negative", "intensity": "low"},
        ]
    }
    out = parse_response(payload)
    assert len(out) == 1
    assert out[0].polarity == Polarity.POSITIVE
    assert out[0].intensity == Intensity.HIGH


def test_parse_response_strips_whitespace_and_lowercases_enum_values() -> None:
    payload = {
        "reasons": [
            {"reason_bucket": " THERMALS ", "polarity": "Positive", "intensity": " HIGH "},
        ]
    }
    out = parse_response(payload)
    assert len(out) == 1
    assert out[0].reason_bucket == ReasonBucket.THERMALS
    assert out[0].polarity == Polarity.POSITIVE
    assert out[0].intensity == Intensity.HIGH


def test_parse_response_drops_entry_with_non_string_field_value() -> None:
    payload = {
        "reasons": [
            {"reason_bucket": 12, "polarity": "positive", "intensity": "high"},
            {"reason_bucket": "thermals", "polarity": True, "intensity": "high"},
            {"reason_bucket": "thermals", "polarity": "positive", "intensity": None},
        ]
    }
    assert parse_response(payload) == []


# ---------------------------------------------------------------------------
# parse_response — top-level shape failures
# ---------------------------------------------------------------------------


def test_parse_response_raises_on_non_dict_top_level() -> None:
    with pytest.raises(LlmParseError, match="expected JSON object"):
        parse_response(["not", "a", "dict"])


def test_parse_response_raises_on_missing_reasons_key() -> None:
    with pytest.raises(LlmParseError, match="expected 'reasons'"):
        parse_response({"something_else": []})


def test_parse_response_raises_on_reasons_not_list() -> None:
    with pytest.raises(LlmParseError, match="expected 'reasons'"):
        parse_response({"reasons": "not a list"})


# ---------------------------------------------------------------------------
# ReasonTagger — cache integration
# ---------------------------------------------------------------------------


def test_classify_cache_miss_calls_ollama_and_stores_row(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_empty_canned())

    tagger = ReasonTagger(_ollama_with(handler))
    tagger.classify(session, comment_text="my comment", context=_basic_context())
    session.commit()

    assert len(calls) == 1
    assert session.query(LlmCache).count() == 1


def test_classify_cache_hit_does_not_call_ollama(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_empty_canned())

    tagger = ReasonTagger(_ollama_with(handler))
    tagger.classify(session, comment_text="my comment", context=_basic_context())
    session.commit()
    tagger.classify(session, comment_text="my comment", context=_basic_context())

    assert len(calls) == 1


def test_classify_cache_scoped_per_comment_text(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_empty_canned())

    tagger = ReasonTagger(_ollama_with(handler))
    tagger.classify(session, comment_text="comment one", context=_basic_context())
    tagger.classify(session, comment_text="comment two", context=_basic_context())
    session.commit()

    assert len(calls) == 2
    assert session.query(LlmCache).count() == 2


def test_classify_cache_scoped_per_winning_product(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_empty_canned())

    tagger = ReasonTagger(_ollama_with(handler))
    ctx_aw = _basic_context()
    ctx_strix = ThreadContext(
        winning_product_id="strix_g16",
        winning_product_display_name="ROG Strix G16",
        op_post_text=ctx_aw.op_post_text,
        products_discussed=ctx_aw.products_discussed,
    )
    tagger.classify(session, comment_text="same comment", context=ctx_aw)
    tagger.classify(session, comment_text="same comment", context=ctx_strix)
    session.commit()

    assert len(calls) == 2
    assert session.query(LlmCache).count() == 2


def test_classify_cache_scoped_per_op_post(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_empty_canned())

    tagger = ReasonTagger(_ollama_with(handler))
    ctx_a = _basic_context()
    ctx_b = ThreadContext(
        winning_product_id=ctx_a.winning_product_id,
        winning_product_display_name=ctx_a.winning_product_display_name,
        op_post_text="A completely different OP post.",
        products_discussed=ctx_a.products_discussed,
    )
    tagger.classify(session, comment_text="same", context=ctx_a)
    tagger.classify(session, comment_text="same", context=ctx_b)
    session.commit()

    assert len(calls) == 2


def test_classify_cache_ignores_winning_display_name(session: Session) -> None:
    """Same winning_product_id but renamed display_name → cache hit."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_empty_canned())

    tagger = ReasonTagger(_ollama_with(handler))
    ctx_a = _basic_context()
    ctx_b = ThreadContext(
        winning_product_id=ctx_a.winning_product_id,
        winning_product_display_name="Alienware 16 (Late 2025)",  # renamed
        op_post_text=ctx_a.op_post_text,
        products_discussed=ctx_a.products_discussed,
    )
    tagger.classify(session, comment_text="x", context=ctx_a)
    session.commit()
    tagger.classify(session, comment_text="x", context=ctx_b)

    assert len(calls) == 1
    assert session.query(LlmCache).count() == 1


def test_classify_cache_ignores_per_product_display_name(session: Session) -> None:
    """Renaming a product in products_discussed but keeping its id → cache hit."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_empty_canned())

    tagger = ReasonTagger(_ollama_with(handler))
    ctx_a = _basic_context()
    renamed_strix = ProductContext(product_id="strix_g16", display_name="Strix G16 (refreshed)")
    ctx_b = ThreadContext(
        winning_product_id=ctx_a.winning_product_id,
        winning_product_display_name=ctx_a.winning_product_display_name,
        op_post_text=ctx_a.op_post_text,
        products_discussed=(_AW16, renamed_strix, _BLADE),
    )
    tagger.classify(session, comment_text="x", context=ctx_a)
    session.commit()
    tagger.classify(session, comment_text="x", context=ctx_b)

    assert len(calls) == 1


def test_classify_cache_is_order_independent_in_products_discussed(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_empty_canned())

    tagger = ReasonTagger(_ollama_with(handler))
    ctx_1 = ThreadContext(
        winning_product_id="aw16",
        winning_product_display_name="Alienware 16 Aurora",
        op_post_text="op",
        products_discussed=(_AW16, _STRIX, _BLADE),
    )
    ctx_2 = ThreadContext(
        winning_product_id="aw16",
        winning_product_display_name="Alienware 16 Aurora",
        op_post_text="op",
        products_discussed=(_BLADE, _STRIX, _AW16),
    )
    tagger.classify(session, comment_text="same", context=ctx_1)
    session.commit()
    tagger.classify(session, comment_text="same", context=ctx_2)

    assert len(calls) == 1


def test_classify_sends_temperature_zero_and_json_format(session: Session) -> None:
    bodies: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content.decode())
        return httpx.Response(200, json=_empty_canned())

    tagger = ReasonTagger(_ollama_with(handler))
    tagger.classify(session, comment_text="x", context=_basic_context())

    assert len(bodies) == 1
    assert '"temperature":0.0' in bodies[0]
    assert '"format":"json"' in bodies[0]


def test_prompt_version_bump_invalidates_cache(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=_empty_canned())

    client = _ollama_with(handler)
    v1 = ReasonTagger(client, prompt_version="reason_tagger_v1")
    v2 = ReasonTagger(client, prompt_version="reason_tagger_v2")

    v1.classify(session, comment_text="x", context=_basic_context())
    session.commit()
    v2.classify(session, comment_text="x", context=_basic_context())
    session.commit()

    assert len(calls) == 2
    rows = session.query(LlmCache).order_by(LlmCache.prompt_version).all()
    assert [r.prompt_version for r in rows] == ["reason_tagger_v1", "reason_tagger_v2"]


def test_classify_returns_parsed_predictions(session: Session) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_canned(
                {
                    "reasons": [
                        {"reason_bucket": "thermals", "polarity": "positive", "intensity": "high"},
                        {
                            "reason_bucket": "price_value",
                            "polarity": "negative",
                            "intensity": "medium",
                        },
                    ]
                }
            ),
        )

    tagger = ReasonTagger(_ollama_with(handler))
    out = tagger.classify(session, comment_text="x", context=_basic_context())
    assert len(out) == 2
    assert out[0].reason_bucket == ReasonBucket.THERMALS
    assert out[1].reason_bucket == ReasonBucket.PRICE_VALUE
