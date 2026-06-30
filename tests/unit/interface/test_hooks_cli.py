"""CLI tests for manual Morphic Chat hook execution."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from interface.cli.main import app

runner = CliRunner()


def test_hooks_run_json_executes_hook_with_noop_default() -> None:
    with runner.isolated_filesystem():
        hook_dir = Path(".morphic/hooks")
        hook_dir.mkdir(parents=True)
        (hook_dir / "pre.json").write_text(
            json.dumps(
                {
                    "command": "exit 99",
                    "enabled": True,
                    "name": "pre-log",
                    "type": "pre_tool",
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        result = runner.invoke(app, ["hooks", "run", "pre_tool", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["hook_execution_mode"] == "noop"
        assert payload["hook_type"] == "pre_tool"
        assert payload["summary"] == {"failed": 0, "skipped": 0, "succeeded": 1}
        assert payload["results"][0]["hook_name"] == "pre-log"
        assert payload["results"][0]["success"] is True
        assert "not executed" in payload["results"][0]["stdout_summary"]
        ledgers = list(Path(".morphic/sessions").glob("*.jsonl"))
        assert len(ledgers) == 1
        assert "hook_execution_completed" in ledgers[0].read_text(encoding="utf-8")


def test_hooks_run_rejects_invalid_hook_type() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["hooks", "run", "before_everything", "--json"])

    assert result.exit_code == 2
    assert "Invalid hook type" in result.output


def test_hooks_run_shell_opt_in_executes_hook_and_writes_audit_log(
    monkeypatch,
) -> None:
    monkeypatch.setenv("MORPHIC_CHAT_HOOK_EXECUTION", "shell")
    with runner.isolated_filesystem():
        hook_dir = Path(".morphic/hooks")
        hook_dir.mkdir(parents=True)
        (hook_dir / "pre.json").write_text(
            json.dumps(
                {
                    "command": "echo hook-ok",
                    "enabled": True,
                    "name": "pre-log",
                    "type": "pre_tool",
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        result = runner.invoke(app, ["hooks", "run", "pre_tool", "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["hook_execution_mode"] == "shell"
        assert payload["results"][0]["stdout_summary"] == "hook-ok"
        audit_log = Path(".morphic/audit_log.jsonl")
        assert audit_log.exists()
        assert "shell_exec" in audit_log.read_text(encoding="utf-8")
