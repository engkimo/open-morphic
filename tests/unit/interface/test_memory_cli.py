"""Tests for Memory CLI commands — Sprint 25.1 (TD-132).

Uses _set_container() to inject a mock container, verifying that CLI
commands correctly call memory_repo methods and format output.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from typer.testing import CliRunner

from domain.entities.memory import MemoryEntry
from domain.value_objects.status import MemoryType

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entry(
    memory_id: str = "aaaa-bbbb-cccc-dddd",
    content: str = "Test memory content",
    memory_type: MemoryType = MemoryType.L2_SEMANTIC,
    access_count: int = 3,
    importance_score: float = 0.8,
    metadata: dict | None = None,
) -> MemoryEntry:
    return MemoryEntry(
        id=memory_id,
        content=content,
        memory_type=memory_type,
        access_count=access_count,
        importance_score=importance_score,
        metadata=metadata or {},
        created_at=datetime(2026, 3, 29, 10, 0, 0),
        last_accessed=datetime(2026, 3, 29, 12, 0, 0),
    )


def _make_container(entries: list[MemoryEntry] | None = None):
    """Build a mock container with memory_repo."""
    entries = entries or []
    memory_repo = MagicMock()
    memory_repo.list_by_type = AsyncMock(return_value=entries)
    memory_repo.search = AsyncMock(return_value=entries)
    memory_repo.get_by_id = AsyncMock(return_value=entries[0] if entries else None)
    memory_repo.delete = AsyncMock()
    return MagicMock(memory_repo=memory_repo)


def _invoke(*args: str, container=None):
    """Invoke CLI with a mock container and return result."""
    from interface.cli._utils import _set_container
    from interface.cli.main import app

    if container:
        _set_container(container)
    result = runner.invoke(app, list(args))
    _set_container(None)
    return result


# ---------------------------------------------------------------------------
# morphic memory list
# ---------------------------------------------------------------------------


class TestListCommand:
    def test_list_empty(self):
        c = _make_container([])
        result = _invoke("memory", "list", container=c)
        assert result.exit_code == 0
        assert "No memory entries found" in result.output

    def test_list_all_types(self):
        entries = [_make_entry(), _make_entry(memory_id="eeee-ffff")]
        c = _make_container(entries)
        result = _invoke("memory", "list", container=c)
        assert result.exit_code == 0
        assert "Memory Entries" in result.output
        # list_by_type called for all 4 MemoryType values
        assert c.memory_repo.list_by_type.call_count == 4

    def test_list_filtered_by_type(self):
        entries = [_make_entry(memory_type=MemoryType.L1_ACTIVE)]
        c = _make_container(entries)
        result = _invoke("memory", "list", "--type", "l1_active", container=c)
        assert result.exit_code == 0
        c.memory_repo.list_by_type.assert_called_once_with(MemoryType.L1_ACTIVE, limit=50)

    def test_list_invalid_type(self):
        c = _make_container([])
        result = _invoke("memory", "list", "--type", "invalid", container=c)
        assert result.exit_code == 1
        assert "Unknown memory type" in result.output

    def test_list_with_limit(self):
        entries = [_make_entry()]
        c = _make_container(entries)
        result = _invoke("memory", "list", "--type", "l2_semantic", "--limit", "10", container=c)
        assert result.exit_code == 0
        c.memory_repo.list_by_type.assert_called_once_with(MemoryType.L2_SEMANTIC, limit=10)


# ---------------------------------------------------------------------------
# morphic memory search
# ---------------------------------------------------------------------------


class TestSearchCommand:
    def test_search_found(self):
        entries = [_make_entry(content="database optimization tips")]
        c = _make_container(entries)
        result = _invoke("memory", "search", "database", container=c)
        assert result.exit_code == 0
        assert "Results for" in result.output
        c.memory_repo.search.assert_called_once_with("database", top_k=10)

    def test_search_no_results(self):
        c = _make_container([])
        result = _invoke("memory", "search", "nonexistent", container=c)
        assert result.exit_code == 0
        assert "No results" in result.output

    def test_search_with_top_k(self):
        entries = [_make_entry()]
        c = _make_container(entries)
        result = _invoke("memory", "search", "query", "--top-k", "5", container=c)
        assert result.exit_code == 0
        c.memory_repo.search.assert_called_once_with("query", top_k=5)


# ---------------------------------------------------------------------------
# morphic memory show
# ---------------------------------------------------------------------------


class TestShowCommand:
    def test_show_found(self):
        entry = _make_entry(content="detailed memory content", metadata={"source_engine": "ollama"})
        c = _make_container([entry])
        result = _invoke("memory", "show", "aaaa-bbbb-cccc-dddd", container=c)
        assert result.exit_code == 0
        assert "aaaa-bbbb-cccc-dddd" in result.output
        assert "detailed memory content" in result.output

    def test_show_not_found(self):
        c = _make_container([])
        result = _invoke("memory", "show", "nonexistent-id", container=c)
        assert result.exit_code == 1
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# morphic memory stats
# ---------------------------------------------------------------------------


class TestStatsCommand:
    def test_stats_empty(self):
        c = _make_container([])
        result = _invoke("memory", "stats", container=c)
        assert result.exit_code == 0
        assert "Memory Statistics" in result.output
        assert "0" in result.output

    def test_stats_with_entries(self):
        entries = [
            _make_entry(access_count=5, importance_score=0.9),
            _make_entry(memory_id="x", access_count=3, importance_score=0.6),
        ]
        c = _make_container(entries)
        result = _invoke("memory", "stats", container=c)
        assert result.exit_code == 0
        assert "Memory Statistics" in result.output


# ---------------------------------------------------------------------------
# morphic memory delete
# ---------------------------------------------------------------------------


class TestDeleteCommand:
    def test_delete_existing(self):
        entry = _make_entry()
        c = _make_container([entry])
        result = _invoke("memory", "delete", "aaaa-bbbb-cccc-dddd", container=c)
        assert result.exit_code == 0
        assert "Deleted" in result.output
        c.memory_repo.delete.assert_called_once_with("aaaa-bbbb-cccc-dddd")

    def test_delete_not_found(self):
        c = _make_container([])
        result = _invoke("memory", "delete", "nonexistent-id", container=c)
        assert result.exit_code == 1
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# Formatter tests
# ---------------------------------------------------------------------------


class TestMemoryFormatters:
    def test_print_memory_table(self, capsys):
        from interface.cli.formatters import print_memory_table

        entries = [
            _make_entry(content="short"),
            _make_entry(
                memory_id="zzzz",
                content="A" * 60,
                memory_type=MemoryType.L3_FACTS,
                importance_score=0.3,
            ),
        ]
        print_memory_table(entries)

    def test_print_memory_table_empty(self, capsys):
        from interface.cli.formatters import print_memory_table

        print_memory_table([])

    def test_print_memory_detail(self, capsys):
        from interface.cli.formatters import print_memory_detail

        entry = _make_entry(
            content="detailed content here",
            metadata={"source_engine": "claude_code", "tags": ["test"]},
        )
        print_memory_detail(entry)

    def test_print_memory_stats(self, capsys):
        from interface.cli.formatters import print_memory_stats

        print_memory_stats(
            type_counts={"l1_active": 5, "l2_semantic": 10, "l3_facts": 3, "l4_cold": 0},
            total_entries=18,
            total_access=42,
            max_importance=0.95,
        )
