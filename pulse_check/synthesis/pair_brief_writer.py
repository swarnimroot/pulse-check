"""Sonnet pair-brief writer — produces a single contrast paragraph for one
product pair (ARCHITECTURE §6.4 — pair brief layout).

Designed session 42. The Pair-page scorecard supplies the per-aspect numerical
detail; this writer supplies the texture in one 50-80 word paragraph framing
where the primary leads, where the comparator leads, and where opinions
converge.

Determinism mirrors `brief_writer.write_a1_brief`: aspect leader/delta are
computed in Python; Sonnet writes only `brief_title` and the contrast text.
Identical payload + prompt_version → cache hit → byte-identical brief.

Cite-pool rule: `cited_mention_ids` MUST be drawn from the union of both
sides' verbatim pools fed into the payload. The citation validator filters
fabricated IDs as a defense-in-depth check.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmResponse, LlmResponseError, call_with_cache
from pulse_check.storage.enums import Aspect, Polarity
from pulse_check.storage.models import AggregateAspectSku, Mention, Product
from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.synthesis.contracts import PairBriefContrast, PairBriefNarrative
from pulse_check.synthesis.selector import AspectSelection, SelectedVerbatim

log = logging.getLogger(__name__)

PAIR_BRIEF_PROMPT_VERSION = "pair_brief_v1"
PAIR_BRIEF_PROMPT_VERSION_STRICT = "pair_brief_v1_strict"
PAIR_BRIEF_MODEL = "claude-sonnet-4-6"
_SONNET_MODEL = PAIR_BRIEF_MODEL
_TEMPERATURE = 0.0
_MAX_TOKENS = 1024

# Net-sentiment delta beyond which one side is treated as the leader for an
# aspect. Mirrors `_PAIR_LEAD_THRESHOLD` in `pulse_check/api/main.py:94` — the
# Pair scorecard uses the same threshold so the prose tracks the visual.
PAIR_LEAD_THRESHOLD = 0.10

# An aspect must have at least this many mentions on at least one side to be
# fed to Sonnet. Aspects with thinner coverage on both sides are dropped from
# the payload entirely so the prompt isn't padded with weak signal.
PAIR_ASPECT_MIN_MENTIONS = 3

# Max verbatims per (side, aspect) sent to Sonnet. Pair brief cites 2-3 IDs
# total across both sides so the pool can be tight without starving the cite
# choice.
PAIR_VERBATIMS_PER_SIDE_CAP = 2

# Per-verbatim raw_text cap applied at payload-build time. Session-43 cost
# reckoning: untruncated mention raw_text averaged 977 chars (max 72,945 —
# Notebookcheck chunks) which pushed per-pair input to ~165K tokens / ~$0.50
# Sonnet. Sonnet only needs enough text to confirm the aspect/sentiment/
# intensity that the deterministic selector already assigned; the full body
# is not load-bearing. Cap at 800 chars (~200 tokens) preserves the lead
# context while dropping per-pair input by ~30x. Mirrors brief_writer.py
# (same value) so a future shared constant move is mechanical. Cache-key
# implication: changing this constant invalidates the LlmCache input_hash
# for every pair-brief row — existing persisted Brief rows are unaffected
# but a re-run would not cache-hit prior calls.
VERBATIM_TEXT_CAP_CHARS = 800

PAIR_PLACEHOLDER_CONTRAST_TEXT = (
    "Insufficient signal on either side to draw a meaningful contrast."
)


@dataclass(frozen=True)
class _SideStats:
    """One side's per-aspect numbers as fed into the Sonnet payload."""

    total_mentions: int
    net_sentiment: float
    pos_count: int
    neg_count: int


@dataclass(frozen=True)
class _PairAspectEntry:
    """Per-aspect contrast row passed to Sonnet."""

    aspect: Aspect
    primary: _SideStats | None
    comparator: _SideStats | None
    delta: float  # primary.net - comparator.net; missing side counted as 0
    leader: Literal["primary", "comparator", "tie"]
    primary_verbatims: tuple[SelectedVerbatim, ...]
    comparator_verbatims: tuple[SelectedVerbatim, ...]


def _side_stats(agg: AggregateAspectSku | None) -> _SideStats | None:
    if agg is None:
        return None
    counts = agg.polarity_counts or {}
    return _SideStats(
        total_mentions=int(agg.total_mentions),
        net_sentiment=float(agg.net_sentiment),
        pos_count=int(counts.get(Polarity.POSITIVE.value, 0)),
        neg_count=int(counts.get(Polarity.NEGATIVE.value, 0)),
    )


def _flatten_selection(selection: AspectSelection | None) -> tuple[SelectedVerbatim, ...]:
    """Pool all four polarity buckets into one ordered tuple; PRIMARY before
    SECONDARY, intensity already-ranked within each bucket by the selector.
    Caller caps with PAIR_VERBATIMS_PER_SIDE_CAP."""
    if selection is None:
        return ()
    pooled: list[SelectedVerbatim] = []
    pooled.extend(selection.primary_positive)
    pooled.extend(selection.primary_negative)
    pooled.extend(selection.secondary_positive)
    pooled.extend(selection.secondary_negative)
    seen: set[str] = set()
    unique: list[SelectedVerbatim] = []
    for v in pooled:
        if v.mention_id in seen:
            continue
        seen.add(v.mention_id)
        unique.append(v)
    return tuple(unique)


def _compute_pair_entries(
    primary_aggs: Mapping[Aspect, AggregateAspectSku],
    comparator_aggs: Mapping[Aspect, AggregateAspectSku],
    primary_selections: Mapping[Aspect, AspectSelection],
    comparator_selections: Mapping[Aspect, AspectSelection],
) -> list[_PairAspectEntry]:
    """Pure routing function — produces sorted aspect entries crossing
    PAIR_ASPECT_MIN_MENTIONS on at least one side. Sort key: abs(delta) desc,
    then aspect name asc (stable tiebreak)."""
    aspects = sorted(set(primary_aggs.keys()) | set(comparator_aggs.keys()), key=lambda a: a.value)
    entries: list[_PairAspectEntry] = []
    for aspect in aspects:
        p_stats = _side_stats(primary_aggs.get(aspect))
        c_stats = _side_stats(comparator_aggs.get(aspect))
        p_total = p_stats.total_mentions if p_stats else 0
        c_total = c_stats.total_mentions if c_stats else 0
        if max(p_total, c_total) < PAIR_ASPECT_MIN_MENTIONS:
            continue
        p_net = p_stats.net_sentiment if p_stats else 0.0
        c_net = c_stats.net_sentiment if c_stats else 0.0
        delta = p_net - c_net
        if delta >= PAIR_LEAD_THRESHOLD:
            leader: Literal["primary", "comparator", "tie"] = "primary"
        elif delta <= -PAIR_LEAD_THRESHOLD:
            leader = "comparator"
        else:
            leader = "tie"
        cap = PAIR_VERBATIMS_PER_SIDE_CAP
        p_verbs = _flatten_selection(primary_selections.get(aspect))[:cap]
        c_verbs = _flatten_selection(comparator_selections.get(aspect))[:cap]
        entries.append(
            _PairAspectEntry(
                aspect=aspect,
                primary=p_stats,
                comparator=c_stats,
                delta=delta,
                leader=leader,
                primary_verbatims=p_verbs,
                comparator_verbatims=c_verbs,
            )
        )
    entries.sort(key=lambda e: (-abs(e.delta), e.aspect.value))
    return entries


def _truncate(text: str) -> str:
    """Cap a verbatim at VERBATIM_TEXT_CAP_CHARS, appending an explicit
    ellipsis marker so Sonnet sees that text was cut. Leaves shorter
    text untouched."""
    if len(text) <= VERBATIM_TEXT_CAP_CHARS:
        return text
    return text[:VERBATIM_TEXT_CAP_CHARS].rstrip() + "..."


def _build_sonnet_payload(
    primary: Product,
    comparator: Product,
    entries: list[_PairAspectEntry],
    verbatim_text: Mapping[str, str],
) -> dict[str, Any]:
    """Build the structured input passed to Sonnet AND used as the cache key."""

    def _side_block(stats: _SideStats | None) -> dict[str, Any] | None:
        if stats is None:
            return None
        return {
            "total_mentions": stats.total_mentions,
            "net_sentiment": round(stats.net_sentiment, 3),
            "pos_count": stats.pos_count,
            "neg_count": stats.neg_count,
        }

    def _verbs_block(verbs: tuple[SelectedVerbatim, ...]) -> list[dict[str, Any]]:
        return [
            {
                "mention_id": v.mention_id,
                "polarity": v.polarity.value,
                "intensity": v.intensity.value,
                "text": _truncate(verbatim_text[v.mention_id]),
            }
            for v in verbs
        ]

    return {
        "pair": {
            "primary": {
                "product_id": primary.product_id,
                "display_name": primary.display_name,
            },
            "comparator": {
                "product_id": comparator.product_id,
                "display_name": comparator.display_name,
            },
        },
        "aspects": [
            {
                "aspect": entry.aspect.value,
                "leader": entry.leader,
                "delta": round(entry.delta, 3),
                "primary": _side_block(entry.primary),
                "comparator": _side_block(entry.comparator),
                "primary_verbatims": _verbs_block(entry.primary_verbatims),
                "comparator_verbatims": _verbs_block(entry.comparator_verbatims),
            }
            for entry in entries
        ],
    }


_SONNET_PROMPT_STRICT_PREAMBLE = """STRICT MODE -- a previous attempt at this \
pair brief was flagged for citation issues. You MUST:
- Use ONLY the verbatim text supplied in the input. Do NOT invent or paraphrase \
evidence not present in the verbatims.
- Do NOT fabricate mention IDs. Use only IDs visible in the input.

"""


_SONNET_PROMPT = """You are a product-listening analyst writing a one-paragraph \
side-by-side contrast for two competing products.

You receive a structured payload describing a product pair (`primary` and \
`comparator`) and a list of aspects, each with per-side aggregate numbers and \
a small pool of verbatim excerpts from real consumer chatter on each side. \
Each aspect carries a `leader` field already computed for you: \
"primary" / "comparator" / "tie".

Your task -- return a JSON object with this exact shape:
{{
  "brief_title": "<primary display_name> vs <comparator display_name>",
  "contrast": {{
    "text": "<50-80 word paragraph, exactly 2 sentences>",
    "cited_mention_ids": ["<id1>", "<id2>", "<id3>"]
  }}
}}

Rules for `contrast.text`:
- ONE paragraph, 50-80 words, exactly 2 sentences.
- Sentence 1: where the PRIMARY product leads -- name the axis of advantage \
in plain English (e.g. "build quality and keyboard feel", "thermal headroom \
under sustained load"). Draw from aspects whose `leader` is "primary".
- Sentence 2: where the COMPARATOR leads (aspects with `leader` = \
"comparator") OR, if the leader skew is one-sided, where the two converge \
(aspects with `leader` = "tie"). Whichever you choose, name the axis in plain \
English.
- Even-handed framing. Do NOT declare an overall winner. Each side gets its \
due in its sentence.
- FORBIDDEN content:
  * No counts, ratios, or percentages ("12 mentions", "60%", "twice as many"). \
The scorecard already carries those.
  * No prescriptive language. Do not recommend a product; do not predict buyer \
behavior. DESCRIBE the contrast.
  * No hedging filler ("it seems", "perhaps", "broadly speaking"). State the \
contrast directly.
  * Do NOT quote raw verbatim text inside `contrast.text`. Refer to the \
texture, not the literal words.
- `cited_mention_ids`: 2-3 IDs DRAWN FROM the verbatims provided in the input \
(either side). Pick mentions whose text best illustrates the contrast you \
describe. Do NOT invent IDs; only IDs visible in the input are valid.

Return ONLY valid JSON, no prose.

INPUT:
{payload_json}
"""


_PAIR_PROMPT_TEMPLATES: dict[str, str] = {
    PAIR_BRIEF_PROMPT_VERSION: _SONNET_PROMPT,
    PAIR_BRIEF_PROMPT_VERSION_STRICT: _SONNET_PROMPT_STRICT_PREAMBLE + _SONNET_PROMPT,
}


def _placeholder_narrative(primary: Product, comparator: Product) -> PairBriefNarrative:
    return PairBriefNarrative(
        brief_title=f"{primary.display_name} vs {comparator.display_name}",
        contrast=PairBriefContrast(
            text=PAIR_PLACEHOLDER_CONTRAST_TEXT,
            cited_mention_ids=[],
        ),
    )


def write_pair_brief(
    session: Session,
    *,
    client: AnthropicClient,
    primary: Product,
    comparator: Product,
    primary_aggregates: Mapping[Aspect, AggregateAspectSku],
    comparator_aggregates: Mapping[Aspect, AggregateAspectSku],
    primary_selections: Mapping[Aspect, AspectSelection],
    comparator_selections: Mapping[Aspect, AspectSelection],
    prompt_version: str = PAIR_BRIEF_PROMPT_VERSION,
) -> PairBriefNarrative:
    """Write a §6.4 PairBriefNarrative for one product pair.

    Determinism: per-aspect routing (leader / delta / verbatim pool) is
    computed in Python; Sonnet writes brief_title and the contrast paragraph
    only. Identical aggregates + selections + prompt_version → cache hit →
    byte-identical brief.

    Returns the placeholder narrative (fixed contrast text, no cites) when no
    aspect crosses `PAIR_ASPECT_MIN_MENTIONS` on either side — Sonnet is not
    invoked in that branch.
    """
    try:
        prompt_template = _PAIR_PROMPT_TEMPLATES[prompt_version]
    except KeyError as exc:
        msg = f"unknown pair brief prompt_version: {prompt_version!r}"
        raise ValueError(msg) from exc

    entries = _compute_pair_entries(
        primary_aggregates,
        comparator_aggregates,
        primary_selections,
        comparator_selections,
    )
    if not entries:
        return _placeholder_narrative(primary, comparator)

    all_mention_ids = sorted({
        v.mention_id
        for entry in entries
        for v in (*entry.primary_verbatims, *entry.comparator_verbatims)
    })
    verbatim_text: dict[str, str] = {}
    if all_mention_ids:
        rows = session.execute(
            select(Mention.mention_id, Mention.raw_text).where(
                Mention.mention_id.in_(all_mention_ids)
            )
        ).all()
        verbatim_text = {mid: text for mid, text in rows}
        missing = set(all_mention_ids) - set(verbatim_text.keys())
        if missing:
            msg = (
                "pair selector returned mention_ids not present in mentions table: "
                f"{sorted(missing)}"
            )
            raise LlmResponseError(msg)

    payload = _build_sonnet_payload(primary, comparator, entries, verbatim_text)

    def _compute() -> LlmResponse:
        return client.generate_json(
            model=_SONNET_MODEL,
            prompt=prompt_template.format(
                payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True)
            ),
            temperature=_TEMPERATURE,
            max_tokens=_MAX_TOKENS,
        )

    response = call_with_cache(
        session,
        task="pair_brief",
        input_payload=payload,
        prompt_version=prompt_version,
        model=_SONNET_MODEL,
        temperature=_TEMPERATURE,
        compute=_compute,
    )

    parsed = response.parsed_output
    if not isinstance(parsed, dict):
        msg = f"expected JSON object from pair brief LLM, got {type(parsed).__name__}"
        raise LlmResponseError(msg)

    brief_title_raw = parsed.get("brief_title")
    if not isinstance(brief_title_raw, str) or not brief_title_raw.strip():
        msg = "pair brief LLM returned no brief_title"
        raise LlmResponseError(msg)

    contrast_raw = parsed.get("contrast")
    contrast = _parse_contrast(contrast_raw, allowed_pool=set(all_mention_ids))
    if contrast is None:
        msg = "pair brief LLM returned malformed or empty contrast block"
        raise LlmResponseError(msg)

    return PairBriefNarrative(
        brief_title=brief_title_raw.strip(),
        contrast=contrast,
    )


def _parse_contrast(raw: Any, *, allowed_pool: set[str]) -> PairBriefContrast | None:
    """Coerce the LLM's `contrast` block into a PairBriefContrast, filtering
    cited_mention_ids against the pooled pair pool (Sonnet writes cited IDs
    directly here; defense-in-depth against fabrication mirrors A1
    `_parse_summary`).

    800-char ceiling vs A1's 600 — pair briefs run longer because each
    sentence enumerates aspects across two sides (session 42 D2).

    Returns None when the block is missing, malformed, or empty — the caller
    raises LlmResponseError on None since pair brief cannot fall back to
    sections like A1 can.
    """
    if not isinstance(raw, dict):
        return None
    text_raw = raw.get("text")
    if not isinstance(text_raw, str) or not text_raw.strip():
        return None
    text = text_raw.strip()
    if len(text) > 800:
        # Sonnet exceeded the contract; truncate rather than dropping the
        # whole paragraph (guardrail mirroring A1 `_parse_summary`).
        text = text[:800]
    raw_ids = raw.get("cited_mention_ids")
    if not isinstance(raw_ids, list):
        cited: list[str] = []
    else:
        cited = [
            mid for mid in raw_ids
            if isinstance(mid, str) and mid in allowed_pool
        ]
    return PairBriefContrast(text=text, cited_mention_ids=cited)
