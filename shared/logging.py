"""Centralized logging configuration for Morphic-Agent.

Call ``setup_logging()`` once at application startup (API or CLI).
All modules use ``logging.getLogger(__name__)`` — no per-module config needed.
"""

from __future__ import annotations

import logging  # noqa: I001
import sys

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with a structured console handler.

    Args:
        level: Python log level name (DEBUG, INFO, WARNING, ERROR).
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))

    root = logging.getLogger()
    # Remove any existing handlers to avoid duplicates on re-init
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)

    # Quiet noisy third-party loggers
    for noisy in (
        "httpx",
        "httpcore",
        "litellm",
        "urllib3",
        "asyncio",
        "sqlalchemy.engine",
        "sqlalchemy.engine.Engine",
        "sqlalchemy.pool",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)
