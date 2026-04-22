"""ReactExecutor — Think-Act-Observe iterative loop.

Infrastructure layer: coordinates LLM tool-calling with LAEE tool execution.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from domain.entities.execution import Action, Observation
from domain.entities.react_trace import ReactStep, ReactTrace, ToolCallRecord
from domain.ports.llm_gateway import LLMGateway, ToolCallResult
from domain.ports.local_executor import LocalExecutorPort
from domain.ports.mcp_client import MCPClientPort
from domain.services.react_controller import ReactController
from domain.value_objects.status import ObservationStatus

logger = logging.getLogger(__name__)

# Tools whose observations may contain real-world data sources (URLs).
_DATA_SOURCE_TOOLS = frozenset({"web_search", "web_fetch", "browser_navigate", "browser_extract"})
_URL_RE = re.compile(r"https?://[^\s\"'<>\])+]+")


@dataclass
class ReactResult:
    """Result of a complete ReAct execution."""

    trace: ReactTrace
    final_answer: str
    total_cost_usd: float
    model_used: str
    tools_used: list[str] | None = None
    data_sources: list[str] | None = None


class ReactExecutor:
    """ReAct loop: LLM reasons, calls tools, observes results, repeats.

    Flow per iteration:
    1. Send messages + tool schemas to LLM
    2. If LLM returns tool_calls → execute via LAEE → append observations
    3. If LLM returns text only → that's the final answer
    4. Repeat until final answer or max_iterations
    """

    MAX_OBSERVATION_CHARS = 3000

    def __init__(
        self,
        llm: LLMGateway,
        executor: LocalExecutorPort,
        tool_schemas: list[dict[str, Any]] | None = None,
        max_iterations: int = 10,
        mcp_client: MCPClientPort | None = None,
        mcp_tool_names: set[str] | None = None,
    ) -> None:
        self._llm = llm
        self._executor = executor
        self._schemas = tool_schemas or []
        self._max = max_iterations
        self._controller = ReactController()
        self._mcp_client = mcp_client
        # Set of tool names that belong to MCP servers (for routing)
        self._mcp_tool_names = mcp_tool_names or set()
        # Map: mcp_tool_name → server_name (for call routing)
        self._mcp_tool_server: dict[str, str] = {}

    @property
    def mcp_client(self) -> MCPClientPort | None:
        """Public accessor for the MCP client (used by container for startup/shutdown)."""
        return self._mcp_client

    @property
    def mcp_tool_count(self) -> int:
        """Number of registered MCP tools."""
        return len(self._mcp_tool_names)

    @property
    def laee_tool_count(self) -> int:
        """Number of LAEE (non-MCP) tool schemas."""
        return len(self._schemas) - len(self._mcp_tool_names)

    async def execute(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 4096,
        allowed_tools: list[str] | None = None,
    ) -> ReactResult:
        """Run the ReAct loop until final answer or max iterations."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        tools = self._filter_tools(allowed_tools) if allowed_tools else self._schemas
        trace = ReactTrace()
        total_cost = 0.0
        model_used = model or ""
        # TD-180: Detect repetitive tool-call loops (same tool+args N times)
        _repeat_threshold = 3
        _last_call_sig: str | None = None
        _repeat_count = 0

        for i in range(self._max):
            response = await self._llm.complete_with_tools(
                messages=messages,
                tools=tools,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            total_cost += response.cost_usd
            model_used = response.model

            step = ReactStep(step_number=i, thought=response.content)

            should_continue, reason = self._controller.should_continue(
                step_count=i + 1,
                max_iterations=self._max,
                has_tool_calls=bool(response.tool_calls),
                has_final_answer=bool(response.content and not response.tool_calls),
            )

            if not response.tool_calls:
                # Final answer
                trace.final_answer = response.content
                trace.terminated_reason = "final_answer"
                trace.steps.append(step)
                logger.info("ReAct finished — step=%d reason=final_answer", i)
                break

            # Build assistant message with tool_calls for conversation history
            assistant_msg = self._build_assistant_message(response)
            messages.append(assistant_msg)

            # Execute each tool call
            for tc in response.tool_calls:
                step.tool_calls.append(
                    ToolCallRecord(
                        id=tc.id,
                        tool_name=tc.tool_name,
                        arguments=tc.arguments,
                    )
                )
                observation = await self._execute_tool(tc)
                truncated = observation[: self.MAX_OBSERVATION_CHARS]
                step.observations.append(truncated)

                tool_msg = self._controller.build_tool_result_message(
                    tool_call_id=tc.id,
                    tool_name=tc.tool_name,
                    result=truncated,
                )
                messages.append(tool_msg)

                logger.info(
                    "ReAct tool — step=%d tool=%s obs_len=%d",
                    i,
                    tc.tool_name,
                    len(truncated),
                )

            trace.steps.append(step)

            # TD-180: Detect repetitive tool-call loops
            if len(response.tool_calls) == 1:
                tc0 = response.tool_calls[0]
                sig = f"{tc0.tool_name}:{sorted(tc0.arguments.items())}"
                if sig == _last_call_sig:
                    _repeat_count += 1
                else:
                    _last_call_sig = sig
                    _repeat_count = 1
                if _repeat_count >= _repeat_threshold:
                    trace.terminated_reason = "repetitive_tool_loop"
                    logger.warning(
                        "ReAct stopped — step=%d tool=%s repeated %d times",
                        i, tc0.tool_name, _repeat_count,
                    )
                    break
            else:
                _last_call_sig = None
                _repeat_count = 0

            if not should_continue:
                trace.terminated_reason = reason  # type: ignore[assignment]
                logger.info("ReAct stopped — step=%d reason=%s", i, reason)
                break
        else:
            # Loop exhausted without break
            trace.terminated_reason = "max_iterations"
            logger.warning("ReAct hit max iterations (%d)", self._max)

        # If no final answer was produced, build a fallback from collected observations.
        # Tool observations (search results, fetched pages, etc.) contain real data that
        # the LLM failed to synthesize — return them rather than an empty result.
        if not trace.final_answer:
            trace.final_answer = self._build_fallback_answer(trace)

        final = trace.final_answer or ""

        # Collect tool names and data sources from the trace
        tools_used_set: set[str] = set()
        data_sources_set: set[str] = set()
        for step in trace.steps:
            for tc in step.tool_calls:
                tools_used_set.add(tc.tool_name)
            # Extract URLs from observations of data-source tools
            for idx, obs in enumerate(step.observations):
                is_data_tool = (
                    idx < len(step.tool_calls)
                    and step.tool_calls[idx].tool_name in _DATA_SOURCE_TOOLS
                )
                if is_data_tool:
                    for url in _URL_RE.findall(obs):
                        data_sources_set.add(url)

        return ReactResult(
            trace=trace,
            final_answer=final,
            total_cost_usd=total_cost,
            model_used=model_used,
            tools_used=sorted(tools_used_set) if tools_used_set else None,
            data_sources=sorted(data_sources_set) if data_sources_set else None,
        )

    def register_mcp_tools(self, server_name: str, tools: list[dict[str, Any]]) -> None:
        """Register MCP tools from a connected server.

        Converts MCP tool descriptions to OpenAI-compatible schemas and adds
        them to the tool list. Routes tool calls to MCPClient.
        """
        for tool_desc in tools:
            name = tool_desc.get("name", "")
            if not name:
                continue
            # Convert to OpenAI function-calling format
            schema: dict[str, Any] = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool_desc.get("description", ""),
                    "parameters": tool_desc.get(
                        "inputSchema", {"type": "object", "properties": {}}
                    ),
                },
            }
            self._schemas.append(schema)
            self._mcp_tool_names.add(name)
            self._mcp_tool_server[name] = server_name
        logger.info("Registered %d MCP tools from server %s", len(tools), server_name)

    async def _execute_tool(self, tc: ToolCallResult) -> str:
        """Execute a tool call — route to MCP or LAEE."""
        # Sprint 12.4: MCP tool routing
        if tc.tool_name in self._mcp_tool_names and self._mcp_client is not None:
            server = self._mcp_tool_server.get(tc.tool_name)
            if server:
                try:
                    result = await self._mcp_client.call_tool(
                        server_name=server,
                        tool_name=tc.tool_name,
                        arguments=tc.arguments,
                    )
                    return str(result)
                except Exception as e:
                    return f"MCP_ERROR: {e}"

        # Default: LAEE LocalExecutor
        action = Action(tool=tc.tool_name, args=tc.arguments)
        obs: Observation = await self._executor.execute(action)
        if obs.status == ObservationStatus.SUCCESS:
            return obs.result
        return f"ERROR: {obs.result}"

    @staticmethod
    def _build_fallback_answer(trace: ReactTrace) -> str:
        """Build a fallback answer from collected observations when no final answer.

        When the LLM fails to produce a synthesis (e.g. max_iterations), the tool
        observations still contain valuable data. Return the most recent observations
        so that downstream consumers get partial results rather than nothing.
        """
        observations: list[str] = []
        for step in trace.steps:
            for idx, obs in enumerate(step.observations):
                if not obs or obs.startswith("ERROR:"):
                    continue
                tool_name = step.tool_calls[idx].tool_name if idx < len(step.tool_calls) else "tool"
                observations.append(f"[{tool_name}] {obs}")

        if not observations:
            return "No results obtained within iteration limit."

        # Keep last 3 observations to stay within reasonable size
        recent = observations[-3:]
        parts = ["Tool results (iteration limit reached):"]
        parts.extend(recent)
        return "\n\n---\n\n".join(parts)

    def _filter_tools(self, allowed: list[str]) -> list[dict[str, Any]]:
        """Filter tool schemas to only include allowed tools."""
        return [t for t in self._schemas if t.get("function", {}).get("name") in allowed]

    @staticmethod
    def _build_assistant_message(response: Any) -> dict[str, Any]:
        """Build assistant message with tool_calls for conversation history."""
        msg: dict[str, Any] = {"role": "assistant", "content": response.content or ""}
        if response.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.tool_name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in response.tool_calls
            ]
        return msg
