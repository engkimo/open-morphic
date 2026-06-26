"""Read-only workspace hook diagnostics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HookDiagnostic:
    """Validation result for one hook source."""

    name: str
    status: str
    message: str
    duration_ms: float = 0.0


class WorkspaceHookRegistry:
    """Validate `.morphic/hooks/*.json` hook definitions without executing them."""

    _VALID_TYPES = {
        "post_edit",
        "post_shell",
        "post_tool",
        "pre_commit",
        "pre_edit",
        "pre_shell",
        "pre_tool",
        "session_end",
    }
    _SECRET_PATTERNS = ("~/.aws", "~/.ssh", ".env")

    def __init__(self, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root)

    def validate(self) -> list[HookDiagnostic]:
        hook_dir = self._workspace_root / ".morphic" / "hooks"
        if not hook_dir.is_dir():
            return [
                HookDiagnostic(
                    name="Hooks",
                    status="OK",
                    message="No hooks configured",
                )
            ]

        diagnostics: list[HookDiagnostic] = []
        for path in sorted(hook_dir.glob("*.json")):
            diagnostics.append(self._validate_file(path))
        if not diagnostics:
            return [
                HookDiagnostic(
                    name="Hooks",
                    status="OK",
                    message="No hooks configured",
                )
            ]
        return diagnostics

    def _validate_file(self, path: Path) -> HookDiagnostic:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            return HookDiagnostic(
                name=f"Hook: {path.stem}",
                status="FAIL",
                message=f"invalid JSON: {exc.msg}",
            )

        if not isinstance(payload, dict):
            return HookDiagnostic(
                name=f"Hook: {path.stem}",
                status="FAIL",
                message="hook definition must be a JSON object",
            )

        hook_name = self._hook_name(path, payload)
        hook_type = payload.get("type")
        command = payload.get("command")
        enabled = payload.get("enabled", True)

        if hook_type not in self._VALID_TYPES:
            return HookDiagnostic(
                name=hook_name,
                status="FAIL",
                message=f"invalid type: {hook_type}",
            )
        if not isinstance(command, str) or not command.strip():
            return HookDiagnostic(
                name=hook_name,
                status="FAIL",
                message="command must not be empty",
            )
        if self._touches_secret_path(command):
            return HookDiagnostic(
                name=hook_name,
                status="FAIL",
                message="command references a secret path",
            )
        if enabled is not True:
            return HookDiagnostic(
                name=hook_name,
                status="WARN",
                message=f"{hook_type} hook is disabled",
            )
        return HookDiagnostic(
            name=hook_name,
            status="OK",
            message=f"{hook_type} hook is valid",
        )

    def _hook_name(self, path: Path, payload: dict[str, Any]) -> str:
        name = payload.get("name")
        if isinstance(name, str) and name.strip():
            return f"Hook: {name.strip()}"
        return f"Hook: {path.stem}"

    def _touches_secret_path(self, command: str) -> bool:
        return any(pattern in command for pattern in self._SECRET_PATTERNS)
