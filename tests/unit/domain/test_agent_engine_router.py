"""Tests for AgentEngineRouter — pure domain service for engine selection.

Sprint 4.1: AgentEngine Domain Foundation
"""

from __future__ import annotations

import math

from domain.services.agent_engine_router import AgentEngineRouter
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType

# ---------------------------------------------------------------------------
# TestAgentEngineType
# ---------------------------------------------------------------------------


class TestAgentEngineType:
    """AgentEngineType enum validation."""

    def test_six_members(self) -> None:
        assert len(AgentEngineType) == 6

    def test_string_values(self) -> None:
        expected = {
            "openhands",
            "claude_code",
            "gemini_cli",
            "codex_cli",
            "adk",
            "ollama",
        }
        assert {e.value for e in AgentEngineType} == expected

    def test_from_string(self) -> None:
        assert AgentEngineType("openhands") == AgentEngineType.OPENHANDS
        assert AgentEngineType("claude_code") == AgentEngineType.CLAUDE_CODE
        assert AgentEngineType("ollama") == AgentEngineType.OLLAMA


# ---------------------------------------------------------------------------
# TestExtendedTaskType
# ---------------------------------------------------------------------------


class TestExtendedTaskType:
    """TaskType extended with 2 new members."""

    def test_new_members_exist(self) -> None:
        assert TaskType.LONG_RUNNING_DEV.value == "long_running_dev"
        assert TaskType.WORKFLOW_PIPELINE.value == "workflow_pipeline"

    def test_total_count(self) -> None:
        assert len(TaskType) == 8

    def test_original_six_unchanged(self) -> None:
        original = {
            "simple_qa",
            "code_generation",
            "complex_reasoning",
            "file_operation",
            "long_context",
            "multimodal",
        }
        current = {t.value for t in TaskType}
        assert original.issubset(current)

    def test_all_values_unique(self) -> None:
        values = [t.value for t in TaskType]
        assert len(values) == len(set(values))


# ---------------------------------------------------------------------------
# TestAgentEngineRouterSelect
# ---------------------------------------------------------------------------


class TestAgentEngineRouterSelect:
    """select() — single engine selection based on heuristics."""

    def test_budget_zero_returns_ollama(self) -> None:
        result = AgentEngineRouter.select(task_type=TaskType.COMPLEX_REASONING, budget=0.0)
        assert result == AgentEngineType.OLLAMA

    def test_negative_budget_returns_ollama(self) -> None:
        result = AgentEngineRouter.select(task_type=TaskType.CODE_GENERATION, budget=-5.0)
        assert result == AgentEngineType.OLLAMA

    def test_hours_gt_one_returns_openhands(self) -> None:
        result = AgentEngineRouter.select(
            task_type=TaskType.CODE_GENERATION,
            budget=10.0,
            estimated_hours=2.0,
        )
        assert result == AgentEngineType.OPENHANDS

    def test_context_tokens_gt_100k_returns_gemini(self) -> None:
        result = AgentEngineRouter.select(
            task_type=TaskType.SIMPLE_QA,
            budget=10.0,
            context_tokens=200_000,
        )
        assert result == AgentEngineType.GEMINI_CLI

    def test_budget_overrides_hours(self) -> None:
        """budget=0 takes precedence over estimated_hours."""
        result = AgentEngineRouter.select(
            task_type=TaskType.CODE_GENERATION,
            budget=0.0,
            estimated_hours=5.0,
        )
        assert result == AgentEngineType.OLLAMA

    def test_budget_overrides_tokens(self) -> None:
        """budget=0 takes precedence over context_tokens."""
        result = AgentEngineRouter.select(
            task_type=TaskType.LONG_CONTEXT,
            budget=0.0,
            context_tokens=500_000,
        )
        assert result == AgentEngineType.OLLAMA

    def test_hours_overrides_tokens(self) -> None:
        """estimated_hours > 1 takes precedence over context_tokens."""
        result = AgentEngineRouter.select(
            task_type=TaskType.LONG_CONTEXT,
            budget=10.0,
            estimated_hours=3.0,
            context_tokens=500_000,
        )
        assert result == AgentEngineType.OPENHANDS

    def test_simple_qa_maps_to_ollama(self) -> None:
        result = AgentEngineRouter.select(task_type=TaskType.SIMPLE_QA, budget=10.0)
        assert result == AgentEngineType.OLLAMA

    def test_code_generation_maps_to_codex(self) -> None:
        result = AgentEngineRouter.select(task_type=TaskType.CODE_GENERATION, budget=10.0)
        assert result == AgentEngineType.CODEX_CLI

    def test_complex_reasoning_maps_to_claude_code(self) -> None:
        result = AgentEngineRouter.select(task_type=TaskType.COMPLEX_REASONING, budget=10.0)
        assert result == AgentEngineType.CLAUDE_CODE

    def test_file_operation_maps_to_ollama(self) -> None:
        result = AgentEngineRouter.select(task_type=TaskType.FILE_OPERATION, budget=10.0)
        assert result == AgentEngineType.OLLAMA

    def test_long_context_maps_to_gemini(self) -> None:
        result = AgentEngineRouter.select(task_type=TaskType.LONG_CONTEXT, budget=10.0)
        assert result == AgentEngineType.GEMINI_CLI

    def test_multimodal_maps_to_claude_code(self) -> None:
        result = AgentEngineRouter.select(task_type=TaskType.MULTIMODAL, budget=10.0)
        assert result == AgentEngineType.CLAUDE_CODE

    def test_long_running_dev_maps_to_openhands(self) -> None:
        result = AgentEngineRouter.select(task_type=TaskType.LONG_RUNNING_DEV, budget=10.0)
        assert result == AgentEngineType.OPENHANDS

    def test_workflow_pipeline_maps_to_adk(self) -> None:
        result = AgentEngineRouter.select(task_type=TaskType.WORKFLOW_PIPELINE, budget=10.0)
        assert result == AgentEngineType.ADK

    def test_infinite_budget(self) -> None:
        """Very large budget uses primary map."""
        result = AgentEngineRouter.select(task_type=TaskType.COMPLEX_REASONING, budget=math.inf)
        assert result == AgentEngineType.CLAUDE_CODE


# ---------------------------------------------------------------------------
# TestAgentEngineRouterFallbackChain
# ---------------------------------------------------------------------------


class TestAgentEngineRouterFallbackChain:
    """get_fallback_chain() — ordered fallback list for an engine."""

    def test_openhands_fallback(self) -> None:
        chain = AgentEngineRouter.get_fallback_chain(AgentEngineType.OPENHANDS)
        assert isinstance(chain, list)
        assert len(chain) > 0
        assert AgentEngineType.OLLAMA in chain

    def test_claude_code_fallback(self) -> None:
        chain = AgentEngineRouter.get_fallback_chain(AgentEngineType.CLAUDE_CODE)
        assert len(chain) > 0

    def test_ollama_empty_chain(self) -> None:
        """OLLAMA is the ultimate fallback — no further chain."""
        chain = AgentEngineRouter.get_fallback_chain(AgentEngineType.OLLAMA)
        assert chain == []

    def test_returns_copy_not_reference(self) -> None:
        """Returned list should be a copy so mutation doesn't affect internals."""
        chain1 = AgentEngineRouter.get_fallback_chain(AgentEngineType.CLAUDE_CODE)
        chain2 = AgentEngineRouter.get_fallback_chain(AgentEngineType.CLAUDE_CODE)
        assert chain1 == chain2
        assert chain1 is not chain2

    def test_all_engines_have_chain_defined(self) -> None:
        """Every engine type has a fallback chain (even if empty)."""
        for engine in AgentEngineType:
            chain = AgentEngineRouter.get_fallback_chain(engine)
            assert isinstance(chain, list)


# ---------------------------------------------------------------------------
# TestAgentEngineRouterSelectWithFallbacks
# ---------------------------------------------------------------------------


class TestAgentEngineRouterSelectWithFallbacks:
    """select_with_fallbacks() — preferred + fallback chain."""

    def test_preferred_is_first(self) -> None:
        result = AgentEngineRouter.select_with_fallbacks(
            task_type=TaskType.COMPLEX_REASONING, budget=10.0
        )
        assert result[0] == AgentEngineType.CLAUDE_CODE

    def test_ollama_always_present(self) -> None:
        """OLLAMA should always be in the chain (ultimate fallback)."""
        result = AgentEngineRouter.select_with_fallbacks(
            task_type=TaskType.COMPLEX_REASONING, budget=10.0
        )
        assert AgentEngineType.OLLAMA in result

    def test_ollama_is_last(self) -> None:
        """OLLAMA should be the last element."""
        result = AgentEngineRouter.select_with_fallbacks(
            task_type=TaskType.CODE_GENERATION, budget=10.0
        )
        assert result[-1] == AgentEngineType.OLLAMA

    def test_no_duplicates(self) -> None:
        result = AgentEngineRouter.select_with_fallbacks(
            task_type=TaskType.COMPLEX_REASONING, budget=10.0
        )
        assert len(result) == len(set(result))

    def test_budget_zero_returns_ollama_only(self) -> None:
        """budget=0 → only OLLAMA (no point listing paid engines)."""
        result = AgentEngineRouter.select_with_fallbacks(
            task_type=TaskType.COMPLEX_REASONING, budget=0.0
        )
        assert result == [AgentEngineType.OLLAMA]

    def test_heuristic_affects_chain(self) -> None:
        """estimated_hours>1 makes OPENHANDS the preferred engine."""
        result = AgentEngineRouter.select_with_fallbacks(
            task_type=TaskType.CODE_GENERATION,
            budget=10.0,
            estimated_hours=3.0,
        )
        assert result[0] == AgentEngineType.OPENHANDS

    def test_long_context_chain_starts_with_gemini(self) -> None:
        result = AgentEngineRouter.select_with_fallbacks(
            task_type=TaskType.SIMPLE_QA,
            budget=10.0,
            context_tokens=200_000,
        )
        assert result[0] == AgentEngineType.GEMINI_CLI

    def test_ollama_preferred_returns_single(self) -> None:
        """When OLLAMA is the primary, chain is just [OLLAMA]."""
        result = AgentEngineRouter.select_with_fallbacks(task_type=TaskType.SIMPLE_QA, budget=10.0)
        # SIMPLE_QA maps to OLLAMA, which has no fallback
        # But select_with_fallbacks ensures OLLAMA is present
        assert result[0] == AgentEngineType.OLLAMA
        assert result == [AgentEngineType.OLLAMA]
