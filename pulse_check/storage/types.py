"""Custom SQLAlchemy types for portability between SQLite and Postgres.

SQLite's driver returns naive datetimes from `DateTime(timezone=True)` columns
because the backend has no native tz support. `UtcDateTime` normalizes this:
on bind it converts tz-aware input to UTC, on load it re-attaches UTC tzinfo
when the driver drops it. Postgres (TIMESTAMPTZ) returns tz-aware natively and
this decorator is a no-op there.

`impl = DateTime` means emitted DDL is unchanged — the Alembic migration is
the same regardless of whether the model uses `DateTime(timezone=True)` or
`UtcDateTime()`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator


class UtcDateTime(TypeDecorator[datetime]):
    """Timezone-aware DateTime that always round-trips as UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("UtcDateTime requires a timezone-aware datetime; got naive")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
