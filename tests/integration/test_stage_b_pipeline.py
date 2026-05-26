"""End-to-end regression test on the Stage B pipeline.

Seeds a small post-classifier corpus (1 product, 6 mentions, attributions
and aspect tags pre-populated — skipping the non-deterministic classifier
step), then runs ``aggregate_a1`` → ``synthesize_a1`` with the
LLM-coupled dedup + brief-writer stages stubbed. Asserts on aggregate
row shape, brief persistence, and citation-validator pass-through.

Catches regressions in:
- Aggregation arithmetic (sentiment formula, polarity_counts, mention_ids)
- Orchestrator wiring (aggregate dependency, allowed_pool construction,
  retry-on-fabricated branch)
- Citation-validator pass-through to the persisted narrative
- Brief schema persistence (scope_type, prompt_version, narrative JSON)

LLM calls are stubbed at the orchestrator's import sites — no LLM
budget, no cache dependency, no flakiness.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from pulse_check.aggregation.a1 import aggregate_a1
from pulse_check.storage.enums import (
    Aspect,
    AttributionMethod,
    AttributionType,
    Intensity,
    Polarity,
    ScopeType,
    SourceType,
)
from pulse_check.storage.models import (
    AggregateAspectSku,
    AspectTag,
    Brief,
    Mention,
    MentionAttribution,
    Product,
    Run,
)
from pulse_check.synthesis import orchestrator
from pulse_check.synthesis.anthropic_client import AnthropicClient
from pulse_check.synthesis.brief_writer import (
    BRIEF_PROMPT_VERSION,
    BRIEF_PROMPT_VERSION_STRICT,
)
from pulse_check.synthesis.contracts import BriefNarrative, BriefSection, Claim

_TAX = "v0"
_PROMPT = "aspect_classifier_v1"
_RUN = "run_integration"
_PRODUCT_ID = "alienware_aurora_16"
_NOW = datetime(2026, 5, 19, tzinfo=UTC)


def _seed_post_classifier_corpus(session: Session) -> None:
    """1 run · 1 product · 6 mentions · 6 PRIMARY attributions · 6 aspect
    tags on THERMALS (4 negative / 2 positive). Deterministic; no LLM."""
    session.add(
        Run(
            run_id=_RUN,
            config_snapshot={},
            taxonomy_version=_TAX,
            prompt_versions={},
        )
    )
    session.add(
        Product(
            product_id=_PRODUCT_ID,
            display_name="Alienware Aurora 16",
            brand="Alienware",
        )
    )
    pattern: list[tuple[str, Polarity, Intensity, int]] = [
        ("m1", Polarity.NEGATIVE, Intensity.HIGH, 5),
        ("m2", Polarity.NEGATIVE, Intensity.HIGH, 10),
        ("m3", Polarity.NEGATIVE, Intensity.MEDIUM, 15),
        ("m4", Polarity.NEGATIVE, Intensity.MEDIUM, 20),
        ("m5", Polarity.POSITIVE, Intensity.MEDIUM, 25),
        ("m6", Polarity.POSITIVE, Intensity.LOW, 30),
    ]
    for mention_id, polarity, intensity, days_old in pattern:
        session.add(
            Mention(
                mention_id=mention_id,
                source_type=SourceType.REDDIT_POST,
                source_url=f"https://example.com/{mention_id}",
                raw_text=f"text for {mention_id}",
                published_at=_NOW - timedelta(days=days_old),
                metadata_={},
            )
        )
        session.add(
            MentionAttribution(
                mention_id=mention_id,
                product_id=_PRODUCT_ID,
                attribution_type=AttributionType.PRIMARY,
                attribution_method=AttributionMethod.REGEX,
            )
        )
        session.add(
            AspectTag(
                mention_id=mention_id,
                product_id=_PRODUCT_ID,
                aspect=Aspect.THERMALS,
                polarity=polarity,
                intensity=intensity,
                classifier_confidence=0.9,
                taxonomy_version=_TAX,
                prompt_version=_PROMPT,
                model="qwen2.5:7b-q4_K_M",
                temperature=0.0,
            )
        )
    session.flush()


def _stub_narrative(cited_mention_ids: list[str]) -> BriefNarrative:
    """Minimal valid BriefNarrative citing IDs known to be in the pool."""
    return BriefNarrative(
        brief_title="Alienware Aurora 16 — thermals are the headline",
        sections=[
            BriefSection(
                heading="High-confidence weaknesses",
                claims=[
                    Claim(
                        header="Sustained thermals",
                        claim_text=(
                            "Users report thermals as the dominant pain "
                            "point on this product."
                        ),
                        cited_mention_ids=cited_mention_ids,
                    )
                ],
            )
        ],
    )


def test_aggregate_then_synthesize_persists_valid_brief(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_post_classifier_corpus(session)

    stats = aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=[_PRODUCT_ID],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    assert stats.groups_seen == 1
    assert stats.aggregates_upserted == 1
    assert stats.mentions_contributing == 6

    aggregate = (
        session.query(AggregateAspectSku)
        .filter_by(run_id=_RUN, product_id=_PRODUCT_ID)
        .one()
    )
    assert aggregate.aspect == Aspect.THERMALS
    assert aggregate.total_mentions == 6
    assert aggregate.polarity_counts["negative"] == 4
    assert aggregate.polarity_counts["positive"] == 2
    assert aggregate.net_sentiment == pytest.approx(-2 / 6)
    assert set(aggregate.mention_ids) == {"m1", "m2", "m3", "m4", "m5", "m6"}

    captured: dict[str, int] = {"dedup": 0, "writer": 0}

    def _stub_dedup(
        session_: Session, mentions: list[Mention], **kwargs: Any
    ) -> dict[str, str]:
        captured["dedup"] += 1
        return {}

    def _stub_writer(
        session_: Session, *, client: Any, product: Product,
        aggregates: dict[Aspect, AggregateAspectSku],
        selections: dict[Aspect, Any], prompt_version: str,
    ) -> BriefNarrative:
        captured["writer"] += 1
        return _stub_narrative(cited_mention_ids=["m1", "m2", "m3"])

    monkeypatch.setattr(orchestrator, "cluster_near_duplicates", _stub_dedup)
    monkeypatch.setattr(orchestrator, "write_a1_brief", _stub_writer)

    brief = orchestrator.synthesize_a1(
        session,
        client=MagicMock(spec=AnthropicClient),  # never invoked by the stubs
        run_id=_RUN,
        product_id=_PRODUCT_ID,
    )
    session.commit()

    assert captured["dedup"] == 1
    assert captured["writer"] == 1  # no retry-on-fabricated triggered

    persisted = session.get(Brief, brief.brief_id)
    assert persisted is not None
    assert persisted.scope_type == ScopeType.ASPECT_1_SKU
    assert persisted.scope_id == _PRODUCT_ID
    assert persisted.run_id == _RUN
    assert persisted.prompt_version == BRIEF_PROMPT_VERSION
    assert persisted.model == "claude-sonnet-4-6"

    narrative = persisted.narrative
    assert narrative["brief_title"].startswith("Alienware Aurora 16")
    assert len(narrative["sections"]) == 1
    assert narrative["sections"][0]["claims"][0]["cited_mention_ids"] == [
        "m1", "m2", "m3",
    ]

    issues = narrative["flagged_citation_issues"]
    assert issues["fabricated_ids"] == []
    assert issues["out_of_context_ids"] == []
    assert issues["empty_claims"] == []
    assert issues["is_valid"] is True


def test_aggregate_excludes_tombstoned_mentions(session: Session) -> None:
    """A tombstoned mention is dropped from polarity counts, total_mentions
    and ``mention_ids`` — its aspect tag still exists in the DB, but the
    aggregator stops surfacing it once the URL goes dead."""
    _seed_post_classifier_corpus(session)

    # Tombstone two of the four negatives. Expected effect on the
    # THERMALS aggregate: 6 → 4 mentions, polarity_counts {neg: 4 → 2,
    # pos: 2}, net_sentiment 0 (= (2 - 2) / 4).
    for dead_id in ("m1", "m2"):
        dead = session.get(Mention, dead_id)
        assert dead is not None
        dead.tombstoned_at = _NOW
        dead.tombstone_reason = "http_404"
    session.flush()

    stats = aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=[_PRODUCT_ID],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    assert stats.aggregates_upserted == 1
    assert stats.mentions_contributing == 4

    aggregate = (
        session.query(AggregateAspectSku)
        .filter_by(run_id=_RUN, product_id=_PRODUCT_ID)
        .one()
    )
    assert aggregate.total_mentions == 4
    assert aggregate.polarity_counts["negative"] == 2
    assert aggregate.polarity_counts["positive"] == 2
    assert aggregate.net_sentiment == pytest.approx(0.0)
    assert set(aggregate.mention_ids) == {"m3", "m4", "m5", "m6"}


def test_synthesize_retries_brief_on_fabricated_citation(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second writer call uses the `_strict` prompt version after the first
    call cites a fabricated mention ID."""
    _seed_post_classifier_corpus(session)
    aggregate_a1(
        session,
        run_id=_RUN,
        product_ids=[_PRODUCT_ID],
        taxonomy_version=_TAX,
        prompt_version=_PROMPT,
        now=_NOW,
    )
    session.commit()

    monkeypatch.setattr(
        orchestrator, "cluster_near_duplicates",
        lambda *_args, **_kwargs: {},
    )

    writer_prompt_versions: list[str] = []

    def _stub_writer(
        session_: Session, *, client: Any, product: Product,
        aggregates: dict[Aspect, AggregateAspectSku],
        selections: dict[Aspect, Any], prompt_version: str,
    ) -> BriefNarrative:
        writer_prompt_versions.append(prompt_version)
        if prompt_version == BRIEF_PROMPT_VERSION:
            # First call: cite a fabricated mention ID (not in the DB).
            return _stub_narrative(cited_mention_ids=["fake_mention_999"])
        # Retry under _strict: cite real IDs.
        return _stub_narrative(cited_mention_ids=["m1", "m2"])

    monkeypatch.setattr(orchestrator, "write_a1_brief", _stub_writer)

    brief = orchestrator.synthesize_a1(
        session,
        client=MagicMock(spec=AnthropicClient),
        run_id=_RUN,
        product_id=_PRODUCT_ID,
    )
    session.commit()

    assert writer_prompt_versions == [BRIEF_PROMPT_VERSION, BRIEF_PROMPT_VERSION_STRICT]
    assert brief.prompt_version == BRIEF_PROMPT_VERSION_STRICT
    assert brief.narrative["flagged_citation_issues"]["fabricated_ids"] == []
