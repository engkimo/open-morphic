"""TaskEventBus — in-memory event bus for real-time task streaming.

Uses asyncio.Queue to pipe events from the execution engine to SSE endpoints.
Multiple subscribers per task are supported (e.g. multiple browser tabs).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class TaskEventBus:
    """Singleton-style event bus. One instance lives in AppContainer."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}

    def subscribe(self, task_id: str) -> asyncio.Queue[dict[str, Any]]:
        """Create a new subscriber queue for a task. Returns the queue."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.setdefault(task_id, []).append(q)
        count = len(self._subscribers[task_id])
        logger.debug("SSE subscriber added for task %s (total=%d)", task_id, count)
        return q

    def unsubscribe(self, task_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove a subscriber queue."""
        queues = self._subscribers.get(task_id, [])
        with contextlib.suppress(ValueError):
            queues.remove(queue)
        if not queues:
            self._subscribers.pop(task_id, None)

    def publish(self, task_id: str, event: dict[str, Any]) -> None:
        """Push an event to all subscribers of a task. Non-blocking."""
        event.setdefault("timestamp", time.time())
        queues = self._subscribers.get(task_id, [])
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("SSE queue full for task %s — dropping event", task_id)

    def has_subscribers(self, task_id: str) -> bool:
        return bool(self._subscribers.get(task_id))
