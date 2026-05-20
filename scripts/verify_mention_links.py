"""CLI: HEAD-check every Mention's source URL and tombstone dead links.

Conservative tombstone policy — only 404 / 410 / DNS-fail / connection-refused
write ``tombstoned_at``. 403 / 5xx / timeout / generic transport errors leave
the mention alive so a single bad day for an upstream host doesn't
permanently drop real citations from briefs.

Usage:
    python scripts/verify_mention_links.py --workers 16
    python scripts/verify_mention_links.py --limit 50 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys

import httpx

from pulse_check.logging_config import configure_logging
from pulse_check.storage.session import session_scope
from pulse_check.verifiers.link_verifier import verify_all_pending

log = logging.getLogger("pulse_check.scripts.verify_mention_links")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="verify-mention-links",
        description=(
            "HEAD-check every not-yet-tombstoned Mention's source URL and "
            "tombstone the dead ones (404 / 410 / DNS / refused)."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of mentions checked (smoke testing).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=16,
        help="Thread-pool size for concurrent HEAD checks.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify and report, but don't write to the DB.",
    )
    parser.add_argument(
        "--commit-every",
        type=int,
        default=100,
        help="Commit after every N checks; smaller = more durable, slower.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    configure_logging()
    # httpx emits an INFO line per request; at 5k URLs that drowns the
    # operator-relevant progress and final-stats lines.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    with session_scope() as session, httpx.Client() as client:
        stats = verify_all_pending(
            session,
            client,
            limit=args.limit,
            workers=args.workers,
            commit_every=args.commit_every,
            dry_run=args.dry_run,
        )

    log.info(
        "done: checked=%d tombstoned=%d alive=%d | by_reason=%s",
        stats.checked,
        stats.tombstoned,
        stats.alive,
        dict(sorted(stats.by_reason.items())),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
