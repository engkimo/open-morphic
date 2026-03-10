"""Tests for UCL cognitive domain components (Sprint 7.1)."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from domain.entities.cognitive import (
    AgentAction,
    AgentAffinityScore,
    Decision,
    SharedTaskState,
)
from domain.ports.insight_extractor import ExtractedInsight
from domain.services.agent_affinity import AgentAffinityScorer
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.cognitive import CognitiveMemoryType

# ──────────────────────────────────────────────
# CognitiveMemoryType
# ──────────────────────────────────────────────


class TestCognitiveMemoryType:
    def test_member_count(self) -> None:
        assert len(CognitiveMemoryType) == 4

    def test_values(self) -> None:
        assert CognitiveMemoryType.EPISODIC == "episodic"
        assert CognitiveMemoryType.SEMANTIC == "semantic"
        assert CognitiveMemoryType.PROCEDURAL == "procedural"
        assert CognitiveMemoryType.WORKING == "working"

    def test_is_str(self) -> None:
        for member in CognitiveMemoryType:
            assert isinstance(member, str)

    def test_from_string(self) -> None:
        assert CognitiveMemoryType("episodic") == CognitiveMemoryType.EPISODIC
        assert CognitiveMemoryType("semantic") == CognitiveMemoryType.SEMANTIC
        assert CognitiveMemoryType("procedural") == CognitiveMemoryType.PROCEDURAL
        assert CognitiveMemoryType("working") == CognitiveMemoryType.WORKING


# ──────────────────────────────────────────────
# Decision
# ──────────────────────────────────────────────


class TestDecision:
    def test_create_minimal(self) -> None:
        d = Decision(description="use Claude", agent_engine=AgentEngineType.CLAUDE_CODE)
        assert d.description == "use Claude"
        assert d.agent_engine == AgentEngineType.CLAUDE_CODE
        assert d.confidence == 0.5
        assert d.rationale == ""

    def test_create_full(self) -> None:
        now = datetime.now()
        d = Decision(
            id="dec-1",
            description="use Gemini for long context",
            rationale="2M token window needed",
            agent_engine=AgentEngineType.GEMINI_CLI,
            confidence=0.9,
            timestamp=now,
        )
        assert d.id == "dec-1"
        assert d.rationale == "2M token window needed"
        assert d.confidence == 0.9
        assert d.timestamp == now

    def test_auto_id(self) -> None:
        d1 = Decision(description="a", agent_engine=AgentEngineType.OLLAMA)
        d2 = Decision(description="b", agent_engine=AgentEngineType.OLLAMA)
        assert d1.id != d2.id

    def test_auto_timestamp(self) -> None:
        before = datetime.now()
        d = Decision(description="test", agent_engine=AgentEngineType.OLLAMA)
        after = datetime.now()
        assert before <= d.timestamp <= after

    def test_empty_description_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Decision(description="", agent_engine=AgentEngineType.OLLAMA)

    def test_confidence_below_0_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Decision(description="x", agent_engine=AgentEngineType.OLLAMA, confidence=-0.1)

    def test_confidence_above_1_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Decision(description="x", agent_engine=AgentEngineType.OLLAMA, confidence=1.1)

    def test_confidence_0_allowed(self) -> None:
        d = Decision(description="x", agent_engine=AgentEngineType.OLLAMA, confidence=0.0)
        assert d.confidence == 0.0

    def test_confidence_1_allowed(self) -> None:
        d = Decision(description="x", agent_engine=AgentEngineType.OLLAMA, confidence=1.0)
        assert d.confidence == 1.0

    def test_all_engine_types(self) -> None:
        for engine in AgentEngineType:
            d = Decision(description="test", agent_engine=engine)
            assert d.agent_engine == engine

    def test_validate_assignment(self) -> None:
        d = Decision(description="test", agent_engine=AgentEngineType.OLLAMA)
        d.confidence = 0.8
        assert d.confidence == 0.8

    def test_validate_assignment_rejects_invalid(self) -> None:
        d = Decision(description="test", agent_engine=AgentEngineType.OLLAMA)
        with pytest.raises(ValidationError):
            d.confidence = 2.0


# ──────────────────────────────────────────────
# AgentAction
# ──────────────────────────────────────────────


class TestAgentAction:
    def test_create_minimal(self) -> None:
        a = AgentAction(agent_engine=AgentEngineType.CODEX_CLI, action_type="execute")
        assert a.agent_engine == AgentEngineType.CODEX_CLI
        assert a.action_type == "execute"
        assert a.summary == ""
        assert a.cost_usd == 0.0
        assert a.duration_seconds == 0.0

    def test_create_full(self) -> None:
        now = datetime.now()
        a = AgentAction(
            id="act-1",
            agent_engine=AgentEngineType.OPENHANDS,
            action_type="plan",
            summary="Generated architecture plan",
            cost_usd=0.05,
            duration_seconds=30.0,
            timestamp=now,
        )
        assert a.id == "act-1"
        assert a.summary == "Generated architecture plan"
        assert a.cost_usd == 0.05
        assert a.duration_seconds == 30.0
        assert a.timestamp == now

    def test_auto_id(self) -> None:
        a1 = AgentAction(agent_engine=AgentEngineType.OLLAMA, action_type="execute")
        a2 = AgentAction(agent_engine=AgentEngineType.OLLAMA, action_type="execute")
        assert a1.id != a2.id

    def test_auto_timestamp(self) -> None:
        before = datetime.now()
        a = AgentAction(agent_engine=AgentEngineType.OLLAMA, action_type="execute")
        after = datetime.now()
        assert before <= a.timestamp <= after

    def test_empty_action_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentAction(agent_engine=AgentEngineType.OLLAMA, action_type="")

    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentAction(
                agent_engine=AgentEngineType.OLLAMA,
                action_type="execute",
                cost_usd=-0.01,
            )

    def test_negative_duration_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentAction(
                agent_engine=AgentEngineType.OLLAMA,
                action_type="execute",
                duration_seconds=-1.0,
            )

    def test_all_engine_types(self) -> None:
        for engine in AgentEngineType:
            a = AgentAction(agent_engine=engine, action_type="review")
            assert a.agent_engine == engine

    def test_custom_action_types(self) -> None:
        for action_type in ["execute", "plan", "review", "handoff", "debug", "custom"]:
            a = AgentAction(agent_engine=AgentEngineType.OLLAMA, action_type=action_type)
            assert a.action_type == action_type

    def test_validate_assignment(self) -> None:
        a = AgentAction(agent_engine=AgentEngineType.OLLAMA, action_type="execute")
        a.cost_usd = 1.0
        assert a.cost_usd == 1.0

    def test_validate_assignment_rejects_invalid(self) -> None:
        a = AgentAction(agent_engine=AgentEngineType.OLLAMA, action_type="execute")
        with pytest.raises(ValidationError):
            a.cost_usd = -5.0


# ──────────────────────────────────────────────
# SharedTaskState
# ──────────────────────────────────────────────


class TestSharedTaskState:
    def test_create_minimal(self) -> None:
        s = SharedTaskState(task_id="task-1")
        assert s.task_id == "task-1"
        assert s.decisions == []
        assert s.artifacts == {}
        assert s.blockers == []
        assert s.agent_history == []

    def test_create_full(self) -> None:
        now = datetime.now()
        dec = Decision(description="choose Claude", agent_engine=AgentEngineType.CLAUDE_CODE)
        act = AgentAction(agent_engine=AgentEngineType.CLAUDE_CODE, action_type="execute")
        s = SharedTaskState(
            task_id="task-2",
            decisions=[dec],
            artifacts={"report": "draft v1"},
            blockers=["need API key"],
            agent_history=[act],
            created_at=now,
            updated_at=now,
        )
        assert len(s.decisions) == 1
        assert s.artifacts["report"] == "draft v1"
        assert s.blockers == ["need API key"]
        assert len(s.agent_history) == 1
        assert s.created_at == now

    def test_empty_task_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SharedTaskState(task_id="")

    def test_add_decision(self) -> None:
        s = SharedTaskState(task_id="t1")
        dec = Decision(description="pick Ollama", agent_engine=AgentEngineType.OLLAMA)
        old_updated = s.updated_at
        s.add_decision(dec)
        assert len(s.decisions) == 1
        assert s.decisions[0] == dec
        assert s.updated_at >= old_updated

    def test_add_action(self) -> None:
        s = SharedTaskState(task_id="t1")
        act = AgentAction(agent_engine=AgentEngineType.GEMINI_CLI, action_type="plan")
        old_updated = s.updated_at
        s.add_action(act)
        assert len(s.agent_history) == 1
        assert s.agent_history[0] == act
        assert s.updated_at >= old_updated

    def test_add_artifact(self) -> None:
        s = SharedTaskState(task_id="t1")
        s.add_artifact("code", "def hello(): pass")
        assert s.artifacts["code"] == "def hello(): pass"

    def test_add_artifact_overwrites(self) -> None:
        s = SharedTaskState(task_id="t1")
        s.add_artifact("code", "v1")
        s.add_artifact("code", "v2")
        assert s.artifacts["code"] == "v2"

    def test_add_blocker(self) -> None:
        s = SharedTaskState(task_id="t1")
        s.add_blocker("need credentials")
        assert s.blockers == ["need credentials"]

    def test_add_blocker_dedup(self) -> None:
        s = SharedTaskState(task_id="t1")
        s.add_blocker("API rate limit")
        s.add_blocker("API rate limit")
        assert len(s.blockers) == 1

    def test_remove_blocker(self) -> None:
        s = SharedTaskState(task_id="t1")
        s.add_blocker("waiting for review")
        s.remove_blocker("waiting for review")
        assert s.blockers == []

    def test_remove_blocker_not_present(self) -> None:
        s = SharedTaskState(task_id="t1")
        old_updated = s.updated_at
        s.remove_blocker("nonexistent")
        assert s.blockers == []
        # updated_at should NOT change when nothing was removed
        assert s.updated_at == old_updated

    def test_last_agent_empty(self) -> None:
        s = SharedTaskState(task_id="t1")
        assert s.last_agent is None

    def test_last_agent(self) -> None:
        s = SharedTaskState(task_id="t1")
        s.add_action(AgentAction(agent_engine=AgentEngineType.OLLAMA, action_type="execute"))
        s.add_action(AgentAction(agent_engine=AgentEngineType.CLAUDE_CODE, action_type="review"))
        assert s.last_agent == AgentEngineType.CLAUDE_CODE

    def test_total_cost_usd_empty(self) -> None:
        s = SharedTaskState(task_id="t1")
        assert s.total_cost_usd == 0.0

    def test_total_cost_usd(self) -> None:
        s = SharedTaskState(task_id="t1")
        s.add_action(
            AgentAction(agent_engine=AgentEngineType.OLLAMA, action_type="execute", cost_usd=0.0)
        )
        s.add_action(
            AgentAction(
                agent_engine=AgentEngineType.CLAUDE_CODE, action_type="review", cost_usd=0.05
            )
        )
        s.add_action(
            AgentAction(agent_engine=AgentEngineType.GEMINI_CLI, action_type="plan", cost_usd=0.03)
        )
        assert abs(s.total_cost_usd - 0.08) < 1e-9

    def test_multiple_decisions(self) -> None:
        s = SharedTaskState(task_id="t1")
        for i in range(5):
            s.add_decision(
                Decision(description=f"decision {i}", agent_engine=AgentEngineType.OLLAMA)
            )
        assert len(s.decisions) == 5

    def test_auto_timestamps(self) -> None:
        before = datetime.now()
        s = SharedTaskState(task_id="t1")
        after = datetime.now()
        assert before <= s.created_at <= after
        assert before <= s.updated_at <= after


# ──────────────────────────────────────────────
# AgentAffinityScore
# ──────────────────────────────────────────────


class TestAgentAffinityScore:
    def test_create_minimal(self) -> None:
        a = AgentAffinityScore(engine=AgentEngineType.OLLAMA, topic="python")
        assert a.engine == AgentEngineType.OLLAMA
        assert a.topic == "python"
        assert a.familiarity == 0.0
        assert a.recency == 0.0
        assert a.success_rate == 0.0
        assert a.cost_efficiency == 0.0
        assert a.sample_count == 0
        assert a.last_used is None

    def test_create_full(self) -> None:
        now = datetime.now()
        a = AgentAffinityScore(
            engine=AgentEngineType.CLAUDE_CODE,
            topic="architecture",
            familiarity=0.9,
            recency=0.8,
            success_rate=0.95,
            cost_efficiency=0.6,
            sample_count=50,
            last_used=now,
        )
        assert a.familiarity == 0.9
        assert a.recency == 0.8
        assert a.success_rate == 0.95
        assert a.cost_efficiency == 0.6
        assert a.sample_count == 50
        assert a.last_used == now

    def test_empty_topic_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentAffinityScore(engine=AgentEngineType.OLLAMA, topic="")

    def test_familiarity_above_1_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentAffinityScore(engine=AgentEngineType.OLLAMA, topic="x", familiarity=1.1)

    def test_familiarity_below_0_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentAffinityScore(engine=AgentEngineType.OLLAMA, topic="x", familiarity=-0.1)

    def test_recency_above_1_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentAffinityScore(engine=AgentEngineType.OLLAMA, topic="x", recency=1.1)

    def test_success_rate_above_1_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentAffinityScore(engine=AgentEngineType.OLLAMA, topic="x", success_rate=1.1)

    def test_cost_efficiency_above_1_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentAffinityScore(engine=AgentEngineType.OLLAMA, topic="x", cost_efficiency=1.1)

    def test_negative_sample_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AgentAffinityScore(engine=AgentEngineType.OLLAMA, topic="x", sample_count=-1)

    def test_all_engine_types(self) -> None:
        for engine in AgentEngineType:
            a = AgentAffinityScore(engine=engine, topic="general")
            assert a.engine == engine


# ──────────────────────────────────────────────
# AgentAffinityScorer (service)
# ──────────────────────────────────────────────


class TestAgentAffinityScorer:
    def _make_affinity(
        self,
        engine: AgentEngineType = AgentEngineType.CLAUDE_CODE,
        topic: str = "python",
        familiarity: float = 0.5,
        recency: float = 0.5,
        success_rate: float = 0.5,
        cost_efficiency: float = 0.5,
        sample_count: int = 10,
    ) -> AgentAffinityScore:
        return AgentAffinityScore(
            engine=engine,
            topic=topic,
            familiarity=familiarity,
            recency=recency,
            success_rate=success_rate,
            cost_efficiency=cost_efficiency,
            sample_count=sample_count,
        )

    def test_score_all_zeros(self) -> None:
        a = self._make_affinity(familiarity=0, recency=0, success_rate=0, cost_efficiency=0)
        assert AgentAffinityScorer.score(a) == 0.0

    def test_score_all_ones(self) -> None:
        a = self._make_affinity(familiarity=1, recency=1, success_rate=1, cost_efficiency=1)
        assert abs(AgentAffinityScorer.score(a) - 1.0) < 1e-9

    def test_score_weights(self) -> None:
        # familiarity only
        a1 = self._make_affinity(familiarity=1, recency=0, success_rate=0, cost_efficiency=0)
        assert abs(AgentAffinityScorer.score(a1) - 0.40) < 1e-9

        # recency only
        a2 = self._make_affinity(familiarity=0, recency=1, success_rate=0, cost_efficiency=0)
        assert abs(AgentAffinityScorer.score(a2) - 0.25) < 1e-9

        # success only
        a3 = self._make_affinity(familiarity=0, recency=0, success_rate=1, cost_efficiency=0)
        assert abs(AgentAffinityScorer.score(a3) - 0.20) < 1e-9

        # cost only
        a4 = self._make_affinity(familiarity=0, recency=0, success_rate=0, cost_efficiency=1)
        assert abs(AgentAffinityScorer.score(a4) - 0.15) < 1e-9

    def test_score_mixed(self) -> None:
        a = self._make_affinity(familiarity=0.8, recency=0.6, success_rate=0.9, cost_efficiency=0.4)
        expected = 0.8 * 0.40 + 0.6 * 0.25 + 0.9 * 0.20 + 0.4 * 0.15
        assert abs(AgentAffinityScorer.score(a) - expected) < 1e-9

    def test_rank_empty(self) -> None:
        assert AgentAffinityScorer.rank([]) == []

    def test_rank_filters_low_samples(self) -> None:
        a = self._make_affinity(sample_count=2)
        assert AgentAffinityScorer.rank([a], min_samples=3) == []

    def test_rank_includes_at_threshold(self) -> None:
        a = self._make_affinity(sample_count=3)
        result = AgentAffinityScorer.rank([a], min_samples=3)
        assert len(result) == 1

    def test_rank_order(self) -> None:
        high = self._make_affinity(
            engine=AgentEngineType.CLAUDE_CODE,
            familiarity=1.0,
            recency=1.0,
            success_rate=1.0,
            cost_efficiency=1.0,
        )
        low = self._make_affinity(
            engine=AgentEngineType.OLLAMA,
            familiarity=0.1,
            recency=0.1,
            success_rate=0.1,
            cost_efficiency=0.1,
        )
        result = AgentAffinityScorer.rank([low, high])
        assert result[0][0] == AgentEngineType.CLAUDE_CODE
        assert result[1][0] == AgentEngineType.OLLAMA

    def test_select_best_empty(self) -> None:
        assert AgentAffinityScorer.select_best([]) is None

    def test_select_best_all_filtered(self) -> None:
        a = self._make_affinity(sample_count=1)
        assert AgentAffinityScorer.select_best([a], min_samples=5) is None

    def test_select_best(self) -> None:
        high = self._make_affinity(
            engine=AgentEngineType.GEMINI_CLI,
            familiarity=0.9,
            recency=0.9,
            success_rate=0.9,
            cost_efficiency=0.9,
        )
        low = self._make_affinity(
            engine=AgentEngineType.OLLAMA,
            familiarity=0.1,
            recency=0.1,
            success_rate=0.1,
            cost_efficiency=0.1,
        )
        assert AgentAffinityScorer.select_best([low, high]) == AgentEngineType.GEMINI_CLI


# ──────────────────────────────────────────────
# ExtractedInsight (value object from port)
# ──────────────────────────────────────────────


class TestExtractedInsight:
    def test_create_minimal(self) -> None:
        insight = ExtractedInsight(
            content="Python is good for ML",
            memory_type=CognitiveMemoryType.SEMANTIC,
        )
        assert insight.content == "Python is good for ML"
        assert insight.memory_type == CognitiveMemoryType.SEMANTIC
        assert insight.confidence == 0.5
        assert insight.source_engine == AgentEngineType.OLLAMA
        assert insight.tags == []

    def test_create_full(self) -> None:
        insight = ExtractedInsight(
            content="Task failed due to timeout",
            memory_type=CognitiveMemoryType.EPISODIC,
            confidence=0.9,
            source_engine=AgentEngineType.CLAUDE_CODE,
            tags=["error", "timeout"],
        )
        assert insight.confidence == 0.9
        assert insight.source_engine == AgentEngineType.CLAUDE_CODE
        assert insight.tags == ["error", "timeout"]

    def test_all_memory_types(self) -> None:
        for mt in CognitiveMemoryType:
            insight = ExtractedInsight(content="test", memory_type=mt)
            assert insight.memory_type == mt
