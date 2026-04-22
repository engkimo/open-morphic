"""TaskComplexity — goal complexity classification for adaptive decomposition."""

from enum import Enum


class TaskComplexity(str, Enum):
    SIMPLE = "simple"  # Single action, 1 subtask, no LLM decomposition
    MEDIUM = "medium"  # 2-3 subtasks via LLM
    COMPLEX = "complex"  # 3-5 subtasks via LLM
