"""CLI tests for Morphic Chat CLI Phase 4."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from domain.entities.approval import ApprovalRequest
from domain.entities.chat_session import ChatSession
from domain.entities.council_runtime import CouncilDecision, CouncilRole, CouncilTurn
from domain.entities.execution import Action, Observation
from domain.entities.workspace_context import ContextIndex
from domain.ports.engine_registry import EngineProfile, EngineRuntimeKind
from domain.ports.local_executor import LocalExecutorPort
from domain.value_objects import RiskLevel
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.status import ObservationStatus
from interface.cli.chat_command import (
    _chat_doctor_payload,
    _chat_hook_executor,
    _chat_tool_executor,
    _role_engine_preferences,
)
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


class _FakeLocalExecutor(LocalExecutorPort):
    async def execute(self, action: Action) -> Observation:
        return Observation(status=ObservationStatus.SUCCESS, result="ok")

    async def undo_last(self) -> Observation:
        return Observation(status=ObservationStatus.SUCCESS, result="undone")

    async def get_undo_stack_size(self) -> int:
        return 0


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
    assert payload["hook_execution_mode"] == "noop"
    assert payload["tool_execution_mode"] == "noop"
    assert any(engine["id"] == "ollama" for engine in payload["engines"])


def test_chat_hook_executor_defaults_to_noop(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from infrastructure.hooks.noop_hook_executor import NoopHookExecutor

    monkeypatch.delenv("MORPHIC_CHAT_HOOK_EXECUTION", raising=False)

    executor = _chat_hook_executor(
        workspace_root=tmp_path,
        local_executor_factory=lambda: _FakeLocalExecutor(),
    )

    assert isinstance(executor, NoopHookExecutor)


@pytest.mark.asyncio
async def test_chat_doctor_payload_reports_shell_hook_execution_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MORPHIC_CHAT_HOOK_EXECUTION", "shell")

    payload = await _chat_doctor_payload(engine_registry=_FakeEngineRegistry())

    assert payload["hook_execution_mode"] == "shell"


def test_chat_hook_executor_uses_shell_only_with_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from infrastructure.hooks.shell_hook_executor import ShellHookExecutor

    monkeypatch.setenv("MORPHIC_CHAT_HOOK_EXECUTION", "shell")

    executor = _chat_hook_executor(
        workspace_root=tmp_path,
        local_executor_factory=lambda: _FakeLocalExecutor(),
    )

    assert isinstance(executor, ShellHookExecutor)


def test_chat_hook_executor_rejects_unknown_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("MORPHIC_CHAT_HOOK_EXECUTION", "always")

    with pytest.raises(ValueError) as exc_info:
        _chat_hook_executor(
            workspace_root=tmp_path,
            local_executor_factory=lambda: _FakeLocalExecutor(),
        )

    assert "Invalid hook execution mode" in str(exc_info.value)


def test_chat_tool_executor_defaults_to_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    from infrastructure.tools.noop_tool_executor import NoopToolExecutor

    monkeypatch.delenv("MORPHIC_CHAT_TOOL_EXECUTION", raising=False)

    executor = _chat_tool_executor(local_executor_factory=lambda: _FakeLocalExecutor())

    assert isinstance(executor, NoopToolExecutor)


def test_chat_tool_executor_uses_laee_only_with_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from infrastructure.tools.laee_tool_executor import LaeeToolExecutor

    monkeypatch.setenv("MORPHIC_CHAT_TOOL_EXECUTION", "laee")

    executor = _chat_tool_executor(local_executor_factory=lambda: _FakeLocalExecutor())

    assert isinstance(executor, LaeeToolExecutor)


def test_chat_tool_executor_rejects_unknown_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MORPHIC_CHAT_TOOL_EXECUTION", "always")

    with pytest.raises(ValueError) as exc_info:
        _chat_tool_executor(local_executor_factory=lambda: _FakeLocalExecutor())

    assert "Invalid tool execution mode" in str(exc_info.value)


def test_chat_doctor_invalid_hook_execution_mode_exits_with_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MORPHIC_CHAT_HOOK_EXECUTION", "always")

    with runner.isolated_filesystem():
        result = runner.invoke(app, ["chat", "--doctor", "--json"])

    assert result.exit_code == 2
    assert "Invalid hook execution mode" in result.output


def test_chat_doctor_invalid_tool_execution_mode_exits_with_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MORPHIC_CHAT_TOOL_EXECUTION", "always")

    with runner.isolated_filesystem():
        result = runner.invoke(app, ["chat", "--doctor", "--json"])

    assert result.exit_code == 2
    assert "Invalid tool execution mode" in result.output


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


@pytest.mark.asyncio
async def test_chat_doctor_payload_reports_laee_tool_execution_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MORPHIC_CHAT_TOOL_EXECUTION", "laee")

    payload = await _chat_doctor_payload(engine_registry=_FakeEngineRegistry())

    assert payload["tool_execution_mode"] == "laee"


def test_chat_repl_status_and_quit_creates_session_ledger() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["chat"], input="/status\n/quit\n")

        assert result.exit_code == 0
        assert "Morphic chat session" in result.output
        assert "session=" in result.output
        assert "session ended" in result.output
        ledgers = list(Path(".morphic/sessions").glob("*.jsonl"))
        assert len(ledgers) == 1


def test_chat_repl_hooks_run_records_hook_events_in_current_session() -> None:
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

        result = runner.invoke(app, ["chat"], input="/hooks run pre_tool\n/quit\n")

        assert result.exit_code == 0
        assert "hooks type=pre_tool mode=noop succeeded=1 failed=0 skipped=0" in result.output
        ledgers = list(Path(".morphic/sessions").glob("*.jsonl"))
        assert len(ledgers) == 1
        events = [
            json.loads(line)
            for line in ledgers[0].read_text(encoding="utf-8").splitlines()
        ]
        assert any(
            event["type"] == "slash_command"
            and event["payload"]["command"] == "/hooks run pre_tool"
            for event in events
        )
        assert any(event["type"] == "hook_execution_completed" for event in events)
        assert any(event["payload"].get("hook_name") == "pre-log" for event in events)


def test_chat_repl_hooks_run_respects_shell_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MORPHIC_CHAT_HOOK_EXECUTION", "shell")
    with runner.isolated_filesystem():
        hook_dir = Path(".morphic/hooks")
        hook_dir.mkdir(parents=True)
        (hook_dir / "pre.json").write_text(
            json.dumps(
                {
                    "command": "echo repl-hook-ok",
                    "enabled": True,
                    "name": "pre-log",
                    "type": "pre_tool",
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        result = runner.invoke(app, ["chat"], input="/hooks run pre_tool\n/quit\n")

        assert result.exit_code == 0
        assert "hooks type=pre_tool mode=shell succeeded=1 failed=0 skipped=0" in result.output
        assert Path(".morphic/audit_log.jsonl").exists()


def test_chat_repl_tools_run_records_tool_and_hook_events() -> None:
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

        result = runner.invoke(
            app,
            ["chat"],
            input='/tools run fs_read {"path":"README.md"}\n/quit\n',
        )

        assert result.exit_code == 0
        assert "tools tool=fs_read mode=noop success=True" in result.output
        ledgers = list(Path(".morphic/sessions").glob("*.jsonl"))
        assert len(ledgers) == 1
        events = [
            json.loads(line)
            for line in ledgers[0].read_text(encoding="utf-8").splitlines()
        ]
        assert any(
            event["type"] == "slash_command"
            and event["payload"]["command"] == '/tools run fs_read {"path":"README.md"}'
            for event in events
        )
        assert any(event["type"] == "hook_execution_completed" for event in events)
        assert any(event["type"] == "tool_call_completed" for event in events)
        tool_completed = next(
            event for event in events if event["type"] == "tool_call_completed"
        )
        assert "not executed" in tool_completed["payload"]["stdout_summary"]


def test_chat_repl_tools_run_rejects_invalid_json_args() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["chat"], input="/tools run fs_read {bad}\n/quit\n")

        assert result.exit_code == 0
        assert "invalid JSON arguments" in result.output


def test_chat_repl_tools_run_respects_laee_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MORPHIC_CHAT_TOOL_EXECUTION", "laee")
    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            ["chat"],
            input='/tools run shell_exec {"cmd":"echo tool-ok"}\n/quit\n',
        )

        assert result.exit_code == 0
        assert "tools tool=shell_exec mode=laee success=True" in result.output
        audit_log = Path(".morphic/audit_log.jsonl")
        assert audit_log.exists()
        assert "shell_exec" in audit_log.read_text(encoding="utf-8")


def test_code_one_shot_runs_goal_without_repl() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(app, ["code", "implement Phase 4"])

        assert result.exit_code == 0
        assert "Plan next step for: implement Phase 4" in result.output
        ledgers = list(Path(".morphic/sessions").glob("*.jsonl"))
        assert len(ledgers) == 1


def test_code_route_council_flag_uses_routed_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    from interface.cli import chat_command

    calls: list[bool] = []

    def fake_council_runtime(
        *, route_council: bool = False, **_kwargs: object
    ) -> _FakeCouncilRuntime:
        calls.append(route_council)
        return _FakeCouncilRuntime()

    monkeypatch.setattr(chat_command, "_chat_engine_registry", _FakeEngineRegistry)
    monkeypatch.setattr(chat_command, "_chat_council_runtime", fake_council_runtime)

    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            ["code", "--route-council", "implement routed council"],
        )

        assert result.exit_code == 0
        assert calls == [True]
        assert "Routed response for: implement routed council" in result.output


def test_code_defaults_to_local_council_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from interface.cli import chat_command

    calls: list[bool] = []

    def fake_council_runtime(
        *, route_council: bool = False, **_kwargs: object
    ) -> _FakeCouncilRuntime:
        calls.append(route_council)
        return _FakeCouncilRuntime()

    monkeypatch.setattr(chat_command, "_chat_engine_registry", _FakeEngineRegistry)
    monkeypatch.setattr(chat_command, "_chat_council_runtime", fake_council_runtime)

    with runner.isolated_filesystem():
        result = runner.invoke(app, ["code", "implement default council"])

        assert result.exit_code == 0
        assert calls == [False]


def test_chat_route_council_flag_uses_routed_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    from interface.cli import chat_command

    calls: list[bool] = []

    def fake_council_runtime(
        *, route_council: bool = False, **_kwargs: object
    ) -> _FakeCouncilRuntime:
        calls.append(route_council)
        return _FakeCouncilRuntime()

    monkeypatch.setattr(chat_command, "_chat_engine_registry", _FakeEngineRegistry)
    monkeypatch.setattr(chat_command, "_chat_council_runtime", fake_council_runtime)

    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            ["chat", "--route-council"],
            input="implement routed council\n/quit\n",
        )

        assert result.exit_code == 0
        assert calls == [True]
        assert "Routed response for: implement routed council" in result.output


def test_code_route_council_role_flags_are_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from interface.cli import chat_command

    calls: list[dict[str, object]] = []

    def fake_council_runtime(
        *,
        route_council: bool = False,
        planner_engine: str | None = None,
        critic_engine: str | None = None,
        leader_engine: str | None = None,
    ) -> _FakeCouncilRuntime:
        calls.append(
            {
                "critic_engine": critic_engine,
                "leader_engine": leader_engine,
                "planner_engine": planner_engine,
                "route_council": route_council,
            }
        )
        return _FakeCouncilRuntime()

    monkeypatch.setattr(chat_command, "_chat_engine_registry", _FakeEngineRegistry)
    monkeypatch.setattr(chat_command, "_chat_council_runtime", fake_council_runtime)

    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            [
                "code",
                "--route-council",
                "--planner-engine",
                "codex_cli",
                "--critic-engine",
                "claude_code",
                "--leader-engine",
                "gemini_cli",
                "implement preferred routing",
            ],
        )

        assert result.exit_code == 0
        assert calls == [
            {
                "critic_engine": "claude_code",
                "leader_engine": "gemini_cli",
                "planner_engine": "codex_cli",
                "route_council": True,
            }
        ]


def test_chat_council_runtime_builds_role_engine_preferences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from interface.cli import chat_command

    class _Container:
        route_to_engine = object()

    captured: dict[str, object] = {}

    class _FakeRouteRuntime(_FakeCouncilRuntime):
        def __init__(
            self,
            route_to_engine: object,
            *,
            role_engines: dict[CouncilRole, AgentEngineType] | None = None,
        ) -> None:
            captured["role_engines"] = role_engines
            captured["route_to_engine"] = route_to_engine

    monkeypatch.setenv("MORPHIC_CHAT_ROUTE_COUNCIL", "0")
    monkeypatch.setattr(chat_command, "_get_container", lambda: _Container())
    monkeypatch.setattr(chat_command, "RouteChatCouncilRuntime", _FakeRouteRuntime)

    runtime = chat_command._chat_council_runtime(
        route_council=True,
        planner_engine="codex_cli",
        critic_engine="claude_code",
        leader_engine="gemini_cli",
    )

    assert isinstance(runtime, _FakeRouteRuntime)
    assert captured["role_engines"] == {
        CouncilRole.PLANNER: AgentEngineType.CODEX_CLI,
        CouncilRole.CRITIC: AgentEngineType.CLAUDE_CODE,
        CouncilRole.LEADER: AgentEngineType.GEMINI_CLI,
    }


def test_role_engine_preferences_reject_invalid_engine_id() -> None:
    with pytest.raises(ValueError) as exc_info:
        _role_engine_preferences(
            planner_engine="missing_engine",
            critic_engine=None,
            leader_engine=None,
        )

    message = str(exc_info.value)
    assert "Invalid planner engine" in message
    assert "codex_cli" in message


def test_code_invalid_role_engine_exits_with_diagnostic() -> None:
    with runner.isolated_filesystem():
        result = runner.invoke(
            app,
            [
                "code",
                "--route-council",
                "--planner-engine",
                "missing_engine",
                "implement preferred routing",
            ],
        )

        assert result.exit_code == 2
        assert "Invalid planner engine" in result.output
        assert "missing_engine" in result.output


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
