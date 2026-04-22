"""Tests for domain/services/fractal_learner.py + domain/entities/fractal_learning.py.

Sprint 15.7 (TD-105): Learning extraction logic — pure domain, no I/O.
"""

from __future__ import annotations

import pytest

from domain.entities.fractal_engine import PlanNode
from domain.entities.fractal_learning import (
    ErrorPattern,
    SuccessfulPath,
    _goal_overlap,
    _ngram_set,
)
from domain.services.fractal_learner import FractalLearner, _extract_goal_fragment
from domain.value_objects.status import SubTaskStatus


def _node(desc: str, status: SubTaskStatus, **kwargs: object) -> PlanNode:
    """Helper to create a PlanNode with minimal args."""
    return PlanNode(description=desc, status=status, **kwargs)


# ── ErrorPattern entity ──


class TestErrorPattern:
    def test_matches_case_insensitive(self) -> None:
        p = ErrorPattern(
            goal_fragment="REST API",
            node_description="Setup project",
            error_message="timeout",
        )
        assert p.matches("Build a REST API", "setup project structure")

    def test_no_match_different_goal(self) -> None:
        p = ErrorPattern(
            goal_fragment="REST API",
            node_description="Setup project",
            error_message="timeout",
        )
        assert not p.matches("Build a CLI tool", "setup project structure")

    def test_no_match_different_node(self) -> None:
        p = ErrorPattern(
            goal_fragment="REST API",
            node_description="Setup project",
            error_message="timeout",
        )
        assert not p.matches("Build a REST API", "Deploy to production")

    def test_increment_updates_count_and_last_seen(self) -> None:
        p = ErrorPattern(
            goal_fragment="test",
            node_description="node",
            error_message="err",
        )
        first_seen = p.last_seen
        assert p.occurrence_count == 1
        p.increment()
        assert p.occurrence_count == 2
        assert p.last_seen >= first_seen


# ── SuccessfulPath entity ──


class TestSuccessfulPath:
    def test_matches_goal(self) -> None:
        sp = SuccessfulPath(
            goal_fragment="REST API",
            node_descriptions=["Setup", "Implement", "Test"],
        )
        assert sp.matches("Build a REST API with auth")

    def test_no_match(self) -> None:
        sp = SuccessfulPath(
            goal_fragment="REST API",
            node_descriptions=["Setup", "Implement"],
        )
        assert not sp.matches("Build a CLI tool")

    def test_increment(self) -> None:
        sp = SuccessfulPath(
            goal_fragment="test",
            node_descriptions=["a"],
        )
        assert sp.usage_count == 1
        sp.increment()
        assert sp.usage_count == 2


# ── FractalLearner.extract_error_patterns ──


class TestExtractErrorPatterns:
    def test_extracts_from_failed_nodes(self) -> None:
        nodes = [
            _node("Setup project", SubTaskStatus.SUCCESS),
            _node("Implement routes", SubTaskStatus.FAILED, error="timeout"),
            _node("Add auth", SubTaskStatus.FAILED, error="permission denied"),
        ]
        patterns = FractalLearner.extract_error_patterns("Build API", nodes)
        assert len(patterns) == 2
        assert patterns[0].error_message == "timeout"
        assert patterns[1].error_message == "permission denied"

    def test_no_patterns_when_all_success(self) -> None:
        nodes = [
            _node("Setup", SubTaskStatus.SUCCESS),
            _node("Build", SubTaskStatus.SUCCESS),
        ]
        patterns = FractalLearner.extract_error_patterns("goal", nodes)
        assert len(patterns) == 0

    def test_empty_nodes(self) -> None:
        patterns = FractalLearner.extract_error_patterns("goal", [])
        assert len(patterns) == 0

    def test_default_error_message(self) -> None:
        nodes = [_node("Fail node", SubTaskStatus.FAILED)]
        patterns = FractalLearner.extract_error_patterns("goal", nodes)
        assert len(patterns) == 1
        assert patterns[0].error_message == "Unknown error"

    def test_nesting_level_preserved(self) -> None:
        nodes = [
            _node("Deep node", SubTaskStatus.FAILED, error="err", nesting_level=2),
        ]
        patterns = FractalLearner.extract_error_patterns("goal", nodes)
        assert patterns[0].nesting_level == 2


# ── FractalLearner.extract_successful_path ──


class TestExtractSuccessfulPath:
    def test_all_success_produces_path(self) -> None:
        nodes = [
            _node("Setup", SubTaskStatus.SUCCESS, cost_usd=0.01),
            _node("Build", SubTaskStatus.SUCCESS, cost_usd=0.02),
            _node("Test", SubTaskStatus.DEGRADED, cost_usd=0.0),
        ]
        path = FractalLearner.extract_successful_path("Build API", nodes)
        assert path is not None
        assert len(path.node_descriptions) == 3
        assert path.total_cost_usd == pytest.approx(0.03)

    def test_any_failure_returns_none(self) -> None:
        nodes = [
            _node("Setup", SubTaskStatus.SUCCESS),
            _node("Build", SubTaskStatus.FAILED, error="err"),
        ]
        path = FractalLearner.extract_successful_path("Build API", nodes)
        assert path is None

    def test_empty_nodes_returns_none(self) -> None:
        path = FractalLearner.extract_successful_path("goal", [])
        assert path is None


# ── FractalLearner.merge ──


class TestMergePatterns:
    def test_merge_error_pattern(self) -> None:
        existing = ErrorPattern(
            goal_fragment="API",
            node_description="Setup",
            error_message="timeout",
        )
        new = ErrorPattern(
            goal_fragment="API",
            node_description="Setup",
            error_message="timeout",
        )
        result = FractalLearner.merge_error_pattern(existing, new)
        assert result.occurrence_count == 2
        assert result is existing

    def test_merge_successful_path_keeps_lower_cost(self) -> None:
        existing = SuccessfulPath(
            goal_fragment="API",
            node_descriptions=["a", "b"],
            total_cost_usd=0.10,
        )
        new = SuccessfulPath(
            goal_fragment="API",
            node_descriptions=["a", "b"],
            total_cost_usd=0.05,
        )
        result = FractalLearner.merge_successful_path(existing, new)
        assert result.usage_count == 2
        assert result.total_cost_usd == pytest.approx(0.05)

    def test_merge_successful_path_no_downgrade_if_existing_cheaper(self) -> None:
        existing = SuccessfulPath(
            goal_fragment="API",
            node_descriptions=["a"],
            total_cost_usd=0.01,
        )
        new = SuccessfulPath(
            goal_fragment="API",
            node_descriptions=["a"],
            total_cost_usd=0.10,
        )
        FractalLearner.merge_successful_path(existing, new)
        assert existing.total_cost_usd == pytest.approx(0.01)


# ── _extract_goal_fragment ──


class TestExtractGoalFragment:
    def test_short_goal_unchanged(self) -> None:
        assert _extract_goal_fragment("Build API") == "Build API"

    def test_sentence_boundary(self) -> None:
        assert _extract_goal_fragment("Build API. Then deploy.") == "Build API"

    def test_japanese_period(self) -> None:
        assert _extract_goal_fragment("APIを作る。デプロイする。") == "APIを作る"

    def test_newline_boundary(self) -> None:
        assert _extract_goal_fragment("Build API\nStep 2") == "Build API"

    def test_truncates_long_goal(self) -> None:
        long_goal = "a" * 200
        result = _extract_goal_fragment(long_goal)
        assert len(result) == 80


# ── N-gram overlap matching ──


class TestNgramOverlap:
    """Tests for character n-gram overlap matching (CJK + Latin)."""

    def test_exact_substring_fast_path(self) -> None:
        assert _goal_overlap("REST API", "Build a REST API")

    def test_rephrased_english(self) -> None:
        assert _goal_overlap(
            "Build a REST API with authentication",
            "Create an authenticated REST API service",
        )

    def test_rephrased_japanese(self) -> None:
        assert _goal_overlap(
            "素数判定関数をPythonで作成して",
            "素数判定を高速化する関数をPythonで実装して",
        )

    def test_no_overlap(self) -> None:
        assert not _goal_overlap("REST API", "Machine learning pipeline")

    def test_short_fragment(self) -> None:
        # Fragments shorter than n-gram size still work
        assert _goal_overlap("API", "Build an API")

    def test_empty_fragment_returns_false(self) -> None:
        assert not _goal_overlap("", "some goal")

    def test_ngram_set_generation(self) -> None:
        ngrams = _ngram_set("abcde", n=3)
        assert ngrams == {"abc", "bcd", "cde"}

    def test_ngram_set_short_text(self) -> None:
        ngrams = _ngram_set("ab", n=4)
        assert ngrams == {"ab"}

    def test_ngram_set_empty(self) -> None:
        assert _ngram_set("", n=4) == set()


class TestMatchesGoalOnEntities:
    """Test matches_goal() on ErrorPattern and SuccessfulPath."""

    def test_error_pattern_matches_rephrased(self) -> None:
        p = ErrorPattern(
            goal_fragment="素数判定関数をPythonで作成して",
            node_description="Create function",
            error_message="timeout",
        )
        assert p.matches_goal("素数判定を高速化する関数をPythonで実装して")

    def test_error_pattern_no_match_unrelated(self) -> None:
        p = ErrorPattern(
            goal_fragment="REST API",
            node_description="Setup",
            error_message="timeout",
        )
        assert not p.matches_goal("Machine learning pipeline")

    def test_successful_path_matches_rephrased(self) -> None:
        sp = SuccessfulPath(
            goal_fragment="素数判定関数をPythonで作成して",
            node_descriptions=["Step 1", "Step 2"],
        )
        assert sp.matches_goal("素数判定を高速化する関数をPythonで実装して")

    def test_successful_path_no_match_unrelated(self) -> None:
        sp = SuccessfulPath(
            goal_fragment="REST API",
            node_descriptions=["Setup"],
        )
        assert not sp.matches_goal("Deploy Docker container")
