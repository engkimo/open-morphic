"""Tests for CodexCLIDriver — OpenAI Codex CLI exec mode."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from domain.entities.agent_engine_event import AgentEngineEvent, AgentEngineEventType
from domain.entities.chat_session import PermissionMode
from domain.ports.agent_engine import AgentEngineCapabilities, AgentEngineResult
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.agent_cli._subprocess_base import CLIResult
from infrastructure.agent_cli.codex_cli_driver import CodexCLIDriver


class _CollectingEventSink:
    def __init__(self) -> None:
        self.events: list[AgentEngineEvent] = []

    async def publish(self, event: AgentEngineEvent) -> None:
        self.events.append(event)


@pytest.fixture()
def driver():
    return CodexCLIDriver(enabled=True, cli_path="codex")


@pytest.fixture()
def disabled_driver():
    return CodexCLIDriver(enabled=False)


# ── Construction ──


class TestConstruction:
    def test_engine_type(self, driver):
        assert driver.engine_type == AgentEngineType.CODEX_CLI

    def test_default_cli_path(self):
        d = CodexCLIDriver(enabled=True)
        assert d._cli_path == "codex"

    def test_custom_cli_path(self):
        d = CodexCLIDriver(enabled=True, cli_path="/opt/codex")
        assert d._cli_path == "/opt/codex"


# ── is_available ──


class TestIsAvailable:
    @pytest.mark.asyncio
    async def test_available_when_enabled_and_binary_exists(self, driver):
        with patch.object(CodexCLIDriver, "_check_cli_exists", return_value=True):
            assert await driver.is_available() is True

    @pytest.mark.asyncio
    async def test_unavailable_when_disabled(self, disabled_driver):
        assert await disabled_driver.is_available() is False

    @pytest.mark.asyncio
    async def test_unavailable_when_binary_missing(self, driver):
        with patch.object(CodexCLIDriver, "_check_cli_exists", return_value=False):
            assert await driver.is_available() is False


# ── run_task ──


class TestRunTask:
    @pytest.mark.asyncio
    async def test_scoped_stream_publishes_jsonl_events_incrementally(self, driver):
        lines = [
            json.dumps({"type": "thread.started", "thread_id": "thread-live"}),
            json.dumps({"type": "turn.started"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "message-1",
                        "type": "agent_message",
                        "text": "Streaming complete.",
                    },
                }
            ),
            json.dumps({"type": "turn.completed", "usage": {"input_tokens": 10}}),
        ]

        async def fake_stream(cmd, *, timeout, on_stdout_line, env=None):
            del cmd, timeout, env
            for line in lines:
                await on_stdout_line(line)
            return CLIResult(stdout="\n".join(lines), stderr="", returncode=0)

        sink = _CollectingEventSink()
        with patch.object(driver, "_run_cli_streaming", side_effect=fake_stream):
            result = await driver.run_task_scoped_stream(
                "Fix tests",
                workspace_root="/workspace",
                permission_mode=PermissionMode.WORKSPACE_WRITE,
                event_sink=sink,
            )

        assert result.success is True
        assert result.output == "Streaming complete."
        assert [event.type for event in sink.events] == [
            AgentEngineEventType.RUN_STARTED,
            AgentEngineEventType.TURN_STARTED,
            AgentEngineEventType.ASSISTANT_MESSAGE,
            AgentEngineEventType.RUN_COMPLETED,
        ]
        assert [event.sequence for event in sink.events] == [0, 1, 2, 3]
        assert all(event.session_id == "thread-live" for event in sink.events)

    @pytest.mark.asyncio
    async def test_jsonl_output_is_normalized_and_final_message_selected(self, driver):
        json_output = "\n".join(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-1"}),
                json.dumps({"type": "turn.started"}),
                json.dumps(
                    {
                        "type": "item.started",
                        "item": {
                            "id": "item-1",
                            "type": "command_execution",
                            "command": "pytest -q",
                            "status": "in_progress",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item-1",
                            "type": "command_execution",
                            "command": "pytest -q",
                            "status": "completed",
                            "exit_code": 0,
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item-2",
                            "type": "agent_message",
                            "text": "Implemented the fix.",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 100,
                            "cached_input_tokens": 80,
                            "output_tokens": 20,
                            "reasoning_output_tokens": 5,
                        },
                    }
                ),
            ]
        )
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("Fix tests")

        assert result.success is True
        assert result.output == "Implemented the fix."
        assert result.metadata["session_id"] == "thread-1"
        assert result.metadata["usage"] == {
            "input_tokens": 100,
            "cached_input_tokens": 80,
            "output_tokens": 20,
            "reasoning_output_tokens": 5,
        }
        assert [event["type"] for event in result.metadata["events"]] == [
            AgentEngineEventType.RUN_STARTED.value,
            AgentEngineEventType.TURN_STARTED.value,
            AgentEngineEventType.TOOL_STARTED.value,
            AgentEngineEventType.TOOL_COMPLETED.value,
            AgentEngineEventType.ASSISTANT_MESSAGE.value,
            AgentEngineEventType.RUN_COMPLETED.value,
        ]

    @pytest.mark.asyncio
    async def test_valid_json_output(self, driver):
        json_output = json.dumps({"result": "Generated code"})
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("Write a function")
        assert isinstance(result, AgentEngineResult)
        assert result.success is True
        assert result.output == "Generated code"
        assert result.engine == AgentEngineType.CODEX_CLI

    @pytest.mark.asyncio
    async def test_invalid_json_fallback(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="plain text", stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.success is True
        assert result.output == "plain text"

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="", stderr="codex error", returncode=1),
        ):
            result = await driver.run_task("test")
        assert result.success is False
        assert "codex error" in result.error

    @pytest.mark.asyncio
    async def test_timeout(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="", stderr="Command timed out after 60s", returncode=-1),
        ):
            result = await driver.run_task("test", timeout_seconds=60)
        assert result.success is False
        assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_disabled_returns_error(self, disabled_driver):
        result = await disabled_driver.run_task("test")
        assert result.success is False
        assert "disabled" in result.error

    @pytest.mark.asyncio
    async def test_command_shape(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task_scoped(
                "Build feature",
                workspace_root="/workspace",
                permission_mode=PermissionMode.READ_ONLY,
            )
        cmd = mock_run.call_args[0][0]
        assert cmd == [
            "codex",
            "exec",
            "--json",
            "--sandbox",
            "read-only",
            "--cd",
            "/workspace",
            "Build feature",
        ]

    @pytest.mark.asyncio
    async def test_resume_command_preserves_sandbox_and_workspace(self, driver):
        sink = _CollectingEventSink()
        with patch.object(
            driver,
            "_run_cli_streaming",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.resume_task_scoped_stream(
                "Continue fixing tests",
                resume_session_id="thread-1",
                workspace_root="/workspace",
                permission_mode=PermissionMode.WORKSPACE_WRITE,
                event_sink=sink,
            )

        assert mock_run.call_args[0][0] == [
            "codex",
            "exec",
            "--json",
            "--sandbox",
            "workspace-write",
            "--cd",
            "/workspace",
            "resume",
            "thread-1",
            "Continue fixing tests",
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("permission_mode", "sandbox"),
        [
            (PermissionMode.READ_ONLY, "read-only"),
            (PermissionMode.WORKSPACE_WRITE, "workspace-write"),
            (PermissionMode.DANGER_FULL_ACCESS, "danger-full-access"),
        ],
    )
    async def test_permission_mode_maps_to_explicit_sandbox(
        self,
        driver,
        permission_mode,
        sandbox,
    ):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task_scoped(
                "test",
                workspace_root="/workspace",
                permission_mode=permission_mode,
            )

        cmd = mock_run.call_args[0][0]
        assert cmd[cmd.index("--sandbox") + 1] == sandbox
        assert "--full-auto" not in cmd

    @pytest.mark.asyncio
    async def test_confirm_destructive_is_rejected_before_subprocess(self, driver):
        with patch.object(driver, "_run_cli") as mock_run:
            result = await driver.run_task_scoped(
                "test",
                workspace_root="/workspace",
                permission_mode=PermissionMode.CONFIRM_DESTRUCTIVE,
            )

        assert result.success is False
        assert "confirm-destructive" in str(result.error)
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_malformed_jsonl_line_does_not_hide_valid_final_message(self, driver):
        stdout = "\n".join(
            [
                "not-json",
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"id": "a", "type": "agent_message", "text": "done"},
                    }
                ),
            ]
        )
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=stdout, stderr="", returncode=0),
        ):
            result = await driver.run_task("test")

        assert result.output == "done"
        assert result.metadata["parse_errors"] == 1

    @pytest.mark.asyncio
    async def test_model_override(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("test", model="gpt-5-codex")
        cmd = mock_run.call_args[0][0]
        assert "--model" in cmd
        assert "gpt-5-codex" in cmd

    @pytest.mark.asyncio
    async def test_no_model_flag_when_none(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("test")
        cmd = mock_run.call_args[0][0]
        assert "--model" not in cmd

    @pytest.mark.asyncio
    async def test_duration_measured(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.duration_seconds >= 0.0

    @pytest.mark.asyncio
    async def test_usage_in_metadata(self, driver):
        json_output = json.dumps(
            {
                "result": "ok",
                "usage": {"prompt_tokens": 200, "completion_tokens": 100},
            }
        )
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.metadata["usage"]["prompt_tokens"] == 200

    @pytest.mark.asyncio
    async def test_model_from_json_response(self, driver):
        json_output = json.dumps({"result": "ok", "model": "gpt-5-codex"})
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.model_used == "gpt-5-codex"

    @pytest.mark.asyncio
    async def test_empty_stderr_uses_exit_code(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="", stderr="", returncode=2),
        ):
            result = await driver.run_task("test")
        assert result.success is False
        assert "Exit code 2" in result.error


# ── get_capabilities ──


class TestGetCapabilities:
    def test_returns_capabilities(self, driver):
        caps = driver.get_capabilities()
        assert isinstance(caps, AgentEngineCapabilities)
        assert caps.engine_type == AgentEngineType.CODEX_CLI
        assert caps.supports_sandbox is True
        assert caps.supports_mcp is True
        assert caps.supports_streaming is True
