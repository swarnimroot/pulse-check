"""Ollama HTTP client wrapper.

Thin layer over Ollama's `/api/generate` endpoint with `format=json` to force
structured JSON output. Designed so taggers (aspect, deliberation, reason)
call `generate_json(...)` and get a parsed dict back, with uniform error
handling and a parse-retry loop.

Dependency injection: pass an `httpx.Client` to the constructor for tests
(wire up `httpx.MockTransport`); production callers use the default client
built from the host URL.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from pulse_check.llm_cache import (
    LlmConnectionError,
    LlmParseError,
    LlmResponse,
    LlmResponseError,
)

log = logging.getLogger(__name__)

_JSON_STRICT_SUFFIX = "\n\nReturn ONLY valid JSON, no prose, no markdown fences."


class OllamaClient:
    """Minimal Ollama client producing JSON-only responses."""

    def __init__(
        self,
        host: str = "http://localhost:11434",
        *,
        timeout: float = 120.0,
        client: httpx.Client | None = None,
    ) -> None:
        if client is None:
            client = httpx.Client(base_url=host, timeout=timeout)
        self._client = client

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OllamaClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float = 0.0,
        max_retries: int = 2,
    ) -> LlmResponse:
        """Call Ollama's `/api/generate` and parse the reply as JSON.

        Retries up to `max_retries` times on parse failure, each time appending
        a stricter JSON-only instruction to the prompt. Connection and HTTP
        errors are not retried — the operator should diagnose them.
        """
        attempt = 0
        effective_prompt = prompt
        last_raw = ""
        while True:
            raw = self._call(model=model, prompt=effective_prompt, temperature=temperature)
            last_raw = raw
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                if attempt >= max_retries:
                    log.warning(
                        "ollama parse failure after %d retries (model=%s)",
                        attempt,
                        model,
                    )
                    msg = f"Ollama returned non-JSON after {attempt} retries: {exc}"
                    raise LlmParseError(msg) from exc
                attempt += 1
                effective_prompt = prompt + _JSON_STRICT_SUFFIX
                log.debug("ollama parse retry %d (model=%s)", attempt, model)
                continue
            return LlmResponse(raw_output=last_raw, parsed_output=parsed)

    def _call(self, *, model: str, prompt: str, temperature: float) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": temperature},
        }
        try:
            resp = self._client.post("/api/generate", json=payload)
        except httpx.RequestError as exc:
            msg = f"could not reach Ollama at {self._client.base_url}: {exc}"
            raise LlmConnectionError(msg) from exc

        if resp.status_code >= 400:
            msg = f"Ollama returned HTTP {resp.status_code} for model={model}: {resp.text[:300]}"
            raise LlmResponseError(msg)

        try:
            body = resp.json()
        except json.JSONDecodeError as exc:
            msg = f"Ollama response envelope was not JSON: {exc}"
            raise LlmResponseError(msg) from exc

        response_text = body.get("response")
        if not isinstance(response_text, str):
            msg = f"Ollama response missing 'response' text field: {body}"
            raise LlmResponseError(msg)
        return response_text
