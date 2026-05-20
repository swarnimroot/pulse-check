"""HEAD-check mention URLs and tombstone the dead ones.

Conservative policy — only 404 / 410 / DNS-fail / connection-refused set
``tombstoned_at``. 403 / 5xx / timeout / generic transport errors stay
alive so a single bad day for an upstream host doesn't permanently drop
real citations from briefs.

Public surface:

``verify_url(client, url) -> VerifyResult``
    Classify a single URL. HEAD first, GET-stream fallback on 405.

``verify_all_pending(session, client, ...) -> BatchStats``
    Iterate every ``Mention`` with ``tombstoned_at IS NULL``, run
    ``verify_url`` over a thread pool, persist tombstones via the
    SQLAlchemy session with periodic commits so a mid-run kill keeps
    partial progress (mirrors ``feedback_long_llm_batch_commits``).
"""

from __future__ import annotations

import logging
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulse_check.storage.models import Mention

log = logging.getLogger(__name__)

# Mirrors Chrome 120 so retailer endpoints behave the way the original
# scrape saw them — the goal is to NOT trigger a fresh anti-bot block
# on what was a reachable URL last quarter.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

TombstoneReason = Literal["http_404", "http_410", "dns_fail", "conn_refused"]


@dataclass(frozen=True)
class VerifyResult:
    url: str
    tombstone_reason: TombstoneReason | None
    note: str  # short status tag for logs ("ok", "http_404", "timeout", ...)


@dataclass
class BatchStats:
    checked: int = 0
    tombstoned: int = 0
    alive: int = 0
    by_reason: dict[str, int] = field(default_factory=dict)


def _classify_connect_error(exc: BaseException) -> TombstoneReason | None:
    """Walk ``__cause__`` / ``__context__`` for a socket-level signal.

    Returns ``"dns_fail"`` for ``socket.gaierror``, ``"conn_refused"`` for
    ``ConnectionRefusedError``, or ``None`` for anything else (left as a
    transient ``conn_error``).
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, socket.gaierror):
            return "dns_fail"
        if isinstance(current, ConnectionRefusedError):
            return "conn_refused"
        current = current.__cause__ or current.__context__
    return None


def verify_url(
    client: httpx.Client,
    url: str,
    *,
    timeout: float | httpx.Timeout = _DEFAULT_TIMEOUT,
) -> VerifyResult:
    """Classify one URL. Tombstones on 404 / 410 / DNS / refused."""
    try:
        response = client.request(
            "HEAD",
            url,
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        )
    except httpx.ConnectError as exc:
        reason = _classify_connect_error(exc)
        return VerifyResult(url=url, tombstone_reason=reason, note=reason or "conn_error")
    except httpx.TimeoutException:
        return VerifyResult(url=url, tombstone_reason=None, note="timeout")
    except httpx.HTTPError:
        return VerifyResult(url=url, tombstone_reason=None, note="transport_error")

    if response.status_code == 405:
        try:
            response = client.request(
                "GET",
                url,
                follow_redirects=True,
                timeout=timeout,
                headers={"User-Agent": _USER_AGENT},
            )
        except httpx.TimeoutException:
            return VerifyResult(url=url, tombstone_reason=None, note="timeout")
        except httpx.HTTPError:
            return VerifyResult(url=url, tombstone_reason=None, note="transport_error")

    status = response.status_code
    if status == 404:
        return VerifyResult(url=url, tombstone_reason="http_404", note="http_404")
    if status == 410:
        return VerifyResult(url=url, tombstone_reason="http_410", note="http_410")
    if 200 <= status < 400:
        return VerifyResult(url=url, tombstone_reason=None, note="ok")
    return VerifyResult(url=url, tombstone_reason=None, note=f"http_{status}")


def verify_all_pending(
    session: Session,
    client: httpx.Client,
    *,
    limit: int | None = None,
    workers: int = 16,
    commit_every: int = 100,
    dry_run: bool = False,
) -> BatchStats:
    """Verify every ``Mention`` with ``tombstoned_at IS NULL`` and persist."""
    query = select(Mention.mention_id, Mention.source_url).where(
        Mention.tombstoned_at.is_(None)
    )
    if limit is not None:
        query = query.limit(limit)
    rows = [(mid, url) for mid, url in session.execute(query).all()]
    log.info(
        "verifying %d mentions (workers=%d, dry_run=%s)",
        len(rows),
        workers,
        dry_run,
    )

    stats = BatchStats()
    now = datetime.now(UTC)

    def _check(row: tuple[str, str]) -> tuple[str, VerifyResult]:
        mention_id, url = row
        return mention_id, verify_url(client, url)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_check, row) for row in rows]
        for future in as_completed(futures):
            mention_id, result = future.result()
            stats.checked += 1
            stats.by_reason[result.note] = stats.by_reason.get(result.note, 0) + 1
            if result.tombstone_reason is not None:
                stats.tombstoned += 1
                if not dry_run:
                    mention = session.get(Mention, mention_id)
                    if mention is not None:
                        mention.tombstoned_at = now
                        mention.tombstone_reason = result.tombstone_reason
            else:
                stats.alive += 1
            if stats.checked % commit_every == 0:
                if not dry_run:
                    session.commit()
                log.info(
                    "verify progress: %d/%d checked, %d tombstoned (dry_run=%s)",
                    stats.checked,
                    len(rows),
                    stats.tombstoned,
                    dry_run,
                )

    if not dry_run:
        session.commit()
    return stats
