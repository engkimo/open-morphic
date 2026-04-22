"""SystemicEvolutionUseCase — Level 3 system-wide evolution.

Combines Level 2 strategy updates with tool gap detection.
Identifies recurring failures that could be solved by new tools,
and uses DiscoverToolsUseCase to suggest them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from application.use_cases.analyze_execution import AnalyzeExecutionUseCase
from application.use_cases.discover_tools import DiscoverToolsUseCase
from application.use_cases.update_strategy import StrategyUpdate, UpdateStrategyUseCase
from domain.value_objects.evolution import EvolutionLevel


@dataclass
class EvolutionReport:
    """Full evolution report — all 3 levels."""

    level: EvolutionLevel
    strategy_update: StrategyUpdate | None = None
    tool_gaps_found: int = 0
    tools_suggested: list[str] = field(default_factory=list)
    summary: str = ""
    created_at: datetime = field(default_factory=datetime.now)


class SystemicEvolutionUseCase:
    """Level 3: Full system evolution — strategy + tool gap detection."""

    def __init__(
        self,
        analyze_execution: AnalyzeExecutionUseCase,
        update_strategy: UpdateStrategyUseCase,
        discover_tools: DiscoverToolsUseCase | None = None,
    ) -> None:
        self._analyze = analyze_execution
        self._update_strategy = update_strategy
        self._discover_tools = discover_tools

    async def identify_tool_gaps(self) -> list[str]:
        """Find recurring failures that could be solved by new tools.

        Looks at failure patterns and checks if any suggest missing tool capabilities.
        """
        patterns = await self._analyze.get_failure_patterns(limit=20)
        if not patterns:
            return []

        # Failures occurring 3+ times are candidates for tool gap
        recurring = [p for p in patterns if p.count >= 3]
        if not recurring:
            return []

        gaps: list[str] = []
        for pattern in recurring:
            gaps.append(pattern.error_pattern)
        return gaps

    async def suggest_tools_for_gaps(self, gaps: list[str]) -> list[str]:
        """Use DiscoverToolsUseCase to suggest tools for identified gaps."""
        if not self._discover_tools or not gaps:
            return []

        suggested: list[str] = []
        for gap in gaps[:5]:  # Limit to top 5 gaps
            result = await self._discover_tools.suggest_for_failure(
                error_message=gap, max_results=2
            )
            for s in result.suggestions:
                if s.name not in suggested:
                    suggested.append(s.name)
        return suggested

    async def run_evolution(self) -> EvolutionReport:
        """Full Level 3 evolution: strategy update + tool gap analysis."""
        # Level 2: Update strategies
        strategy_update = await self._update_strategy.run_full_update()

        # Level 3: Tool gap detection
        gaps = await self.identify_tool_gaps()
        suggested = await self.suggest_tools_for_gaps(gaps)

        # Build summary
        parts: list[str] = []
        if strategy_update.model_preferences_updated:
            parts.append(f"{strategy_update.model_preferences_updated} model preferences updated")
        if strategy_update.engine_preferences_updated:
            parts.append(f"{strategy_update.engine_preferences_updated} engine preferences updated")
        if strategy_update.recovery_rules_added:
            parts.append(f"{strategy_update.recovery_rules_added} recovery rules added")
        if gaps:
            parts.append(f"{len(gaps)} tool gaps found")
        if suggested:
            parts.append(f"{len(suggested)} tools suggested: {', '.join(suggested)}")

        summary = "; ".join(parts) if parts else "No changes needed"

        return EvolutionReport(
            level=EvolutionLevel.SYSTEMIC,
            strategy_update=strategy_update,
            tool_gaps_found=len(gaps),
            tools_suggested=suggested,
            summary=summary,
        )
