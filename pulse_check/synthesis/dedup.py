"""Haiku near-duplicate clustering for verbatim-mention pools.

The selector picks ~3 positive + ~3 negative verbatims per aspect
(ARCHITECTURE §7.1 step 4). Without dedup, near-paraphrase mentions
("fans run loud" vs "the fans are loud") flood the selector and starve
diverse coverage. This module clusters mentions that say the same thing
so the selector picks one representative per cluster.

Routed to Haiku per LLM_ROUTING (ARCHITECTURE §6.1): cheap, fast, and the
"these two say the same thing" judgment doesn't need Sonnet's reasoning.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmResponse, LlmResponseError, call_with_cache
from pulse_check.storage.models import Mention
from pulse_check.synthesis.anthropic_client import AnthropicClient

log = logging.getLogger(__name__)

DEDUP_PROMPT_VERSION = "a1_dedup_v1"
_HAIKU_MODEL = "claude-haiku-4-5-20251001"
_TEMPERATURE = 0.0
_MAX_TOKENS = 4096

_PROMPT_TEMPLATE = """You are an expert at identifying paraphrases. Cluster mentions that \
express the same point (near-duplicates) while keeping distinct points separate.

CRITICAL RULES:
1. Cluster ONLY mentions that say essentially the same thing (paraphrases, rewording, same \
point with different words).
2. NEVER cluster mentions that share a topic but express different points. Examples of \
mentions you must NOT cluster together:
   - "The fans are loud" and "The fans run quiet" (opposite polarity).
   - "Battery lasts 8 hours" and "Battery lasts 4 hours" (different claims).
   - "Good build quality" and "Cheap plastic feel" (different specific points).
3. Each input mention_id must appear in exactly one cluster.
4. Use any opaque cluster labels (e.g. "A", "B", "C", or any strings) — they will be \
remapped downstream.

MENTIONS TO CLUSTER:
{mentions_list}

Return ONLY a valid JSON object with this structure:
{{
  "assignments": [
    {{"mention_id": "<id>", "cluster_id": "<label>"}},
    ...
  ]
}}

Every input mention_id must appear exactly once. No extra mention_ids.
"""


def _build_prompt(mentions: list[Mention]) -> str:
    """Format mentions as `[mention_id] "raw text"` lines, JSON-escaping the text."""
    lines = [f"[{m.mention_id}] {json.dumps(m.raw_text, ensure_ascii=False)}" for m in mentions]
    return _PROMPT_TEMPLATE.format(mentions_list="\n".join(lines))


def _normalize_cluster_ids(assignments: list[dict[str, Any]]) -> dict[str, str]:
    """Remap arbitrary cluster labels to opaque c0, c1, ... in first-seen order.

    Returns `{mention_id: cluster_id}` where cluster_ids are `c0`, `c1`, ...
    """
    result: dict[str, str] = {}
    label_map: dict[str, str] = {}
    next_idx = 0
    for item in assignments:
        mention_id = item.get("mention_id")
        raw_label = item.get("cluster_id")
        if not isinstance(mention_id, str) or not isinstance(raw_label, str):
            continue
        if raw_label not in label_map:
            label_map[raw_label] = f"c{next_idx}"
            next_idx += 1
        result[mention_id] = label_map[raw_label]
    return result


def cluster_near_duplicates(
    session: Session,
    mentions: list[Mention],
    *,
    client: AnthropicClient,
    prompt_version: str = DEDUP_PROMPT_VERSION,
) -> dict[str, str]:
    """Return a `{mention_id: cluster_id}` map.

    Mentions that paraphrase each other share a cluster_id; mentions that
    don't paraphrase any other mention get a unique cluster_id.

    Determinism: identical input mention pool + same prompt_version yields
    identical cluster assignments via the LLM cache layer.
    """
    if not mentions:
        return {}
    if len(mentions) == 1:
        return {mentions[0].mention_id: "c0"}

    input_payload = sorted(
        ({"mention_id": m.mention_id, "text": m.raw_text} for m in mentions),
        key=lambda x: x["mention_id"],
    )

    def _compute() -> LlmResponse:
        return client.generate_json(
            model=_HAIKU_MODEL,
            prompt=_build_prompt(mentions),
            temperature=_TEMPERATURE,
            max_tokens=_MAX_TOKENS,
        )

    response = call_with_cache(
        session,
        task="a1_dedup",
        input_payload=input_payload,
        prompt_version=prompt_version,
        model=_HAIKU_MODEL,
        temperature=_TEMPERATURE,
        compute=_compute,
    )

    parsed = response.parsed_output
    if not isinstance(parsed, dict):
        msg = f"expected JSON object from dedup LLM, got {type(parsed).__name__}"
        raise LlmResponseError(msg)

    assignments_raw = parsed.get("assignments")
    if not isinstance(assignments_raw, list):
        msg = f"expected 'assignments' to be a list, got {type(assignments_raw).__name__}"
        raise LlmResponseError(msg)

    input_ids = {m.mention_id for m in mentions}
    output_ids = {
        item.get("mention_id")
        for item in assignments_raw
        if isinstance(item, dict)
    }
    if output_ids != input_ids:
        missing = input_ids - output_ids
        extra = output_ids - input_ids
        parts: list[str] = []
        if missing:
            parts.append(f"missing mention_ids: {sorted(missing)}")
        if extra:
            parts.append(f"extra mention_ids: {sorted(str(x) for x in extra)}")
        msg = "dedup assignments validation failed: " + "; ".join(parts)
        raise LlmResponseError(msg)

    return _normalize_cluster_ids(assignments_raw)
