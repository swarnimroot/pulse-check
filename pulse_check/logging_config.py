"""Logging configuration.

Stdlib logging with a rotating file handler pointing at `data/pulse_check.log`.
Console handler mirrors to stderr so long-running scripts show progress.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pulse_check.settings import get_settings

_CONFIGURED = False


def configure_logging() -> None:
    """Idempotent global logging setup.

    Call once at process start (e.g. from each `scripts/*.py` CLI entry).
    Safe to call multiple times — subsequent calls are no-ops.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    log_file = Path(settings.log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    file_handler = RotatingFileHandler(
        log_file, maxBytes=10_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    _CONFIGURED = True
