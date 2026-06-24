"""CLI tests for Morphic Chat CLI Phase 4."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from domain.entities.approval import ApprovalRequest
from domain.entities.chat_session import ChatSession
from domain.entities.council_runtime import CouncilDecision, CouncilRole, CouncilTurn
from domain.entities.workspace_context import ContextIndex
from domain.ports.engine_registry import EngineProfile, EngineRuntimeKind
from domain.value_objects import RiskLevel
from interface.cli.chat_command import _chat_doctor_payload
from interface.cli.chat_repl import ChatRepl
from interface.cli.main import app
from interface.cli.renderers import render_approval_request
from interface.cli.slash_commands import parse_slash_command

runner = CliRunner()


class _FakeEngineRegistry:
    async def list_engines(self) -> list[EngineProfile]:
        return [
            EngineProfile(
                id="codex_cli",
                display_name="Codex CLI",
                kind=EngineRuntimeKind.EXTERNAL_CLI,
                available=True,
                supports_editing=True,
            )
        ]

    async def get_engine(self, engine_id: str) -> EngineProfile | None:
        return (await self.list_engines())[0] if engine_id == "codex_cli" else None


class _FakeCouncilRuntime:
    async def deliberate(
        self,
        session: ChatSession,
        context: ContextIndex,
        user_message: str,
    ) -> tuple[list[CouncilTurn], CouncilDecision]:
        turn = CouncilTurn(
            role=CouncilRole.LEADER,
            engine_id="codex_cli",
            content=f"Routed response for: {user_message}",
            evidence=[f"context_sources={len(context.sources)}"],
        )
        decision = CouncilDecision(
            leader_engine_id="codex_cli",
            selected_role=CouncilRole.LEADER,
            selected_content=turn.content,
            rationale="fake route-backed runtime",
            evidence=turn.evidence,
        )
        return [turn], decision


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


@pytest.mark.asyncio
async def test_chat_doctor_payload_uses_injected_engine_registry() -> None:
    payload = await _chat_doctor_payload(engine_registry=_FakeEngineRegistry())

    assert payload["engines"] == [
        {
            "available": True,
            "capabilities": [],
            "context_window": 0,
            "cost_profile": None,
            "display_name": "Codex CLI",
            "id": "codex_cli",
            "kind": "external_cli",
            "latency_profile": None,
            "supports_editing": True,
            "supports_json_output": False,
            "supports_sandbox": False,
            "supports_streaming": False,
        }
    ]


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


@pytest.mark.asyncio
async def test_chat_repl_run_goal_uses_injected_council_runtime(tmp_path) -> None:
    output = await ChatRepl(
        workspace_root=tmp_path,
        council_runtime=_FakeCouncilRuntime(),
    ).run_goal(goal="implement routed council")

    assert output == "Routed response for: implement routed council"
    ledger = next((tmp_path / ".morphic" / "sessions").glob("*.jsonl"))
    assert "codex_cli" in ledger.read_text(encoding="utf-8")


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
