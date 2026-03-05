"""UpdateStrategyUseCase — Level 2 cross-session learning.

Recalculates model/engine preferences from execution history,
and extracts new recovery rules from failure→success sequences.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from domain.entities.execution_record import ExecutionRecord
from domain.entities.strategy import EnginePreference, ModelPreference, RecoveryRule
from domain.ports.execution_record_repository import ExecutionRecordRepository
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from infrastructure.evolution.strategy_store import StrategyStore


@dataclass
class StrategyUpdate:
    """Result of a strategy update run."""

    model_preferences_updated: int = 0
    engine_preferences_updated: int = 0
    recovery_rules_added: int = 0
    details: list[str] = field(default_factory=list)


class UpdateStrategyUseCase:
    """Level 2: Recalculate preferences from execution history."""

    def __init__(
        self,
        execution_repo: ExecutionRecordRepository,
        strategy_store: StrategyStore,
        min_samples: int = 5,
    ) -> None:
        self._execution_repo = execution_repo
        self._strategy_store = strategy_store
        self._min_samples = min_samples

    async def update_model_preferences(self) -> list[ModelPreference]:
        """Recalculate model preferences from execution history."""
        records = await self._execution_repo.list_recent(limit=1000)
        if not records:
            return []

        # Group by (task_type, model)
        groups: dict[tuple[TaskType, str], list[ExecutionRecord]] = defaultdict(list)
        for r in records:
            if r.model_used:
                groups[(r.task_type, r.model_used)].append(r)

        prefs: list[ModelPreference] = []
        for (task_type, model), group in groups.items():
            if len(group) < self._min_samples:
                continue
            success_count = sum(1 for r in group if r.success)
            total_cost = sum(r.cost_usd for r in group)
            total_duration = sum(r.duration_seconds for r in group)
            n = len(group)

            prefs.append(
                ModelPreference(
                    task_type=task_type,
                    model=model,
                    success_rate=success_count / n,
                    avg_cost_usd=total_cost / n,
                    avg_duration_seconds=total_duration / n,
                    sample_count=n,
                )
            )

        self._strategy_store.save_model_preferences(prefs)
        return prefs

    async def update_engine_preferences(self) -> list[EnginePreference]:
        """Recalculate engine preferences from execution history."""
        records = await self._execution_repo.list_recent(limit=1000)
        if not records:
            return []

        groups: dict[tuple[TaskType, AgentEngineType], list[ExecutionRecord]] = defaultdict(list)
        for r in records:
            groups[(r.task_type, r.engine_used)].append(r)

        prefs: list[EnginePreference] = []
        for (task_type, engine), group in groups.items():
            if len(group) < self._min_samples:
                continue
            success_count = sum(1 for r in group if r.success)
            total_cost = sum(r.cost_usd for r in group)
            total_duration = sum(r.duration_seconds for r in group)
            n = len(group)

            prefs.append(
                EnginePreference(
                    task_type=task_type,
                    engine=engine,
                    success_rate=success_count / n,
                    avg_cost_usd=total_cost / n,
                    avg_duration_seconds=total_duration / n,
                    sample_count=n,
                )
            )

        self._strategy_store.save_engine_preferences(prefs)
        return prefs

    async def update_recovery_rules(self) -> list[RecoveryRule]:
        """Extract new recovery rules from failure patterns.

        Finds errors that appear in both failed and successful records,
        suggesting the successful approach is a viable alternative.
        """
        failures = await self._execution_repo.list_failures()
        if not failures:
            return []

        existing_rules = self._strategy_store.load_recovery_rules()
        existing_patterns = {r.error_pattern for r in existing_rules}

        # Group failures by normalized error
        error_groups: dict[str, list[ExecutionRecord]] = defaultdict(list)
        for f in failures:
            key = (f.error_message or "")[:80].strip()
            if key:
                error_groups[key].append(f)

        # Get recent successes to find alternatives
        all_records = await self._execution_repo.list_recent(limit=500)
        successes = [r for r in all_records if r.success]

        new_rules: list[RecoveryRule] = []
        for error_key, failed_records in error_groups.items():
            if error_key in existing_patterns:
                continue
            if len(failed_records) < 2:
                continue  # Need at least 2 failures to be a pattern

            # Find a successful record with the same task type
            failed_types = {r.task_type for r in failed_records}
            failed_engines = {r.engine_used for r in failed_records}

            for success in successes:
                if success.task_type in failed_types and success.engine_used not in failed_engines:
                    rule = RecoveryRule(
                        error_pattern=error_key,
                        failed_tool=failed_records[0].engine_used.value,
                        alternative_tool=success.engine_used.value,
                        success_count=1,
                        total_attempts=1,
                    )
                    new_rules.append(rule)
                    self._strategy_store.append_recovery_rule(rule)
                    existing_patterns.add(error_key)
                    break

        return new_rules

    async def run_full_update(self) -> StrategyUpdate:
        """Run all Level 2 updates."""
        model_prefs = await self.update_model_preferences()
        engine_prefs = await self.update_engine_preferences()
        recovery_rules = await self.update_recovery_rules()

        details: list[str] = []
        if model_prefs:
            details.append(f"Updated {len(model_prefs)} model preferences")
        if engine_prefs:
            details.append(f"Updated {len(engine_prefs)} engine preferences")
        if recovery_rules:
            details.append(f"Added {len(recovery_rules)} recovery rules")

        return StrategyUpdate(
            model_preferences_updated=len(model_prefs),
            engine_preferences_updated=len(engine_prefs),
            recovery_rules_added=len(recovery_rules),
            details=details,
        )
