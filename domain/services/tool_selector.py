"""ToolSelector — task-type-based tool profile selection.

Pure domain service: no I/O, no framework dependencies.
"""

from __future__ import annotations

from domain.value_objects.model_tier import TaskType

# Task type → tool name prefixes/names
TASK_TOOL_PROFILES: dict[TaskType, list[str]] = {
    TaskType.SIMPLE_QA: ["web_search", "web_fetch"],
    TaskType.CODE_GENERATION: ["web_search", "web_fetch", "shell_exec", "fs_read", "fs_write"],
    TaskType.COMPLEX_REASONING: [
        "web_search",
        "web_fetch",
        "shell_exec",
        "fs_read",
        "fs_write",
        "fs_glob",
    ],
    TaskType.FILE_OPERATION: [
        "fs_read",
        "fs_write",
        "fs_edit",
        "fs_delete",
        "fs_move",
        "fs_glob",
        "fs_tree",
        "shell_exec",
    ],
    TaskType.LONG_CONTEXT: ["web_search", "web_fetch", "fs_read", "fs_glob"],
    TaskType.MULTIMODAL: ["web_search", "web_fetch", "browser_navigate", "browser_screenshot"],
    TaskType.LONG_RUNNING_DEV: [
        "web_search",
        "web_fetch",
        "shell_exec",
        "fs_read",
        "fs_write",
        "fs_edit",
        "fs_glob",
        "fs_tree",
        "dev_git",
        "dev_pkg_install",
    ],
    TaskType.WORKFLOW_PIPELINE: [
        "web_search",
        "web_fetch",
        "shell_exec",
        "fs_read",
        "fs_write",
        "fs_glob",
    ],
    TaskType.WEB_SEARCH: [
        "web_search",
        "web_fetch",
        "browser_navigate",
        "browser_extract",
    ],
}

DEFAULT_TOOLS: list[str] = ["web_search", "web_fetch", "fs_read", "fs_glob", "shell_exec"]


class ToolSelector:
    """Select tool profiles based on task type."""

    @staticmethod
    def select(task_type: TaskType) -> list[str]:
        """Return tool names appropriate for the given task type."""
        return TASK_TOOL_PROFILES.get(task_type, DEFAULT_TOOLS)
