"""Workspace hook registry diagnostics for Morphic Chat CLI."""

from __future__ import annotations

import json

from domain.entities.hook import HookType
from infrastructure.hooks.workspace_hook_registry import WorkspaceHookRegistry


def _write_hook(tmp_path, name: str, payload: dict[str, object]) -> None:
    hook_dir = tmp_path / ".morphic" / "hooks"
    hook_dir.mkdir(parents=True, exist_ok=True)
    (hook_dir / name).write_text(
        json.dumps(payload, sort_keys=True),
        encoding="utf-8",
    )


def test_workspace_hook_registry_reports_valid_hooks(tmp_path) -> None:
    _write_hook(
        tmp_path,
        "lint.json",
        {
            "command": "uv run --extra dev ruff check .",
            "enabled": True,
            "name": "lint",
            "type": "pre_commit",
        },
    )

    checks = WorkspaceHookRegistry(tmp_path).validate()

    assert len(checks) == 1
    assert checks[0].name == "Hook: lint"
    assert checks[0].status == "OK"
    assert "pre_commit" in checks[0].message


def test_workspace_hook_registry_isolates_invalid_hooks(tmp_path) -> None:
    _write_hook(
        tmp_path,
        "valid.json",
        {
            "command": "uv run pytest tests/unit/ -q",
            "enabled": True,
            "name": "unit",
            "type": "post_shell",
        },
    )
    _write_hook(
        tmp_path,
        "bad-type.json",
        {
            "command": "echo ok",
            "enabled": True,
            "name": "bad-type",
            "type": "before_everything",
        },
    )
    _write_hook(
        tmp_path,
        "empty-command.json",
        {
            "command": "",
            "enabled": True,
            "name": "empty-command",
            "type": "pre_tool",
        },
    )

    checks = WorkspaceHookRegistry(tmp_path).validate()
    by_name = {check.name: check for check in checks}

    assert by_name["Hook: unit"].status == "OK"
    assert by_name["Hook: bad-type"].status == "FAIL"
    assert "invalid type" in by_name["Hook: bad-type"].message
    assert by_name["Hook: empty-command"].status == "FAIL"
    assert "command must not be empty" in by_name["Hook: empty-command"].message


def test_workspace_hook_registry_blocks_secret_touching_commands(tmp_path) -> None:
    _write_hook(
        tmp_path,
        "secret.json",
        {
            "command": "cat ~/.ssh/id_rsa",
            "enabled": True,
            "name": "secret-read",
            "type": "pre_shell",
        },
    )

    checks = WorkspaceHookRegistry(tmp_path).validate()

    assert checks[0].status == "FAIL"
    assert "secret path" in checks[0].message


def test_workspace_hook_registry_reports_missing_directory_as_ok(tmp_path) -> None:
    checks = WorkspaceHookRegistry(tmp_path).validate()

    assert len(checks) == 1
    assert checks[0].name == "Hooks"
    assert checks[0].status == "OK"
    assert "No hooks configured" in checks[0].message


def test_workspace_hook_registry_lists_valid_hook_definitions_by_type(tmp_path) -> None:
    _write_hook(
        tmp_path,
        "lint.json",
        {
            "command": "uv run --extra dev ruff check .",
            "enabled": True,
            "name": "lint",
            "type": "pre_commit",
        },
    )
    _write_hook(
        tmp_path,
        "disabled.json",
        {
            "command": "echo skipped",
            "enabled": False,
            "name": "disabled",
            "type": "pre_commit",
        },
    )
    _write_hook(
        tmp_path,
        "wrong-type.json",
        {
            "command": "echo ignored",
            "enabled": True,
            "name": "wrong-type",
            "type": "post_shell",
        },
    )
    _write_hook(
        tmp_path,
        "secret.json",
        {
            "command": "cat ~/.ssh/id_rsa",
            "enabled": True,
            "name": "secret",
            "type": "pre_commit",
        },
    )

    hooks = WorkspaceHookRegistry(tmp_path).hooks_for(HookType.PRE_COMMIT)

    assert [hook.name for hook in hooks] == ["disabled", "lint"]
    assert hooks[0].enabled is False
    assert hooks[0].source_path == ".morphic/hooks/disabled.json"
    assert hooks[1].enabled is True
    assert hooks[1].command == "uv run --extra dev ruff check ."
