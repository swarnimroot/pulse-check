"""Aspect + polarity + intensity classifier — Qwen 7B via Ollama.

Implements the ``tag_mention_aspects`` contract (ARCHITECTURE §6.1):

    input:   (mention_text, product_context)
    output:  list[{aspect, polarity, intensity, confidence}]

The classifier is multi-label and may return an empty list for mentions that
discuss none of the 11 v0 aspects. Every call goes through ``call_with_cache``
keyed on ``(mention_text, product_id, PROMPT_VERSION, model, temperature)``
— editing the prompt or the anchor examples requires a ``PROMPT_VERSION``
bump so the cache invalidates cleanly while the old rows remain as an audit
trail (ARCHITECTURE §13 — "classifier prompt tweaked" row).

Taxonomy v0 is the 11-aspect PRD §4.1 list; see ``pulse_check.storage.enums.Aspect``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmParseError, LlmResponse, call_with_cache
from pulse_check.storage.enums import Aspect, Intensity, Polarity

log = logging.getLogger(__name__)


class JsonGenerator(Protocol):
    """Structural type for any client able to produce a JSON response.

    Both ``OllamaClient`` (Qwen) and ``AnthropicClient`` (Sonnet/Haiku)
    implement this signature, so the classifier accepts either via
    duck-typing — no inheritance required.
    """

    def generate_json(
        self,
        *,
        model: str,
        prompt: str,
        temperature: float = 0.0,
    ) -> LlmResponse: ...

PROMPT_VERSION = "aspect_classifier_v1"
TAXONOMY_VERSION = "v0"
_DEFAULT_MODEL = "qwen2.5:7b-q4_K_M"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProductContext:
    """Minimal product info the classifier needs to ground its tagging.

    ``product_id`` is included in the cache key so the same mention text
    attributed to two products tags independently. ``display_name`` appears
    in the prompt text so the model reads a real name rather than a slug.
    """

    product_id: str
    display_name: str


@dataclass(frozen=True)
class AspectPrediction:
    aspect: Aspect
    polarity: Polarity
    intensity: Intensity
    confidence: float | None


# ---------------------------------------------------------------------------
# Prompt (version v1)
# ---------------------------------------------------------------------------


_ASPECT_DEFS: dict[Aspect, str] = {
    Aspect.THERMALS: "cooling, fan noise, under-load temperature, throttling",
    Aspect.PERFORMANCE: "fps, CPU/GPU speed, stuttering, benchmarks",
    Aspect.KEYBOARD: "typing feel, key travel, layout, backlighting",
    Aspect.DISPLAY: "brightness, color, refresh rate, ghosting, panel quality",
    Aspect.BATTERY: "battery life, runtime unplugged, charging speed",
    Aspect.BUILD_QUALITY: "chassis flex, materials, hinge, durability, rattles",
    Aspect.SOFTWARE_EXPERIENCE: "bloatware, driver issues, control-center apps, Windows experience",
    Aspect.PRICE_VALUE: "cost vs. spec, value for money, deals, overpricing",
    Aspect.SUPPORT_WARRANTY: "RMA experience, customer service, warranty coverage",
    Aspect.AESTHETICS: "looks, design, RGB, visual restraint",
    Aspect.PORTABILITY: "weight, thickness, travel-friendliness",
}

# 2 anchors per aspect, hand-picked to span polarity and intensity. These are
# synthetic stand-ins for v1 — first scrape will surface real-language
# patterns; anchor set gets refined (→ v2) during Wave 2 eval iteration.
_ANCHOR_EXAMPLES: dict[Aspect, list[tuple[str, Polarity, Intensity]]] = {
    Aspect.THERMALS: [
        (
            "Temps hit 95C on the CPU during Cyberpunk. Fans are a jet engine.",
            Polarity.NEGATIVE,
            Intensity.HIGH,
        ),
        (
            "Fans ramp up under load but it stays around 85C, no throttling.",
            Polarity.NEUTRAL,
            Intensity.LOW,
        ),
    ],
    Aspect.PERFORMANCE: [
        (
            "4090 runs every AAA title at 120+ fps at 1440p. Monster.",
            Polarity.POSITIVE,
            Intensity.HIGH,
        ),
        (
            "Noticeable stutter in Hogwarts Legacy even at medium settings.",
            Polarity.NEGATIVE,
            Intensity.MEDIUM,
        ),
    ],
    Aspect.KEYBOARD: [
        (
            "Keys have decent travel but feel mushy after a week.",
            Polarity.NEGATIVE,
            Intensity.MEDIUM,
        ),
        (
            "Per-key RGB and the typing feel is honestly the best in class.",
            Polarity.POSITIVE,
            Intensity.HIGH,
        ),
    ],
    Aspect.DISPLAY: [
        (
            "Mini-LED panel is gorgeous — 1200 nits and zero blooming.",
            Polarity.POSITIVE,
            Intensity.HIGH,
        ),
        (
            "240 Hz but the colors look washed out out of the box.",
            Polarity.NEGATIVE,
            Intensity.MEDIUM,
        ),
    ],
    Aspect.BATTERY: [
        (
            "Got about 4 hours of light web browsing before it died.",
            Polarity.NEUTRAL,
            Intensity.LOW,
        ),
        (
            "Barely lasts 90 minutes unplugged. Unusable away from a desk.",
            Polarity.NEGATIVE,
            Intensity.HIGH,
        ),
    ],
    Aspect.BUILD_QUALITY: [
        (
            "Lid has noticeable flex and the hinge wobbles after six months.",
            Polarity.NEGATIVE,
            Intensity.MEDIUM,
        ),
        (
            "Aluminum chassis feels absolutely solid, no creaks.",
            Polarity.POSITIVE,
            Intensity.MEDIUM,
        ),
    ],
    Aspect.SOFTWARE_EXPERIENCE: [
        (
            "Command Center crashes every time I open the power profile menu.",
            Polarity.NEGATIVE,
            Intensity.HIGH,
        ),
        (
            "Pre-installed bloatware but easy to uninstall.",
            Polarity.NEGATIVE,
            Intensity.LOW,
        ),
    ],
    Aspect.PRICE_VALUE: [
        (
            "Overpriced by $400 for what you get vs. the Strix.",
            Polarity.NEGATIVE,
            Intensity.HIGH,
        ),
        (
            "Caught it on sale for $1899 — absolute steal.",
            Polarity.POSITIVE,
            Intensity.HIGH,
        ),
    ],
    Aspect.SUPPORT_WARRANTY: [
        (
            "Dell premium support replaced the motherboard in 3 days.",
            Polarity.POSITIVE,
            Intensity.HIGH,
        ),
        (
            "RMA took six weeks and I had to call three times.",
            Polarity.NEGATIVE,
            Intensity.HIGH,
        ),
    ],
    Aspect.AESTHETICS: [
        (
            "Love that they toned down the RGB — finally looks professional.",
            Polarity.POSITIVE,
            Intensity.MEDIUM,
        ),
        (
            "Bezels are chunky and the lid logo is too flashy for work.",
            Polarity.NEGATIVE,
            Intensity.MEDIUM,
        ),
    ],
    Aspect.PORTABILITY: [
        (
            "2.7 kg — carrying this in a backpack all day is brutal.",
            Polarity.NEGATIVE,
            Intensity.HIGH,
        ),
        (
            "Slim enough to slip into my bag alongside a 13-inch work laptop.",
            Polarity.POSITIVE,
            Intensity.MEDIUM,
        ),
    ],
}


def _format_anchor_line(text: str, polarity: Polarity, intensity: Intensity) -> str:
    return f'  - "{text}"  →  polarity={polarity.value}, intensity={intensity.value}'


def _format_aspects_block() -> str:
    return "\n".join(f"- {aspect.value}: {_ASPECT_DEFS[aspect]}" for aspect in Aspect)


def _format_anchors_block() -> str:
    lines: list[str] = []
    for aspect in Aspect:
        lines.append(f"{aspect.value}:")
        for text, pol, intn in _ANCHOR_EXAMPLES[aspect]:
            lines.append(_format_anchor_line(text, pol, intn))
    return "\n".join(lines)


_PROMPT_TEMPLATE = """You are a strict review-tagger for gaming laptops. You read one mention and \
identify which aspects it discusses, the polarity toward each, and the intensity of \
the language used. Multi-label is allowed. Empty output is valid — only tag aspects \
that are clearly discussed.

ASPECTS (use the exact value strings):
{aspects_block}

POLARITY (choose one per tag):
- negative: criticism, complaint, dislike, dysfunction
- neutral: observation without a strong lean
- positive: praise, approval, preference

INTENSITY (choose one per tag):
- low: passing mention, mild language
- medium: a clear opinion in normal language
- high: strong language, quantifiers, severity words ("unbearable", "amazing"), \
explicit comparisons

ANCHOR EXAMPLES:
{anchors_block}

OUTPUT — JSON only, no prose, no markdown:
{{"tags": [{{"aspect": "<aspect>", "polarity": "<polarity>", "intensity": "<intensity>", \
"confidence": <number between 0 and 1>}}]}}

If the mention discusses none of the listed aspects, output {{"tags": []}}.

MENTION (product: {product_display_name}):
\"\"\"
{mention_text}
\"\"\"
"""


def build_prompt(*, mention_text: str, product: ProductContext) -> str:
    """Render the v1 prompt for a single mention.

    Prompt string is deterministic — any change to wording, aspect definitions,
    or anchor examples must come with a ``PROMPT_VERSION`` bump so the cache
    invalidates.
    """
    return _PROMPT_TEMPLATE.format(
        aspects_block=_format_aspects_block(),
        anchors_block=_format_anchors_block(),
        product_display_name=product.display_name,
        mention_text=mention_text,
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def _coerce_enum(
    value: Any, enum_cls: type[Aspect] | type[Polarity] | type[Intensity], field: str
) -> Any:
    if not isinstance(value, str):
        log.warning("aspect_classifier: %s not a string: %r", field, value)
        return None
    try:
        return enum_cls(value.strip().lower())
    except ValueError:
        log.warning("aspect_classifier: unknown %s value: %r", field, value)
        return None


def _coerce_confidence(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        # bool is an int subclass; explicitly reject before the numeric branch.
        log.warning("aspect_classifier: confidence was a bool: %r", value)
        return None
    if isinstance(value, (int, float)):
        conf = float(value)
        if 0.0 <= conf <= 1.0:
            return conf
        log.warning("aspect_classifier: confidence out of range: %r", conf)
        return None
    log.warning("aspect_classifier: confidence not numeric: %r", value)
    return None


def parse_response(parsed: Any) -> list[AspectPrediction]:
    """Turn a parsed JSON payload into ``AspectPrediction``s; skip malformed tags.

    Raises ``LlmParseError`` on top-level shape issues (not a dict, missing
    ``tags``, or ``tags`` not a list). Individual tag entries with unknown
    aspect / polarity / intensity values are dropped with a warn-log so the
    classifier still returns a useful partial result rather than failing the
    whole batch on a single hallucinated label.
    """
    if not isinstance(parsed, dict):
        msg = f"expected JSON object, got {type(parsed).__name__}"
        raise LlmParseError(msg)

    tags = parsed.get("tags")
    if not isinstance(tags, list):
        msg = f"expected 'tags' to be a list, got {type(tags).__name__}"
        raise LlmParseError(msg)

    out: list[AspectPrediction] = []
    for raw in tags:
        if not isinstance(raw, dict):
            log.warning("aspect_classifier: tag entry not an object: %r", raw)
            continue
        aspect = _coerce_enum(raw.get("aspect"), Aspect, "aspect")
        polarity = _coerce_enum(raw.get("polarity"), Polarity, "polarity")
        intensity = _coerce_enum(raw.get("intensity"), Intensity, "intensity")
        if aspect is None or polarity is None or intensity is None:
            continue
        out.append(
            AspectPrediction(
                aspect=aspect,
                polarity=polarity,
                intensity=intensity,
                confidence=_coerce_confidence(raw.get("confidence")),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Classifier wrapper
# ---------------------------------------------------------------------------


class AspectClassifier:
    """Cache-aware wrapper around ``OllamaClient.generate_json``.

    Carries the prompt/model/temperature so callers (batch tagger, CLI drivers)
    only pass the per-mention inputs.
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
        product: ProductContext,
    ) -> list[AspectPrediction]:
        """Return aspect predictions for one ``(mention, product)`` pair.

        Cache key is hashed over ``mention_text`` + ``product_id`` + the module
        constants. Display name is only in the prompt text, not the key —
        renaming a product without changing its id doesn't re-tag.
        """
        input_payload = {
            "mention_text": mention_text,
            "product_id": product.product_id,
        }

        def _compute() -> LlmResponse:
            prompt = build_prompt(mention_text=mention_text, product=product)
            return self._client.generate_json(
                model=self._model,
                prompt=prompt,
                temperature=self._temperature,
            )

        response = call_with_cache(
            session,
            task="aspect_tagging",
            input_payload=input_payload,
            prompt_version=self._prompt_version,
            model=self._model,
            temperature=self._temperature,
            compute=_compute,
        )
        return parse_response(response.parsed_output)
