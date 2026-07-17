"""Signal-aware control for one active interactive chat turn."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Callable, Coroutine, Iterator
from contextlib import contextmanager
from types import FrameType
from typing import Any, TypeVar

T = TypeVar("T")


class TurnCancelledError(Exception):
    """The interactive user cancelled the active turn without exiting the REPL."""


class ActiveTurnController:
    """Own at most one turn task and route Ctrl-C to that task only."""

    def __init__(self) -> None:
        self._active_task: asyncio.Task[Any] | None = None
        self._cancel_requested = False
        self._previous_sigint_handler: Any = None
        self._steer_prompt: str | None = None

    @property
    def has_active_turn(self) -> bool:
        task = self._active_task
        return task is not None and not task.done()

    async def run(self, operation: Callable[[], Coroutine[Any, Any, T]]) -> T:
        """Run one controlled turn and distinguish requested from caller cancellation."""
        if self.has_active_turn:
            raise RuntimeError("another chat turn is already active")

        self._cancel_requested = False
        task = asyncio.create_task(operation())
        self._active_task = task
        try:
            with self._route_sigint_to_active_turn():
                try:
                    return await task
                except asyncio.CancelledError:
                    if self._cancel_requested:
                        raise TurnCancelledError from None
                    raise
        finally:
            self._active_task = None
            self._cancel_requested = False

    def cancel_active_turn(self) -> bool:
        """Request cancellation without cancelling the REPL's parent task."""
        task = self._active_task
        if task is None or task.done():
            return False
        if not self._cancel_requested:
            self._cancel_requested = True
            task.cancel()
        return True

    def steer_active_turn(self, prompt: str) -> bool:
        """Queue one replacement prompt and cancel the active turn exactly once."""
        normalized = prompt.strip()
        if not normalized:
            raise ValueError("steer prompt must not be empty")
        if self._steer_prompt is not None or self._cancel_requested:
            return False
        self._steer_prompt = normalized
        if self.cancel_active_turn():
            return True
        self._steer_prompt = None
        return False

    def take_steer_prompt(self) -> str | None:
        """Consume the pending replacement prompt after cancellation cleanup."""
        prompt = self._steer_prompt
        self._steer_prompt = None
        return prompt

    @contextmanager
    def _route_sigint_to_active_turn(self) -> Iterator[None]:
        try:
            previous = signal.getsignal(signal.SIGINT)
            self._previous_sigint_handler = previous
            signal.signal(signal.SIGINT, self._handle_sigint)
        except (OSError, ValueError):
            self._previous_sigint_handler = None
            yield
            return

        try:
            yield
        finally:
            signal.signal(signal.SIGINT, previous)
            self._previous_sigint_handler = None

    def _handle_sigint(self, signum: int, frame: FrameType | None) -> None:
        if self.cancel_active_turn():
            return

        previous = self._previous_sigint_handler
        if callable(previous):
            previous(signum, frame)
        elif previous == signal.SIG_DFL:
            signal.default_int_handler(signum, frame)
