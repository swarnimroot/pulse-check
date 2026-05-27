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


# ---------------------------------------------------------------------------
# Token-usage logging (session 43 — cost visibility in-flight)
# ---------------------------------------------------------------------------


def test_estimate_cost_usd_sonnet() -> None:
    from pulse_check.synthesis.anthropic_client import _estimate_cost_usd

    # 100,000 in @ $3/M + 1,000 out @ $15/M = $0.30 + $0.015 = $0.315
    assert _estimate_cost_usd("claude-sonnet-4-6", 100_000, 1_000) == pytest.approx(0.315)


def test_estimate_cost_usd_unknown_model_returns_none() -> None:
    from pulse_check.synthesis.anthropic_client import _estimate_cost_usd

    assert _estimate_cost_usd("some-future-model", 1000, 100) is None


def test_usage_logged_when_response_carries_usage(caplog: pytest.LogCaptureFixture) -> None:
    """A call with a `usage` attr on the response writes a single INFO line
    with in_tokens / out_tokens / est_cost — the lever an operator uses to
    watch spend accumulate in-flight (session-43 cost-blowup remediation)."""
    sdk = MagicMock()

    class _UsageBearingResponse:
        def __init__(self) -> None:
            self.content = [_FakeBlock('{"ok": true}')]
            usage = MagicMock()
            usage.input_tokens = 12_345
            usage.output_tokens = 234
            self.usage = usage

    sdk.messages.create.return_value = _UsageBearingResponse()

    client = _make_client(sdk)
    with caplog.at_level("INFO", logger="pulse_check.synthesis.anthropic_client"):
        client.generate_json(model=_SONNET, prompt="x")

    usage_lines = [
        r for r in caplog.records if "anthropic call model=" in r.getMessage()
    ]
    assert len(usage_lines) == 1
    msg = usage_lines[0].getMessage()
    assert "model=claude-sonnet-4-6" in msg
    assert "in_tokens=12345" in msg
    assert "out_tokens=234" in msg
    assert "est_cost=$" in msg
