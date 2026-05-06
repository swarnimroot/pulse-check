"""Content-type triage classifier — Haiku via Anthropic.

One-pass triage that tags every mention as ``review``, ``deal``, or
``other``. Used as a gate before aspect tagging so deal-roundup posts do
not inflate aspect aggregates (the contamination flagged in session 5).

Mention-scoped (no product context): a post is one content type
regardless of which products it references. Cache key: ``(mention_text,
PROMPT_VERSION, model, temperature)``.

Implements the same ``JsonGenerator`` duck-type contract as the aspect
classifier — Haiku/Sonnet via ``AnthropicClient`` and Qwen via
``OllamaClient`` are both compatible callers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmParseError, LlmResponse, call_with_cache
from pulse_check.storage.enums import ContentType
from pulse_check.tagging.aspect_classifier import JsonGenerator

log = logging.getLogger(__name__)


PROMPT_VERSION = "content_type_classifier_v1"
# Default to Haiku per session 5 routing — cheap, fast, sufficient for triage.
_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
# Cap to keep prompts modest. Intent is decisive in the opening of a post —
# review/deal/other distinction is rarely buried halfway through.
_MAX_MENTION_CHARS = 3000


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContentTypePrediction:
    content_type: ContentType
    confidence: float | None
    rationale: str | None


# ---------------------------------------------------------------------------
# Prompt (version v1)
# ---------------------------------------------------------------------------


_ANCHOR_EXAMPLES: list[tuple[ContentType, str]] = [
    (
        ContentType.REVIEW,
        "Two weeks with the Aurora 16 — keys feel mushy after extended use, "
        "but the display is fantastic. Would I buy again? Probably yes for "
        "the price.",
    ),
    (
        ContentType.REVIEW,
        "Just got the Strix at $1899 on sale. Coming from a 2019 MBP the fan "
        "noise is brutal but performance is wild. Mixed feelings.",
    ),
    (
        ContentType.DEAL,
        "Best Cyber Monday gaming laptop deals: Alienware 16 Aurora at $899, "
        "ASUS Strix G16 at $1199, Lenovo Legion 7i at $1399. All-time lows!",
    ),
    (
        ContentType.DEAL,
        "[$899] Alienware 16 Aurora — Best Buy weekly deal. Stack with 5% "
        "credit card cashback for $854.",
    ),
    (
        ContentType.OTHER,
        "Does the Aurora 16 support Thunderbolt 4? Spec sheet is unclear "
        "whether it's full TB or just USB4.",
    ),
    (
        ContentType.OTHER,
        "Looking for laptop recommendations under $1500. Video editing and "
        "some light gaming. Suggestions?",
    ),
]


_PROMPT_TEMPLATE = """You are a triage classifier for product-listening posts \
about gaming laptops. Read one mention and pick exactly one content type.

CONTENT TYPES:
- review: first-person ownership, evaluation, comparison, or critique of a \
product. May mention price/deals as context but the substance is product \
experience.
- deal: a price/promotion announcement, deal aggregator post, or shopping \
listicle. No substantive first-person evaluation. May list multiple SKUs.
- other: anything else — a question about specs, news article, off-topic \
discussion, recommendation request, meme, etc.

TIE-BREAKING:
- Substantive first-person evaluation present → review (even if price is \
mentioned).
- Price/promotion is the dominant or only content → deal.
- Pure question, news, or off-topic → other.

ANCHOR EXAMPLES:
{anchors_block}

OUTPUT — JSON only, no prose, no markdown:
{{"content_type": "<review|deal|other>", "confidence": <0.0-1.0>, \
"rationale": "<one short sentence>"}}

MENTION:
\"\"\"
{mention_text}
\"\"\"
"""


def _format_anchors_block() -> str:
    return "\n".join(f'  {ct.value}: "{ex}"' for ct, ex in _ANCHOR_EXAMPLES)


def build_prompt(*, mention_text: str) -> str:
    """Render the v1 prompt for one mention. Mention text is clipped to
    ``_MAX_MENTION_CHARS`` to keep prompts modest — content-type intent is
    decisive in the opening of a post.
    """
    clipped = mention_text[:_MAX_MENTION_CHARS]
    return _PROMPT_TEMPLATE.format(
        anchors_block=_format_anchors_block(),
        mention_text=clipped,
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _coerce_content_type(value: Any) -> ContentType | None:
    if not isinstance(value, str):
        log.warning("content_type_classifier: content_type not a string: %r", value)
        return None
    try:
        return ContentType(value.strip().lower())
    except ValueError:
        log.warning("content_type_classifier: unknown content_type value: %r", value)
        return None


def _coerce_confidence(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        log.warning("content_type_classifier: confidence was a bool: %r", value)
        return None
    if isinstance(value, (int, float)):
        conf = float(value)
        if 0.0 <= conf <= 1.0:
            return conf
        log.warning("content_type_classifier: confidence out of range: %r", conf)
        return None
    log.warning("content_type_classifier: confidence not numeric: %r", value)
    return None


def _coerce_rationale(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    log.warning("content_type_classifier: rationale not a string: %r", value)
    return None


def parse_response(parsed: Any) -> ContentTypePrediction | None:
    """Turn a parsed JSON payload into a ``ContentTypePrediction``.

    Returns ``None`` if the content_type value is missing / invalid (the
    caller should drop the row in that case). Raises ``LlmParseError`` only
    on top-level shape issues.
    """
    if not isinstance(parsed, dict):
        msg = f"expected JSON object, got {type(parsed).__name__}"
        raise LlmParseError(msg)

    content_type = _coerce_content_type(parsed.get("content_type"))
    if content_type is None:
        return None

    return ContentTypePrediction(
        content_type=content_type,
        confidence=_coerce_confidence(parsed.get("confidence")),
        rationale=_coerce_rationale(parsed.get("rationale")),
    )


# ---------------------------------------------------------------------------
# Classifier wrapper
# ---------------------------------------------------------------------------


class ContentTypeClassifier:
    """Cache-aware wrapper around a JSON-generating LLM client.

    Carries the prompt/model/temperature so callers (batch runner, CLI)
    only pass the per-mention text.
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
        mention_text: str,
    ) -> ContentTypePrediction | None:
        """Return a content-type prediction for one mention, or ``None`` if
        the model returned an unparseable content_type value.
        """
        clipped = mention_text[:_MAX_MENTION_CHARS]
        input_payload = {"mention_text": clipped}

        def _compute() -> LlmResponse:
            prompt = build_prompt(mention_text=mention_text)
            return self._client.generate_json(
                model=self._model,
                prompt=prompt,
                temperature=self._temperature,
            )

        response = call_with_cache(
            session,
            task="content_type_classification",
            input_payload=input_payload,
            prompt_version=self._prompt_version,
            model=self._model,
            temperature=self._temperature,
            compute=_compute,
        )
        return parse_response(response.parsed_output)
