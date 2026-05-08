"""Sonnet brief writer — assembles a §6.3 BriefNarrative from selected verbatims.

Locked four-quadrant layout (ARCHITECTURE §6.3 — A1 brief layout):
  1. High-confidence strengths   — PRIMARY pos ≥ 3
  2. High-confidence weaknesses  — PRIMARY neg ≥ 3 (placeholder if empty)
  3. Low-signal strengths        — SECONDARY pos ≥ 1, not in §1
  4. Low-signal weaknesses       — SECONDARY neg ≥ 1, not in §2

Each section has up to 3 aspects ranked by the relevant count desc. Each
aspect = one Claim citing up to 3 mention IDs from the selector output.

Sonnet writes ONLY `brief_title` and one `claim_text` per (quadrant, aspect);
the writer constructs the `BriefNarrative` shape deterministically so no
fabricated mention IDs can slip in (defense-in-depth alongside
`citation_validator`, bite 10.4).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmResponse, LlmResponseError, call_with_cache
from pulse_check.storage.enums import Aspect, AttributionType, Polarity
from pulse_check.storage.models import AggregateAspectSku, Mention, Product
from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.synthesis.contracts import BriefNarrative, BriefSection, Claim
from pulse_check.synthesis.selector import AspectSelection, SelectedVerbatim

log = logging.getLogger(__name__)

BRIEF_PROMPT_VERSION = "a1_brief_v1"
_SONNET_MODEL = "claude-sonnet-4-6"
_TEMPERATURE = 0.0
_MAX_TOKENS = 4096

PER_QUADRANT_ASPECT_CAP = 3
HIGH_CONF_THRESHOLD = 3   # min PRIMARY mentions of a polarity for §1/§2 inclusion
SECONDARY_THRESHOLD = 1   # min SECONDARY mentions for §3/§4 inclusion

SECTION_HEADINGS: dict[int, str] = {
    1: "High-confidence strengths",
    2: "High-confidence weaknesses",
    3: "Low-signal strengths (public chatter)",
    4: "Low-signal weaknesses (public chatter)",
}

PLACEHOLDER_CLAIM_TEXT = "No top-of-mind criticism in PRIMARY chatter — see §4 below"


@dataclass(frozen=True)
class _QuadrantAspectEntry:
    aspect: Aspect
    count_for_quadrant: int
    selected: tuple[SelectedVerbatim, ...]


@dataclass(frozen=True)
class _QuadrantPlan:
    quadrant_id: int
    heading: str
    polarity: Polarity
    bucket: AttributionType
    aspect_entries: tuple[_QuadrantAspectEntry, ...]


def _polarity_count(counts: Mapping[str, Any] | None, polarity: Polarity) -> int:
    if not counts:
        return 0
    value = counts.get(polarity.value, 0)
    return int(value) if isinstance(value, int) else 0


def _route_aspects_to_quadrants(
    aggregates: Mapping[Aspect, AggregateAspectSku],
    selections: Mapping[Aspect, AspectSelection],
) -> list[_QuadrantPlan]:
    """Pure function — apply the locked routing rules, return four plans."""

    def _gather(
        polarity: Polarity,
        bucket_attr: str,
        counts_attr: str,
        threshold: int,
        excluded_aspects: set[Aspect],
    ) -> list[_QuadrantAspectEntry]:
        pairs: list[tuple[Aspect, int, tuple[SelectedVerbatim, ...]]] = []
        for aspect, agg in aggregates.items():
            if aspect in excluded_aspects:
                continue
            sel = selections.get(aspect)
            if sel is None:
                continue
            count = _polarity_count(getattr(agg, counts_attr), polarity)
            if count < threshold:
                continue
            verbatims: tuple[SelectedVerbatim, ...] = getattr(sel, bucket_attr)
            if not verbatims:
                continue
            pairs.append((aspect, count, verbatims))
        pairs.sort(key=lambda t: (-t[1], t[0].value))
        return [
            _QuadrantAspectEntry(aspect=a, count_for_quadrant=c, selected=v)
            for a, c, v in pairs[:PER_QUADRANT_ASPECT_CAP]
        ]

    q1 = _gather(
        Polarity.POSITIVE, "primary_positive", "polarity_counts",
        HIGH_CONF_THRESHOLD, set(),
    )
    q2 = _gather(
        Polarity.NEGATIVE, "primary_negative", "polarity_counts",
        HIGH_CONF_THRESHOLD, set(),
    )
    q1_aspects = {e.aspect for e in q1}
    q2_aspects = {e.aspect for e in q2}
    q3 = _gather(
        Polarity.POSITIVE, "secondary_positive", "polarity_counts_secondary",
        SECONDARY_THRESHOLD, q1_aspects,
    )
    q4 = _gather(
        Polarity.NEGATIVE, "secondary_negative", "polarity_counts_secondary",
        SECONDARY_THRESHOLD, q2_aspects,
    )

    pri = AttributionType.PRIMARY
    sec = AttributionType.SECONDARY
    return [
        _QuadrantPlan(1, SECTION_HEADINGS[1], Polarity.POSITIVE, pri, tuple(q1)),
        _QuadrantPlan(2, SECTION_HEADINGS[2], Polarity.NEGATIVE, pri, tuple(q2)),
        _QuadrantPlan(3, SECTION_HEADINGS[3], Polarity.POSITIVE, sec, tuple(q3)),
        _QuadrantPlan(4, SECTION_HEADINGS[4], Polarity.NEGATIVE, sec, tuple(q4)),
    ]


def _build_sonnet_payload(
    product: Product,
    aggregates: Mapping[Aspect, AggregateAspectSku],
    plans: list[_QuadrantPlan],
    verbatim_text: Mapping[str, str],
) -> dict[str, Any]:
    """Build the structured input passed to Sonnet AND used as the cache key."""
    return {
        "product": {
            "product_id": product.product_id,
            "display_name": product.display_name,
        },
        "quadrants": [
            {
                "quadrant_id": plan.quadrant_id,
                "heading": plan.heading,
                "polarity": plan.polarity.value,
                "bucket": plan.bucket.value,
                "aspects": [
                    {
                        "aspect": entry.aspect.value,
                        "count_for_quadrant": entry.count_for_quadrant,
                        "primary_pos_count": _polarity_count(
                            aggregates[entry.aspect].polarity_counts, Polarity.POSITIVE
                        ),
                        "primary_neg_count": _polarity_count(
                            aggregates[entry.aspect].polarity_counts, Polarity.NEGATIVE
                        ),
                        "secondary_pos_count": _polarity_count(
                            aggregates[entry.aspect].polarity_counts_secondary, Polarity.POSITIVE
                        ),
                        "secondary_neg_count": _polarity_count(
                            aggregates[entry.aspect].polarity_counts_secondary, Polarity.NEGATIVE
                        ),
                        "verbatims": [
                            {
                                "mention_id": v.mention_id,
                                "intensity": v.intensity.value,
                                "text": verbatim_text[v.mention_id],
                            }
                            for v in entry.selected
                        ],
                    }
                    for entry in plan.aspect_entries
                ],
            }
            for plan in plans
        ],
    }


_SONNET_PROMPT = """You are a product-listening analyst writing a one-page \
voice-of-customer brief.

You receive a structured payload describing one product and four pre-routed \
quadrants of evidence:
  Q1 = high-confidence strengths   (PRIMARY pos >= 3)
  Q2 = high-confidence weaknesses  (PRIMARY neg >= 3)
  Q3 = low-signal strengths        (SECONDARY pos >= 1, not already in Q1)
  Q4 = low-signal weaknesses       (SECONDARY neg >= 1, not already in Q2)

Each quadrant lists 0-3 aspects; each aspect carries up to 3 verbatim \
excerpts that are the only cite-able evidence.

Your task -- return a JSON object with this exact shape:
{{
  "brief_title": "<one-line title naming the product>",
  "claims": [
    {{"quadrant_id": <int 1..4>, "aspect": "<aspect_id>", \
"claim_text": "<1-2 sentences>"}}
  ]
}}

Rules:
- Write ONE entry in `claims` per (quadrant_id, aspect) pair present in the \
input. Do NOT invent aspects or quadrants.
- `claim_text` is 1-2 sentences summarizing what the verbatims for that \
aspect actually say. Cite specific points, not generalities.
- Do NOT include mention IDs or quote raw verbatim text inside `claim_text`. \
The orchestrator wires citations from the input pool.
- If a quadrant in the input has zero aspects, skip it -- do not emit a \
claim for it.
- Return ONLY valid JSON, no prose.

INPUT:
{payload_json}
"""


def write_a1_brief(
    session: Session,
    *,
    client: AnthropicClient,
    product: Product,
    aggregates: Mapping[Aspect, AggregateAspectSku],
    selections: Mapping[Aspect, AspectSelection],
    prompt_version: str = BRIEF_PROMPT_VERSION,
) -> BriefNarrative:
    """Write a §6.3 BriefNarrative for one product.

    Determinism: the four-quadrant structure (which aspects → which section)
    is computed in Python; Sonnet only writes `brief_title` and per-aspect
    `claim_text`. Identical aggregates + selections + prompt_version → cache
    hit on the Sonnet call → byte-identical brief.

    Empty section 2 always renders with the operator-locked placeholder claim
    (ARCHITECTURE §6.3 A1 brief layout). Sections 1, 3, 4 are omitted when
    their qualifying-aspect set is empty.
    """
    plans = _route_aspects_to_quadrants(aggregates, selections)
    all_empty = all(not p.aspect_entries for p in plans)

    if all_empty:
        # No data anywhere -- short-circuit Sonnet entirely. The brief is just
        # the locked placeholder, with a deterministic title.
        return BriefNarrative(
            brief_title=f"{product.display_name} — A1 voice",
            sections=[
                BriefSection(
                    heading=SECTION_HEADINGS[2],
                    claims=[Claim(claim_text=PLACEHOLDER_CLAIM_TEXT, cited_mention_ids=[])],
                )
            ],
        )

    all_mention_ids = sorted({
        v.mention_id
        for plan in plans
        for entry in plan.aspect_entries
        for v in entry.selected
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
            msg = f"selector returned mention_ids not present in mentions table: {sorted(missing)}"
            raise LlmResponseError(msg)

    payload = _build_sonnet_payload(product, aggregates, plans, verbatim_text)

    def _compute() -> LlmResponse:
        return client.generate_json(
            model=_SONNET_MODEL,
            prompt=_SONNET_PROMPT.format(
                payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True)
            ),
            temperature=_TEMPERATURE,
            max_tokens=_MAX_TOKENS,
        )

    response = call_with_cache(
        session,
        task="a1_brief",
        input_payload=payload,
        prompt_version=prompt_version,
        model=_SONNET_MODEL,
        temperature=_TEMPERATURE,
        compute=_compute,
    )

    parsed = response.parsed_output
    if not isinstance(parsed, dict):
        msg = f"expected JSON object from brief writer LLM, got {type(parsed).__name__}"
        raise LlmResponseError(msg)

    brief_title_raw = parsed.get("brief_title")
    if not isinstance(brief_title_raw, str) or not brief_title_raw.strip():
        msg = "brief writer LLM returned no brief_title"
        raise LlmResponseError(msg)

    claims_raw = parsed.get("claims")
    if not isinstance(claims_raw, list):
        msg = f"expected 'claims' to be a list, got {type(claims_raw).__name__}"
        raise LlmResponseError(msg)

    claim_text_by_key: dict[tuple[int, str], str] = {}
    for item in claims_raw:
        if not isinstance(item, dict):
            continue
        qid = item.get("quadrant_id")
        aspect_id = item.get("aspect")
        text = item.get("claim_text")
        if (
            isinstance(qid, int)
            and isinstance(aspect_id, str)
            and isinstance(text, str)
            and text.strip()
        ):
            claim_text_by_key[(qid, aspect_id)] = text.strip()

    sections: list[BriefSection] = []
    for plan in plans:
        if plan.quadrant_id == 2 and not plan.aspect_entries:
            sections.append(
                BriefSection(
                    heading=plan.heading,
                    claims=[Claim(claim_text=PLACEHOLDER_CLAIM_TEXT, cited_mention_ids=[])],
                )
            )
            continue
        if not plan.aspect_entries:
            continue

        section_claims: list[Claim] = []
        for entry in plan.aspect_entries:
            text = claim_text_by_key.get((plan.quadrant_id, entry.aspect.value))
            if text is None:
                msg = (
                    f"brief writer LLM omitted claim_text for quadrant={plan.quadrant_id} "
                    f"aspect={entry.aspect.value}"
                )
                raise LlmResponseError(msg)
            section_claims.append(
                Claim(
                    claim_text=text,
                    cited_mention_ids=[v.mention_id for v in entry.selected],
                )
            )
        sections.append(BriefSection(heading=plan.heading, claims=section_claims))

    return BriefNarrative(brief_title=brief_title_raw.strip(), sections=sections)
