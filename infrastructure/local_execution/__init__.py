"""LAEE — Local Autonomous Execution Engine.

Implements LocalExecutorPort for direct local PC control.
"""

from infrastructure.local_execution.audit_log import JsonlAuditLogger
from infrastructure.local_execution.executor import LocalExecutor
from infrastructure.local_execution.undo_manager import UndoManager

__all__ = ["JsonlAuditLogger", "LocalExecutor", "UndoManager"]
