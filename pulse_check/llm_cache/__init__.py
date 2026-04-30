"""LLM cache helpers: keyed by (content hash, prompt version, model, temperature).

The cache is the single source of reproducibility for every LLM call in
pulse-check. See `cache.py` for the contract.
"""

from pulse_check.llm_cache.cache import (
    LlmConnectionError,
    LlmError,
    LlmParseError,
    LlmResponse,
    LlmResponseError,
    cache_key,
    call_with_cache,
    hash_input,
)

__all__ = [
    "LlmConnectionError",
    "LlmError",
    "LlmParseError",
    "LlmResponse",
    "LlmResponseError",
    "cache_key",
    "call_with_cache",
    "hash_input",
]
