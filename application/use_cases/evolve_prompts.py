"""EvolvePromptsUseCase — prompt template versioning with performance tracking.

Creates versioned prompt templates, records outcomes, selects the best
performing version, and suggests improvements from failure patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.entities.prompt_template import PromptTemplate
from domain.ports.prompt_template_repository import PromptTemplateRepository
from domain.value_objects.model_tier import TaskType


@dataclass
class PromptSuggestion:
    """A suggested improvement to a prompt template."""

    template_name: str
    current_version: int
    suggestion: str
    reason: str


@dataclass
class PromptEvolutionResult:
    """Result of a prompt evolution analysis."""

    templates_analyzed: int = 0
    suggestions: list[PromptSuggestion] = field(default_factory=list)
    best_templates: dict[str, int] = field(default_factory=dict)  # name → version


class EvolvePromptsUseCase:
    """Manage prompt templates with performance-based evolution."""

    def __init__(
        self,
        repo: PromptTemplateRepository,
        min_samples: int = 5,
    ) -> None:
        self._repo = repo
        self._min_samples = min_samples

    async def create_version(
        self,
        name: str,
        content: str,
        task_type: TaskType | None = None,
    ) -> PromptTemplate:
        """Create a new version of a prompt template.

        Auto-increments version number from the latest version.
        """
        latest = await self._repo.get_latest(name)
        version = (latest.version + 1) if latest else 1

        template = PromptTemplate(
            name=name,
            version=version,
            content=content,
            task_type=task_type,
        )
        await self._repo.save(template)
        return template

    async def record_outcome(
        self,
        name: str,
        version: int,
        success: bool,
        cost_usd: float = 0.0,
    ) -> bool:
        """Record an execution outcome for a template version.

        Returns True if the template was found and updated.
        """
        template = await self._repo.get_by_name_and_version(name, version)
        if template is None:
            return False

        template.record_outcome(success, cost_usd)
        await self._repo.save(template)
        return True

    async def get_best_template(self, name: str) -> PromptTemplate | None:
        """Get the best-performing version of a template.

        Requires min_samples outcomes. Falls back to latest version
        if no version has enough data.
        """
        versions = await self._repo.list_by_name(name)
        if not versions:
            return None

        # Filter to versions with enough samples
        qualified = [v for v in versions if v.sample_count >= self._min_samples]
        if not qualified:
            return versions[0]  # fallback: latest version

        # Sort by success_rate descending, then by avg_cost ascending
        qualified.sort(key=lambda v: (-v.success_rate, v.avg_cost_usd))
        return qualified[0]

    async def suggest_improvements(
        self,
        name: str,
    ) -> list[PromptSuggestion]:
        """Analyze template performance and suggest improvements.

        Compares versions to identify what works and what doesn't.
        """
        versions = await self._repo.list_by_name(name)
        if len(versions) < 2:
            return []

        suggestions: list[PromptSuggestion] = []
        latest = versions[0]

        # Check if latest is underperforming compared to an older version
        for older in versions[1:]:
            if (
                older.sample_count >= self._min_samples
                and latest.sample_count >= self._min_samples
                and older.success_rate > latest.success_rate + 0.1
            ):
                suggestions.append(
                    PromptSuggestion(
                        template_name=name,
                        current_version=latest.version,
                        suggestion=f"Revert to v{older.version} or merge its approach",
                        reason=(
                            f"v{older.version} has {older.success_rate:.0%} success "
                            f"vs v{latest.version} at {latest.success_rate:.0%}"
                        ),
                    )
                )

        # Check if latest has high failure rate
        if latest.sample_count >= self._min_samples and latest.success_rate < 0.5:
            suggestions.append(
                PromptSuggestion(
                    template_name=name,
                    current_version=latest.version,
                    suggestion="Consider rewriting — success rate below 50%",
                    reason=f"v{latest.version}: {latest.success_rate:.0%} success "
                    f"over {latest.sample_count} samples",
                )
            )

        # Check cost regression
        for older in versions[1:]:
            if (
                older.sample_count >= self._min_samples
                and latest.sample_count >= self._min_samples
                and latest.avg_cost_usd > older.avg_cost_usd * 1.5
                and latest.success_rate <= older.success_rate
            ):
                suggestions.append(
                    PromptSuggestion(
                        template_name=name,
                        current_version=latest.version,
                        suggestion="Cost increased without quality improvement",
                        reason=(
                            f"v{latest.version} costs ${latest.avg_cost_usd:.4f}/task "
                            f"vs v{older.version} at ${older.avg_cost_usd:.4f}/task"
                        ),
                    )
                )
                break  # only one cost suggestion

        return suggestions

    async def run_evolution(self) -> PromptEvolutionResult:
        """Analyze all templates and produce evolution suggestions."""
        all_templates = await self._repo.list_all()
        if not all_templates:
            return PromptEvolutionResult()

        # Group by name
        by_name: dict[str, list[PromptTemplate]] = {}
        for t in all_templates:
            by_name.setdefault(t.name, []).append(t)

        result = PromptEvolutionResult(templates_analyzed=len(by_name))

        for name in by_name:
            # Best template per name
            best = await self.get_best_template(name)
            if best:
                result.best_templates[name] = best.version

            # Suggestions per name
            suggestions = await self.suggest_improvements(name)
            result.suggestions.extend(suggestions)

        return result
