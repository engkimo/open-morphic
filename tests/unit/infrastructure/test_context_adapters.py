"""Tests for all 6 context adapters."""

from __future__ import annotations

import pytest

from domain.entities.cognitive import AgentAction, Decision, SharedTaskState
from domain.ports.context_adapter import AdapterInsight, ContextAdapterPort
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.cognitive import CognitiveMemoryType
from infrastructure.cognitive.adapters import (
    ADKContextAdapter,
    ClaudeCodeContextAdapter,
    CodexContextAdapter,
    GeminiContextAdapter,
    OllamaContextAdapter,
    OpenHandsContextAdapter,
)

# ─── Fixtures ─────────────────────────────────────────────


def _make_state(**kwargs) -> SharedTaskState:
    defaults = {
        "task_id": "test-task-42",
        "decisions": [
            Decision(
                description="chose FastAPI",
                rationale="best async support",
                agent_engine=AgentEngineType.CLAUDE_CODE,
                confidence=0.9,
            ),
        ],
        "artifacts": {"api.py": "created", "test_api.py": "generated"},
        "blockers": ["CI pipeline broken"],
        "agent_history": [
            AgentAction(
                agent_engine=AgentEngineType.CLAUDE_CODE,
                action_type="execute",
                summary="wrote API routes",
                cost_usd=0.01,
            ),
        ],
    }
    defaults.update(kwargs)
    return SharedTaskState(**defaults)


SAMPLE_OUTPUT_WITH_INSIGHTS = """
I decided to use FastAPI for the web framework.
Created file `src/api.py` with route definitions.
The project uses PostgreSQL for persistence.
Error: connection timeout when connecting to Redis.
I went with JWT for authentication tokens.
Modified file config.yaml for database settings.
The system requires Python 3.12 or higher.
"""

ALL_ADAPTERS: list[type[ContextAdapterPort]] = [
    ClaudeCodeContextAdapter,
    GeminiContextAdapter,
    CodexContextAdapter,
    OllamaContextAdapter,
    OpenHandsContextAdapter,
    ADKContextAdapter,
]


# ─── Port Compliance ──────────────────────────────────────


class TestPortCompliance:
    """All adapters implement ContextAdapterPort correctly."""

    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
    def test_is_context_adapter_port(self, adapter_cls):
        assert issubclass(adapter_cls, ContextAdapterPort)

    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
    def test_engine_type_returns_valid(self, adapter_cls):
        adapter = adapter_cls()
        engine = adapter.engine_type()
        assert isinstance(engine, AgentEngineType)


# ─── Engine Type Mapping ──────────────────────────────────


class TestEngineTypeMapping:
    def test_claude_code(self):
        assert ClaudeCodeContextAdapter().engine_type() == AgentEngineType.CLAUDE_CODE

    def test_gemini(self):
        assert GeminiContextAdapter().engine_type() == AgentEngineType.GEMINI_CLI

    def test_codex(self):
        assert CodexContextAdapter().engine_type() == AgentEngineType.CODEX_CLI

    def test_ollama(self):
        assert OllamaContextAdapter().engine_type() == AgentEngineType.OLLAMA

    def test_openhands(self):
        assert OpenHandsContextAdapter().engine_type() == AgentEngineType.OPENHANDS

    def test_adk(self):
        assert ADKContextAdapter().engine_type() == AgentEngineType.ADK


# ─── Inject Context ───────────────────────────────────────


class TestInjectContext:
    """Each adapter produces engine-specific formatted context."""

    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
    def test_inject_returns_string(self, adapter_cls):
        adapter = adapter_cls()
        result = adapter.inject_context(_make_state(), "some memory context")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
    def test_inject_contains_task_id(self, adapter_cls):
        adapter = adapter_cls()
        result = adapter.inject_context(_make_state(), "")
        assert "test-task-42" in result

    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
    def test_inject_contains_decision(self, adapter_cls):
        adapter = adapter_cls()
        result = adapter.inject_context(_make_state(), "")
        assert "FastAPI" in result or "chose" in result.lower()

    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
    def test_inject_contains_blocker(self, adapter_cls):
        adapter = adapter_cls()
        result = adapter.inject_context(_make_state(), "")
        assert "CI" in result or "broken" in result.lower() or "blocker" in result.lower()

    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
    def test_inject_includes_memory(self, adapter_cls):
        adapter = adapter_cls()
        result = adapter.inject_context(_make_state(), "project uses uv for deps")
        assert "uv" in result or "deps" in result

    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
    def test_inject_empty_state(self, adapter_cls):
        adapter = adapter_cls()
        state = SharedTaskState(task_id="empty-task")
        result = adapter.inject_context(state, "")
        assert isinstance(result, str)
        assert "empty-task" in result

    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
    def test_inject_respects_token_budget(self, adapter_cls):
        adapter = adapter_cls()
        result = adapter.inject_context(_make_state(), "x" * 50000, max_tokens=100)
        # ~100 tokens ≈ ~400 chars, allow some overhead
        assert len(result) < 800

    # Engine-specific format checks
    def test_claude_code_markdown_format(self):
        adapter = ClaudeCodeContextAdapter()
        result = adapter.inject_context(_make_state(), "memory")
        assert "# Morphic-Agent" in result

    def test_gemini_xml_format(self):
        adapter = GeminiContextAdapter()
        result = adapter.inject_context(_make_state(), "memory")
        assert "<morphic-context>" in result
        assert "</morphic-context>" in result

    def test_codex_agents_md_format(self):
        adapter = CodexContextAdapter()
        result = adapter.inject_context(_make_state(), "memory")
        assert "AGENTS.md" in result

    def test_ollama_compact_format(self):
        adapter = OllamaContextAdapter()
        result = adapter.inject_context(_make_state(), "memory")
        # Ollama format is ultra-compact — shorter than others
        claude_result = ClaudeCodeContextAdapter().inject_context(_make_state(), "memory")
        assert len(result) <= len(claude_result)

    def test_openhands_task_context_format(self):
        adapter = OpenHandsContextAdapter()
        result = adapter.inject_context(_make_state(), "memory")
        assert "Task Context" in result

    def test_adk_workflow_format(self):
        adapter = ADKContextAdapter()
        result = adapter.inject_context(_make_state(), "memory")
        assert "<workflow-context" in result
        assert "</workflow-context>" in result


# ─── Extract Insights ─────────────────────────────────────


class TestExtractInsights:
    """Each adapter extracts structured insights from output."""

    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
    def test_extract_returns_list(self, adapter_cls):
        adapter = adapter_cls()
        result = adapter.extract_insights(SAMPLE_OUTPUT_WITH_INSIGHTS)
        assert isinstance(result, list)
        assert all(isinstance(i, AdapterInsight) for i in result)

    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
    def test_extract_finds_decisions(self, adapter_cls):
        adapter = adapter_cls()
        result = adapter.extract_insights(SAMPLE_OUTPUT_WITH_INSIGHTS)
        decision_insights = [i for i in result if "decision" in i.tags]
        assert len(decision_insights) > 0

    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
    def test_extract_finds_files(self, adapter_cls):
        adapter = adapter_cls()
        result = adapter.extract_insights(SAMPLE_OUTPUT_WITH_INSIGHTS)
        file_insights = [i for i in result if "file" in i.tags]
        assert len(file_insights) > 0

    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
    def test_extract_empty_output(self, adapter_cls):
        adapter = adapter_cls()
        result = adapter.extract_insights("")
        assert result == []

    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
    def test_extract_confidence_range(self, adapter_cls):
        adapter = adapter_cls()
        result = adapter.extract_insights(SAMPLE_OUTPUT_WITH_INSIGHTS)
        for insight in result:
            assert 0.0 <= insight.confidence <= 1.0

    @pytest.mark.parametrize("adapter_cls", ALL_ADAPTERS)
    def test_extract_memory_types_valid(self, adapter_cls):
        adapter = adapter_cls()
        result = adapter.extract_insights(SAMPLE_OUTPUT_WITH_INSIGHTS)
        for insight in result:
            assert isinstance(insight.memory_type, CognitiveMemoryType)

    def test_claude_code_extracts_errors(self):
        adapter = ClaudeCodeContextAdapter()
        result = adapter.extract_insights(SAMPLE_OUTPUT_WITH_INSIGHTS)
        error_insights = [i for i in result if "error" in i.tags]
        assert len(error_insights) > 0

    def test_gemini_extracts_facts(self):
        adapter = GeminiContextAdapter()
        result = adapter.extract_insights(SAMPLE_OUTPUT_WITH_INSIGHTS)
        fact_insights = [i for i in result if "fact" in i.tags]
        assert len(fact_insights) > 0

    def test_codex_file_confidence_high(self):
        adapter = CodexContextAdapter()
        result = adapter.extract_insights(SAMPLE_OUTPUT_WITH_INSIGHTS)
        file_insights = [i for i in result if "file" in i.tags]
        # Codex is code-centric — file extraction should be high confidence
        for fi in file_insights:
            assert fi.confidence >= 0.8

    def test_ollama_lower_confidence(self):
        adapter = OllamaContextAdapter()
        result = adapter.extract_insights(SAMPLE_OUTPUT_WITH_INSIGHTS)
        # Ollama has smaller models — lower confidence overall
        if result:
            avg_conf = sum(i.confidence for i in result) / len(result)
            assert avg_conf <= 0.7
