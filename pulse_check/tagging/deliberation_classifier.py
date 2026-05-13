"""Deliberation thread classifier — Qwen 7B via Ollama.

Implements the ``classify_deliberation_thread`` contract (ARCHITECTURE §6.1):

    input:   (thread, products)
    output:  {is_deliberation, is_resolved, products_discussed,
              chosen_product_id, chosen_external_name, confidence}

One Qwen call returns all six fields — outcome extraction is folded into the
classifier rather than split into a separate pass. The classifier is
full-product-universe: callers pass the run's full tracked product set per
thread, not a per-pair subset.

``chosen_external_name`` (v2) captures the OP's chosen winner when it is NOT
in the tracked product universe (e.g., "I went with the Razer Blade 16" when
Razer is untracked). Free-text. Mutually exclusive with ``chosen_product_id``:
at most one is set per thread.

Resolution is **OP-only** per ARCHITECTURE §11 ("Resolved deliberation
thread"). Third-party assertions ("I think OP went with X") do not resolve.
To make that rule structural rather than stringly-typed at every call site,
``DeliberationThread`` separates OP-authored segments from other-commenter
segments and the prompt renders each with role markers ([OP_POST], [OP_EDIT],
[OP_COMMENT], [OTHER_COMMENT]).

Every call goes through ``call_with_cache`` keyed on the thread content +
product universe + ``PROMPT_VERSION`` + model + temperature. Editing the
prompt or the resolution rule requires a ``PROMPT_VERSION`` bump so the
cache invalidates cleanly while the old rows remain as an audit trail.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmParseError, LlmResponse, call_with_cache
from pulse_check.tagging.aspect_classifier import ProductContext

log = logging.getLogger(__name__)


class JsonGenerator(Protocol):
    """Structural type for any client able to produce a JSON response.

    Both ``OllamaClient`` (Qwen) and ``AnthropicClient`` (Sonnet/Haiku)
    implement this signature, so the classifier accepts either via
    duck-typing.
    """

    def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float = 0.0,
    ) -> LlmResponse: ...


PROMPT_VERSION = "deliberation_classifier_v2"
_DEFAULT_MODEL = "qwen2.5:7b-q4_K_M"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeliberationThread:
    """One thread laid out by author role so OP-only resolution is structural.

    - ``op_post_text`` is always present (the OP's original post body).
    - ``op_edit_text`` is the post body *after* an OP edit, if any.
    - ``op_top_level_comments`` are top-level comments by the OP under their
      own post, in chronological order.
    - ``other_top_level_comments`` are top-level comments by other users.
      They appear in the prompt for context but do NOT count toward
      resolution per ARCHITECTURE §11.

    ``thread_id`` is for logging only — it is **not** part of the cache key,
    so two threads with identical content + product universe share a cache
    row (acceptable; collisions on real-world thread text are vanishingly
    unlikely).
    """

    thread_id: str
    op_post_text: str
    op_edit_text: str | None = None
    op_top_level_comments: tuple[str, ...] = ()
    other_top_level_comments: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeliberationPrediction:
    """Per-thread classification — mirrors ARCH §6.1 JSON shape + confidence.

    ``chosen_external_name`` (v2) is mutually exclusive with
    ``chosen_product_id``: at most one is set. The default is ``None`` so v1
    callers that don't pass it still construct a valid v2 prediction.
    """

    is_deliberation: bool
    is_resolved: bool
    products_discussed: tuple[str, ...]
    chosen_product_id: str | None
    confidence: float | None
    chosen_external_name: str | None = None


# ---------------------------------------------------------------------------
# Prompt (version v1)
# ---------------------------------------------------------------------------


def _format_products_block(products: tuple[ProductContext, ...]) -> str:
    # Sort by product_id so prompt rendering is order-independent at the
    # caller surface — same set of products, any order, produces the same
    # prompt (and therefore the same cache key + LLM call).
    sorted_products = sorted(products, key=lambda p: p.product_id)
    return "\n".join(f"- {p.product_id} | {p.display_name}" for p in sorted_products)


def _format_thread_block(thread: DeliberationThread) -> str:
    lines: list[str] = ["[OP_POST]", thread.op_post_text]
    if thread.op_edit_text is not None:
        lines.append("")
        lines.append("[OP_EDIT]")
        lines.append(thread.op_edit_text)
    for i, comment in enumerate(thread.op_top_level_comments, start=1):
        lines.append("")
        lines.append(f"[OP_COMMENT {i}]")
        lines.append(comment)
    for i, comment in enumerate(thread.other_top_level_comments, start=1):
        lines.append("")
        lines.append(f"[OTHER_COMMENT {i}]")
        lines.append(comment)
    return "\n".join(lines)


_PROMPT_TEMPLATE = """You are a strict thread analyst for product deliberations. \
You read a Reddit-style thread and classify whether it is a comparative \
deliberation between products, which products were discussed, and whether the \
original poster (OP) reached a resolution.

PRODUCT UNIVERSE — the tracked products for this run. Use these exact \
product_id strings in your output. Do NOT invent or paraphrase IDs.
{products_block}

THREAD CONTENT — segments are labeled by author role:
- [OP_POST]        the original post body, authored by the OP
- [OP_EDIT]        a later edit of the original post body, still by the OP
- [OP_COMMENT n]   a top-level comment authored by the OP under their own post
- [OTHER_COMMENT n] a top-level comment by some other user

{thread_block}

RULES:
1. is_deliberation = true ONLY if the thread is a comparative purchase / \
choice deliberation (someone weighing two or more products, or asking for \
help choosing). Single-product reviews, help-desk questions, and off-topic \
posts are NOT deliberations.
2. products_discussed = the subset of PRODUCT UNIVERSE product_ids that are \
substantively discussed anywhere in the thread. Use the exact id strings. \
Products mentioned only in passing, or referenced but not in the universe, \
are excluded.
3. is_resolved = true ONLY if a segment labeled [OP_POST], [OP_EDIT], or \
[OP_COMMENT] names the chosen product. The chosen product can be either:
   (a) a tracked product from PRODUCT UNIVERSE — set chosen_product_id to \
its product_id and leave chosen_external_name = null; OR
   (b) an untracked external product (a specific product NOT in PRODUCT \
UNIVERSE, e.g. "the Razer Blade 16", "MSI Stealth 16 AI Studio") — set \
chosen_external_name to the product name as the OP wrote it and leave \
chosen_product_id = null.
   Assertions made in [OTHER_COMMENT] segments (e.g., "I think OP went \
with X") do NOT count toward resolution.
4. chosen_product_id, if set, MUST be a product_id from products_discussed.
5. chosen_product_id and chosen_external_name are mutually exclusive — at \
most one is set per thread. If neither is set, both MUST be null and \
is_resolved = false.
6. confidence = your overall confidence in the classification, between 0 \
and 1.

OUTPUT — JSON only, no prose, no markdown:
{{"is_deliberation": <bool>, "is_resolved": <bool>, "products_discussed": \
["<product_id>", ...], "chosen_product_id": "<product_id>" | null, \
"chosen_external_name": "<product name>" | null, "confidence": <number \
between 0 and 1>}}

If the thread is not a deliberation, output \
{{"is_deliberation": false, "is_resolved": false, "products_discussed": [], \
"chosen_product_id": null, "chosen_external_name": null, "confidence": \
<number between 0 and 1>}}.
"""


def build_prompt(
    *, thread: DeliberationThread, products: tuple[ProductContext, ...]
) -> str:
    """Render the v1 prompt for a single thread + product universe.

    Prompt string is deterministic on ``(thread content, product set)`` —
    product ordering is normalized internally. Any change to wording or the
    resolution rule must come with a ``PROMPT_VERSION`` bump so the cache
    invalidates.
    """
    return _PROMPT_TEMPLATE.format(
        products_block=_format_products_block(products),
        thread_block=_format_thread_block(thread),
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _coerce_bool(value: Any, field: str) -> bool | None:
    if isinstance(value, bool):
        return value
    log.warning("deliberation_classifier: %s not a bool: %r", field, value)
    return None


def _coerce_product_id_list(value: Any, universe: set[str]) -> list[str]:
    if not isinstance(value, list):
        log.warning("deliberation_classifier: products_discussed not a list: %r", value)
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in value:
        if not isinstance(raw, str):
            log.warning("deliberation_classifier: product id not a string: %r", raw)
            continue
        if raw not in universe:
            log.warning(
                "deliberation_classifier: unknown product id %r dropped (not in universe)", raw
            )
            continue
        if raw in seen:
            log.warning("deliberation_classifier: duplicate product id %r dropped", raw)
            continue
        seen.add(raw)
        out.append(raw)
    return out


def _coerce_chosen_product_id(value: Any, discussed: list[str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        log.warning("deliberation_classifier: chosen_product_id not a string: %r", value)
        return None
    if value not in discussed:
        log.warning(
            "deliberation_classifier: chosen_product_id %r not in products_discussed; "
            "demoting to null",
            value,
        )
        return None
    return value


def _coerce_chosen_external_name(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        log.warning(
            "deliberation_classifier: chosen_external_name not a string: %r", value
        )
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def _coerce_confidence(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        # bool is an int subclass; explicitly reject before the numeric branch.
        log.warning("deliberation_classifier: confidence was a bool: %r", value)
        return None
    if isinstance(value, (int, float)):
        conf = float(value)
        if 0.0 <= conf <= 1.0:
            return conf
        log.warning("deliberation_classifier: confidence out of range: %r", conf)
        return None
    log.warning("deliberation_classifier: confidence not numeric: %r", value)
    return None


def parse_response(
    parsed: Any, *, products: tuple[ProductContext, ...]
) -> DeliberationPrediction:
    """Turn a parsed JSON payload into a ``DeliberationPrediction``.

    Raises ``LlmParseError`` on top-level shape issues (not a dict, missing
    ``is_deliberation``). Other fields fall back to safe defaults with a
    warn-log rather than failing the whole batch — the resolution rule and
    universe-membership constraints are enforced defensively after parsing.

    Defensive consistency rules:
    - If ``is_deliberation`` is false, ``products_discussed`` is forced to
      empty, both winner fields to null, and ``is_resolved`` to false.
    - If ``chosen_product_id`` is not in (the filtered) ``products_discussed``,
      it is demoted to null.
    - If ``chosen_product_id`` and ``chosen_external_name`` are both set, the
      tracked id wins (more specific) and the external name is dropped.
    - If ``is_resolved`` is true but BOTH winner fields are null, the
      resolution is demoted to false.
    """
    if not isinstance(parsed, dict):
        msg = f"expected JSON object, got {type(parsed).__name__}"
        raise LlmParseError(msg)

    universe = {p.product_id for p in products}

    is_deliberation = _coerce_bool(parsed.get("is_deliberation"), "is_deliberation")
    if is_deliberation is None:
        msg = "missing or invalid 'is_deliberation' field"
        raise LlmParseError(msg)

    is_resolved_raw = _coerce_bool(parsed.get("is_resolved"), "is_resolved")
    is_resolved = False if is_resolved_raw is None else is_resolved_raw

    discussed_list = _coerce_product_id_list(parsed.get("products_discussed"), universe)
    chosen = _coerce_chosen_product_id(parsed.get("chosen_product_id"), discussed_list)
    external = _coerce_chosen_external_name(parsed.get("chosen_external_name"))
    confidence = _coerce_confidence(parsed.get("confidence"))

    if not is_deliberation:
        if discussed_list or chosen is not None or external is not None or is_resolved:
            log.warning(
                "deliberation_classifier: is_deliberation=false but downstream fields "
                "non-empty; forcing to safe defaults"
            )
        discussed_list = []
        chosen = None
        external = None
        is_resolved = False

    if chosen is not None and external is not None:
        log.warning(
            "deliberation_classifier: both chosen_product_id=%r and "
            "chosen_external_name=%r set; dropping external name (tracked wins)",
            chosen,
            external,
        )
        external = None

    if is_resolved and chosen is None and external is None:
        log.warning(
            "deliberation_classifier: is_resolved=true but no winner set "
            "(chosen_product_id and chosen_external_name both null); demoting"
        )
        is_resolved = False

    return DeliberationPrediction(
        is_deliberation=is_deliberation,
        is_resolved=is_resolved,
        products_discussed=tuple(discussed_list),
        chosen_product_id=chosen,
        confidence=confidence,
        chosen_external_name=external,
    )


# ---------------------------------------------------------------------------
# Classifier wrapper
# ---------------------------------------------------------------------------


class DeliberationClassifier:
    """Cache-aware wrapper around ``OllamaClient.generate_json``.

    Carries prompt_version/model/temperature so callers (batch tagger, CLI)
    only pass per-thread inputs.
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
        thread: DeliberationThread,
        products: tuple[ProductContext, ...],
    ) -> DeliberationPrediction:
        """Return a deliberation prediction for one ``(thread, product universe)``.

        Cache key is hashed over the thread content fields + sorted
        product_ids + module constants. ``thread_id`` and per-product
        ``display_name`` are **not** in the key — renaming a product or
        re-scraping the same content does not re-classify.
        """
        input_payload = {
            "op_post_text": thread.op_post_text,
            "op_edit_text": thread.op_edit_text,
            "op_top_level_comments": list(thread.op_top_level_comments),
            "other_top_level_comments": list(thread.other_top_level_comments),
            "product_ids": sorted(p.product_id for p in products),
        }

        def _compute() -> LlmResponse:
            prompt = build_prompt(thread=thread, products=products)
            return self._client.generate_json(
                model=self._model,
                prompt=prompt,
                temperature=self._temperature,
            )

        response = call_with_cache(
            session,
            task="deliberation_tagging",
            input_payload=input_payload,
            prompt_version=self._prompt_version,
            model=self._model,
            temperature=self._temperature,
            compute=_compute,
        )
        return parse_response(response.parsed_output, products=products)
