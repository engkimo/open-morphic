"""CLI tests for Morphic Chat CLI Phase 4."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from domain.entities.approval import ApprovalRequest
from domain.value_objects import RiskLevel
from interface.cli.main import app
from interface.cli.renderers import render_approval_request
from interface.cli.slash_commands import parse_slash_command

runner = CliRunner()


def test_parse_slash_command_name_and_args() -> None:
    command = parse_slash_command("/resume latest")

    assert command.name == "resume"
    assert command.args == "latest"


def test_parse_slash_command_rejects_non_slash() -> None:
    try:
        parse_slash_command("status")
    except ValueError as exc:
        assert "slash" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_chat_doctor_json_lists_engines() -> None:
    result = runner.invoke(app, ["chat", "--doctor", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "engines" in payload
    assert any(engine["id"] == "ollama" for engine in payload["engines"])


def test_chat_repl_status_and_quit_creates_session_ledger() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["chat"], input="/status\n/quit\n")

        assert result.exit_code == 0
        assert "Morphic chat session" in result.output
        assert "session=" in result.output
        assert "session ended" in result.output
        ledgers = list(Path(".morphic/sessions").glob("*.jsonl"))
        assert len(ledgers) == 1


def test_code_one_shot_runs_goal_without_repl() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["code", "implement Phase 4"])

        assert result.exit_code == 0
        assert "Plan next step for: implement Phase 4" in result.output
        ledgers = list(Path(".morphic/sessions").glob("*.jsonl"))
        assert len(ledgers) == 1


def test_render_approval_request_includes_risk_and_action() -> None:
    request = ApprovalRequest(
        id="approval-1",
        session_id="chat-1",
        action_summary="Edit files",
        risk_level=RiskLevel.HIGH,
        reason="workspace mutation",
    )

    rendered = render_approval_request(request)

    assert "Edit files" in rendered
    assert "HIGH" in rendered
    assert "workspace mutation" in rendered
