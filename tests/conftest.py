"""Pytest fixtures shared across the test tree.

- `engine`: in-memory SQLite engine with schema created via `Base.metadata.create_all`
  (not via Alembic — keeps unit tests fast; Alembic is verified separately in
  integration tests).
- `session`: function-scoped SQLAlchemy Session bound to the in-memory engine.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from pulse_check.storage.models import Base


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with factory() as s:
        yield s
