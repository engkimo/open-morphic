"""Tests for LiteLLMGateway.complete_with_tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from infrastructure.llm.litellm_gateway import LiteLLMGateway


@pytest.fixture
def gateway():
    ollama = AsyncMock()
    ollama.is_running = AsyncMock(return_value=True)
    ollama.list_models = AsyncMock(return_value=["qwen3:8b"])

    cost_tracker = AsyncMock()
    cost_tracker.record = AsyncMock()

    settings = MagicMock()
    settings.ollama_base_url = "http://127.0.0.1:11434"
    settings.ollama_default_model = "qwen3:8b"
    settings.local_first = True

    return LiteLLMGateway(ollama=ollama, cost_tracker=cost_tracker, settings=settings)


def _make_tool_call(tc_id="call_1", name="web_search", arguments='{"query": "test"}'):
    tc = MagicMock()
    tc.id = tc_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


def _make_response(content="", tool_calls=None, cost=0.001):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls

    choice = MagicMock()
    choice.message = msg

    usage = MagicMock()
    usage.prompt_tokens = 100
    usage.completion_tokens = 50

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    resp._hidden_params = {"response_cost": cost}
    return resp


class TestCompleteWithTools:
    @pytest.mark.asyncio
    @patch("infrastructure.llm.litellm_gateway.litellm.acompletion")
    async def test_no_tool_calls(self, mock_acompletion, gateway):
        mock_acompletion.return_value = _make_response(content="Hello", tool_calls=None)

        tools = [{"type": "function", "function": {"name": "web_search"}}]
        result = await gateway.complete_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
            model="ollama/qwen3:8b",
        )

        assert result.content == "Hello"
        assert result.tool_calls == []
        assert result.model == "ollama/qwen3:8b"

    @pytest.mark.asyncio
    @patch("infrastructure.llm.litellm_gateway.litellm.acompletion")
    async def test_with_tool_calls(self, mock_acompletion, gateway):
        tc = _make_tool_call("call_1", "web_search", '{"query": "python"}')
        mock_acompletion.return_value = _make_response(content="", tool_calls=[tc])

        tools = [{"type": "function", "function": {"name": "web_search"}}]
        result = await gateway.complete_with_tools(
            messages=[{"role": "user", "content": "search python"}],
            tools=tools,
            model="ollama/qwen3:8b",
        )

        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].id == "call_1"
        assert result.tool_calls[0].tool_name == "web_search"
        assert result.tool_calls[0].arguments == {"query": "python"}

    @pytest.mark.asyncio
    @patch("infrastructure.llm.litellm_gateway.litellm.acompletion")
    async def test_multiple_tool_calls(self, mock_acompletion, gateway):
        tc1 = _make_tool_call("call_1", "web_search", '{"query": "a"}')
        tc2 = _make_tool_call("call_2", "web_fetch", '{"url": "https://example.com"}')
        mock_acompletion.return_value = _make_response(content="", tool_calls=[tc1, tc2])

        result = await gateway.complete_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[],
            model="ollama/qwen3:8b",
        )

        assert len(result.tool_calls) == 2
        assert result.tool_calls[0].tool_name == "web_search"
        assert result.tool_calls[1].tool_name == "web_fetch"

    @pytest.mark.asyncio
    @patch("infrastructure.llm.litellm_gateway.litellm.acompletion")
    async def test_cost_tracking(self, mock_acompletion, gateway):
        mock_acompletion.return_value = _make_response(content="ok", cost=0.005)

        result = await gateway.complete_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            model="ollama/qwen3:8b",
        )

        assert result.cost_usd == 0.005
        gateway._cost_tracker.record.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("infrastructure.llm.litellm_gateway.litellm.acompletion")
    async def test_ollama_kwargs(self, mock_acompletion, gateway):
        mock_acompletion.return_value = _make_response(content="ok")

        await gateway.complete_with_tools(
            messages=[{"role": "user", "content": "hi"}],
            tools=[],
            model="ollama/qwen3:8b",
        )

        call_kwargs = mock_acompletion.call_args.kwargs
        assert call_kwargs["api_base"] == "http://127.0.0.1:11434"
        assert call_kwargs["extra_body"]["think"] is False

    @pytest.mark.asyncio
    @patch("infrastructure.llm.litellm_gateway.litellm.acompletion")
    async def test_invalid_json_arguments_fallback(self, mock_acompletion, gateway):
        tc = _make_tool_call("call_1", "web_search", "not-valid-json")
        mock_acompletion.return_value = _make_response(content="", tool_calls=[tc])

        result = await gateway.complete_with_tools(
            messages=[{"role": "user", "content": "test"}],
            tools=[],
            model="ollama/qwen3:8b",
        )

        assert result.tool_calls[0].arguments == {"raw": "not-valid-json"}
