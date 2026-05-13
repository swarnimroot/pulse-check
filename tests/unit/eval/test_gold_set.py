"""Gold-set sampling + Sonnet labeling + JSONL IO tests.

Coverage priorities:
- Stratified sampling hits every source bucket, respects the total, and is
  deterministic for a given seed
- Sampling draws PRIMARY attributions only (secondary ones are ignored)
- Sampling returns [] on empty input
- label_with_sonnet: returns entries with parsed labels; caches second call
- JSONL round-trip preserves all fields incl. operator states
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from pulse_check.eval.gold_set import (
    GoldSetEntry,
    SampledAttribution,
    label_with_sonnet,
    read_jsonl,
    sample_attributions_stratified,
    write_jsonl,
)
from pulse_check.storage.enums import (
    AttributionMethod,
    AttributionType,
    ContentType,
    SourceType,
)
from pulse_check.storage.models import (
    ContentTypeTag,
    LlmCache,
    Mention,
    MentionAttribution,
    Product,
)
from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.tagging.aspect_classifier import PROMPT_VERSION

_SONNET_MODEL = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_corpus(
    session: Session,
    *,
    per_source: int,
    products: list[tuple[str, str]],
) -> None:
    """Seed `per_source` primary attributions for each source type, per product."""
    for product_id, display_name in products:
        session.add(
            Product(
                product_id=product_id,
                display_name=display_name,
                brand=product_id.split("_")[0],
            )
        )

    counter = 0
    for source_type in SourceType:
        for product_id, _ in products:
            for i in range(per_source):
                mention_id = f"{source_type.value}-{product_id}-{i}"
                session.add(
                    Mention(
                        mention_id=mention_id,
                        source_type=source_type,
                        source_url=f"https://example.com/{mention_id}",
                        raw_text=f"text {counter} about {product_id}",
                        metadata_={},
                    )
                )
                session.add(
                    MentionAttribution(
                        mention_id=mention_id,
                        product_id=product_id,
                        attribution_type=AttributionType.PRIMARY,
                        attribution_method=AttributionMethod.REGEX,
                    )
                )
                counter += 1
    session.flush()


class _FakeBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeBlock(text)]


def _canned_sonnet_sdk(
    response_body: dict[str, Any] | None = None,
) -> MagicMock:
    sdk = MagicMock()
    body = response_body or {"tags": []}
    sdk.messages.create.return_value = _FakeResponse(json.dumps(body))
    return sdk


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def test_sample_empty_corpus_returns_empty(session: Session) -> None:
    rng = random.Random(0)
    samples = sample_attributions_stratified(session, product_ids=["aw16"], total=10, rng=rng)
    assert samples == []


def test_sample_empty_total_returns_empty(session: Session) -> None:
    _make_corpus(session, per_source=2, products=[("aw16", "Alienware 16 Aurora")])
    rng = random.Random(0)
    assert sample_attributions_stratified(session, product_ids=["aw16"], total=0, rng=rng) == []


def test_sample_empty_product_ids_returns_empty(session: Session) -> None:
    _make_corpus(session, per_source=2, products=[("aw16", "Alienware 16 Aurora")])
    rng = random.Random(0)
    assert sample_attributions_stratified(session, product_ids=[], total=10, rng=rng) == []


def test_sample_stratified_distributes_across_source_buckets(session: Session) -> None:
    # 2 products × 6 source types × 5 mentions = 60 primary attributions.
    _make_corpus(
        session,
        per_source=5,
        products=[("aw16", "Alienware 16 Aurora"), ("strix_g16", "ROG Strix G16")],
    )
    rng = random.Random(42)
    samples = sample_attributions_stratified(
        session, product_ids=["aw16", "strix_g16"], total=12, rng=rng
    )
    # 12 // 6 buckets = 2 per bucket
    assert len(samples) == 12
    by_source: dict[SourceType, int] = {}
    for s in samples:
        by_source[s.source_type] = by_source.get(s.source_type, 0) + 1
    assert all(count == 2 for count in by_source.values())
    assert set(by_source.keys()) == set(SourceType)


def test_sample_distributes_remainder_in_source_order(session: Session) -> None:
    # 6 buckets, total=8 → 1 per bucket + 2 remainder → 2 buckets get 2.
    _make_corpus(session, per_source=5, products=[("aw16", "Alienware 16 Aurora")])
    rng = random.Random(42)
    samples = sample_attributions_stratified(session, product_ids=["aw16"], total=8, rng=rng)
    assert len(samples) == 8
    counts: dict[SourceType, int] = {src: 0 for src in SourceType}
    for s in samples:
        counts[s.source_type] += 1
    # Exactly 2 buckets get 2, rest get 1.
    assert sorted(counts.values()) == [1, 1, 1, 1, 2, 2]
    # Remainder goes to the first two source-values alphabetically.
    sorted_sources = sorted(SourceType, key=lambda s: s.value)
    assert counts[sorted_sources[0]] == 2
    assert counts[sorted_sources[1]] == 2


def test_sample_ignores_secondary_attributions(session: Session) -> None:
    _make_corpus(session, per_source=2, products=[("aw16", "Alienware 16 Aurora")])
    # Add a secondary attribution pointing at a different product.
    session.add(Product(product_id="strix_g16", display_name="ROG Strix G16", brand="asus"))
    session.add(
        MentionAttribution(
            mention_id="reddit_post-aw16-0",
            product_id="strix_g16",
            attribution_type=AttributionType.SECONDARY,
            attribution_method=AttributionMethod.REGEX,
        )
    )
    session.flush()

    rng = random.Random(0)
    samples = sample_attributions_stratified(
        session, product_ids=["aw16", "strix_g16"], total=100, rng=rng
    )
    # Every sample is a primary attribution; none target strix_g16 because strix
    # has no primary attributions.
    assert all(s.product_id == "aw16" for s in samples)


def test_sample_is_deterministic_with_same_seed(session: Session) -> None:
    _make_corpus(session, per_source=4, products=[("aw16", "Alienware 16 Aurora")])
    s1 = sample_attributions_stratified(
        session, product_ids=["aw16"], total=6, rng=random.Random(7)
    )
    s2 = sample_attributions_stratified(
        session, product_ids=["aw16"], total=6, rng=random.Random(7)
    )
    assert [s.mention_id for s in s1] == [s.mention_id for s in s2]


def test_sample_excludes_filtered_content_types(session: Session) -> None:
    """exclude_content_types drops matching ContentTypeTag rows before stratification.

    Mentions without a ContentTypeTag row are kept (un-classified != excluded).
    """
    _make_corpus(session, per_source=3, products=[("aw16", "Alienware 16 Aurora")])
    # Tag every mention_id ending in '-0' as deal; '-1' as review; '-2' left untagged.
    for source_type in SourceType:
        session.add(
            ContentTypeTag(
                mention_id=f"{source_type.value}-aw16-0",
                content_type=ContentType.DEAL,
                prompt_version="content_type_classifier_v1",
                model="claude-haiku-4-5-20251001",
                temperature=0.0,
            )
        )
        session.add(
            ContentTypeTag(
                mention_id=f"{source_type.value}-aw16-1",
                content_type=ContentType.REVIEW,
                prompt_version="content_type_classifier_v1",
                model="claude-haiku-4-5-20251001",
                temperature=0.0,
            )
        )
    session.flush()

    rng = random.Random(0)
    samples = sample_attributions_stratified(
        session,
        product_ids=["aw16"],
        total=100,
        rng=rng,
        exclude_content_types=[ContentType.DEAL],
    )
    # 6 deal mentions excluded; 12 remain (6 review + 6 untagged).
    sampled_ids = {s.mention_id for s in samples}
    assert len(sampled_ids) == 12
    assert not any(mid.endswith("-0") for mid in sampled_ids)


def test_sample_default_no_exclusion_preserves_existing_behavior(session: Session) -> None:
    """exclude_content_types=None (the default) MUST behave identically to the
    pre-patch sampler so existing callers aren't surprised."""
    _make_corpus(session, per_source=2, products=[("aw16", "Alienware 16 Aurora")])
    # Tag one mention deal; default sampler should still include it.
    session.add(
        ContentTypeTag(
            mention_id="reddit_post-aw16-0",
            content_type=ContentType.DEAL,
            prompt_version="content_type_classifier_v1",
            model="claude-haiku-4-5-20251001",
            temperature=0.0,
        )
    )
    session.flush()

    rng = random.Random(0)
    samples = sample_attributions_stratified(session, product_ids=["aw16"], total=100, rng=rng)
    sampled_ids = {s.mention_id for s in samples}
    assert "reddit_post-aw16-0" in sampled_ids


def test_sample_shortfall_when_bucket_too_thin(session: Session) -> None:
    # Only 1 attribution per source; asking for total=18 (3 per bucket).
    _make_corpus(session, per_source=1, products=[("aw16", "Alienware 16 Aurora")])
    rng = random.Random(0)
    samples = sample_attributions_stratified(session, product_ids=["aw16"], total=18, rng=rng)
    # Each bucket has 1; total = 6, not 18.
    assert len(samples) == 6


# ---------------------------------------------------------------------------
# Sonnet labeling
# ---------------------------------------------------------------------------


def _make_sample(mention_id: str = "m1") -> SampledAttribution:
    return SampledAttribution(
        mention_id=mention_id,
        product_id="aw16",
        mention_text=f"the fans on this {mention_id} thing are jet engines",
        source_type=SourceType.REDDIT_POST,
        product_display_name="Alienware 16 Aurora",
    )


def test_label_with_sonnet_parses_labels_into_entries(session: Session) -> None:
    sdk = _canned_sonnet_sdk(
        {"tags": [{"aspect": "thermals", "polarity": "negative", "intensity": "high"}]}
    )
    client = AnthropicClient(sdk=sdk)

    entries = label_with_sonnet(
        session,
        samples=[_make_sample()],
        client=client,
        model=_SONNET_MODEL,
    )
    session.commit()

    assert len(entries) == 1
    entry = entries[0]
    assert entry.mention_id == "m1"
    assert entry.sonnet_labels == [
        {"aspect": "thermals", "polarity": "negative", "intensity": "high", "confidence": None}
    ]
    assert entry.operator_flag is None

    # Cache row landed under the Sonnet model + aspect prompt version.
    rows = session.query(LlmCache).all()
    assert len(rows) == 1
    assert rows[0].model == _SONNET_MODEL
    assert rows[0].prompt_version == PROMPT_VERSION


def test_label_with_sonnet_caches_repeated_samples(session: Session) -> None:
    sdk = _canned_sonnet_sdk({"tags": []})
    client = AnthropicClient(sdk=sdk)

    label_with_sonnet(session, samples=[_make_sample()], client=client, model=_SONNET_MODEL)
    session.commit()
    label_with_sonnet(session, samples=[_make_sample()], client=client, model=_SONNET_MODEL)

    # Second call is a cache hit — SDK called once total.
    assert sdk.messages.create.call_count == 1


def test_label_with_sonnet_distinct_samples_hit_sonnet_per_sample(session: Session) -> None:
    sdk = _canned_sonnet_sdk({"tags": []})
    client = AnthropicClient(sdk=sdk)

    samples = [_make_sample("m1"), _make_sample("m2"), _make_sample("m3")]
    entries = label_with_sonnet(session, samples=samples, client=client, model=_SONNET_MODEL)
    session.commit()

    assert len(entries) == 3
    # Cache is scoped per (mention_text, product_id). Texts differ via the
    # mention_id fixture, so all three miss.
    assert sdk.messages.create.call_count == 3


# ---------------------------------------------------------------------------
# JSONL IO
# ---------------------------------------------------------------------------


def test_jsonl_roundtrip_preserves_all_fields(tmp_path: Path) -> None:
    original = [
        GoldSetEntry(
            mention_id="m1",
            product_id="aw16",
            mention_text="fans jet engine",
            source_type=SourceType.REDDIT_POST,
            product_display_name="Alienware 16 Aurora",
            sonnet_labels=[
                {
                    "aspect": "thermals",
                    "polarity": "negative",
                    "intensity": "high",
                    "confidence": 0.9,
                }
            ],
            operator_flag="accept",
            operator_notes="clear thermals signal",
            operator_labels=None,
        ),
        GoldSetEntry(
            mention_id="m2",
            product_id="strix_g16",
            mention_text="240 Hz display is great",
            source_type=SourceType.BESTBUY_REVIEW,
            product_display_name="ROG Strix G16",
            sonnet_labels=[],
            operator_flag="corrected",
            operator_notes=None,
            operator_labels=[
                {
                    "aspect": "display",
                    "polarity": "positive",
                    "intensity": "medium",
                    "confidence": 0.85,
                }
            ],
        ),
    ]
    path = tmp_path / "gold.jsonl"
    write_jsonl(original, path)

    loaded = read_jsonl(path)
    assert loaded == original


def test_read_jsonl_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "gold.jsonl"
    entry_json = json.dumps(
        {
            "mention_id": "m1",
            "product_id": "aw16",
            "mention_text": "text",
            "source_type": "reddit_post",
            "product_display_name": "AW16",
            "sonnet_labels": [],
        }
    )
    path.write_text(f"\n{entry_json}\n\n", encoding="utf-8")
    entries = read_jsonl(path)
    assert len(entries) == 1
    assert entries[0].mention_id == "m1"
    assert entries[0].operator_flag is None


def test_read_jsonl_tolerates_missing_optional_fields(tmp_path: Path) -> None:
    path = tmp_path / "gold.jsonl"
    minimal = {
        "mention_id": "m1",
        "product_id": "aw16",
        "mention_text": "x",
        "source_type": "article",
        "product_display_name": "AW16",
        "sonnet_labels": [],
    }
    path.write_text(json.dumps(minimal) + "\n", encoding="utf-8")
    entries = read_jsonl(path)
    assert entries[0].operator_flag is None
    assert entries[0].operator_labels is None
    assert entries[0].operator_notes is None
