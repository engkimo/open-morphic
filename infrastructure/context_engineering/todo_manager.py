"""TodoManager — Manus Principle 4: steer LLM attention via todo.md.

LLMs attend most to the start and end of context. By injecting a
current-state summary (todo.md) we counteract mid-context dilution
and prevent long-task drift.
"""

from __future__ import annotations

from pathlib import Path

from domain.entities.task import TaskEntity
from domain.ports.todo_manager import TodoManagerPort
from domain.value_objects.status import SubTaskStatus

# Status markers for todo.md rendering
_STATUS_MAP = {
    SubTaskStatus.SUCCESS: "[x]",
    SubTaskStatus.RUNNING: "[ ] **[IN PROGRESS]**",
    SubTaskStatus.FAILED: "[ ] ~~FAILED~~",
    SubTaskStatus.PENDING: "[ ]",
}


class FileTodoManager(TodoManagerPort):
    """File-backed todo.md manager. Implements TodoManagerPort."""

    def __init__(self, todo_path: Path | str = "todo.md") -> None:
        self._path = Path(todo_path)

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> str:
        """Return current todo.md content, or empty string if not found."""
        if not self._path.exists():
            return ""
        return self._path.read_text(encoding="utf-8")

    def update_from_task(self, task: TaskEntity) -> None:
        """Rewrite todo.md to reflect current task state."""
        content = self._render(task)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(content, encoding="utf-8")

    def format_for_context(self, task: TaskEntity) -> str:
        """Return a compact string for LLM context injection."""
        return self._render(task)

    @staticmethod
    def _render(task: TaskEntity) -> str:
        """Render task state as Markdown checklist."""
        lines = [
            "# todo.md",
            "",
            f"## Goal: {task.goal}",
            "",
            "### Tasks",
        ]

        for subtask in task.subtasks:
            marker = _STATUS_MAP.get(subtask.status, "[ ]")
            lines.append(f"- {marker} {subtask.description}")

        progress = f"{task.success_rate:.0%}" if task.subtasks else "0%"
        lines.append("")
        lines.append(f"**Progress: {progress}**")

        return "\n".join(lines)
