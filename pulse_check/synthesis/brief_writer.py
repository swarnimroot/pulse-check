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
from pulse_check.synthesis.contracts import (
    BriefNarrative,
    BriefSection,
    BriefSummary,
    Claim,
)
from pulse_check.synthesis.selector import AspectSelection, SelectedVerbatim

log = logging.getLogger(__name__)

BRIEF_PROMPT_VERSION = "a1_brief_v3"
BRIEF_PROMPT_VERSION_STRICT = "a1_brief_v3_strict"
# Legacy versions retained for cache reads on historical briefs; never used
# for new writes after session 41.
BRIEF_PROMPT_VERSION_V2 = "a1_brief_v2"
BRIEF_PROMPT_VERSION_V2_STRICT = "a1_brief_v2_strict"
BRIEF_MODEL = "claude-sonnet-4-6"
_SONNET_MODEL = BRIEF_MODEL  # internal alias preserved for grep stability
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
PLACEHOLDER_CLAIM_HEADER = "No criticism noted"


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


_SONNET_PROMPT_STRICT_PREAMBLE = """STRICT MODE -- a previous attempt at this \
brief was flagged for citation issues. You MUST:
- Use ONLY the verbatim text supplied in the input. Do NOT invent or paraphrase \
evidence not present in the verbatims.
- Do NOT introduce specific counts (e.g. "60 threads", "10 users") in \
`claim_text` unless the count is directly visible in the verbatims.
- Do NOT fabricate aspect IDs or quadrant IDs. Use only what the input supplies.

"""


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
  "summary": {{
    "text": "<50-80 word paragraph, 1-2 sentences>",
    "cited_mention_ids": ["<id1>", "<id2>", "..."]
  }},
  "claims": [
    {{"quadrant_id": <int 1..4>, "aspect": "<aspect_id>", \
"header": "<2-5 word headline>", \
"claim_text": "<1-2 sentences>"}}
  ]
}}

Rules for `claims`:
- Write ONE entry per (quadrant_id, aspect) pair present in the input. Do \
NOT invent aspects or quadrants.
- `header` is a 2-5 word headline naming THE SPECIFIC THING the bullet is \
about, in plain English an executive could scan in one glance. Examples: \
"Keyboard feels premium", "Thermals run hot under load", "Display brightness \
underwhelms", "Build quality reassures". Do NOT just echo the aspect name; \
say what about it.
- `claim_text` is 1-2 sentences summarizing what the verbatims for that \
aspect actually say. Cite specific points, not generalities. Do NOT repeat \
the header verbatim; expand on it.
- Do NOT include mention IDs or quote raw verbatim text inside `claim_text` \
or `header`. The orchestrator wires citations from the input pool.
- If a quadrant in the input has zero aspects, skip it -- do not emit a \
claim for it.

Rules for `summary`:
- ONE paragraph, 50-80 words, exactly 2 sentences.
- Sentence 1: what the conversation centers on -- the topic texture of \
chatter for this product. What ARE people discussing? (e.g. "Discussion \
clusters around thermals under sustained load and keyboard feel, with a \
recurring undercurrent of pricing frustration.")
- Sentence 2: where consensus holds versus where opinions split. Name the \
axis of agreement and the axis of polarization, without restating the \
specific aspect names already covered in `claims`. (e.g. "Build quality \
draws broad agreement; display performance polarizes buyers, with pointed \
praise alongside equally pointed criticism.")
- FORBIDDEN content (avoid redundancy with the snapshot row and the claims):
  * No counts, ratios, or percentages ("60 threads", "10 users", "33%"). \
The snapshot row carries those.
  * Do not name a specific aspect already named in the `header` field of any \
emitted claim. If the claims cover Thermals and Keyboard, the summary should \
not also say "thermals" or "keyboard" by name -- find adjacent texture (heat, \
typing feel) or higher-level framing (build quality, daily-use ergonomics).
  * Do not say "consumer sentiment is positive/negative overall" -- net \
sentiment is in the snapshot.
- `cited_mention_ids`: 2-3 IDs DRAWN FROM the verbatims provided in the \
input quadrants. Pick mentions whose text best illustrates the texture you \
describe. Do NOT invent IDs; only IDs visible in the input are valid.
- The summary paragraph is DESCRIPTIVE, not prescriptive. Do not recommend \
actions; do not predict.

Return ONLY valid JSON, no prose.

INPUT:
{payload_json}
"""


_BRIEF_PROMPT_TEMPLATES: dict[str, str] = {
    BRIEF_PROMPT_VERSION: _SONNET_PROMPT,
    BRIEF_PROMPT_VERSION_STRICT: _SONNET_PROMPT_STRICT_PREAMBLE + _SONNET_PROMPT,
}


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
    try:
        prompt_template = _BRIEF_PROMPT_TEMPLATES[prompt_version]
    except KeyError as exc:
        msg = f"unknown brief prompt_version: {prompt_version!r}"
        raise ValueError(msg) from exc

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
                    claims=[
                        Claim(
                            header=PLACEHOLDER_CLAIM_HEADER,
                            claim_text=PLACEHOLDER_CLAIM_TEXT,
                            cited_mention_ids=[],
                        )
                    ],
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
            prompt=prompt_template.format(
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

    claim_by_key: dict[tuple[int, str], tuple[str, str]] = {}
    for item in claims_raw:
        if not isinstance(item, dict):
            continue
        qid = item.get("quadrant_id")
        aspect_id = item.get("aspect")
        text = item.get("claim_text")
        header = item.get("header")
        if (
            isinstance(qid, int)
            and isinstance(aspect_id, str)
            and isinstance(text, str)
            and text.strip()
            and isinstance(header, str)
            and header.strip()
        ):
            claim_by_key[(qid, aspect_id)] = (header.strip(), text.strip())

    sections: list[BriefSection] = []
    for plan in plans:
        if plan.quadrant_id == 2 and not plan.aspect_entries:
            sections.append(
                BriefSection(
                    heading=plan.heading,
                    claims=[
                        Claim(
                            header=PLACEHOLDER_CLAIM_HEADER,
                            claim_text=PLACEHOLDER_CLAIM_TEXT,
                            cited_mention_ids=[],
                        )
                    ],
                )
            )
            continue
        if not plan.aspect_entries:
            continue

        section_claims: list[Claim] = []
        for entry in plan.aspect_entries:
            pair = claim_by_key.get((plan.quadrant_id, entry.aspect.value))
            if pair is None:
                msg = (
                    "brief writer LLM omitted header/claim_text for "
                    f"quadrant={plan.quadrant_id} aspect={entry.aspect.value}"
                )
                raise LlmResponseError(msg)
            header_text, claim_text = pair
            section_claims.append(
                Claim(
                    header=header_text,
                    claim_text=claim_text,
                    cited_mention_ids=[v.mention_id for v in entry.selected],
                )
            )
        sections.append(BriefSection(heading=plan.heading, claims=section_claims))

    # Look up the summary block under the canonical key first, then fall back
    # to the legacy `vibe_summary` key for cached Sonnet responses written
    # earlier in session 41 before the rename.
    summary_raw = parsed.get("summary")
    if summary_raw is None:
        summary_raw = parsed.get("vibe_summary")
    summary = _parse_summary(summary_raw, allowed_pool=set(all_mention_ids))

    return BriefNarrative(
        brief_title=brief_title_raw.strip(),
        sections=sections,
        summary=summary,
    )


def _parse_summary(
    raw: Any, *, allowed_pool: set[str]
) -> BriefSummary | None:
    """Coerce the LLM's `summary` block into a BriefSummary, filtering
    cited_mention_ids against the input pool (defense-in-depth: Sonnet writes
    cited IDs directly here, unlike the per-claim cites which are wired in
    Python).

    Returns None when the block is missing, malformed, or has empty text.
    The frontend renders gracefully when summary is None.
    """
    if not isinstance(raw, dict):
        return None
    text_raw = raw.get("text")
    if not isinstance(text_raw, str) or not text_raw.strip():
        return None
    text = text_raw.strip()
    if len(text) > 600:
        # Sonnet exceeded the contract; truncate to the schema bound rather
        # than dropping the paragraph entirely. The prompt asks for 50-80
        # words; this is a guardrail, not a normal path.
        text = text[:600]
    raw_ids = raw.get("cited_mention_ids")
    if not isinstance(raw_ids, list):
        cited: list[str] = []
    else:
        cited = [
            mid for mid in raw_ids
            if isinstance(mid, str) and mid in allowed_pool
        ]
    return BriefSummary(text=text, cited_mention_ids=cited)
