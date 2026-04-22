"""Context Engineering — Manus 5 Principles implementation.

Principle 1: KV-cache stable prefix (KVCacheOptimizer)
Principle 2: Tool masking (domain/services/tool_state_machine.py)
Principle 3: Filesystem as infinite context (FileContext)
Principle 4: todo.md attention steering (FileTodoManager)
Principle 5: Observation diversity (ObservationDiversifier)
"""

from infrastructure.context_engineering.file_context import FileContext
from infrastructure.context_engineering.kv_cache_optimizer import KVCacheOptimizer
from infrastructure.context_engineering.observation_diversifier import (
    ObservationDiversifier,
)
from infrastructure.context_engineering.todo_manager import FileTodoManager

__all__ = [
    "FileContext",
    "FileTodoManager",
    "KVCacheOptimizer",
    "ObservationDiversifier",
]
