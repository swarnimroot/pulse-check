"""Aspect-tagging gold set — sampling, Sonnet labeling, JSONL IO.

Gold sets drive the classifier eval (Wave 2 TASKS §A1 / TESTING §6). The v1
format is a JSONL file where each line is one ``(mention, product)`` pair
plus Sonnet's aspect labels plus an optional operator review state.

Sampling is stratified across ``source_type`` buckets so the gold set isn't
dominated by whichever source happens to be most populous. Within a bucket
the sample is uniform random, seeded for reproducibility.

Sonnet labeling reuses the Qwen classifier's prompt (same task, same
taxonomy) so the gold labels sit on exactly the same label space Qwen is
being evaluated against. The call flows through ``call_with_cache`` so a
re-run against the same mentions is free after the first pass.

File layout::

    data/gold_sets/aspect_tagging_v1.jsonl     # one entry per line

Each entry::

    {
      "mention_id": ...,
      "product_id": ...,
      "mention_text": ...,
      "source_type": "reddit_post",
      "product_display_name": "Alienware 16 Aurora",
      "sonnet_labels": [{"aspect": ..., "polarity": ..., "intensity": ..., "confidence": ...}, ...],
      "operator_flag": "accept" | "flag" | "corrected" | null,
      "operator_notes": "optional free-text note" | null,
      "operator_labels": [...] | null    # present only when flag="corrected"
    }
"""

from __future__ import annotations

import json
import logging
import random
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.llm_cache import LlmResponse, call_with_cache
from pulse_check.storage.enums import AttributionType, SourceType
from pulse_check.storage.models import Mention, MentionAttribution, Product
from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.tagging.aspect_classifier import (
    PROMPT_VERSION as ASPECT_PROMPT_VERSION,
)
from pulse_check.tagging.aspect_classifier import (
    AspectPrediction,
    ProductContext,
    build_prompt,
    parse_response,
)

log = logging.getLogger(__name__)

OperatorFlag = Literal["accept", "flag", "corrected"]


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SampledAttribution:
    """One ``(mention, product)`` pair picked for gold labeling."""

    mention_id: str
    product_id: str
    mention_text: str
    source_type: SourceType
    product_display_name: str


@dataclass
class GoldSetEntry:
    """One row in the gold-set JSONL.

    ``sonnet_labels`` is Sonnet's verbatim labeling; canonical and unedited.
    The operator review CLI writes ``operator_flag`` / ``operator_notes`` /
    ``operator_labels`` as they spot-check. Only ``corrected`` sets
    ``operator_labels``.
    """

    mention_id: str
    product_id: str
    mention_text: str
    source_type: SourceType
    product_display_name: str
    sonnet_labels: list[dict[str, Any]]
    operator_flag: OperatorFlag | None = None
    operator_notes: str | None = None
    operator_labels: list[dict[str, Any]] | None = None


def prediction_to_dict(pred: AspectPrediction) -> dict[str, Any]:
    """Canonical JSON-serializable form of an ``AspectPrediction``."""
    return {
        "aspect": pred.aspect.value,
        "polarity": pred.polarity.value,
        "intensity": pred.intensity.value,
        "confidence": pred.confidence,
    }


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def sample_attributions_stratified(
    session: Session,
    *,
    product_ids: Iterable[str],
    total: int,
    rng: random.Random,
) -> list[SampledAttribution]:
    """Draw ``total`` primary-attribution rows, evenly across source types.

    Quota is ``total // buckets`` with the remainder distributed one-per-bucket
    in source-value order. A bucket whose pool is smaller than its quota
    contributes everything it has; the shortfall is not redistributed (keeps
    the math predictable — operator can bump ``total`` if a bucket is thin).

    Only PRIMARY attributions are sampled: the gold set measures A1 accuracy,
    which is "what does this mention say about the product it's primarily
    about." Secondary attributions are A2 territory (Wave 3).
    """
    product_set = {pid for pid in product_ids}
    if not product_set or total <= 0:
        return []

    rows: Sequence[tuple[MentionAttribution, Mention, Product]] = (
        session.execute(
            select(MentionAttribution, Mention, Product)
            .join(Mention, Mention.mention_id == MentionAttribution.mention_id)
            .join(Product, Product.product_id == MentionAttribution.product_id)
            .where(
                MentionAttribution.product_id.in_(product_set),
                MentionAttribution.attribution_type == AttributionType.PRIMARY,
            )
        )
        .tuples()
        .all()
    )

    by_source: dict[SourceType, list[tuple[MentionAttribution, Mention, Product]]] = defaultdict(
        list
    )
    for attr, mention, product in rows:
        by_source[mention.source_type].append((attr, mention, product))

    buckets = sorted(
        ((src, pool) for src, pool in by_source.items() if pool),
        key=lambda b: b[0].value,
    )
    if not buckets:
        return []

    per_bucket = total // len(buckets)
    remainder = total - per_bucket * len(buckets)

    samples: list[SampledAttribution] = []
    for idx, (_src, pool) in enumerate(buckets):
        take = min(per_bucket + (1 if idx < remainder else 0), len(pool))
        rng.shuffle(pool)
        for attr, mention, product in pool[:take]:
            samples.append(
                SampledAttribution(
                    mention_id=attr.mention_id,
                    product_id=attr.product_id,
                    mention_text=mention.raw_text,
                    source_type=mention.source_type,
                    product_display_name=product.display_name,
                )
            )
    return samples


# ---------------------------------------------------------------------------
# Sonnet labeling
# ---------------------------------------------------------------------------


def label_with_sonnet(
    session: Session,
    *,
    samples: Iterable[SampledAttribution],
    client: AnthropicClient,
    model: str,
) -> list[GoldSetEntry]:
    """Label each sample with Sonnet, routed through ``call_with_cache``.

    Cache key pins ``(mention_text, product_id, ASPECT_PROMPT_VERSION, model,
    0.0)``: re-running the same sample set is free after the first pass, and
    swapping to a new prompt version naturally reopens the budget without
    losing the audit trail of the earlier labels.
    """
    entries: list[GoldSetEntry] = []
    for sample in samples:
        entry = _label_one(session, sample=sample, client=client, model=model)
        entries.append(entry)
    return entries


def _label_one(
    session: Session,
    *,
    sample: SampledAttribution,
    client: AnthropicClient,
    model: str,
) -> GoldSetEntry:
    product = ProductContext(
        product_id=sample.product_id,
        display_name=sample.product_display_name,
    )
    input_payload = {
        "mention_text": sample.mention_text,
        "product_id": sample.product_id,
    }

    def _compute() -> LlmResponse:
        prompt = build_prompt(mention_text=sample.mention_text, product=product)
        return client.generate_json(model=model, prompt=prompt, temperature=0.0)

    response = call_with_cache(
        session,
        task="aspect_gold_label",
        input_payload=input_payload,
        prompt_version=ASPECT_PROMPT_VERSION,
        model=model,
        temperature=0.0,
        compute=_compute,
    )
    preds = parse_response(response.parsed_output)
    return GoldSetEntry(
        mention_id=sample.mention_id,
        product_id=sample.product_id,
        mention_text=sample.mention_text,
        source_type=sample.source_type,
        product_display_name=sample.product_display_name,
        sonnet_labels=[prediction_to_dict(p) for p in preds],
    )


# ---------------------------------------------------------------------------
# JSONL IO
# ---------------------------------------------------------------------------


def _entry_to_dict(entry: GoldSetEntry) -> dict[str, Any]:
    return {
        "mention_id": entry.mention_id,
        "product_id": entry.product_id,
        "mention_text": entry.mention_text,
        "source_type": entry.source_type.value,
        "product_display_name": entry.product_display_name,
        "sonnet_labels": entry.sonnet_labels,
        "operator_flag": entry.operator_flag,
        "operator_notes": entry.operator_notes,
        "operator_labels": entry.operator_labels,
    }


def _dict_to_entry(data: dict[str, Any]) -> GoldSetEntry:
    flag = data.get("operator_flag")
    if flag is not None and flag not in ("accept", "flag", "corrected"):
        msg = f"unknown operator_flag: {flag!r}"
        raise ValueError(msg)
    return GoldSetEntry(
        mention_id=data["mention_id"],
        product_id=data["product_id"],
        mention_text=data["mention_text"],
        source_type=SourceType(data["source_type"]),
        product_display_name=data["product_display_name"],
        sonnet_labels=list(data.get("sonnet_labels") or []),
        operator_flag=flag,
        operator_notes=data.get("operator_notes"),
        operator_labels=data.get("operator_labels"),
    )


def write_jsonl(entries: Iterable[GoldSetEntry], path: Path) -> None:
    """Write entries to ``path`` as UTF-8 JSONL, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(_entry_to_dict(entry), ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[GoldSetEntry]:
    """Read entries from a JSONL written by ``write_jsonl``. Skips blank lines."""
    entries: list[GoldSetEntry] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            entries.append(_dict_to_entry(json.loads(line)))
    return entries
