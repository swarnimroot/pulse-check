"""FastAPI dependencies.

`get_session` yields a SQLAlchemy session per request, transactional via
`session_scope()`. Tests override this dependency on the app to bind handlers
to an in-memory SQLite session bound to the same engine the test seeds.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from pulse_check.storage.session import session_scope


def get_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session
