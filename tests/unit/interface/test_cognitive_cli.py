"""Tests for cognitive / UCL CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from domain.entities.cognitive import (
    AgentAction,
    AgentAffinityScore,
    Decision,
    SharedTaskState,
)
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.cognitive.affinity_store import InMemoryAgentAffinityRepository
from infrastructure.persistence.shared_task_state_repo import (
    InMemorySharedTaskStateRepository,
)
from interface.cli.main import app

runner = CliRunner()

# Patch target: cognitive module has its own bound reference via `from main import _get_container`
_PATCH_TARGET = "interface.cli.commands.cognitive._get_container"


def _make_container():  # type: ignore[no-untyped-def]
    container = MagicMock()
    container.shared_task_state_repo = InMemorySharedTaskStateRepository()
    container.affinity_repo = InMemoryAgentAffinityRepository()
    container.extract_insights = MagicMock()
    container.handoff_task = MagicMock()
    return container


def _make_state(task_id: str = "task-1") -> SharedTaskState:
    state = SharedTaskState(task_id=task_id)
    state.add_decision(
        Decision(
            description="Use Ollama",
            rationale="Free",
            agent_engine=AgentEngineType.OLLAMA,
            confidence=0.9,
        )
    )
    state.add_action(
        AgentAction(
            agent_engine=AgentEngineType.OLLAMA,
            action_type="execute",
            summary="Ran task",
        )
    )
    return state


class TestCognitiveStateCLI:
    def setup_method(self) -> None:
        self.container = _make_container()

    def test_state_list_empty(self) -> None:
        with patch(_PATCH_TARGET, return_value=self.container):
            result = runner.invoke(app, ["cognitive", "state"])
        assert result.exit_code == 0
        assert "No active" in result.output

    def test_state_list_with_data(self) -> None:
        state = _make_state()
        self.container.shared_task_state_repo._store[state.task_id] = state
        with patch(_PATCH_TARGET, return_value=self.container):
            result = runner.invoke(app, ["cognitive", "state"])
        assert result.exit_code == 0
        assert "task-1" in result.output

    def test_state_show(self) -> None:
        state = _make_state("task-show")
        self.container.shared_task_state_repo._store[state.task_id] = state
        with patch(_PATCH_TARGET, return_value=self.container):
            result = runner.invoke(app, ["cognitive", "state", "task-show"])
        assert result.exit_code == 0
        assert "task-show" in result.output
        assert "Use Ollama" in result.output

    def test_state_show_not_found(self) -> None:
        with patch(_PATCH_TARGET, return_value=self.container):
            result = runner.invoke(app, ["cognitive", "state", "nonexistent"])
        assert result.exit_code == 1

    def test_delete(self) -> None:
        state = _make_state("task-del")
        self.container.shared_task_state_repo._store[state.task_id] = state
        with patch(_PATCH_TARGET, return_value=self.container):
            result = runner.invoke(app, ["cognitive", "delete", "task-del"])
        assert result.exit_code == 0
        assert "Deleted" in result.output

    def test_delete_not_found(self) -> None:
        with patch(_PATCH_TARGET, return_value=self.container):
            result = runner.invoke(app, ["cognitive", "delete", "nonexistent"])
        assert result.exit_code == 1


class TestCognitiveAffinityCLI:
    def setup_method(self) -> None:
        self.container = _make_container()

    def test_affinity_empty(self) -> None:
        with patch(_PATCH_TARGET, return_value=self.container):
            result = runner.invoke(app, ["cognitive", "affinity"])
        assert result.exit_code == 0
        assert "No affinity" in result.output

    def test_affinity_with_data(self) -> None:
        score = AgentAffinityScore(
            engine=AgentEngineType.CLAUDE_CODE,
            topic="backend",
            familiarity=0.8,
            recency=0.7,
            success_rate=0.9,
            cost_efficiency=0.4,
            sample_count=5,
        )
        self.container.affinity_repo._store[(AgentEngineType.CLAUDE_CODE, "backend")] = score
        with patch(_PATCH_TARGET, return_value=self.container):
            result = runner.invoke(app, ["cognitive", "affinity"])
        assert result.exit_code == 0
        assert "claude_code" in result.output
        assert "backend" in result.output

    def test_affinity_filter_topic(self) -> None:
        score = AgentAffinityScore(
            engine=AgentEngineType.OLLAMA,
            topic="frontend",
            familiarity=0.5,
            sample_count=3,
        )
        self.container.affinity_repo._store[(AgentEngineType.OLLAMA, "frontend")] = score
        with patch(_PATCH_TARGET, return_value=self.container):
            result = runner.invoke(app, ["cognitive", "affinity", "--topic", "frontend"])
        assert result.exit_code == 0
        assert "frontend" in result.output

    def test_affinity_invalid_engine(self) -> None:
        with patch(_PATCH_TARGET, return_value=self.container):
            result = runner.invoke(app, ["cognitive", "affinity", "--engine", "invalid"])
        assert result.exit_code == 1


class TestCognitiveInsightsCLI:
    def setup_method(self) -> None:
        self.container = _make_container()

    def test_insights_invalid_engine(self) -> None:
        with patch(_PATCH_TARGET, return_value=self.container):
            result = runner.invoke(
                app,
                [
                    "cognitive",
                    "insights",
                    "--task-id",
                    "t-1",
                    "--engine",
                    "invalid",
                    "--output",
                    "some text",
                ],
            )
        assert result.exit_code == 1
