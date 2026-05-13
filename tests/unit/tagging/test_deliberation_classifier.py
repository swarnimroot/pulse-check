"""Deliberation classifier tests.

Coverage priorities:
- Prompt is deterministic and embeds the product universe, the OP-only
  resolution rule, and segment markers in the right places.
- parse_response: happy paths (resolved / unresolved / non-deliberation);
  defensive coercion drops unknown product_ids and demotes inconsistent
  states; raises only on top-level shape failure.
- DeliberationClassifier: cache miss calls Ollama + stores a row; cache hit
  does not; cache key is scoped to thread content + product universe and
  ignores thread_id / display_name.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmParseError
from pulse_check.storage.models import LlmCache
from pulse_check.tagging.aspect_classifier import ProductContext
from pulse_check.tagging.deliberation_classifier import (
    PROMPT_VERSION,
    DeliberationClassifier,
    DeliberationPrediction,
    DeliberationThread,
    build_prompt,
    parse_response,
)
from pulse_check.tagging.ollama import OllamaClient

_AW16 = ProductContext(product_id="aw16", display_name="Alienware 16 Aurora")
_STRIX = ProductContext(product_id="strix_g16", display_name="ROG Strix G16")
_BLADE = ProductContext(product_id="razer_blade_16", display_name="Razer Blade 16")
_UNIVERSE = (_AW16, _STRIX, _BLADE)


def _ollama_with(handler: Callable[[httpx.Request], httpx.Response]) -> OllamaClient:
    transport = httpx.MockTransport(handler)
    return OllamaClient(client=httpx.Client(transport=transport, base_url="http://mock"))


def _canned(body: dict[str, object]) -> dict[str, object]:
    return {"response": json.dumps(body), "done": True}


def _basic_thread(thread_id: str = "t_basic") -> DeliberationThread:
    return DeliberationThread(
        thread_id=thread_id,
        op_post_text="Trying to decide between the AW16 and Strix G16 for college.",
        op_edit_text=None,
        op_top_level_comments=(),
        other_top_level_comments=("Both are solid — depends on your weight tolerance.",),
    )


def _resolved_thread() -> DeliberationThread:
    return DeliberationThread(
        thread_id="t_resolved",
        op_post_text="AW16 vs Strix G16 — heading to college, gaming + class.",
        op_edit_text="EDIT: went with the AW16, thanks all.",
        op_top_level_comments=("Pulled the trigger on the AW16 last night.",),
        other_top_level_comments=("FWIW I think the Blade is better.",),
    )


# ---------------------------------------------------------------------------
# Version constants
# ---------------------------------------------------------------------------


def test_prompt_version_is_v1_shape() -> None:
    assert PROMPT_VERSION.startswith("deliberation_classifier_v")


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------


def test_build_prompt_renders_all_products_in_universe() -> None:
    prompt = build_prompt(thread=_basic_thread(), products=_UNIVERSE)
    for product in _UNIVERSE:
        assert product.product_id in prompt
        assert product.display_name in prompt


def test_build_prompt_includes_op_only_rule() -> None:
    prompt = build_prompt(thread=_basic_thread(), products=_UNIVERSE)
    # Substring asserts on the wording that defines the OP-only contract.
    assert "OP-only" not in prompt  # we don't use that shorthand; we spell it out
    assert "[OP_POST]" in prompt
    assert "[OP_EDIT]" in prompt
    assert "[OP_COMMENT" in prompt
    assert "[OTHER_COMMENT" in prompt
    assert "do NOT count toward resolution" in prompt


def test_build_prompt_renders_op_post_with_marker() -> None:
    thread = _basic_thread()
    prompt = build_prompt(thread=thread, products=_UNIVERSE)
    op_post_index = prompt.index(thread.op_post_text)
    op_marker_index = prompt.index("[OP_POST]")
    # OP_POST marker must precede the OP body text it labels.
    assert op_marker_index < op_post_index


def test_build_prompt_renders_op_edit_marker_when_present() -> None:
    thread = _resolved_thread()
    prompt = build_prompt(thread=thread, products=_UNIVERSE)
    assert "EDIT: went with the AW16" in prompt


def test_build_prompt_omits_op_edit_segment_when_absent() -> None:
    # Compare prompts with and without an op_edit: presence/absence of the
    # edit segment should be the *only* difference reflected in the [OP_EDIT]
    # marker count (legend + rule mentions stay constant).
    without_edit = build_prompt(thread=_basic_thread(), products=_UNIVERSE)
    with_edit = build_prompt(
        thread=DeliberationThread(
            thread_id="t",
            op_post_text=_basic_thread().op_post_text,
            op_edit_text="EDIT: an addendum that should appear",
            op_top_level_comments=_basic_thread().op_top_level_comments,
            other_top_level_comments=_basic_thread().other_top_level_comments,
        ),
        products=_UNIVERSE,
    )
    assert without_edit.count("[OP_EDIT]") + 1 == with_edit.count("[OP_EDIT]")
    assert "EDIT: an addendum that should appear" not in without_edit
    assert "EDIT: an addendum that should appear" in with_edit


def test_build_prompt_describes_chosen_external_name_field() -> None:
    """v2: prompt must instruct the model on the untracked-winner channel."""
    prompt = build_prompt(thread=_basic_thread(), products=_UNIVERSE)
    assert "chosen_external_name" in prompt
    assert "NOT in PRODUCT UNIVERSE" in prompt
    assert "mutually exclusive" in prompt


def test_build_prompt_renders_op_and_other_comment_markers() -> None:
    thread = _resolved_thread()
    prompt = build_prompt(thread=thread, products=_UNIVERSE)
    assert "[OP_COMMENT 1]" in prompt
    assert "Pulled the trigger on the AW16" in prompt
    assert "[OTHER_COMMENT 1]" in prompt
    assert "FWIW I think the Blade is better." in prompt


def test_build_prompt_is_deterministic() -> None:
    thread = _basic_thread()
    p1 = build_prompt(thread=thread, products=_UNIVERSE)
    p2 = build_prompt(thread=thread, products=_UNIVERSE)
    assert p1 == p2


def test_build_prompt_is_order_independent_in_products() -> None:
    p1 = build_prompt(thread=_basic_thread(), products=(_AW16, _STRIX, _BLADE))
    p2 = build_prompt(thread=_basic_thread(), products=(_BLADE, _AW16, _STRIX))
    assert p1 == p2


def test_build_prompt_differs_per_thread_content() -> None:
    p1 = build_prompt(thread=_basic_thread(), products=_UNIVERSE)
    other = DeliberationThread(
        thread_id="t_other",
        op_post_text="Different post body entirely.",
    )
    p2 = build_prompt(thread=other, products=_UNIVERSE)
    assert p1 != p2


# ---------------------------------------------------------------------------
# parse_response
# ---------------------------------------------------------------------------


def test_parse_response_happy_path_resolved() -> None:
    payload = {
        "is_deliberation": True,
        "is_resolved": True,
        "products_discussed": ["aw16", "strix_g16"],
        "chosen_product_id": "aw16",
        "confidence": 0.85,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred == DeliberationPrediction(
        is_deliberation=True,
        is_resolved=True,
        products_discussed=("aw16", "strix_g16"),
        chosen_product_id="aw16",
        confidence=0.85,
    )


def test_parse_response_happy_path_unresolved() -> None:
    payload = {
        "is_deliberation": True,
        "is_resolved": False,
        "products_discussed": ["aw16", "strix_g16"],
        "chosen_product_id": None,
        "confidence": 0.7,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.is_deliberation is True
    assert pred.is_resolved is False
    assert pred.products_discussed == ("aw16", "strix_g16")
    assert pred.chosen_product_id is None


def test_parse_response_happy_path_non_deliberation() -> None:
    payload = {
        "is_deliberation": False,
        "is_resolved": False,
        "products_discussed": [],
        "chosen_product_id": None,
        "confidence": 0.9,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.is_deliberation is False
    assert pred.is_resolved is False
    assert pred.products_discussed == ()
    assert pred.chosen_product_id is None
    assert pred.confidence == 0.9


def test_parse_response_drops_unknown_product_id() -> None:
    payload = {
        "is_deliberation": True,
        "is_resolved": False,
        "products_discussed": ["aw16", "msi_titan_18"],  # msi_titan_18 not in universe
        "chosen_product_id": None,
        "confidence": 0.6,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.products_discussed == ("aw16",)


def test_parse_response_demotes_chosen_not_in_discussed() -> None:
    payload = {
        "is_deliberation": True,
        "is_resolved": True,
        "products_discussed": ["aw16"],
        "chosen_product_id": "strix_g16",  # not in discussed list
        "confidence": 0.8,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.chosen_product_id is None
    assert pred.is_resolved is False


def test_parse_response_demotes_chosen_not_in_universe() -> None:
    payload = {
        "is_deliberation": True,
        "is_resolved": True,
        "products_discussed": ["aw16"],
        "chosen_product_id": "msi_titan_18",  # absent from universe → also absent from discussed
        "confidence": 0.5,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.chosen_product_id is None
    assert pred.is_resolved is False


def test_parse_response_demotes_resolved_with_null_chosen() -> None:
    payload = {
        "is_deliberation": True,
        "is_resolved": True,
        "products_discussed": ["aw16", "strix_g16"],
        "chosen_product_id": None,
        "confidence": 0.5,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.is_resolved is False


# ---------------------------------------------------------------------------
# parse_response — chosen_external_name (v2)
# ---------------------------------------------------------------------------


def test_parse_response_happy_path_external_winner() -> None:
    """OP picks an untracked product → chosen_external_name set, is_resolved true."""
    payload = {
        "is_deliberation": True,
        "is_resolved": True,
        "products_discussed": ["aw16", "strix_g16"],
        "chosen_product_id": None,
        "chosen_external_name": "Razer Blade 16",
        "confidence": 0.85,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.is_resolved is True
    assert pred.chosen_product_id is None
    assert pred.chosen_external_name == "Razer Blade 16"
    assert pred.products_discussed == ("aw16", "strix_g16")


def test_parse_response_external_name_absent_defaults_to_none() -> None:
    """v1-shaped payload (no chosen_external_name) parses cleanly."""
    payload = {
        "is_deliberation": True,
        "is_resolved": True,
        "products_discussed": ["aw16"],
        "chosen_product_id": "aw16",
        "confidence": 0.9,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.chosen_external_name is None
    assert pred.chosen_product_id == "aw16"


def test_parse_response_mutex_prefers_tracked_when_both_set() -> None:
    """Both winner channels set → tracked wins, external dropped."""
    payload = {
        "is_deliberation": True,
        "is_resolved": True,
        "products_discussed": ["aw16"],
        "chosen_product_id": "aw16",
        "chosen_external_name": "Razer Blade 16",
        "confidence": 0.7,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.chosen_product_id == "aw16"
    assert pred.chosen_external_name is None
    assert pred.is_resolved is True


def test_parse_response_demotes_resolved_when_no_winner() -> None:
    """is_resolved=true but both winner channels null → demote."""
    payload = {
        "is_deliberation": True,
        "is_resolved": True,
        "products_discussed": ["aw16", "strix_g16"],
        "chosen_product_id": None,
        "chosen_external_name": None,
        "confidence": 0.4,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.is_resolved is False


def test_parse_response_external_name_strips_whitespace() -> None:
    payload = {
        "is_deliberation": True,
        "is_resolved": True,
        "products_discussed": ["aw16"],
        "chosen_product_id": None,
        "chosen_external_name": "  Razer Blade 16  ",
        "confidence": 0.8,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.chosen_external_name == "Razer Blade 16"


def test_parse_response_external_name_empty_string_becomes_none() -> None:
    payload = {
        "is_deliberation": True,
        "is_resolved": False,
        "products_discussed": ["aw16"],
        "chosen_product_id": None,
        "chosen_external_name": "   ",
        "confidence": 0.5,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.chosen_external_name is None


def test_parse_response_external_name_non_string_becomes_none() -> None:
    payload = {
        "is_deliberation": True,
        "is_resolved": False,
        "products_discussed": ["aw16"],
        "chosen_product_id": None,
        "chosen_external_name": 42,
        "confidence": 0.5,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.chosen_external_name is None


def test_parse_response_non_deliberation_clears_external_name() -> None:
    payload = {
        "is_deliberation": False,
        "is_resolved": True,
        "products_discussed": [],
        "chosen_product_id": None,
        "chosen_external_name": "Razer Blade 16",
        "confidence": 0.3,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.chosen_external_name is None
    assert pred.is_resolved is False


def test_prediction_dataclass_external_name_defaults_to_none() -> None:
    """v1-shape construction still works (backward-compat for tests/fixtures)."""
    pred = DeliberationPrediction(
        is_deliberation=True,
        is_resolved=False,
        products_discussed=("aw16",),
        chosen_product_id=None,
        confidence=0.5,
    )
    assert pred.chosen_external_name is None


def test_parse_response_forces_empty_state_when_not_deliberation() -> None:
    # Model emits inconsistent state — is_deliberation=false but downstream fields
    # are populated. Defensive coercion forces them to safe defaults.
    payload = {
        "is_deliberation": False,
        "is_resolved": True,
        "products_discussed": ["aw16", "strix_g16"],
        "chosen_product_id": "aw16",
        "confidence": 0.3,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.is_deliberation is False
    assert pred.is_resolved is False
    assert pred.products_discussed == ()
    assert pred.chosen_product_id is None


def test_parse_response_dedupes_repeated_product_ids() -> None:
    payload = {
        "is_deliberation": True,
        "is_resolved": False,
        "products_discussed": ["aw16", "aw16", "strix_g16"],
        "chosen_product_id": None,
        "confidence": 0.7,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.products_discussed == ("aw16", "strix_g16")


def test_parse_response_raises_on_non_dict() -> None:
    with pytest.raises(LlmParseError):
        parse_response([], products=_UNIVERSE)


def test_parse_response_raises_on_missing_is_deliberation() -> None:
    with pytest.raises(LlmParseError):
        parse_response(
            {"is_resolved": False, "products_discussed": [], "chosen_product_id": None},
            products=_UNIVERSE,
        )


def test_parse_response_missing_is_resolved_defaults_false() -> None:
    payload = {
        "is_deliberation": True,
        "products_discussed": ["aw16", "strix_g16"],
        "chosen_product_id": None,
        "confidence": 0.6,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.is_resolved is False


def test_parse_response_confidence_out_of_range_becomes_none() -> None:
    payload = {
        "is_deliberation": True,
        "is_resolved": False,
        "products_discussed": [],
        "chosen_product_id": None,
        "confidence": 1.5,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.confidence is None


def test_parse_response_confidence_bool_rejected() -> None:
    payload = {
        "is_deliberation": True,
        "is_resolved": False,
        "products_discussed": [],
        "chosen_product_id": None,
        "confidence": True,
    }
    pred = parse_response(payload, products=_UNIVERSE)
    assert pred.confidence is None


# ---------------------------------------------------------------------------
# DeliberationClassifier — cache integration
# ---------------------------------------------------------------------------


def test_classify_cache_miss_calls_ollama_and_stores_row(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=_canned(
                {
                    "is_deliberation": True,
                    "is_resolved": True,
                    "products_discussed": ["aw16", "strix_g16"],
                    "chosen_product_id": "aw16",
                    "confidence": 0.8,
                }
            ),
        )

    classifier = DeliberationClassifier(_ollama_with(handler))
    pred = classifier.classify(session, thread=_resolved_thread(), products=_UNIVERSE)
    session.commit()

    assert pred.is_deliberation is True
    assert pred.is_resolved is True
    assert pred.chosen_product_id == "aw16"
    assert pred.products_discussed == ("aw16", "strix_g16")
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
        return httpx.Response(
            200,
            json=_canned(
                {
                    "is_deliberation": False,
                    "is_resolved": False,
                    "products_discussed": [],
                    "chosen_product_id": None,
                    "confidence": 0.5,
                }
            ),
        )

    classifier = DeliberationClassifier(_ollama_with(handler))
    classifier.classify(session, thread=_basic_thread(), products=_UNIVERSE)
    session.commit()
    classifier.classify(session, thread=_basic_thread(), products=_UNIVERSE)

    assert len(calls) == 1


def test_classify_cache_scoped_per_thread_text(session: Session) -> None:
    """Different op_post_text → two cache rows, two Ollama calls."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=_canned(
                {
                    "is_deliberation": False,
                    "is_resolved": False,
                    "products_discussed": [],
                    "chosen_product_id": None,
                    "confidence": 0.5,
                }
            ),
        )

    classifier = DeliberationClassifier(_ollama_with(handler))
    t1 = DeliberationThread(thread_id="t1", op_post_text="aw16 or strix")
    t2 = DeliberationThread(thread_id="t2", op_post_text="blade or strix")
    classifier.classify(session, thread=t1, products=_UNIVERSE)
    classifier.classify(session, thread=t2, products=_UNIVERSE)
    session.commit()

    assert len(calls) == 2
    assert session.query(LlmCache).count() == 2


def test_classify_cache_scoped_per_product_universe(session: Session) -> None:
    """Same thread, different product set → two cache rows."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=_canned(
                {
                    "is_deliberation": False,
                    "is_resolved": False,
                    "products_discussed": [],
                    "chosen_product_id": None,
                    "confidence": 0.5,
                }
            ),
        )

    classifier = DeliberationClassifier(_ollama_with(handler))
    classifier.classify(session, thread=_basic_thread(), products=(_AW16, _STRIX))
    classifier.classify(session, thread=_basic_thread(), products=(_AW16, _STRIX, _BLADE))
    session.commit()

    assert len(calls) == 2
    assert session.query(LlmCache).count() == 2


def test_classify_cache_ignores_thread_id(session: Session) -> None:
    """Same content + same universe but different thread_id → cache hit."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=_canned(
                {
                    "is_deliberation": False,
                    "is_resolved": False,
                    "products_discussed": [],
                    "chosen_product_id": None,
                    "confidence": 0.5,
                }
            ),
        )

    classifier = DeliberationClassifier(_ollama_with(handler))
    t1 = DeliberationThread(thread_id="alpha", op_post_text="same body")
    t2 = DeliberationThread(thread_id="beta", op_post_text="same body")
    classifier.classify(session, thread=t1, products=_UNIVERSE)
    session.commit()
    classifier.classify(session, thread=t2, products=_UNIVERSE)

    assert len(calls) == 1
    assert session.query(LlmCache).count() == 1


def test_classify_cache_ignores_display_name(session: Session) -> None:
    """Same product_ids but renamed display_name → cache hit."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=_canned(
                {
                    "is_deliberation": False,
                    "is_resolved": False,
                    "products_discussed": [],
                    "chosen_product_id": None,
                    "confidence": 0.5,
                }
            ),
        )

    classifier = DeliberationClassifier(_ollama_with(handler))
    renamed = ProductContext(product_id="aw16", display_name="Alienware 16 (Late 2025)")
    classifier.classify(session, thread=_basic_thread(), products=(renamed, _STRIX, _BLADE))
    session.commit()
    classifier.classify(session, thread=_basic_thread(), products=_UNIVERSE)

    assert len(calls) == 1
    assert session.query(LlmCache).count() == 1


def test_classify_cache_is_order_independent_in_products(session: Session) -> None:
    """Same product set in two different orders → cache hit."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=_canned(
                {
                    "is_deliberation": False,
                    "is_resolved": False,
                    "products_discussed": [],
                    "chosen_product_id": None,
                    "confidence": 0.5,
                }
            ),
        )

    classifier = DeliberationClassifier(_ollama_with(handler))
    classifier.classify(session, thread=_basic_thread(), products=(_AW16, _STRIX, _BLADE))
    session.commit()
    classifier.classify(session, thread=_basic_thread(), products=(_BLADE, _AW16, _STRIX))

    assert len(calls) == 1
    assert session.query(LlmCache).count() == 1


def test_classify_sends_temperature_zero_in_request_body(session: Session) -> None:
    bodies: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content.decode())
        return httpx.Response(
            200,
            json=_canned(
                {
                    "is_deliberation": False,
                    "is_resolved": False,
                    "products_discussed": [],
                    "chosen_product_id": None,
                    "confidence": 0.5,
                }
            ),
        )

    classifier = DeliberationClassifier(_ollama_with(handler))
    classifier.classify(session, thread=_basic_thread(), products=_UNIVERSE)

    assert len(bodies) == 1
    assert '"temperature":0.0' in bodies[0]
    assert '"format":"json"' in bodies[0]


def test_prompt_version_bump_invalidates_cache(session: Session) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            200,
            json=_canned(
                {
                    "is_deliberation": False,
                    "is_resolved": False,
                    "products_discussed": [],
                    "chosen_product_id": None,
                    "confidence": 0.5,
                }
            ),
        )

    client = _ollama_with(handler)
    v1 = DeliberationClassifier(client, prompt_version="deliberation_classifier_v1")
    v2 = DeliberationClassifier(client, prompt_version="deliberation_classifier_v2")

    v1.classify(session, thread=_basic_thread(), products=_UNIVERSE)
    session.commit()
    v2.classify(session, thread=_basic_thread(), products=_UNIVERSE)
    session.commit()

    assert len(calls) == 2
    rows = session.query(LlmCache).order_by(LlmCache.prompt_version).all()
    assert [r.prompt_version for r in rows] == [
        "deliberation_classifier_v1",
        "deliberation_classifier_v2",
    ]
