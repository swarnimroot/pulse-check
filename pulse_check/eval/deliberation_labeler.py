"""Sonnet labeler for the ``deliberation_v1`` gold set.

Wraps the production ``deliberation_classifier`` prompt with Sonnet as the
oracle generator. ``build_prompt`` and ``parse_response`` are imported from
the classifier so labels share the production output contract verbatim —
divergence would defeat the gold set's purpose.

The labeler exists only to namespace the Sonnet call under a separate
``task`` + ``prompt_version`` in the LLM cache:

- ``task='deliberation_labeling'`` (vs classifier's ``deliberation_tagging``)
- ``PROMPT_VERSION='deliberation_labeling_v2'``

so labels and predictions occupy disjoint cache rows. Either side can be
re-run without invalidating the other, and operator review pass can iterate
on the labeling prompt (with a version bump) without forcing a full
classifier re-tag.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pulse_check.llm_cache import LlmResponse, call_with_cache
from pulse_check.tagging.aspect_classifier import ProductContext
from pulse_check.tagging.deliberation_classifier import (
    DeliberationPrediction,
    DeliberationThread,
    JsonGenerator,
    build_prompt,
    parse_response,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


PROMPT_VERSION = "deliberation_labeling_v2"
_DEFAULT_MODEL = "claude-sonnet-4-6"


class DeliberationLabeler:
    """Cache-aware Sonnet wrapper that emits one gold-set label per thread.

    Output schema is identical to :class:`DeliberationClassifier` — both
    return :class:`DeliberationPrediction`. The labeler differs only in the
    cache namespace.
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

    def label(
        self,
        session: Session,
        *,
        thread: DeliberationThread,
        products: tuple[ProductContext, ...],
    ) -> DeliberationPrediction:
        """Return a Sonnet-generated gold-set label for one thread.

        Cache key matches the classifier's discipline: hashed over the thread
        content fields + sorted ``product_ids`` + module constants.
        ``thread_id`` and per-product ``display_name`` are not in the key.
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
            task="deliberation_labeling",
            input_payload=input_payload,
            prompt_version=self._prompt_version,
            model=self._model,
            temperature=self._temperature,
            compute=_compute,
        )
        return parse_response(response.parsed_output, products=products)
