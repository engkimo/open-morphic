"""Read-only workspace hook diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from domain.entities.hook import HookDefinition, HookDiagnostic, HookType
from domain.ports.hook_registry import HookRegistryPort


class WorkspaceHookRegistry(HookRegistryPort):
    """Validate `.morphic/hooks/*.json` hook definitions without executing them."""

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

    def hooks_for(self, hook_type: HookType) -> list[HookDefinition]:
        hooks: list[HookDefinition] = []
        hook_dir = self._workspace_root / ".morphic" / "hooks"
        if not hook_dir.is_dir():
            return hooks
        for path in sorted(hook_dir.glob("*.json")):
            hook = self._definition_for(path)
            if hook is not None and hook.hook_type is hook_type:
                hooks.append(hook)
        return hooks

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

        if self._hook_type_for(hook_type) is None:
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

    def _definition_for(self, path: Path) -> HookDefinition | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None

        hook_type = self._hook_type_for(payload.get("type"))
        command = payload.get("command")
        if hook_type is None or not isinstance(command, str) or not command.strip():
            return None
        if self._touches_secret_path(command):
            return None

        return HookDefinition(
            name=self._hook_name(path, payload).removeprefix("Hook: "),
            hook_type=hook_type,
            command=command.strip(),
            enabled=payload.get("enabled", True) is True,
            source_path=str(path.relative_to(self._workspace_root)),
        )

    def _hook_type_for(self, value: object) -> HookType | None:
        if not isinstance(value, str):
            return None
        try:
            return HookType(value)
        except ValueError:
            return None

    def _hook_name(self, path: Path, payload: dict[str, Any]) -> str:
        name = payload.get("name")
        if isinstance(name, str) and name.strip():
            return f"Hook: {name.strip()}"
        return f"Hook: {path.stem}"

    def _touches_secret_path(self, command: str) -> bool:
        return any(pattern in command for pattern in self._SECRET_PATTERNS)
