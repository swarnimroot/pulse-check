"""Anthropic client wrapper (Sonnet + Haiku).

Thin layer over the Anthropic Python SDK. Uses plain prompt-for-JSON (no tool
use) with a parse-retry loop matching the Ollama wrapper. Same error
hierarchy so tagging and synthesis can swap models with identical exception
handling.
"""

from __future__ import annotations

import json
import logging

import anthropic

from pulse_check.llm_cache import (
    LlmConnectionError,
    LlmParseError,
    LlmResponse,
    LlmResponseError,
)

log = logging.getLogger(__name__)

_JSON_STRICT_SUFFIX = "\n\nReturn ONLY valid JSON, no prose, no markdown fences."

# Per-million-token pricing for models we route to. Used only for log-line
# cost estimates so an operator watching a batch run can see spend accumulate
# in-flight (session-43 lesson — a 200-pair batch silently burned $54 because
# nobody could see per-call cost). Numbers stale-tolerant: a rate revision
# affects the log line, not behavior. Cache write/read tokens are not tracked
# here because the project does not currently use Anthropic prompt caching.
_PRICING_PER_MTOKEN: dict[str, tuple[float, float]] = {
    # model_id : (input $/Mtok, output $/Mtok)
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-opus-4-7": (15.0, 75.0),
}


def _estimate_cost_usd(model: str, in_tokens: int, out_tokens: int) -> float | None:
    """Return USD cost estimate or None when the model is not in the pricing
    table. Caller logs unknown-model calls without a cost number rather than
    guessing — better silent than misleading."""
    rates = _PRICING_PER_MTOKEN.get(model)
    if rates is None:
        return None
    in_rate, out_rate = rates
    return (in_tokens / 1_000_000) * in_rate + (out_tokens / 1_000_000) * out_rate


def _strip_markdown_fences(raw: str) -> str:
    """Defensively strip ```json...``` or ```...``` fences.

    Anthropic models often wrap JSON output in markdown fences even when
    explicitly instructed otherwise. Anthropic has no equivalent of
    Ollama's ``format=json`` hard-mode, so we strip post-hoc.
    """
    s = raw.strip()
    if not s.startswith("```"):
        return s
    # Drop the opening fence (``` or ```json or ```JSON, possibly with newline).
    after_open = s[3:]
    # If the first line is a language tag (e.g. "json"), drop it.
    newline_idx = after_open.find("\n")
    if newline_idx != -1:
        first_line = after_open[:newline_idx].strip()
        if first_line == "" or first_line.lower() == "json":
            after_open = after_open[newline_idx + 1 :]
    # Drop the trailing fence if present.
    if after_open.rstrip().endswith("```"):
        after_open = after_open.rstrip()[:-3]
    return after_open.strip()


class AnthropicClient:
    """Minimal Anthropic client producing JSON-only responses."""

    def __init__(
        self,
        api_key: str = "",
        *,
        timeout: float = 120.0,
        sdk: anthropic.Anthropic | None = None,
    ) -> None:
        if sdk is None:
            sdk = anthropic.Anthropic(api_key=api_key, timeout=timeout)
        self._sdk = sdk

    def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        max_retries: int = 2,
    ) -> LlmResponse:
        """Call Anthropic messages.create and parse the first text block as JSON.

        Retries up to `max_retries` times on parse failure, each time appending
        a stricter JSON-only instruction to the prompt.
        """
        attempt = 0
        effective_prompt = prompt
        last_raw = ""
        while True:
            raw = self._call(
                model=model,
                prompt=effective_prompt,
                system=system,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            last_raw = raw
            cleaned = _strip_markdown_fences(raw)
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError as exc:
                if attempt >= max_retries:
                    log.warning(
                        "anthropic parse failure after %d retries (model=%s)",
                        attempt,
                        model,
                    )
                    msg = f"Anthropic returned non-JSON after {attempt} retries: {exc}"
                    raise LlmParseError(msg) from exc
                attempt += 1
                effective_prompt = prompt + _JSON_STRICT_SUFFIX
                log.debug("anthropic parse retry %d (model=%s)", attempt, model)
                continue
            return LlmResponse(raw_output=last_raw, parsed_output=parsed)

    def _call(
        self,
        *,
        model: str,
        prompt: str,
        system: str | None,
        temperature: float,
        max_tokens: int,
    ) -> str:
        messages: list[anthropic.types.MessageParam] = [{"role": "user", "content": prompt}]
        # Opus 4.7 returns HTTP 400 if `temperature` is passed (deprecated for this model).
        # Cache keys still use the caller's requested temperature so the recorded
        # deterministic intent stays consistent with the rest of the project.
        omit_temperature = model.startswith("claude-opus-4-7")
        try:
            if system is None:
                if omit_temperature:
                    response = self._sdk.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        messages=messages,
                    )
                else:
                    response = self._sdk.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        messages=messages,
                    )
            else:
                if omit_temperature:
                    response = self._sdk.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        system=system,
                        messages=messages,
                    )
                else:
                    response = self._sdk.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        system=system,
                        messages=messages,
                    )
        except anthropic.APIConnectionError as exc:
            msg = f"could not reach Anthropic API: {exc}"
            raise LlmConnectionError(msg) from exc
        except anthropic.APIStatusError as exc:
            msg = f"Anthropic returned HTTP {exc.status_code}: {exc.message}"
            raise LlmResponseError(msg) from exc
        except anthropic.APIError as exc:
            msg = f"Anthropic SDK error: {exc}"
            raise LlmResponseError(msg) from exc

        if not response.content:
            msg = "Anthropic response had empty content array"
            raise LlmResponseError(msg)

        # Log token usage + estimated cost at INFO so batch operators see
        # per-call spend accumulating without needing the billing dashboard.
        # `response.usage` is provided by the SDK; defensive getattr so a
        # future SDK shape change degrades to a silent skip rather than a crash.
        usage = getattr(response, "usage", None)
        if usage is not None:
            in_tok = int(getattr(usage, "input_tokens", 0) or 0)
            out_tok = int(getattr(usage, "output_tokens", 0) or 0)
            est = _estimate_cost_usd(model, in_tok, out_tok)
            if est is not None:
                log.info(
                    "anthropic call model=%s in_tokens=%d out_tokens=%d est_cost=$%.4f",
                    model,
                    in_tok,
                    out_tok,
                    est,
                )
            else:
                log.info(
                    "anthropic call model=%s in_tokens=%d out_tokens=%d est_cost=unknown",
                    model,
                    in_tok,
                    out_tok,
                )

        first_block = response.content[0]
        text = getattr(first_block, "text", None)
        if not isinstance(text, str):
            msg = f"Anthropic first content block was not text (type={type(first_block).__name__})"
            raise LlmResponseError(msg)
        return text
