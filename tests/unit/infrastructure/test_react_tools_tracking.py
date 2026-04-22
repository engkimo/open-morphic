"""Tests for ReactExecutor tools_used/data_sources tracking (Sprint 12.1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock

import pytest

from domain.entities.execution import Observation
from domain.value_objects.status import ObservationStatus
from infrastructure.task_graph.react_executor import ReactExecutor


@dataclass
class FakeToolCall:
    id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass
class FakeLLMResponse:
    content: str
    model: str = "test-model"
    cost_usd: float = 0.01
    tool_calls: list[FakeToolCall] | None = None


def _make_executor(responses: list[FakeLLMResponse]) -> ReactExecutor:
    """Build ReactExecutor with mocked LLM and executor."""
    llm = AsyncMock()
    llm.complete_with_tools = AsyncMock(side_effect=responses)

    executor = AsyncMock()
    executor.execute = AsyncMock(
        return_value=Observation(
            status=ObservationStatus.SUCCESS,
            result='{"results": [{"url": "https://example.com/movie", "title": "Test"}]}',
        )
    )

    schemas = [
        {"type": "function", "function": {"name": "web_search", "parameters": {}}},
        {"type": "function", "function": {"name": "web_fetch", "parameters": {}}},
        {"type": "function", "function": {"name": "shell_exec", "parameters": {}}},
    ]

    return ReactExecutor(llm=llm, executor=executor, tool_schemas=schemas)


class TestToolsUsedTracking:
    @pytest.mark.asyncio
    async def test_no_tools_returns_none(self) -> None:
        """When no tool calls are made, tools_used should be None."""
        executor = _make_executor(
            [
                FakeLLMResponse(content="The answer is 42"),
            ]
        )
        result = await executor.execute(system_prompt="test", user_prompt="test")
        assert result.tools_used is None

    @pytest.mark.asyncio
    async def test_single_tool_tracked(self) -> None:
        """Single tool call should be tracked in tools_used."""
        executor = _make_executor(
            [
                FakeLLMResponse(
                    content="Let me search",
                    tool_calls=[
                        FakeToolCall(
                            id="tc1",
                            tool_name="web_search",
                            arguments={"q": "test"},
                        )
                    ],
                ),
                FakeLLMResponse(content="Found results"),
            ]
        )
        result = await executor.execute(system_prompt="test", user_prompt="test")
        assert result.tools_used == ["web_search"]

    @pytest.mark.asyncio
    async def test_multiple_tools_tracked(self) -> None:
        """Multiple tool calls should be tracked and sorted."""
        executor = _make_executor(
            [
                FakeLLMResponse(
                    content="Searching",
                    tool_calls=[
                        FakeToolCall(id="tc1", tool_name="web_search", arguments={"q": "test"}),
                        FakeToolCall(
                            id="tc2",
                            tool_name="web_fetch",
                            arguments={"url": "https://example.com"},
                        ),
                    ],
                ),
                FakeLLMResponse(content="Done"),
            ]
        )
        result = await executor.execute(system_prompt="test", user_prompt="test")
        assert result.tools_used == ["web_fetch", "web_search"]


class TestDataSourcesTracking:
    @pytest.mark.asyncio
    async def test_urls_extracted_from_web_search(self) -> None:
        """URLs from web_search observations should be captured."""
        executor = _make_executor(
            [
                FakeLLMResponse(
                    content="Searching",
                    tool_calls=[
                        FakeToolCall(
                            id="tc1",
                            tool_name="web_search",
                            arguments={"q": "tickets"},
                        )
                    ],
                ),
                FakeLLMResponse(content="Found it"),
            ]
        )
        result = await executor.execute(system_prompt="test", user_prompt="test")
        assert result.data_sources is not None
        assert "https://example.com/movie" in result.data_sources

    @pytest.mark.asyncio
    async def test_no_urls_from_non_data_tools(self) -> None:
        """URLs from non-data tools (e.g. shell_exec) should not be captured."""
        llm = AsyncMock()
        llm.complete_with_tools = AsyncMock(
            side_effect=[
                FakeLLMResponse(
                    content="Running",
                    tool_calls=[
                        FakeToolCall(
                            id="tc1",
                            tool_name="shell_exec",
                            arguments={"cmd": "echo"},
                        )
                    ],
                ),
                FakeLLMResponse(content="Done"),
            ]
        )
        executor_mock = AsyncMock()
        executor_mock.execute = AsyncMock(
            return_value=Observation(
                status=ObservationStatus.SUCCESS,
                result="Output from https://example.com/data",
            )
        )
        react = ReactExecutor(
            llm=llm,
            executor=executor_mock,
            tool_schemas=[
                {"type": "function", "function": {"name": "shell_exec", "parameters": {}}},
            ],
        )
        result = await react.execute(system_prompt="test", user_prompt="test")
        assert result.data_sources is None


class TestMCPToolRouting:
    @pytest.mark.asyncio
    async def test_mcp_tool_routed_to_client(self) -> None:
        """MCP tool calls should be routed to MCPClient, not LAEE."""
        mcp_client = AsyncMock()
        mcp_client.call_tool = AsyncMock(return_value="MCP result data")

        llm = AsyncMock()
        llm.complete_with_tools = AsyncMock(
            side_effect=[
                FakeLLMResponse(
                    content="Calling brave",
                    tool_calls=[
                        FakeToolCall(
                            id="tc1",
                            tool_name="brave_search",
                            arguments={"q": "test"},
                        )
                    ],
                ),
                FakeLLMResponse(content="Got results"),
            ]
        )
        executor_mock = AsyncMock()

        react = ReactExecutor(
            llm=llm,
            executor=executor_mock,
            tool_schemas=[
                {"type": "function", "function": {"name": "brave_search", "parameters": {}}},
            ],
            mcp_client=mcp_client,
            mcp_tool_names={"brave_search"},
        )
        react._mcp_tool_server["brave_search"] = "brave"

        result = await react.execute(system_prompt="test", user_prompt="test")

        mcp_client.call_tool.assert_called_once_with(
            server_name="brave",
            tool_name="brave_search",
            arguments={"q": "test"},
        )
        # LAEE executor should NOT have been called
        executor_mock.execute.assert_not_called()
        assert result.tools_used == ["brave_search"]
