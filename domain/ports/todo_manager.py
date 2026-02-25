"""TodoManager port — Manus Principle 4: steer LLM attention via todo.md."""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.entities.task import TaskEntity


class TodoManagerPort(ABC):
    """Read and update a todo.md file to keep LLM focus on current goals."""

    @abstractmethod
    def read(self) -> str:
        """Return current todo.md content."""
        ...

    @abstractmethod
    def update_from_task(self, task: TaskEntity) -> None:
        """Rewrite todo.md to reflect current task state."""
        ...

    @abstractmethod
    def format_for_context(self, task: TaskEntity) -> str:
        """Return a compact string for injection into LLM context."""
        ...
