"""SQLAlchemy declarative models for the pulse-check analytical store.

Schema tracks ARCHITECTURE §3. SQLite-first, Postgres-compatible — every column
type, JSON column, and timezone-aware DateTime works in both dialects so a future
cloud migration is a connection-string change plus `alembic upgrade head`.

Notes:
- Enums are stored as strings with `native_enum=False` so SQLite uses CHECK
  constraints. Postgres will create real ENUM types if we flip the flag later.
- JSON columns use SQLAlchemy's portable `JSON` type.
- `Mention.metadata_` shadows the reserved `metadata` attribute on DeclarativeBase;
  the column name on disk is `metadata`.
- Aggregate tables carry `mention_ids` (provenance) as JSON arrays per the
  evidence-first principle (ARCHITECTURE §8).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from pulse_check.storage.enums import (
    Addressability,
    Aspect,
    AttributionMethod,
    AttributionType,
    ContentType,
    Intensity,
    Polarity,
    ReasonBucket,
    ScopeType,
    SourceType,
)
from pulse_check.storage.types import UtcDateTime


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _enum_values(obj: type) -> list[str]:
    """Return the string values of an Enum class (not the member names).

    SQLAlchemy's Enum defaults to storing member *names* (e.g. 'REDDIT_POST');
    we want the member *values* (e.g. 'reddit_post') per ARCHITECTURE §3.
    """
    return [e.value for e in obj]  # type: ignore[attr-defined]


class Base(DeclarativeBase):
    """Declarative base for all pulse-check ORM models."""


# ---------------------------------------------------------------------------
# Core tables (ARCHITECTURE §3.1)
# ---------------------------------------------------------------------------


class Product(Base):
    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    brand: Mapped[str] = mapped_column(String(128), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    attribution_patterns: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    urls: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now_utc, nullable=False)


class Run(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now_utc, nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    taxonomy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_versions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Mention(Base):
    __tablename__ = "mentions"

    mention_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, native_enum=False, length=32, values_callable=_enum_values),
        nullable=False,
    )
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    author: Mapped[str | None] = mapped_column(String(256), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str | None] = mapped_column(String(256), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON, default=dict, nullable=False
    )
    first_seen_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now_utc, nullable=False)
    tombstoned_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    tombstone_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)


class MentionAttribution(Base):
    __tablename__ = "mention_attributions"
    __table_args__ = (
        UniqueConstraint(
            "mention_id",
            "product_id",
            "attribution_type",
            name="uq_mention_attributions_key",
        ),
    )

    attribution_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mention_id: Mapped[str] = mapped_column(
        ForeignKey("mentions.mention_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attribution_type: Mapped[AttributionType] = mapped_column(
        SAEnum(AttributionType, native_enum=False, length=16, values_callable=_enum_values),
        nullable=False,
    )
    attribution_method: Mapped[AttributionMethod] = mapped_column(
        SAEnum(AttributionMethod, native_enum=False, length=16, values_callable=_enum_values),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# Tagging tables (ARCHITECTURE §3.2)
# ---------------------------------------------------------------------------


class AspectTag(Base):
    __tablename__ = "aspect_tags"
    __table_args__ = (
        UniqueConstraint(
            "mention_id",
            "product_id",
            "aspect",
            "taxonomy_version",
            "prompt_version",
            name="uq_aspect_tags_key",
        ),
    )

    tag_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mention_id: Mapped[str] = mapped_column(
        ForeignKey("mentions.mention_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    aspect: Mapped[Aspect] = mapped_column(
        SAEnum(Aspect, native_enum=False, length=32, values_callable=_enum_values), nullable=False
    )
    polarity: Mapped[Polarity] = mapped_column(
        SAEnum(Polarity, native_enum=False, length=16, values_callable=_enum_values), nullable=False
    )
    intensity: Mapped[Intensity] = mapped_column(
        SAEnum(Intensity, native_enum=False, length=16, values_callable=_enum_values),
        nullable=False,
    )
    classifier_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    taxonomy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now_utc, nullable=False)


class ContentTypeTag(Base):
    __tablename__ = "content_type_tags"
    __table_args__ = (
        UniqueConstraint(
            "mention_id",
            "prompt_version",
            name="uq_content_type_tags_key",
        ),
    )

    tag_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mention_id: Mapped[str] = mapped_column(
        ForeignKey("mentions.mention_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_type: Mapped[ContentType] = mapped_column(
        SAEnum(ContentType, native_enum=False, length=16, values_callable=_enum_values),
        nullable=False,
    )
    classifier_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now_utc, nullable=False)


class DeliberationTag(Base):
    __tablename__ = "deliberation_tags"

    tag_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_mention_id: Mapped[str] = mapped_column(
        ForeignKey("mentions.mention_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_deliberation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False)
    products_discussed: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    chosen_product_id: Mapped[str | None] = mapped_column(
        ForeignKey("products.product_id", ondelete="SET NULL"), nullable=True
    )
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now_utc, nullable=False)


class ReasonTag(Base):
    __tablename__ = "reason_tags"

    tag_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mention_id: Mapped[str] = mapped_column(
        ForeignKey("mentions.mention_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    thread_mention_id: Mapped[str] = mapped_column(
        ForeignKey("mentions.mention_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    winning_product_id: Mapped[str] = mapped_column(
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason_bucket: Mapped[ReasonBucket] = mapped_column(
        SAEnum(ReasonBucket, native_enum=False, length=32, values_callable=_enum_values),
        nullable=False,
    )
    polarity: Mapped[Polarity] = mapped_column(
        SAEnum(Polarity, native_enum=False, length=16, values_callable=_enum_values), nullable=False
    )
    intensity: Mapped[Intensity] = mapped_column(
        SAEnum(Intensity, native_enum=False, length=16, values_callable=_enum_values),
        nullable=False,
    )
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now_utc, nullable=False)


# ---------------------------------------------------------------------------
# Aggregate tables (ARCHITECTURE §3.3)
# ---------------------------------------------------------------------------


class AggregateAspectSku(Base):
    __tablename__ = "aggregates_aspect_sku"
    __table_args__ = (
        UniqueConstraint("run_id", "product_id", "aspect", name="uq_aggregates_aspect_sku_key"),
    )

    aggregate_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    aspect: Mapped[Aspect] = mapped_column(
        SAEnum(Aspect, native_enum=False, length=32, values_callable=_enum_values), nullable=False
    )
    total_mentions: Mapped[int] = mapped_column(Integer, nullable=False)
    polarity_counts: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    net_sentiment: Mapped[float] = mapped_column(Float, nullable=False)
    intensity_counts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    verified_share: Mapped[float] = mapped_column(Float, nullable=False)
    by_source: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    by_recency: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    mention_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now_utc, nullable=False)


class AggregatePairReason(Base):
    __tablename__ = "aggregates_pair_reason"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "pair_id",
            "winning_product_id",
            "reason_bucket",
            name="uq_aggregates_pair_reason_key",
        ),
    )

    aggregate_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False, index=True
    )
    pair_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    winning_product_id: Mapped[str] = mapped_column(
        ForeignKey("products.product_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason_bucket: Mapped[ReasonBucket] = mapped_column(
        SAEnum(ReasonBucket, native_enum=False, length=32, values_callable=_enum_values),
        nullable=False,
    )
    total_mentions: Mapped[int] = mapped_column(Integer, nullable=False)
    intensity_counts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    addressability: Mapped[Addressability] = mapped_column(
        SAEnum(Addressability, native_enum=False, length=16, values_callable=_enum_values),
        nullable=False,
    )
    addressability_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    representative_mention_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    mention_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now_utc, nullable=False)


class PairWinRate(Base):
    __tablename__ = "pair_win_rates"
    __table_args__ = (UniqueConstraint("run_id", "pair_id", name="uq_pair_win_rates_key"),)

    aggregate_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False, index=True
    )
    pair_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    product_a_id: Mapped[str] = mapped_column(
        ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False
    )
    product_b_id: Mapped[str] = mapped_column(
        ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False
    )
    total_resolved_threads: Mapped[int] = mapped_column(Integer, nullable=False)
    a_wins: Mapped[int] = mapped_column(Integer, nullable=False)
    b_wins: Mapped[int] = mapped_column(Integer, nullable=False)
    ties: Mapped[int] = mapped_column(Integer, nullable=False)
    thread_mention_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now_utc, nullable=False)


class Brief(Base):
    __tablename__ = "briefs"

    brief_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False, index=True
    )
    scope_type: Mapped[ScopeType] = mapped_column(
        SAEnum(ScopeType, native_enum=False, length=16, values_callable=_enum_values),
        nullable=False,
    )
    scope_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    narrative: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now_utc, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)


# ---------------------------------------------------------------------------
# LLM cache (ARCHITECTURE §3.4)
# ---------------------------------------------------------------------------


class LlmCache(Base):
    __tablename__ = "llm_cache"

    cache_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    raw_output: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_output: Mapped[Any] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=_now_utc, nullable=False)
