"""Reason tagger — Qwen 7B via Ollama.

Implements the ``tag_reasons`` contract (ARCHITECTURE §6.1):

    input:   (comment_text, thread_context, winning_product)
    output:  list[{reason_bucket, polarity, intensity}]

Per comment in a resolved deliberation thread, the classifier returns the
``ReasonBucket`` values the commenter cites as justification for / against
the thread's winning product. Multi-label is allowed and empty is valid.
The 15-value ``ReasonBucket`` taxonomy is the 11 aspects plus 4 extras —
``brand_loyalty``, ``value_deal``, ``support_reputation``, ``prior_ownership``
(ARCHITECTURE §3.2).

Comment selection is polarity-agnostic at the caller (batch driver) layer —
both endorsement and dissent get tagged so dissent ("I would have picked the
Blade for thermals") still surfaces ``thermals`` as a deliberation criterion.
Aggregation groups by ``(winning_product_id, reason_bucket)`` and preserves
polarity downstream.

Every call goes through ``call_with_cache`` keyed on:
    sha256(comment_text + winning_product_id + op_post_text +
           sorted(products_discussed product_ids) + PROMPT_VERSION + model + temp)

``winning_product_display_name`` and per-product ``display_name``s render in
the prompt but are *not* part of the cache key — renaming a product without
changing its id does not re-tag.

Output schema matches the ARCHITECTURE §6.1 contract literally: no
``confidence`` field. ``tag_mention_aspects`` and ``classify_deliberation_thread``
both emit one, but ``tag_reasons`` does not per the spec. If 13.e iteration
shows confidence is debug-useful, adding it requires a ``PROMPT_VERSION`` bump
and an ARCH §6.1 row edit in the same change.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmParseError, LlmResponse, call_with_cache
from pulse_check.storage.enums import Intensity, Polarity, ReasonBucket
from pulse_check.tagging.aspect_classifier import ProductContext

log = logging.getLogger(__name__)


class JsonGenerator(Protocol):
    """Structural type for any client able to produce a JSON response.

    Mirrors the Protocol in aspect_classifier / deliberation_classifier so
    the reason tagger accepts either ``OllamaClient`` or ``AnthropicClient``
    via duck-typing.
    """

    def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float = 0.0,
    ) -> LlmResponse: ...


PROMPT_VERSION = "reason_tagger_v1"
TAXONOMY_VERSION = "v0"
_DEFAULT_MODEL = "qwen2.5:7b-q4_K_M"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThreadContext:
    """Minimal thread context the reason tagger needs to ground each comment.

    - ``winning_product_id`` + ``winning_product_display_name`` identify the
      product the OP resolved on (per deliberation classifier output).
    - ``op_post_text`` is the original deliberation prompt — what the OP was
      weighing.
    - ``products_discussed`` is the set of tracked products debated in the
      thread (typically what the deliberation classifier returned). The
      model uses it to disambiguate abbreviations ("the Strix" → "ROG Strix
      G16") and ground reasons against the right product.

    Sibling-comment context is deliberately excluded: nested replies rarely
    introduce new reasons and the N_comments × N_siblings token cost is not
    justified. Add only if 13.e iteration shows a clear recall miss.
    """

    winning_product_id: str
    winning_product_display_name: str
    op_post_text: str
    products_discussed: tuple[ProductContext, ...]


@dataclass(frozen=True)
class ReasonPrediction:
    """Per-comment reason — matches ARCH §6.1 ``tag_reasons`` JSON shape."""

    reason_bucket: ReasonBucket
    polarity: Polarity
    intensity: Intensity


# ---------------------------------------------------------------------------
# Prompt (version v1)
# ---------------------------------------------------------------------------


_REASON_DEFS: dict[ReasonBucket, str] = {
    # 11 aspect-aligned — wording mirrors aspect_classifier._ASPECT_DEFS so
    # the model carries an identical mental model on the overlap set.
    ReasonBucket.THERMALS: "cooling, fan noise, under-load temperature, throttling",
    ReasonBucket.PERFORMANCE: "fps, CPU/GPU speed, stuttering, benchmarks",
    ReasonBucket.KEYBOARD: "typing feel, key travel, layout, backlighting",
    ReasonBucket.DISPLAY: "brightness, color, refresh rate, ghosting, panel quality",
    ReasonBucket.BATTERY: "battery life, runtime unplugged, charging speed",
    ReasonBucket.BUILD_QUALITY: "chassis flex, materials, hinge, durability, rattles",
    ReasonBucket.SOFTWARE_EXPERIENCE: (
        "bloatware, driver issues, control-center apps, Windows experience"
    ),
    ReasonBucket.PRICE_VALUE: (
        "cost vs. spec, value for money, overpricing — independent of any "
        "specific current sale or deal"
    ),
    ReasonBucket.SUPPORT_WARRANTY: (
        "lived RMA experience, customer service interactions actually had, "
        "warranty coverage actually used"
    ),
    ReasonBucket.AESTHETICS: "looks, design, RGB, visual restraint",
    ReasonBucket.PORTABILITY: "weight, thickness, travel-friendliness",
    # 4 extras (ARCHITECTURE §3.2) — hand-written; each names its nearest
    # aspect-aligned neighbor to anchor the disambiguation.
    ReasonBucket.BRAND_LOYALTY: (
        "loyalty to a brand from prior good or bad history with that brand — "
        "distinct from support_warranty (which is the lived RMA experience)"
    ),
    ReasonBucket.VALUE_DEAL: (
        "a specific deal, discount, sale price, or coupon available right now — "
        "distinct from price_value (which is the spec-vs-price judgment)"
    ),
    ReasonBucket.SUPPORT_REPUTATION: (
        "reputation of the brand's support before any first-hand experience — "
        "what people say about the company's support — distinct from "
        "support_warranty (which is the first-hand RMA experience)"
    ),
    ReasonBucket.PRIOR_OWNERSHIP: (
        "owns or previously owned a model from this brand or product family — "
        "distinct from brand_loyalty (this is the fact of ownership, not "
        "the affinity that may or may not follow)"
    ),
}


def _format_reasons_block() -> str:
    return "\n".join(f"- {r.value}: {_REASON_DEFS[r]}" for r in ReasonBucket)


def _format_products_discussed_block(products: tuple[ProductContext, ...]) -> str:
    # Sort by product_id so prompt rendering is order-independent at the
    # caller surface — same set of products in any order produces the same
    # prompt (and therefore the same cache key + LLM call).
    sorted_products = sorted(products, key=lambda p: p.product_id)
    return "\n".join(f"- {p.product_id} | {p.display_name}" for p in sorted_products)


_PROMPT_TEMPLATE = """You are a strict reason-tagger for product deliberation threads. \
You read ONE comment from a resolved deliberation thread and identify which reasons \
the commenter cites — for or against the thread's WINNING product. Multi-label is \
allowed. Empty output is valid — only tag reasons that the comment clearly cites.

THREAD CONTEXT — the original deliberation post and the products under debate:
- The OP's WINNING product: {winning_product_id} | {winning_product_display_name}
- Products discussed in this thread:
{products_discussed_block}

OP POST:
\"\"\"
{op_post_text}
\"\"\"

REASON BUCKETS (use the exact value strings):
{reasons_block}

POLARITY — choose one per tag. Polarity is relative to the WINNING product:
- positive: the comment endorses or favors the WINNING product on this reason
- negative: the comment criticizes the WINNING product on this reason, OR \
praises a non-winning product on this reason as a knock against the winner
- neutral: the reason is cited as a deliberation factor without a clear lean

INTENSITY (choose one per tag):
- low: passing mention, mild language
- medium: a clear opinion in normal language
- high: strong language, quantifiers, severity words, explicit comparisons

OUTPUT — JSON only, no prose, no markdown:
{{"reasons": [{{"reason_bucket": "<reason_bucket>", "polarity": "<polarity>", \
"intensity": "<intensity>"}}]}}

If the comment cites no reasons from the list above, output {{"reasons": []}}.

COMMENT:
\"\"\"
{comment_text}
\"\"\"
"""


def build_prompt(*, comment_text: str, context: ThreadContext) -> str:
    """Render the v1 prompt for a single comment + thread context.

    Prompt string is deterministic on ``(comment_text, context)`` — product
    ordering in ``context.products_discussed`` is normalized internally. Any
    change to wording or reason definitions must come with a
    ``PROMPT_VERSION`` bump so the cache invalidates.
    """
    return _PROMPT_TEMPLATE.format(
        winning_product_id=context.winning_product_id,
        winning_product_display_name=context.winning_product_display_name,
        products_discussed_block=_format_products_discussed_block(context.products_discussed),
        op_post_text=context.op_post_text,
        reasons_block=_format_reasons_block(),
        comment_text=comment_text,
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _coerce_enum(
    value: Any,
    enum_cls: type[ReasonBucket] | type[Polarity] | type[Intensity],
    field: str,
) -> Any:
    if not isinstance(value, str):
        log.warning("reason_tagger: %s not a string: %r", field, value)
        return None
    try:
        return enum_cls(value.strip().lower())
    except ValueError:
        log.warning("reason_tagger: unknown %s value: %r", field, value)
        return None


def parse_response(parsed: Any) -> list[ReasonPrediction]:
    """Turn a parsed JSON payload into a list of ``ReasonPrediction``.

    Raises ``LlmParseError`` on top-level shape issues (not a dict, missing
    ``reasons``, or ``reasons`` not a list). Individual entries with unknown
    bucket / polarity / intensity values are dropped with a warn-log so a
    single hallucinated tag does not fail the whole batch.

    Within-response deduplication: if the LLM emits multiple entries for the
    same ``reason_bucket``, only the first is kept. The ``reason_tags`` table
    does NOT enforce uniqueness on
    ``(mention_id, winning_product_id, reason_bucket, prompt_version)`` —
    the schema permits duplicates — but downstream aggregation groups by
    ``(winning_product, reason_bucket)`` and duplicates would silently
    double-count. Dedup defensively at the classifier so callers can trust
    the output shape.
    """
    if not isinstance(parsed, dict):
        msg = f"expected JSON object, got {type(parsed).__name__}"
        raise LlmParseError(msg)

    reasons = parsed.get("reasons")
    if not isinstance(reasons, list):
        msg = f"expected 'reasons' to be a list, got {type(reasons).__name__}"
        raise LlmParseError(msg)

    out: list[ReasonPrediction] = []
    seen_buckets: set[ReasonBucket] = set()
    for raw in reasons:
        if not isinstance(raw, dict):
            log.warning("reason_tagger: entry not an object: %r", raw)
            continue
        bucket = _coerce_enum(raw.get("reason_bucket"), ReasonBucket, "reason_bucket")
        polarity = _coerce_enum(raw.get("polarity"), Polarity, "polarity")
        intensity = _coerce_enum(raw.get("intensity"), Intensity, "intensity")
        if bucket is None or polarity is None or intensity is None:
            continue
        if bucket in seen_buckets:
            log.warning(
                "reason_tagger: duplicate reason_bucket %s in response; keeping first",
                bucket.value,
            )
            continue
        seen_buckets.add(bucket)
        out.append(
            ReasonPrediction(
                reason_bucket=bucket,
                polarity=polarity,
                intensity=intensity,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Classifier wrapper
# ---------------------------------------------------------------------------


class ReasonTagger:
    """Cache-aware wrapper around ``OllamaClient.generate_json``.

    Carries prompt_version / model / temperature so callers (batch tagger,
    CLI driver) only pass per-comment inputs.
    """

    def __init__(
        self,
        client: JsonGenerator,
        *,
        model: str = _DEFAULT_MODEL,
        temperature: float = 0.0,
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature
        self._prompt_version = prompt_version

    @property
    def model(self) -> str:
        return self._model

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    def classify(
        self,
        session: Session,
        *,
        comment_text: str,
        context: ThreadContext,
    ) -> list[ReasonPrediction]:
        """Return reason predictions for one ``(comment, thread context)``.

        Cache key is hashed over ``comment_text`` + ``winning_product_id`` +
        ``op_post_text`` + sorted ``product_ids`` from ``products_discussed``
        + module constants. ``winning_product_display_name`` and per-product
        ``display_name`` strings are *not* in the key — renaming a product
        without changing its id does not re-tag.
        """
        input_payload = {
            "comment_text": comment_text,
            "winning_product_id": context.winning_product_id,
            "op_post_text": context.op_post_text,
            "products_discussed_ids": sorted(p.product_id for p in context.products_discussed),
        }

        def _compute() -> LlmResponse:
            prompt = build_prompt(comment_text=comment_text, context=context)
            return self._client.generate_json(
                model=self._model,
                prompt=prompt,
                temperature=self._temperature,
            )

        response = call_with_cache(
            session,
            task="reason_tagging",
            input_payload=input_payload,
            prompt_version=self._prompt_version,
            model=self._model,
            temperature=self._temperature,
            compute=_compute,
        )
        return parse_response(response.parsed_output)
