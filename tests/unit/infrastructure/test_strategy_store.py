"""Tests for StrategyStore — JSONL file-based strategy persistence."""

from __future__ import annotations

from pathlib import Path

from domain.entities.strategy import EnginePreference, ModelPreference, RecoveryRule
from domain.ports.strategy_repository import StrategyRepository
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from infrastructure.evolution.strategy_store import StrategyStore


class TestStrategyStore:
    def setup_method(self, tmp_path: Path | None = None) -> None:
        import tempfile

        self._tmpdir = tempfile.mkdtemp()
        self.store = StrategyStore(base_dir=Path(self._tmpdir))

    def test_is_a_strategy_repository(self) -> None:
        assert isinstance(self.store, StrategyRepository)

    def test_recovery_rules_roundtrip(self) -> None:
        rules = [
            RecoveryRule(
                error_pattern="timeout",
                failed_tool="browser_navigate",
                alternative_tool="web_fetch",
                success_count=3,
                total_attempts=5,
            ),
            RecoveryRule(
                error_pattern="connection refused",
                alternative_tool="shell_exec",
            ),
        ]
        self.store.save_recovery_rules(rules)
        loaded = self.store.load_recovery_rules()
        assert len(loaded) == 2
        assert loaded[0].error_pattern == "timeout"
        assert loaded[0].success_count == 3
        assert loaded[1].error_pattern == "connection refused"

    def test_recovery_rules_empty_file(self) -> None:
        loaded = self.store.load_recovery_rules()
        assert loaded == []

    def test_append_recovery_rule(self) -> None:
        rule1 = RecoveryRule(error_pattern="err1", alternative_tool="alt1")
        rule2 = RecoveryRule(error_pattern="err2", alternative_tool="alt2")
        self.store.append_recovery_rule(rule1)
        self.store.append_recovery_rule(rule2)
        loaded = self.store.load_recovery_rules()
        assert len(loaded) == 2

    def test_model_preferences_roundtrip(self) -> None:
        prefs = [
            ModelPreference(
                task_type=TaskType.SIMPLE_QA,
                model="ollama/qwen3:8b",
                success_rate=0.85,
                avg_cost_usd=0.0,
                sample_count=20,
            ),
            ModelPreference(
                task_type=TaskType.CODE_GENERATION,
                model="claude-sonnet-4-6",
                success_rate=0.92,
                avg_cost_usd=0.05,
                sample_count=15,
            ),
        ]
        self.store.save_model_preferences(prefs)
        loaded = self.store.load_model_preferences()
        assert len(loaded) == 2
        assert loaded[0].task_type == TaskType.SIMPLE_QA
        assert loaded[0].success_rate == 0.85

    def test_model_preferences_empty(self) -> None:
        loaded = self.store.load_model_preferences()
        assert loaded == []

    def test_engine_preferences_roundtrip(self) -> None:
        prefs = [
            EnginePreference(
                task_type=TaskType.LONG_RUNNING_DEV,
                engine=AgentEngineType.OPENHANDS,
                success_rate=0.78,
                sample_count=10,
            ),
        ]
        self.store.save_engine_preferences(prefs)
        loaded = self.store.load_engine_preferences()
        assert len(loaded) == 1
        assert loaded[0].engine == AgentEngineType.OPENHANDS

    def test_engine_preferences_empty(self) -> None:
        loaded = self.store.load_engine_preferences()
        assert loaded == []

    def test_overwrite_on_save(self) -> None:
        self.store.save_recovery_rules([RecoveryRule(error_pattern="old", alternative_tool="x")])
        self.store.save_recovery_rules([RecoveryRule(error_pattern="new", alternative_tool="y")])
        loaded = self.store.load_recovery_rules()
        assert len(loaded) == 1
        assert loaded[0].error_pattern == "new"

    def test_invalid_json_line_skipped(self) -> None:
        # Write a valid rule then corrupt one line
        self.store.append_recovery_rule(RecoveryRule(error_pattern="valid", alternative_tool="alt"))
        path = self.store._rules_path
        with open(path, "a") as f:
            f.write("not valid json\n")
        self.store.append_recovery_rule(
            RecoveryRule(error_pattern="also_valid", alternative_tool="alt2")
        )
        loaded = self.store.load_recovery_rules()
        assert len(loaded) == 2  # invalid line skipped

    def test_creates_directory(self) -> None:
        import tempfile

        deep = Path(tempfile.mkdtemp()) / "deep" / "nested" / "dir"
        store = StrategyStore(base_dir=deep)
        assert deep.exists()
        store.save_recovery_rules([RecoveryRule(error_pattern="x", alternative_tool="y")])
        assert store.load_recovery_rules()[0].error_pattern == "x"
