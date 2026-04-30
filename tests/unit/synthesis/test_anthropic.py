"""Anthropic client tests with a mocked SDK."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import anthropic
import httpx
import pytest

from pulse_check.llm_cache import (
    LlmConnectionError,
    LlmParseError,
    LlmResponseError,
)
from pulse_check.synthesis.anthropic_client import AnthropicClient

_SONNET = "claude-sonnet-4-6"
_HAIKU = "claude-haiku-4-5-20251001"


class _FakeBlock:
    """Mimics an Anthropic TextBlock with a `.text` attribute."""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeBlock(text)]


def _make_client(sdk: Any) -> AnthropicClient:
    return AnthropicClient(sdk=sdk)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_generate_json_happy_path() -> None:
    sdk = MagicMock()
    sdk.messages.create.return_value = _FakeResponse('{"brief": "ok"}')

    client = _make_client(sdk)
    result = client.generate_json(model=_SONNET, prompt="write a brief")

    assert result.parsed_output == {"brief": "ok"}
    sdk.messages.create.assert_called_once()
    kwargs = sdk.messages.create.call_args.kwargs
    assert kwargs["model"] == _SONNET
    assert kwargs["temperature"] == 0.0
    assert kwargs["messages"] == [{"role": "user", "content": "write a brief"}]
    assert "system" not in kwargs  # system defaults to None → not passed


def test_system_prompt_is_forwarded_when_provided() -> None:
    sdk = MagicMock()
    sdk.messages.create.return_value = _FakeResponse("{}")

    client = _make_client(sdk)
    client.generate_json(model=_SONNET, prompt="p", system="you are strict")

    kwargs = sdk.messages.create.call_args.kwargs
    assert kwargs["system"] == "you are strict"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_connection_error_wrapped() -> None:
    sdk = MagicMock()
    sdk.messages.create.side_effect = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com")
    )

    client = _make_client(sdk)
    with pytest.raises(LlmConnectionError) as err:
        client.generate_json(model=_SONNET, prompt="x")
    assert "could not reach Anthropic" in str(err.value)


def test_api_status_error_wrapped() -> None:
    sdk = MagicMock()
    response = httpx.Response(
        500, text="boom", request=httpx.Request("POST", "https://api.anthropic.com")
    )
    sdk.messages.create.side_effect = anthropic.APIStatusError("boom", response=response, body=None)

    client = _make_client(sdk)
    with pytest.raises(LlmResponseError) as err:
        client.generate_json(model=_SONNET, prompt="x")
    assert "500" in str(err.value)


def test_empty_content_raises_response_error() -> None:
    sdk = MagicMock()
    fake = MagicMock()
    fake.content = []
    sdk.messages.create.return_value = fake

    client = _make_client(sdk)
    with pytest.raises(LlmResponseError) as err:
        client.generate_json(model=_SONNET, prompt="x")
    assert "empty content" in str(err.value)


def test_non_text_block_raises_response_error() -> None:
    sdk = MagicMock()
    fake = MagicMock()
    fake.content = [object()]  # has no .text attr
    sdk.messages.create.return_value = fake

    client = _make_client(sdk)
    with pytest.raises(LlmResponseError) as err:
        client.generate_json(model=_SONNET, prompt="x")
    assert "not text" in str(err.value)


# ---------------------------------------------------------------------------
# Parse retry loop
# ---------------------------------------------------------------------------


def test_parse_retry_recovers_on_second_attempt() -> None:
    sdk = MagicMock()
    sdk.messages.create.side_effect = [
        _FakeResponse("not json"),
        _FakeResponse('{"ok": true}'),
    ]

    client = _make_client(sdk)
    result = client.generate_json(model=_HAIKU, prompt="cluster", max_retries=2)

    assert result.parsed_output == {"ok": True}
    assert sdk.messages.create.call_count == 2
    second_call = sdk.messages.create.call_args_list[1].kwargs
    assert "Return ONLY valid JSON" in second_call["messages"][0]["content"]


def test_parse_retry_exhaustion_raises_parse_error() -> None:
    sdk = MagicMock()
    sdk.messages.create.return_value = _FakeResponse("still not json")

    client = _make_client(sdk)
    with pytest.raises(LlmParseError) as err:
        client.generate_json(model=_HAIKU, prompt="x", max_retries=2)
    assert "after 2 retries" in str(err.value)
