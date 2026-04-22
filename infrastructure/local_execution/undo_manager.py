"""Undo Manager — stack-based undo for reversible LAEE operations."""

from __future__ import annotations

from domain.entities.execution import UndoAction


class UndoManager:
    """Stack of reversible operations. Push on execute, pop on undo."""

    def __init__(self) -> None:
        self._stack: list[UndoAction] = []

    def push(self, undo_action: UndoAction) -> None:
        self._stack.append(undo_action)

    def pop(self) -> UndoAction | None:
        return self._stack.pop() if self._stack else None

    @property
    def size(self) -> int:
        return len(self._stack)
