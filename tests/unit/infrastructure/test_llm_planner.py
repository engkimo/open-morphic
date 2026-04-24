"""Tests for LLMPlanner — fractal engine PlannerPort implementation.

Sprint 15.2: ~18 tests covering candidate generation, direction handling,
terminal heuristics, fallback behavior, and prompt construction.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from domain.entities.fractal_engine import CandidateNode
from domain.ports.llm_gateway import LLMGateway, LLMResponse
from domain.value_objects.fractal_engine import NodeState
from infrastructure.fractal.llm_planner import LLMPlanner, _extract_json

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _llm_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="test-model",
        prompt_tokens=50,
        completion_tokens=30,
        cost_usd=0.0,
    )


def _json_payload(items: list[dict]) -> str:
    return json.dumps(items)


def _sample_items(count: int = 3) -> list[dict]:
    """Generate sample well-formed candidate dicts."""
    return [
        {
            "description": f"Step {i + 1}: do something",
            "is_terminal": i == count - 1,
            "score": round(0.5 + i * 0.1, 2),
            "condition": None,
            "input_artifacts": {},
            "output_artifacts": {},
        }
        for i in range(count)
    ]


@pytest.fixture
def llm() -> AsyncMock:
    return AsyncMock(spec=LLMGateway)


@pytest.fixture
def planner(llm: AsyncMock) -> LLMPlanner:
    return LLMPlanner(llm, candidates_per_node=3, max_depth=3)


# ===================================================================
# TestGenerateCandidates
# ===================================================================


class TestGenerateCandidates:
    """Core generation from LLM JSON."""

    @pytest.mark.asyncio
    async def test_generates_candidates_from_llm_json(
        self, llm: AsyncMock, planner: LLMPlanner
    ) -> None:
        items = _sample_items(3)
        llm.complete.return_value = _llm_response(_json_payload(items))

        result = await planner.generate_candidates("Build a REST API", "", 0)

        assert len(result) == 3
        assert all(isinstance(c, CandidateNode) for c in result)
        assert result[0].node.description == "Step 1: do something"
        assert result[2].node.is_terminal is True

    @pytest.mark.asyncio
    async def test_conditional_nodes_get_conditional_state(
        self, llm: AsyncMock, planner: LLMPlanner
    ) -> None:
        items = [
            {
                "description": "Primary step",
                "is_terminal": True,
                "score": 0.9,
                "condition": None,
                "input_artifacts": {},
                "output_artifacts": {},
            },
            {
                "description": "Fallback step",
                "is_terminal": True,
                "score": 0.4,
                "condition": "primary step fails with timeout",
                "input_artifacts": {},
                "output_artifacts": {},
            },
        ]
        llm.complete.return_value = _llm_response(_json_payload(items))

        result = await planner.generate_candidates("Do task", "", 0)

        assert result[0].state == NodeState.VISIBLE
        assert result[0].activation_condition is None
        assert result[1].state == NodeState.CONDITIONAL
        assert result[1].activation_condition == "primary step fails with timeout"

    @pytest.mark.asyncio
    async def test_scores_clamped_to_valid_range(self, llm: AsyncMock, planner: LLMPlanner) -> None:
        items = [
            {
                "description": "Over score",
                "is_terminal": True,
                "score": 1.5,
                "condition": None,
                "input_artifacts": {},
                "output_artifacts": {},
            },
            {
                "description": "Under score",
                "is_terminal": True,
                "score": -0.3,
                "condition": None,
                "input_artifacts": {},
                "output_artifacts": {},
            },
        ]
        llm.complete.return_value = _llm_response(_json_payload(items))

        result = await planner.generate_candidates("Clamp test", "", 0)

        assert result[0].score == 1.0
        assert result[1].score == 0.0

    @pytest.mark.asyncio
    async def test_nesting_level_propagated(self, llm: AsyncMock, planner: LLMPlanner) -> None:
        items = _sample_items(2)
        llm.complete.return_value = _llm_response(_json_payload(items))

        result = await planner.generate_candidates("Sub-goal", "", nesting_level=2)

        assert all(c.node.nesting_level == 2 for c in result)

    @pytest.mark.asyncio
    async def test_input_output_artifacts_parsed(self, llm: AsyncMock, planner: LLMPlanner) -> None:
        items = [
            {
                "description": "Fetch data",
                "is_terminal": True,
                "score": 0.8,
                "condition": None,
                "input_artifacts": {"url": "https://example.com"},
                "output_artifacts": {"response": "json_data"},
            },
        ]
        llm.complete.return_value = _llm_response(_json_payload(items))

        result = await planner.generate_candidates("Fetch", "", 0)

        assert result[0].node.input_artifacts == {"url": "https://example.com"}
        assert result[0].node.output_artifacts == {"response": "json_data"}

    @pytest.mark.asyncio
    async def test_empty_description_filtered(self, llm: AsyncMock, planner: LLMPlanner) -> None:
        items = [
            {
                "description": "",
                "is_terminal": True,
                "score": 0.5,
                "condition": None,
                "input_artifacts": {},
                "output_artifacts": {},
            },
            {
                "description": "   ",
                "is_terminal": True,
                "score": 0.5,
                "condition": None,
                "input_artifacts": {},
                "output_artifacts": {},
            },
            {
                "description": "Valid step",
                "is_terminal": True,
                "score": 0.9,
                "condition": None,
                "input_artifacts": {},
                "output_artifacts": {},
            },
        ]
        llm.complete.return_value = _llm_response(_json_payload(items))

        result = await planner.generate_candidates("Filter test", "", 0)

        assert len(result) == 1
        assert result[0].node.description == "Valid step"


# ===================================================================
# TestDirection
# ===================================================================


class TestDirection:
    """Verify direction is communicated to the LLM via the user message (TD-190)."""

    @pytest.mark.asyncio
    async def test_forward_direction_in_user_message(
        self, llm: AsyncMock, planner: LLMPlanner
    ) -> None:
        llm.complete.return_value = _llm_response(_json_payload(_sample_items(1)))

        await planner.generate_candidates("Goal", "", 0, direction="forward")

        user_msg = llm.complete.call_args[0][0][1]["content"]
        assert "Direction: FORWARD" in user_msg

    @pytest.mark.asyncio
    async def test_backward_direction_in_user_message(
        self, llm: AsyncMock, planner: LLMPlanner
    ) -> None:
        llm.complete.return_value = _llm_response(_json_payload(_sample_items(1)))

        await planner.generate_candidates("Goal", "", 0, direction="backward")

        user_msg = llm.complete.call_args[0][0][1]["content"]
        assert "Direction: BACKWARD" in user_msg


# ===================================================================
# TestTerminalHeuristic
# ===================================================================


class TestTerminalHeuristic:
    """Terminal detection — LLM decision + depth-based forcing."""

    @pytest.mark.asyncio
    async def test_llm_decides_is_terminal(self, llm: AsyncMock, planner: LLMPlanner) -> None:
        items = [
            {
                "description": "Non-terminal",
                "is_terminal": False,
                "score": 0.8,
                "condition": None,
                "input_artifacts": {},
                "output_artifacts": {},
            },
            {
                "description": "Terminal",
                "is_terminal": True,
                "score": 0.9,
                "condition": None,
                "input_artifacts": {},
                "output_artifacts": {},
            },
        ]
        llm.complete.return_value = _llm_response(_json_payload(items))

        result = await planner.generate_candidates("Goal", "", nesting_level=0)

        assert result[0].node.is_terminal is False
        assert result[1].node.is_terminal is True

    @pytest.mark.asyncio
    async def test_force_terminal_at_max_depth(self, llm: AsyncMock, planner: LLMPlanner) -> None:
        """nesting_level >= max_depth - 1 forces all nodes terminal."""
        items = [
            {
                "description": "Should be forced terminal",
                "is_terminal": False,
                "score": 0.8,
                "condition": None,
                "input_artifacts": {},
                "output_artifacts": {},
            },
        ]
        llm.complete.return_value = _llm_response(_json_payload(items))

        # max_depth=3, nesting_level=2 → force terminal
        result = await planner.generate_candidates("Deep goal", "", nesting_level=2)

        assert result[0].node.is_terminal is True

    @pytest.mark.asyncio
    async def test_not_forced_below_max_depth(self, llm: AsyncMock, planner: LLMPlanner) -> None:
        """nesting_level < max_depth - 1 → LLM's is_terminal value kept."""
        items = [
            {
                "description": "Non-terminal from LLM",
                "is_terminal": False,
                "score": 0.8,
                "condition": None,
                "input_artifacts": {},
                "output_artifacts": {},
            },
        ]
        llm.complete.return_value = _llm_response(_json_payload(items))

        # max_depth=3, nesting_level=1 → no forcing
        result = await planner.generate_candidates("Mid goal", "", nesting_level=1)

        assert result[0].node.is_terminal is False


# ===================================================================
# TestFallback
# ===================================================================


class TestFallback:
    """Fallback behavior on LLM failure or bad output."""

    @pytest.mark.asyncio
    async def test_invalid_json_returns_fallback(self, llm: AsyncMock, planner: LLMPlanner) -> None:
        llm.complete.return_value = _llm_response("This is not JSON at all")

        result = await planner.generate_candidates("Bad JSON goal", "", 0)

        assert len(result) == 1
        assert result[0].node.description == "Bad JSON goal"
        assert result[0].node.is_terminal is True
        assert result[0].state == NodeState.VISIBLE
        assert result[0].score == 1.0

    @pytest.mark.asyncio
    async def test_llm_exception_returns_fallback(
        self, llm: AsyncMock, planner: LLMPlanner
    ) -> None:
        llm.complete.side_effect = RuntimeError("LLM unavailable")

        result = await planner.generate_candidates("Exception goal", "", 1)

        assert len(result) == 1
        assert result[0].node.description == "Exception goal"
        assert result[0].node.nesting_level == 1
        assert result[0].node.is_terminal is True
        assert result[0].state == NodeState.VISIBLE
        assert result[0].score == 1.0

    @pytest.mark.asyncio
    async def test_fallback_is_terminal_and_visible(
        self, llm: AsyncMock, planner: LLMPlanner
    ) -> None:
        """Empty array from LLM → fallback node."""
        llm.complete.return_value = _llm_response("[]")

        result = await planner.generate_candidates("Empty goal", "", 0)

        assert len(result) == 1
        assert result[0].node.is_terminal is True
        assert result[0].state == NodeState.VISIBLE
        assert result[0].score == 1.0


# ===================================================================
# TestPromptConstruction
# ===================================================================


class TestPromptConstruction:
    """Verify prompt content passed to the LLM gateway."""

    @pytest.mark.asyncio
    async def test_context_in_user_message(self, llm: AsyncMock, planner: LLMPlanner) -> None:
        llm.complete.return_value = _llm_response(_json_payload(_sample_items(1)))

        await planner.generate_candidates(
            "Goal", context="Parent decided to use Python", nesting_level=0
        )

        user_msg = llm.complete.call_args[0][0][1]["content"]
        assert "Parent decided to use Python" in user_msg

    @pytest.mark.asyncio
    async def test_candidates_count_in_user_message(
        self, llm: AsyncMock, planner: LLMPlanner
    ) -> None:
        llm.complete.return_value = _llm_response(_json_payload(_sample_items(1)))

        await planner.generate_candidates("Goal", "", 0)

        user_msg = llm.complete.call_args[0][0][1]["content"]
        assert "3" in user_msg  # candidates_per_node=3

    @pytest.mark.asyncio
    async def test_nesting_level_in_user_message(
        self, llm: AsyncMock, planner: LLMPlanner
    ) -> None:
        llm.complete.return_value = _llm_response(_json_payload(_sample_items(1)))

        await planner.generate_candidates("Goal", "", nesting_level=2)

        user_msg = llm.complete.call_args[0][0][1]["content"]
        assert "Nesting level: 2" in user_msg

    @pytest.mark.asyncio
    async def test_model_override_passed_to_gateway(self, llm: AsyncMock) -> None:
        planner = LLMPlanner(llm, model="claude-sonnet-4-6")
        llm.complete.return_value = _llm_response(_json_payload(_sample_items(1)))

        await planner.generate_candidates("Goal", "", 0)

        _, kwargs = llm.complete.call_args
        assert kwargs["model"] == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_goal_in_user_message(self, llm: AsyncMock, planner: LLMPlanner) -> None:
        llm.complete.return_value = _llm_response(_json_payload(_sample_items(1)))

        await planner.generate_candidates("Build a REST API", "", 0)

        messages = llm.complete.call_args[0][0]
        assert messages[1]["role"] == "user"
        assert "Build a REST API" in messages[1]["content"]


# ===================================================================
# TestStablePrefix — TD-190 KV-cache stable system prefix
# ===================================================================


class TestStablePrefix:
    """The system prompt must be byte-identical across every call regardless
    of direction, nesting level, parent context, candidates_per_node, or
    learning data. Manus 5原則 KV-cache stability: prefix changes destroy
    the cache for every subsequent token. All runtime values live in the
    user message instead."""

    @pytest.mark.asyncio
    async def test_system_prompt_byte_stable_across_directions(
        self, llm: AsyncMock, planner: LLMPlanner
    ) -> None:
        llm.complete.return_value = _llm_response(_json_payload(_sample_items(1)))

        await planner.generate_candidates("Goal", "", 0, direction="forward")
        sys_fwd = llm.complete.call_args[0][0][0]["content"]
        await planner.generate_candidates("Goal", "", 0, direction="backward")
        sys_bwd = llm.complete.call_args[0][0][0]["content"]

        assert sys_fwd == sys_bwd

    @pytest.mark.asyncio
    async def test_system_prompt_byte_stable_across_nesting_levels(
        self, llm: AsyncMock, planner: LLMPlanner
    ) -> None:
        llm.complete.return_value = _llm_response(_json_payload(_sample_items(1)))

        seen: set[str] = set()
        for level in (0, 1, 2):
            await planner.generate_candidates("Goal", "", nesting_level=level)
            seen.add(llm.complete.call_args[0][0][0]["content"])

        assert len(seen) == 1, "system prompt drifted across nesting levels"

    @pytest.mark.asyncio
    async def test_system_prompt_byte_stable_across_contexts(
        self, llm: AsyncMock, planner: LLMPlanner
    ) -> None:
        llm.complete.return_value = _llm_response(_json_payload(_sample_items(1)))

        await planner.generate_candidates("Goal", "", 0)
        sys_empty = llm.complete.call_args[0][0][0]["content"]
        await planner.generate_candidates("Goal", "Parent chose Python", 0)
        sys_with_ctx = llm.complete.call_args[0][0][0]["content"]

        assert sys_empty == sys_with_ctx

    @pytest.mark.asyncio
    async def test_system_prompt_byte_stable_across_candidates_per_node(
        self, llm: AsyncMock
    ) -> None:
        llm.complete.return_value = _llm_response(_json_payload(_sample_items(1)))
        p3 = LLMPlanner(llm, candidates_per_node=3)
        p7 = LLMPlanner(llm, candidates_per_node=7)

        await p3.generate_candidates("Goal", "", 0)
        sys_3 = llm.complete.call_args[0][0][0]["content"]
        await p7.generate_candidates("Goal", "", 0)
        sys_7 = llm.complete.call_args[0][0][0]["content"]

        assert sys_3 == sys_7

    @pytest.mark.asyncio
    async def test_system_prompt_equals_module_constant(
        self, llm: AsyncMock, planner: LLMPlanner
    ) -> None:
        """The shipped system prompt is exactly the module constant — no
        runtime concatenation. Catches accidental f-string templating."""
        from infrastructure.fractal.llm_planner import _SYSTEM_PROMPT

        llm.complete.return_value = _llm_response(_json_payload(_sample_items(1)))
        await planner.generate_candidates("Goal", "Parent ctx", 1, direction="backward")

        sys_msg = llm.complete.call_args[0][0][0]["content"]
        assert sys_msg == _SYSTEM_PROMPT


# ===================================================================
# TestExtractJson (module-level function)
# ===================================================================


class TestExtractJson:
    """Unit tests for the _extract_json helper."""

    def test_plain_array(self) -> None:
        assert _extract_json('[{"a": 1}]') == '[{"a": 1}]'

    def test_markdown_code_block(self) -> None:
        text = '```json\n[{"a": 1}]\n```'
        assert _extract_json(text) == '[{"a": 1}]'

    def test_think_tags_stripped(self) -> None:
        text = '<think>reasoning here</think>\n[{"a": 1}]'
        assert _extract_json(text) == '[{"a": 1}]'

    def test_no_array_returns_text(self) -> None:
        assert _extract_json("no json here") == "no json here"
