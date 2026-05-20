"""Unit tests for the link verifier."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from pulse_check.storage.enums import SourceType
from pulse_check.storage.models import Mention
from pulse_check.verifiers.link_verifier import (
    verify_all_pending,
    verify_url,
)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _seed_mention(session: Session, mention_id: str, url: str) -> None:
    session.add(
        Mention(
            mention_id=mention_id,
            source_type=SourceType.REDDIT_POST,
            source_url=url,
            raw_text=f"text {mention_id}",
            metadata_={},
        )
    )


# --------------------------------------------------------------------------- #
# verify_url
# --------------------------------------------------------------------------- #


def test_verify_url_200_ok() -> None:
    with _client(lambda req: httpx.Response(200)) as c:
        result = verify_url(c, "https://example.com/p1")
    assert result.tombstone_reason is None
    assert result.note == "ok"


def test_verify_url_404_tombstones() -> None:
    with _client(lambda req: httpx.Response(404)) as c:
        result = verify_url(c, "https://example.com/p1")
    assert result.tombstone_reason == "http_404"
    assert result.note == "http_404"


def test_verify_url_410_tombstones() -> None:
    with _client(lambda req: httpx.Response(410)) as c:
        result = verify_url(c, "https://example.com/p1")
    assert result.tombstone_reason == "http_410"


def test_verify_url_403_left_alive() -> None:
    """Retailer bot-blocks are usually 403 — do NOT tombstone."""
    with _client(lambda req: httpx.Response(403)) as c:
        result = verify_url(c, "https://example.com/p1")
    assert result.tombstone_reason is None
    assert result.note == "http_403"


def test_verify_url_5xx_left_alive() -> None:
    with _client(lambda req: httpx.Response(503)) as c:
        result = verify_url(c, "https://example.com/p1")
    assert result.tombstone_reason is None
    assert result.note == "http_503"


def test_verify_url_405_falls_back_to_get() -> None:
    """HEAD blocked on some hosts; GET-stream fallback resolves it."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "HEAD":
            return httpx.Response(405)
        return httpx.Response(200)

    with _client(handler) as c:
        result = verify_url(c, "https://example.com/p1")
    assert result.tombstone_reason is None
    assert result.note == "ok"


def test_verify_url_dns_fail_tombstones() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        try:
            raise socket.gaierror("getaddrinfo failed")
        except socket.gaierror as cause:
            raise httpx.ConnectError("dns resolution failed") from cause

    with _client(handler) as c:
        result = verify_url(c, "https://no-such-host.example/")
    assert result.tombstone_reason == "dns_fail"
    assert result.note == "dns_fail"


def test_verify_url_conn_refused_tombstones() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        try:
            raise ConnectionRefusedError("connection refused")
        except ConnectionRefusedError as cause:
            raise httpx.ConnectError("connect failed") from cause

    with _client(handler) as c:
        result = verify_url(c, "https://example.com/p1")
    assert result.tombstone_reason == "conn_refused"


def test_verify_url_generic_conn_error_left_alive() -> None:
    """``ConnectError`` without a known socket cause is treated as transient."""

    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("opaque transport failure")

    with _client(handler) as c:
        result = verify_url(c, "https://example.com/p1")
    assert result.tombstone_reason is None
    assert result.note == "conn_error"


def test_verify_url_timeout_left_alive() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    with _client(handler) as c:
        result = verify_url(c, "https://example.com/p1")
    assert result.tombstone_reason is None
    assert result.note == "timeout"


def test_verify_url_follows_redirect_to_404() -> None:
    """Final destination after redirect chain decides the verdict."""
    visits: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        visits.append(str(req.url))
        if "/old" in str(req.url):
            return httpx.Response(301, headers={"Location": "https://example.com/new"})
        return httpx.Response(404)

    with _client(handler) as c:
        result = verify_url(c, "https://example.com/old")
    assert result.tombstone_reason == "http_404"
    assert len(visits) == 2  # redirect followed


# --------------------------------------------------------------------------- #
# verify_all_pending
# --------------------------------------------------------------------------- #


def test_verify_all_pending_writes_tombstoned_at(session: Session) -> None:
    _seed_mention(session, "m1", "https://alive.example/p")
    _seed_mention(session, "m2", "https://dead-404.example/p")
    _seed_mention(session, "m3", "https://dead-410.example/p")
    session.commit()

    def handler(req: httpx.Request) -> httpx.Response:
        u = str(req.url)
        if "dead-404" in u:
            return httpx.Response(404)
        if "dead-410" in u:
            return httpx.Response(410)
        return httpx.Response(200)

    with _client(handler) as c:
        stats = verify_all_pending(session, c, workers=1)

    assert stats.checked == 3
    assert stats.tombstoned == 2
    assert stats.alive == 1
    assert stats.by_reason == {"ok": 1, "http_404": 1, "http_410": 1}

    alive = session.get(Mention, "m1")
    dead_404 = session.get(Mention, "m2")
    dead_410 = session.get(Mention, "m3")
    assert alive is not None and alive.tombstoned_at is None
    assert dead_404 is not None and dead_404.tombstoned_at is not None
    assert dead_404.tombstone_reason == "http_404"
    assert dead_410 is not None and dead_410.tombstone_reason == "http_410"


def test_verify_all_pending_skips_already_tombstoned(session: Session) -> None:
    """Re-running verification shouldn't re-hit URLs that are already dead."""
    session.add(
        Mention(
            mention_id="m1",
            source_type=SourceType.REDDIT_POST,
            source_url="https://example.com/p1",
            raw_text="...",
            metadata_={},
            tombstoned_at=datetime(2026, 1, 1, tzinfo=UTC),
            tombstone_reason="http_404",
        )
    )
    _seed_mention(session, "m2", "https://example.com/p2")
    session.commit()

    seen_urls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen_urls.append(str(req.url))
        return httpx.Response(200)

    with _client(handler) as c:
        stats = verify_all_pending(session, c, workers=1)

    assert stats.checked == 1
    assert seen_urls == ["https://example.com/p2"]


def test_verify_all_pending_dry_run_does_not_persist(session: Session) -> None:
    _seed_mention(session, "m1", "https://example.com/dead")
    session.commit()

    with _client(lambda req: httpx.Response(404)) as c:
        stats = verify_all_pending(session, c, workers=1, dry_run=True)

    assert stats.tombstoned == 1
    mention = session.get(Mention, "m1")
    assert mention is not None
    assert mention.tombstoned_at is None  # dry_run preserved
    assert mention.tombstone_reason is None


def test_verify_all_pending_honors_limit(session: Session) -> None:
    for i in range(5):
        _seed_mention(session, f"m{i}", f"https://example.com/p{i}")
    session.commit()

    with _client(lambda req: httpx.Response(200)) as c:
        stats = verify_all_pending(session, c, workers=1, limit=2)

    assert stats.checked == 2


# --------------------------------------------------------------------------- #
# verify_all_pending — reddit throttle
# --------------------------------------------------------------------------- #


def test_verify_all_pending_serializes_reddit_calls(session: Session) -> None:
    """Reddit URLs flow through the per-domain lock one-at-a-time even when
    ``workers`` would otherwise let them overlap."""
    _seed_mention(session, "r1", "https://www.reddit.com/r/foo/1")
    _seed_mention(session, "r2", "https://old.reddit.com/r/foo/2")
    _seed_mention(session, "r3", "https://m.reddit.com/r/foo/3")
    session.commit()

    state = {"current": 0, "max": 0}
    state_lock = threading.Lock()

    def handler(req: httpx.Request) -> httpx.Response:
        with state_lock:
            state["current"] += 1
            state["max"] = max(state["max"], state["current"])
        time.sleep(0.02)  # window for unthrottled overlap to manifest
        with state_lock:
            state["current"] -= 1
        return httpx.Response(200)

    with _client(handler) as c:
        verify_all_pending(
            session,
            c,
            workers=4,
            reddit_throttle_sec=0.0,
            sleep_fn=lambda _: None,
        )

    assert state["max"] == 1


def test_verify_all_pending_sleeps_only_for_reddit(session: Session) -> None:
    """``sleep_fn`` fires once per reddit URL; non-reddit URLs skip it."""
    _seed_mention(session, "r1", "https://www.reddit.com/r/foo/1")
    _seed_mention(session, "r2", "https://old.reddit.com/r/foo/2")
    _seed_mention(session, "e1", "https://example.com/p1")
    session.commit()

    sleeps: list[float] = []

    with _client(lambda req: httpx.Response(200)) as c:
        verify_all_pending(
            session,
            c,
            workers=1,
            reddit_throttle_sec=1.5,
            sleep_fn=sleeps.append,
        )

    assert sleeps == [1.5, 1.5]


def test_verify_all_pending_throttles_reddit_subdomain_variants(
    session: Session,
) -> None:
    """Match ``reddit.com`` and its subdomains; sibling hosts skip the throttle."""
    _seed_mention(session, "m1", "https://www.reddit.com/r/foo/1")
    _seed_mention(session, "m2", "https://old.reddit.com/r/foo/2")
    _seed_mention(session, "m3", "https://m.reddit.com/r/foo/3")
    _seed_mention(session, "m4", "https://reddit.com/r/foo/4")
    _seed_mention(session, "m5", "https://notreddit.com/foo/5")
    session.commit()

    sleeps: list[float] = []

    with _client(lambda req: httpx.Response(200)) as c:
        verify_all_pending(
            session,
            c,
            workers=1,
            reddit_throttle_sec=0.1,
            sleep_fn=sleeps.append,
        )

    assert len(sleeps) == 4
