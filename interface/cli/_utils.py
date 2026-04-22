"""Shared CLI utilities — container access and async bridge.

Extracted from main.py to break circular imports between main.py and command modules.
"""

from __future__ import annotations

import asyncio
from typing import Any

# Lazy singleton — created once on first access
_container_instance: Any = None


def _get_container() -> Any:
    """Lazy-init the AppContainer singleton. Swappable for testing."""
    global _container_instance  # noqa: PLW0603
    if _container_instance is None:
        from interface.api.container import AppContainer

        _container_instance = AppContainer()
    return _container_instance


def _set_container(container: Any) -> None:
    """Override the container (for testing)."""
    global _container_instance  # noqa: PLW0603
    _container_instance = container


def _run(coro: Any) -> Any:
    """Thin wrapper to run an async coroutine from sync typer commands.

    Falls back to loop.run_until_complete() when called inside an existing
    event loop (e.g. pytest-asyncio tests).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside a loop — run directly on it
    return loop.run_until_complete(coro)
