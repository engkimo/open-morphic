"""LocalExecutor — LAEE core. Ties risk assessment, approval, tools, audit, and undo."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from domain.entities.execution import Action, Observation, UndoAction
from domain.ports.audit_logger import AuditLogger
from domain.ports.local_executor import LocalExecutorPort
from domain.services.approval_engine import ApprovalEngine
from domain.services.risk_assessor import RiskAssessor
from domain.value_objects import ApprovalMode
from domain.value_objects.status import ObservationStatus
from infrastructure.local_execution.tools import TOOL_REGISTRY, ToolFunc
from infrastructure.local_execution.undo_manager import UndoManager

# Tools that support undo
_UNDOABLE_TOOLS = {"fs_write", "fs_edit", "fs_move"}


class LocalExecutor(LocalExecutorPort):
    """Execute actions on the local machine with risk assessment and approval.

    Flow: assess risk → check approval → create undo → execute → audit log.
    """

    def __init__(
        self,
        approval_mode: ApprovalMode,
        audit_logger: AuditLogger,
        undo_enabled: bool = True,
        registry: dict[str, ToolFunc] | None = None,
    ) -> None:
        self._mode = approval_mode
        self._audit = audit_logger
        self._undo_enabled = undo_enabled
        self._undo_manager = UndoManager()
        self._risk_assessor = RiskAssessor()
        self._approval_engine = ApprovalEngine()
        self._registry = registry if registry is not None else TOOL_REGISTRY

    async def execute(self, action: Action) -> Observation:
        # 1. Assess risk
        risk = self._risk_assessor.assess(action)

        # 2. Check approval
        if self._approval_engine.needs_approval(self._mode, risk):
            self._audit.log(action, "Denied: requires user approval", risk, success=False)
            return Observation(
                status=ObservationStatus.DENIED,
                result=f"Action requires approval (risk={risk.name}, mode={self._mode.value})",
            )

        # 3. Resolve tool
        tool_func = self._registry.get(action.tool)
        if tool_func is None:
            self._audit.log(action, f"Unknown tool: {action.tool}", risk, success=False)
            return Observation(
                status=ObservationStatus.ERROR, result=f"Unknown tool: {action.tool}"
            )

        # 4. Create undo info (before execution)
        undo = None
        if self._undo_enabled and action.tool in _UNDOABLE_TOOLS:
            undo = _build_undo(action)

        # 5. Execute
        try:
            result = await tool_func(action.args)
        except Exception as e:
            self._audit.log(action, str(e)[:500], risk, success=False)
            return Observation(status=ObservationStatus.ERROR, result=str(e))

        # 6. Push undo
        if undo is not None:
            self._undo_manager.push(undo)

        # 7. Audit
        self._audit.log(action, result[:500], risk, success=True)
        return Observation(status=ObservationStatus.SUCCESS, result=result)

    async def undo_last(self) -> Observation:
        undo = self._undo_manager.pop()
        if undo is None:
            return Observation(
                status=ObservationStatus.ERROR, result="Nothing to undo"
            )

        tool_func = self._registry.get(undo.undo_tool)
        if tool_func is None:
            return Observation(
                status=ObservationStatus.ERROR,
                result=f"Undo tool not found: {undo.undo_tool}",
            )

        try:
            result = await tool_func(undo.undo_args)
        except Exception as e:
            return Observation(status=ObservationStatus.ERROR, result=f"Undo failed: {e}")

        risk = self._risk_assessor.assess(
            Action(tool=undo.undo_tool, args=undo.undo_args)
        )
        self._audit.log(
            Action(tool=undo.undo_tool, args=undo.undo_args, description="undo"),
            result[:500],
            risk,
            success=True,
        )
        return Observation(status=ObservationStatus.SUCCESS, result=f"Undone: {result}")

    async def get_undo_stack_size(self) -> int:
        return self._undo_manager.size


def _build_undo(action: Action) -> UndoAction | None:
    """Create undo info for reversible operations."""
    args: dict[str, Any] = action.args

    if action.tool == "fs_write":
        path = Path(args.get("path", ""))
        if path.exists():
            # Overwrite: undo restores original content
            original = path.read_text()
            return UndoAction(
                original_tool="fs_write",
                original_args=args,
                undo_tool="fs_write",
                undo_args={"path": str(path), "content": original},
            )
        # New file: undo deletes it
        return UndoAction(
            original_tool="fs_write",
            original_args=args,
            undo_tool="fs_delete",
            undo_args={"path": str(path)},
        )

    if action.tool == "fs_edit":
        return UndoAction(
            original_tool="fs_edit",
            original_args=args,
            undo_tool="fs_edit",
            undo_args={"path": args["path"], "old": args["new"], "new": args["old"]},
        )

    if action.tool == "fs_move":
        return UndoAction(
            original_tool="fs_move",
            original_args=args,
            undo_tool="fs_move",
            undo_args={"src": args["dst"], "dst": args["src"]},
        )

    return None
