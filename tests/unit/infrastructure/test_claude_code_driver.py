"""Tests for ClaudeCodeDriver — Claude Code CLI headless mode."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from domain.entities.agent_engine_event import AgentEngineEvent, AgentEngineEventType
from domain.entities.chat_session import PermissionMode
from domain.ports.agent_engine import AgentEngineCapabilities, AgentEngineResult
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.agent_cli._subprocess_base import CLIResult
from infrastructure.agent_cli.claude_code_driver import ClaudeCodeDriver


class _CollectingEventSink:
    def __init__(self) -> None:
        self.events: list[AgentEngineEvent] = []

    async def publish(self, event: AgentEngineEvent) -> None:
        self.events.append(event)


@pytest.fixture()
def driver():
    return ClaudeCodeDriver(enabled=True, cli_path="claude")


@pytest.fixture()
def disabled_driver():
    return ClaudeCodeDriver(enabled=False)


# ── Construction ──


class TestConstruction:
    def test_engine_type(self, driver):
        assert driver.engine_type == AgentEngineType.CLAUDE_CODE

    def test_default_cli_path(self):
        d = ClaudeCodeDriver(enabled=True)
        assert d._cli_path == "claude"

    def test_custom_cli_path(self):
        d = ClaudeCodeDriver(enabled=True, cli_path="/usr/local/bin/claude")
        assert d._cli_path == "/usr/local/bin/claude"


# ── is_available ──


class TestIsAvailable:
    @pytest.mark.asyncio
    async def test_available_when_enabled_and_binary_exists(self, driver):
        with patch.object(ClaudeCodeDriver, "_check_cli_exists", return_value=True):
            assert await driver.is_available() is True

    @pytest.mark.asyncio
    async def test_unavailable_when_disabled(self, disabled_driver):
        assert await disabled_driver.is_available() is False

    @pytest.mark.asyncio
    async def test_unavailable_when_binary_missing(self, driver):
        with patch.object(ClaudeCodeDriver, "_check_cli_exists", return_value=False):
            assert await driver.is_available() is False


# ── run_task ──


class TestRunTask:
    @pytest.mark.asyncio
    async def test_scoped_stream_normalizes_claude_jsonl(self, driver):
        lines = [
            json.dumps(
                {
                    "type": "system",
                    "subtype": "init",
                    "session_id": "claude-session-1",
                    "model": "claude-sonnet-4-6",
                }
            ),
            json.dumps(
                {
                    "type": "assistant",
                    "session_id": "claude-session-1",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "tool-1",
                                "name": "Bash",
                                "input": {"command": "pytest -q"},
                            }
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "user",
                    "session_id": "claude-session-1",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tool-1",
                                "content": "3517 passed",
                            }
                        ]
                    },
                }
            ),
            json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "session_id": "claude-session-1",
                    "result": "All tests pass.",
                    "total_cost_usd": 0.02,
                }
            ),
        ]

        async def fake_stream(cmd, *, timeout, on_stdout_line, env=None, cwd=None):
            del cmd, timeout, env, cwd
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

        assert result.output == "All tests pass."
        assert result.metadata["session_id"] == "claude-session-1"
        assert result.cost_usd == 0.02
        assert [event.type for event in sink.events] == [
            AgentEngineEventType.RUN_STARTED,
            AgentEngineEventType.TOOL_STARTED,
            AgentEngineEventType.TOOL_COMPLETED,
            AgentEngineEventType.RUN_COMPLETED,
        ]

    @pytest.mark.asyncio
    async def test_resume_stream_uses_explicit_session_id(self, driver):
        sink = _CollectingEventSink()
        with patch.object(
            driver,
            "_run_cli_streaming",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.resume_task_scoped_stream(
                "Continue",
                resume_session_id="claude-session-1",
                workspace_root="/workspace",
                permission_mode=PermissionMode.WORKSPACE_WRITE,
                event_sink=sink,
            )

        cmd = mock_run.call_args[0][0]
        assert cmd[cmd.index("--resume") + 1] == "claude-session-1"
        assert cmd[cmd.index("--output-format") + 1] == "stream-json"
        assert mock_run.call_args.kwargs["cwd"] == "/workspace"
    @pytest.mark.asyncio
    async def test_valid_json_output(self, driver):
        json_output = json.dumps({"result": "Hello world", "session_id": "sess-123"})
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("Say hello")
        assert isinstance(result, AgentEngineResult)
        assert result.success is True
        assert result.output == "Hello world"
        assert result.engine == AgentEngineType.CLAUDE_CODE
        assert result.metadata.get("session_id") == "sess-123"

    @pytest.mark.asyncio
    async def test_session_id_in_metadata(self, driver):
        json_output = json.dumps({"result": "ok", "session_id": "abc-456"})
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.metadata["session_id"] == "abc-456"

    @pytest.mark.asyncio
    async def test_invalid_json_fallback(self, driver):
        """When stdout is not valid JSON, use raw stdout as output."""
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="raw text output", stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.success is True
        assert result.output == "raw text output"

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="", stderr="error msg", returncode=1),
        ):
            result = await driver.run_task("test")
        assert result.success is False
        assert "error msg" in result.error

    @pytest.mark.asyncio
    async def test_timeout(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="", stderr="Command timed out after 10s", returncode=-1),
        ):
            result = await driver.run_task("test", timeout_seconds=10)
        assert result.success is False
        assert "timed out" in result.error

    @pytest.mark.asyncio
    async def test_disabled_returns_error(self, disabled_driver):
        result = await disabled_driver.run_task("test")
        assert result.success is False
        assert "disabled" in result.error

    @pytest.mark.asyncio
    async def test_command_shape(self, driver):
        """Verify the exact CLI command constructed."""
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("Do something")
        cmd = mock_run.call_args[0][0]
        expected = [
            "claude",
            "-p",
            "Do something",
            "--output-format",
            "json",
            "--max-turns",
            "10",
            "--permission-mode",
            "plan",
        ]
        assert cmd == expected

    @pytest.mark.asyncio
    async def test_scoped_workspace_write_preserves_native_harness(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task_scoped(
                "Fix tests",
                workspace_root="/workspace",
                permission_mode=PermissionMode.WORKSPACE_WRITE,
            )

        cmd = mock_run.call_args[0][0]
        assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"
        assert mock_run.call_args.kwargs["cwd"] == "/workspace"
        assert "--setting-sources" not in cmd
        assert "--allowedTools" not in cmd
        assert "--disable-slash-commands" not in cmd

    @pytest.mark.asyncio
    async def test_danger_full_access_requires_explicit_bypass_flag(self, driver):
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task_scoped(
                "Fix tests",
                workspace_root="/workspace",
                permission_mode=PermissionMode.DANGER_FULL_ACCESS,
            )

        cmd = mock_run.call_args[0][0]
        assert "--dangerously-skip-permissions" in cmd
        assert cmd[cmd.index("--permission-mode") + 1] == "bypassPermissions"

    @pytest.mark.asyncio
    async def test_confirm_destructive_is_rejected_before_subprocess(self, driver):
        with patch.object(driver, "_run_cli") as mock_run:
            result = await driver.run_task_scoped(
                "Fix tests",
                workspace_root="/workspace",
                permission_mode=PermissionMode.CONFIRM_DESTRUCTIVE,
            )

        assert result.success is False
        assert "confirm-destructive" in str(result.error)
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_model_override(self, driver):
        """Model flag is appended when specified."""
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout="{}", stderr="", returncode=0),
        ) as mock_run:
            await driver.run_task("test", model="claude-opus-4-6")
        cmd = mock_run.call_args[0][0]
        assert "--model" in cmd
        assert "claude-opus-4-6" in cmd

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
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            }
        )
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.metadata["usage"] == {"prompt_tokens": 100, "completion_tokens": 50}

    @pytest.mark.asyncio
    async def test_model_from_json_response(self, driver):
        json_output = json.dumps({"result": "ok", "model": "claude-sonnet-4-6"})
        with patch.object(
            driver,
            "_run_cli",
            return_value=CLIResult(stdout=json_output, stderr="", returncode=0),
        ):
            result = await driver.run_task("test")
        assert result.model_used == "claude-sonnet-4-6"


# ── get_capabilities ──


class TestGetCapabilities:
    def test_returns_capabilities(self, driver):
        caps = driver.get_capabilities()
        assert isinstance(caps, AgentEngineCapabilities)
        assert caps.engine_type == AgentEngineType.CLAUDE_CODE
        assert caps.max_context_tokens == 200_000
        assert caps.supports_parallel is True
        assert caps.supports_streaming is True
