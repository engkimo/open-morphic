"""Tests for Learning repository CLI — Sprint 25.3 (TD-134).

Uses _set_container() to inject a mock container, verifying that CLI
commands correctly call learning_repo methods and format output.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from typer.testing import CliRunner

from domain.entities.fractal_learning import ErrorPattern, SuccessfulPath

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_error_pattern(
    goal: str = "Pythonで素数判定",
    node: str = "implement function",
    error: str = "SyntaxError in generated code",
    count: int = 3,
) -> ErrorPattern:
    return ErrorPattern(
        goal_fragment=goal,
        node_description=node,
        error_message=error,
        occurrence_count=count,
        first_seen=datetime(2026, 3, 29, 10, 0, 0),
        last_seen=datetime(2026, 3, 29, 14, 0, 0),
    )


def _make_successful_path(
    goal: str = "Pythonで素数判定",
    nodes: list[str] | None = None,
    cost: float = 0.0,
    usage: int = 2,
) -> SuccessfulPath:
    return SuccessfulPath(
        goal_fragment=goal,
        node_descriptions=nodes or ["plan", "implement", "test"],
        total_cost_usd=cost,
        usage_count=usage,
        first_used=datetime(2026, 3, 29, 10, 0, 0),
        last_used=datetime(2026, 3, 29, 14, 0, 0),
    )


def _make_container(
    patterns: list[ErrorPattern] | None = None,
    paths: list[SuccessfulPath] | None = None,
    repo_available: bool = True,
):
    patterns = patterns or []
    paths = paths or []
    if not repo_available:
        return MagicMock(learning_repo=None)
    repo = MagicMock()
    repo.list_error_patterns = AsyncMock(return_value=patterns)
    repo.list_successful_paths = AsyncMock(return_value=paths)
    repo.find_error_patterns_by_goal = AsyncMock(return_value=patterns)
    repo.find_successful_paths = AsyncMock(return_value=paths)
    return MagicMock(learning_repo=repo)


def _invoke(*args: str, container=None):
    from interface.cli._utils import _set_container
    from interface.cli.main import app

    if container:
        _set_container(container)
    result = runner.invoke(app, list(args))
    _set_container(None)
    return result


# ---------------------------------------------------------------------------
# morphic learning list
# ---------------------------------------------------------------------------


class TestListCommand:
    def test_list_all_empty(self):
        c = _make_container([], [])
        result = _invoke("learning", "list", container=c)
        assert result.exit_code == 0
        assert "No learning data" in result.output

    def test_list_all_with_data(self):
        c = _make_container(
            patterns=[_make_error_pattern()],
            paths=[_make_successful_path()],
        )
        result = _invoke("learning", "list", container=c)
        assert result.exit_code == 0
        assert "Error Patterns" in result.output
        assert "Successful Paths" in result.output

    def test_list_errors_only(self):
        c = _make_container(patterns=[_make_error_pattern()])
        result = _invoke("learning", "list", "--kind", "errors", container=c)
        assert result.exit_code == 0
        c.learning_repo.list_error_patterns.assert_called()

    def test_list_successes_only(self):
        c = _make_container(paths=[_make_successful_path()])
        result = _invoke(
            "learning", "list", "--kind", "successes", container=c
        )
        assert result.exit_code == 0
        c.learning_repo.list_successful_paths.assert_called()

    def test_list_no_repo(self):
        c = _make_container(repo_available=False)
        result = _invoke("learning", "list", container=c)
        assert result.exit_code == 1
        assert "not available" in result.output


# ---------------------------------------------------------------------------
# morphic learning search
# ---------------------------------------------------------------------------


class TestSearchCommand:
    def test_search_found(self):
        c = _make_container(
            patterns=[_make_error_pattern()],
            paths=[_make_successful_path()],
        )
        result = _invoke("learning", "search", "素数判定", container=c)
        assert result.exit_code == 0
        assert "Error Patterns matching" in result.output
        assert "Successful Paths matching" in result.output

    def test_search_no_results(self):
        c = _make_container([], [])
        result = _invoke("learning", "search", "nonexistent", container=c)
        assert result.exit_code == 0
        assert "No learning data matching" in result.output

    def test_search_no_repo(self):
        c = _make_container(repo_available=False)
        result = _invoke("learning", "search", "test", container=c)
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# morphic learning stats
# ---------------------------------------------------------------------------


class TestStatsCommand:
    def test_stats_empty(self):
        c = _make_container([], [])
        result = _invoke("learning", "stats", container=c)
        assert result.exit_code == 0
        assert "Learning Statistics" in result.output

    def test_stats_with_data(self):
        c = _make_container(
            patterns=[
                _make_error_pattern(count=5),
                _make_error_pattern(goal="other", count=2),
            ],
            paths=[
                _make_successful_path(cost=0.01, usage=3),
            ],
        )
        result = _invoke("learning", "stats", container=c)
        assert result.exit_code == 0
        assert "Learning Statistics" in result.output

    def test_stats_no_repo(self):
        c = _make_container(repo_available=False)
        result = _invoke("learning", "stats", container=c)
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Formatter tests
# ---------------------------------------------------------------------------


class TestLearningFormatters:
    def test_print_error_pattern_table(self):
        from interface.cli.formatters import print_error_pattern_table

        patterns = [
            _make_error_pattern(),
            _make_error_pattern(count=7, error="timeout"),
        ]
        print_error_pattern_table(patterns)

    def test_print_error_pattern_table_empty(self):
        from interface.cli.formatters import print_error_pattern_table

        print_error_pattern_table([])

    def test_print_successful_path_table(self):
        from interface.cli.formatters import print_successful_path_table

        paths = [
            _make_successful_path(),
            _make_successful_path(
                nodes=["a", "b", "c", "d", "e"],
                cost=0.05,
            ),
        ]
        print_successful_path_table(paths)

    def test_print_successful_path_table_empty(self):
        from interface.cli.formatters import print_successful_path_table

        print_successful_path_table([])

    def test_print_learning_stats(self):
        from interface.cli.formatters import print_learning_stats

        print_learning_stats(
            patterns=[_make_error_pattern(count=5)],
            paths=[_make_successful_path(cost=0.01)],
        )

    def test_print_learning_stats_empty(self):
        from interface.cli.formatters import print_learning_stats

        print_learning_stats([], [])
