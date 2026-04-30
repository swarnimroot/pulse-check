"""Ollama client tests using httpx.MockTransport for full request/response control."""

from __future__ import annotations

import httpx
import pytest

from pulse_check.llm_cache import (
    LlmConnectionError,
    LlmParseError,
    LlmResponseError,
)
from pulse_check.tagging.ollama import OllamaClient

_MODEL = "qwen2.5:7b-q4_K_M"


def _make_client(handler: httpx.MockTransport) -> OllamaClient:
    mock = httpx.Client(transport=handler, base_url="http://mock")
    return OllamaClient(client=mock)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_generate_json_happy_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/generate"
        body = request.content.decode()
        assert '"format":"json"' in body
        assert '"temperature":0.0' in body
        return httpx.Response(
            200,
            json={
                "model": _MODEL,
                "response": '{"aspects": ["thermals"]}',
                "done": True,
            },
        )

    client = _make_client(httpx.MockTransport(handler))
    result = client.generate_json(model=_MODEL, prompt="classify this")
    assert result.parsed_output == {"aspects": ["thermals"]}
    assert result.raw_output == '{"aspects": ["thermals"]}'


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_connection_error_raises_llm_connection_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(LlmConnectionError) as err:
        client.generate_json(model=_MODEL, prompt="x")
    assert "could not reach Ollama" in str(err.value)


def test_non_2xx_raises_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal server error")

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(LlmResponseError) as err:
        client.generate_json(model=_MODEL, prompt="x")
    assert "500" in str(err.value)


def test_envelope_not_json_raises_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json envelope")

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(LlmResponseError):
        client.generate_json(model=_MODEL, prompt="x")


def test_missing_response_field_raises_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"done": True})  # no 'response' field

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(LlmResponseError) as err:
        client.generate_json(model=_MODEL, prompt="x")
    assert "missing 'response'" in str(err.value)


# ---------------------------------------------------------------------------
# Parse retry loop
# ---------------------------------------------------------------------------


def test_parse_retry_recovers_on_second_attempt() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        calls.append(body)
        if len(calls) == 1:
            return httpx.Response(200, json={"response": "not valid json"})
        return httpx.Response(200, json={"response": '{"ok": true}'})

    client = _make_client(httpx.MockTransport(handler))
    result = client.generate_json(model=_MODEL, prompt="classify", max_retries=2)
    assert result.parsed_output == {"ok": True}
    # First call: plain prompt; second: prompt + strictening suffix
    assert len(calls) == 2
    assert "Return ONLY valid JSON" in calls[1]


def test_parse_retry_exhaustion_raises_parse_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "still not json"})

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(LlmParseError) as err:
        client.generate_json(model=_MODEL, prompt="x", max_retries=2)
    assert "after 2 retries" in str(err.value)


def test_zero_retries_raises_immediately_on_parse_failure() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"response": "nope"})

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(LlmParseError):
        client.generate_json(model=_MODEL, prompt="x", max_retries=0)
    assert len(calls) == 1
