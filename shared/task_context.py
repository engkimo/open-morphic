"""Task ID propagation via ContextVar — cross-cutting cost attribution.

ContextVar lets us thread a ``task_id`` through async code without changing
every function signature: nested awaits inherit the caller's context, so
``CostTracker.record`` can stamp the active task on each ``CostRecord``.

Use ``task_id_scope`` as a context manager around code that should be
attributed to a single task. ``get_current_task_id`` returns the active id
or ``None`` when no scope is active.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_current_task_id: ContextVar[str | None] = ContextVar("current_task_id", default=None)


def get_current_task_id() -> str | None:
    """Return the task_id of the active scope, or None."""
    return _current_task_id.get()


@contextmanager
def task_id_scope(task_id: str) -> Iterator[None]:
    """Bind ``task_id`` as the active task for the duration of the block."""
    token = _current_task_id.set(task_id)
    try:
        yield
    finally:
        _current_task_id.reset(token)
