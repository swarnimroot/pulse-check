"""Cache-aware LLM call wrapper tests.

Covers key determinism + bump behavior, hit-does-not-call-compute, miss-
stores-row, and raw+parsed output fidelity.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from pulse_check.llm_cache import (
    LlmResponse,
    cache_key,
    call_with_cache,
    hash_input,
)
from pulse_check.storage.models import LlmCache

# ---------------------------------------------------------------------------
# Key determinism
# ---------------------------------------------------------------------------


def test_hash_input_stable_for_same_payload() -> None:
    payload = {"mention_text": "laptop runs hot", "product": "aw16"}
    assert hash_input(payload) == hash_input(dict(payload))


def test_hash_input_ignores_key_order() -> None:
    a = hash_input({"x": 1, "y": 2})
    b = hash_input({"y": 2, "x": 1})
    assert a == b


def test_hash_input_differs_on_content_change() -> None:
    assert hash_input({"x": 1}) != hash_input({"x": 2})


def test_cache_key_deterministic() -> None:
    ih = hash_input({"x": 1})
    k1 = cache_key(
        input_hash=ih,
        prompt_version="v1",
        model="qwen2.5:7b-q4_K_M",
        temperature=0.0,
    )
    k2 = cache_key(
        input_hash=ih,
        prompt_version="v1",
        model="qwen2.5:7b-q4_K_M",
        temperature=0.0,
    )
    assert k1 == k2


def test_cache_key_differs_on_prompt_version_bump() -> None:
    ih = hash_input({"x": 1})
    k1 = cache_key(input_hash=ih, prompt_version="v1", model="m", temperature=0.0)
    k2 = cache_key(input_hash=ih, prompt_version="v2", model="m", temperature=0.0)
    assert k1 != k2


def test_cache_key_differs_on_model_swap() -> None:
    ih = hash_input({"x": 1})
    k1 = cache_key(input_hash=ih, prompt_version="v1", model="qwen2.5:7b-q4_K_M", temperature=0.0)
    k2 = cache_key(
        input_hash=ih,
        prompt_version="v1",
        model="claude-haiku-4-5-20251001",
        temperature=0.0,
    )
    assert k1 != k2


def test_cache_key_differs_on_temperature_change() -> None:
    ih = hash_input({"x": 1})
    k1 = cache_key(input_hash=ih, prompt_version="v1", model="m", temperature=0.0)
    k2 = cache_key(input_hash=ih, prompt_version="v1", model="m", temperature=0.5)
    assert k1 != k2


def test_cache_key_temperature_normalization() -> None:
    """`0.0`, `0`, and `0.00` should all produce the same key."""
    ih = hash_input({"x": 1})
    ks = [
        cache_key(input_hash=ih, prompt_version="v1", model="m", temperature=t)
        for t in (0.0, 0, 0.00)
    ]
    assert ks[0] == ks[1] == ks[2]


# ---------------------------------------------------------------------------
# call_with_cache behavior
# ---------------------------------------------------------------------------


class _Counter:
    def __init__(self, response: LlmResponse) -> None:
        self.calls = 0
        self.response = response

    def __call__(self) -> LlmResponse:
        self.calls += 1
        return self.response


def _call(
    session: Session,
    compute: _Counter,
    *,
    payload: Any = None,
    prompt_version: str = "aspect_v1",
    model: str = "qwen2.5:7b-q4_K_M",
    temperature: float = 0.0,
) -> LlmResponse:
    return call_with_cache(
        session,
        task="aspect_tagging",
        input_payload=payload if payload is not None else {"mention": "x"},
        prompt_version=prompt_version,
        model=model,
        temperature=temperature,
        compute=compute,
    )


def test_miss_invokes_compute_and_stores_row(session: Session) -> None:
    compute = _Counter(LlmResponse(raw_output='{"aspects":[]}', parsed_output={"aspects": []}))
    result = _call(session, compute)
    session.commit()

    assert compute.calls == 1
    assert result.parsed_output == {"aspects": []}

    rows = session.query(LlmCache).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.prompt_version == "aspect_v1"
    assert row.model == "qwen2.5:7b-q4_K_M"
    assert row.temperature == 0.0
    assert row.parsed_output == {"aspects": []}
    assert row.raw_output == '{"aspects":[]}'


def test_hit_does_not_invoke_compute(session: Session) -> None:
    compute1 = _Counter(LlmResponse(raw_output='{"aspects":[]}', parsed_output={"aspects": []}))
    _call(session, compute1)
    session.commit()

    compute2 = _Counter(
        LlmResponse(raw_output="SHOULD_NOT_BE_CALLED", parsed_output={"differ": True})
    )
    result = _call(session, compute2)

    assert compute2.calls == 0
    # Returned data must come from the cache, not compute2.
    assert result.raw_output == '{"aspects":[]}'
    assert result.parsed_output == {"aspects": []}


def test_prompt_version_bump_misses_and_coexists(session: Session) -> None:
    c_v1 = _Counter(LlmResponse(raw_output='{"v":1}', parsed_output={"v": 1}))
    _call(session, c_v1, prompt_version="v1")
    session.commit()

    c_v2 = _Counter(LlmResponse(raw_output='{"v":2}', parsed_output={"v": 2}))
    result = _call(session, c_v2, prompt_version="v2")
    session.commit()

    assert c_v2.calls == 1  # v2 missed
    assert result.parsed_output == {"v": 2}

    rows = session.query(LlmCache).order_by(LlmCache.prompt_version).all()
    assert [r.prompt_version for r in rows] == ["v1", "v2"]


def test_different_payloads_produce_different_keys(session: Session) -> None:
    c1 = _Counter(LlmResponse(raw_output="{}", parsed_output={}))
    _call(session, c1, payload={"mention": "a"})
    session.commit()

    c2 = _Counter(LlmResponse(raw_output="{}", parsed_output={}))
    _call(session, c2, payload={"mention": "b"})
    session.commit()

    assert c2.calls == 1
    assert session.query(LlmCache).count() == 2


def test_hit_within_same_session_flushes_for_reuse(session: Session) -> None:
    """A second call in the same session (before commit) should still hit."""
    compute = _Counter(LlmResponse(raw_output="{}", parsed_output={}))
    _call(session, compute)
    _call(session, compute)  # same key; should hit the flushed row
    assert compute.calls == 1


def test_null_parsed_output_cached(session: Session) -> None:
    compute = _Counter(LlmResponse(raw_output="not-json", parsed_output=None))
    _call(session, compute)
    session.commit()

    row = session.query(LlmCache).one()
    assert row.parsed_output is None
    assert row.raw_output == "not-json"
