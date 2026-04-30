"""Cache-aware LLM call wrapper and shared protocol types.

Every LLM call in pulse-check (Qwen local, Sonnet, Haiku) goes through
`call_with_cache`. On a cache hit, the wrapper returns the stored output
without invoking the model. On a miss, it calls the caller-supplied
`compute` callable (which handles the real API call), stores the result
keyed on a deterministic hash of the inputs, and returns it.

The `compute` inversion-of-control means this module stays LLM-agnostic and
unit-testable. Tagging and synthesis own their clients + prompt strings.

Cache key (ARCHITECTURE §3.4):
    sha256(
        sha256(json.dumps(input_payload, sort_keys=True))   # input_hash
        + "|" + prompt_version
        + "|" + model
        + "|" + f"{temperature:.10f}"
    )

Temperature is normalized to 10 decimal places so `0.0`, `0`, and `0.00`
produce the same key. Any change to `prompt_version`, `model`, or the
input payload produces a new key — no eviction; old rows remain for audit.

Concurrency caveat (v1): two concurrent callers computing the same key
will race on INSERT. Single-operator batch workload, so not handled.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from pulse_check.storage.models import LlmCache

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LlmResponse:
    """Uniform return type for both cache hits and fresh LLM calls.

    `raw_output` is the model's verbatim text reply. `parsed_output` is the
    JSON-decoded form when the caller requested JSON output; `None` otherwise
    or on parse failure (in which case the caller should have already raised).
    """

    raw_output: str
    parsed_output: Any = None


class LlmError(Exception):
    """Base for all LLM-client errors."""


class LlmConnectionError(LlmError):
    """Could not reach the LLM provider (DNS / TCP / timeout)."""


class LlmResponseError(LlmError):
    """Provider returned a non-2xx response."""


class LlmParseError(LlmError):
    """Provider returned text that isn't valid JSON, after retries."""


# ---------------------------------------------------------------------------
# Cache key derivation
# ---------------------------------------------------------------------------


def hash_input(payload: Any) -> str:
    """Deterministic sha256 of a JSON-serializable payload."""
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def cache_key(*, input_hash: str, prompt_version: str, model: str, temperature: float) -> str:
    """Derive the cache_key PK from input hash + call metadata."""
    combined = f"{input_hash}|{prompt_version}|{model}|{temperature:.10f}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Cache-aware call
# ---------------------------------------------------------------------------


def call_with_cache(
    session: Session,
    *,
    task: str,
    input_payload: Any,
    prompt_version: str,
    model: str,
    temperature: float,
    compute: Callable[[], LlmResponse],
) -> LlmResponse:
    """Return a cached LlmResponse for these inputs, or compute and store one.

    `task` is a free-form label for logging only — it is not in the cache key.
    `input_payload` is the business-level input (e.g., `{"mention_text": ...,
    "product_context": ...}`). It must be JSON-serializable so the hash is
    stable across runs.
    """
    ih = hash_input(input_payload)
    key = cache_key(
        input_hash=ih,
        prompt_version=prompt_version,
        model=model,
        temperature=temperature,
    )

    existing = session.get(LlmCache, key)
    if existing is not None:
        log.debug("llm cache hit: task=%s model=%s key=%s", task, model, key[:12])
        return LlmResponse(
            raw_output=existing.raw_output,
            parsed_output=existing.parsed_output,
        )

    log.debug("llm cache miss: task=%s model=%s key=%s", task, model, key[:12])
    response = compute()

    session.add(
        LlmCache(
            cache_key=key,
            input_hash=ih,
            prompt_version=prompt_version,
            model=model,
            temperature=temperature,
            raw_output=response.raw_output,
            parsed_output=response.parsed_output,
        )
    )
    session.flush()

    return response
