"""Sonnet labeler for the ``reason_tagging_v1`` gold set.

Wraps the production ``reason_tagger`` prompt with Sonnet as the oracle.
``build_prompt`` and ``parse_response`` are imported from the production
tagger so labels share its output contract verbatim — divergence would
defeat the gold set's purpose.

The labeler exists only to namespace the Sonnet call under a separate
``task`` + ``prompt_version`` in the LLM cache:

- ``task='reason_labeling'`` (vs tagger's ``reason_tagging``)
- ``PROMPT_VERSION='reason_labeling_v1'``

so labels and tags occupy disjoint cache rows. Either side can be re-run
without invalidating the other, and operator review pass can iterate on the
labeling prompt (with a version bump) without forcing a full re-tag.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pulse_check.llm_cache import LlmResponse, call_with_cache
from pulse_check.tagging.reason_tagger import (
    JsonGenerator,
    ReasonPrediction,
    ThreadContext,
    build_prompt,
    parse_response,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


PROMPT_VERSION = "reason_labeling_v1"
_DEFAULT_MODEL = "claude-sonnet-4-6"


class ReasonLabeler:
    """Cache-aware Sonnet wrapper that emits gold-set reason labels per comment.

    Output schema is identical to :class:`ReasonTagger` — both return
    ``list[ReasonPrediction]``. The labeler differs only in the cache
    namespace.
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
        comment_text: str,
        context: ThreadContext,
    ) -> list[ReasonPrediction]:
        """Return Sonnet-generated reason labels for one ``(comment, context)``.

        Cache key matches the production tagger's discipline: hashed over
        ``comment_text`` + ``winning_product_id`` + ``op_post_text`` + sorted
        ``product_ids`` from ``products_discussed`` + module constants.
        Display-name strings are not in the key.
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
            task="reason_labeling",
            input_payload=input_payload,
            prompt_version=self._prompt_version,
            model=self._model,
            temperature=self._temperature,
            compute=_compute,
        )
        return parse_response(response.parsed_output)
