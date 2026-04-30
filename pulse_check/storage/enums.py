"""Enumerations used in the SQLAlchemy schema and throughout the pipeline.

Values are string-valued so they round-trip cleanly through SQLite CHECK constraints,
Postgres (via future `native_enum=True`), and JSON payloads.
"""

from __future__ import annotations

import enum


class SourceType(enum.StrEnum):
    REDDIT_POST = "reddit_post"
    REDDIT_COMMENT = "reddit_comment"
    BESTBUY_REVIEW = "bestbuy_review"
    AMAZON_REVIEW = "amazon_review"
    YOUTUBE_CHUNK = "youtube_chunk"
    ARTICLE = "article"


class AttributionType(enum.StrEnum):
    PRIMARY = "primary"
    SECONDARY = "secondary"


class AttributionMethod(enum.StrEnum):
    REGEX = "regex"
    URL = "url"


class Polarity(enum.StrEnum):
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"


class Intensity(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Aspect(enum.StrEnum):
    """11-aspect taxonomy v0 (PRD §4.1)."""

    THERMALS = "thermals"
    PERFORMANCE = "performance"
    KEYBOARD = "keyboard"
    DISPLAY = "display"
    BATTERY = "battery"
    BUILD_QUALITY = "build_quality"
    SOFTWARE_EXPERIENCE = "software_experience"
    PRICE_VALUE = "price_value"
    SUPPORT_WARRANTY = "support_warranty"
    AESTHETICS = "aesthetics"
    PORTABILITY = "portability"


class ReasonBucket(enum.StrEnum):
    """A2 reason bucket taxonomy — the 11 aspects plus 4 extras (ARCHITECTURE §3.2)."""

    THERMALS = "thermals"
    PERFORMANCE = "performance"
    KEYBOARD = "keyboard"
    DISPLAY = "display"
    BATTERY = "battery"
    BUILD_QUALITY = "build_quality"
    SOFTWARE_EXPERIENCE = "software_experience"
    PRICE_VALUE = "price_value"
    SUPPORT_WARRANTY = "support_warranty"
    AESTHETICS = "aesthetics"
    PORTABILITY = "portability"
    BRAND_LOYALTY = "brand_loyalty"
    VALUE_DEAL = "value_deal"
    SUPPORT_REPUTATION = "support_reputation"
    PRIOR_OWNERSHIP = "prior_ownership"


class Addressability(enum.StrEnum):
    MESSAGING = "messaging"
    SOFTWARE = "software"
    HARDWARE = "hardware"
    PRICING = "pricing"
    MIXED = "mixed"


class ScopeType(enum.StrEnum):
    ASPECT_1_SKU = "aspect_1_sku"
    ASPECT_2_PAIR = "aspect_2_pair"
