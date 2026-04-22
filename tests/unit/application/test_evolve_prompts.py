"""Tests for EvolvePromptsUseCase — prompt template evolution."""

from __future__ import annotations

import pytest

from application.use_cases.evolve_prompts import (
    EvolvePromptsUseCase,
    PromptEvolutionResult,
)
from domain.entities.prompt_template import PromptTemplate
from domain.value_objects.model_tier import TaskType
from infrastructure.evolution.in_memory_prompt_template_repo import (
    InMemoryPromptTemplateRepository,
)


@pytest.fixture()
def repo() -> InMemoryPromptTemplateRepository:
    return InMemoryPromptTemplateRepository()


@pytest.fixture()
def uc(repo: InMemoryPromptTemplateRepository) -> EvolvePromptsUseCase:
    return EvolvePromptsUseCase(repo=repo, min_samples=5)


# ══════════════════════════════════════════════════════════════════
#  create_version
# ══════════════════════════════════════════════════════════════════


class TestCreateVersion:
    @pytest.mark.asyncio
    async def test_first_version_is_1(self, uc: EvolvePromptsUseCase):
        t = await uc.create_version("planner", "You plan.")
        assert t.version == 1
        assert t.name == "planner"
        assert t.content == "You plan."

    @pytest.mark.asyncio
    async def test_auto_increment_version(self, uc: EvolvePromptsUseCase):
        await uc.create_version("planner", "v1 content")
        t2 = await uc.create_version("planner", "v2 content")
        assert t2.version == 2

    @pytest.mark.asyncio
    async def test_different_names_independent(self, uc: EvolvePromptsUseCase):
        await uc.create_version("planner", "plan content")
        t = await uc.create_version("coder", "code content")
        assert t.version == 1

    @pytest.mark.asyncio
    async def test_task_type_stored(self, uc: EvolvePromptsUseCase):
        t = await uc.create_version("coder", "Write code.", task_type=TaskType.CODE_GENERATION)
        assert t.task_type == TaskType.CODE_GENERATION

    @pytest.mark.asyncio
    async def test_template_persisted(
        self, uc: EvolvePromptsUseCase, repo: InMemoryPromptTemplateRepository
    ):
        t = await uc.create_version("x", "content")
        stored = await repo.get_latest("x")
        assert stored is not None
        assert stored.id == t.id


# ══════════════════════════════════════════════════════════════════
#  record_outcome
# ══════════════════════════════════════════════════════════════════


class TestRecordOutcome:
    @pytest.mark.asyncio
    async def test_record_success(self, uc: EvolvePromptsUseCase):
        await uc.create_version("x", "content")
        result = await uc.record_outcome("x", 1, success=True, cost_usd=0.01)
        assert result is True

    @pytest.mark.asyncio
    async def test_record_updates_metrics(
        self, uc: EvolvePromptsUseCase, repo: InMemoryPromptTemplateRepository
    ):
        await uc.create_version("x", "content")
        await uc.record_outcome("x", 1, success=True, cost_usd=0.05)
        await uc.record_outcome("x", 1, success=False, cost_usd=0.03)
        t = await repo.get_by_name_and_version("x", 1)
        assert t is not None
        assert t.success_count == 1
        assert t.failure_count == 1
        assert t.total_cost_usd == pytest.approx(0.08)

    @pytest.mark.asyncio
    async def test_record_nonexistent_returns_false(self, uc: EvolvePromptsUseCase):
        result = await uc.record_outcome("missing", 99, success=True)
        assert result is False


# ══════════════════════════════════════════════════════════════════
#  get_best_template
# ══════════════════════════════════════════════════════════════════


class TestGetBestTemplate:
    @pytest.mark.asyncio
    async def test_no_templates_returns_none(self, uc: EvolvePromptsUseCase):
        result = await uc.get_best_template("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_fallback_to_latest_when_no_qualified(self, uc: EvolvePromptsUseCase):
        await uc.create_version("x", "v1")
        await uc.create_version("x", "v2")
        # No outcomes recorded → no version qualifies → fallback to latest (v2)
        best = await uc.get_best_template("x")
        assert best is not None
        assert best.version == 2

    @pytest.mark.asyncio
    async def test_best_by_success_rate(self, uc: EvolvePromptsUseCase):
        await uc.create_version("x", "v1")
        await uc.create_version("x", "v2")
        # v1: 4/5 = 80% success
        for _ in range(4):
            await uc.record_outcome("x", 1, success=True, cost_usd=0.01)
        await uc.record_outcome("x", 1, success=False, cost_usd=0.01)
        # v2: 3/5 = 60% success
        for _ in range(3):
            await uc.record_outcome("x", 2, success=True, cost_usd=0.01)
        for _ in range(2):
            await uc.record_outcome("x", 2, success=False, cost_usd=0.01)

        best = await uc.get_best_template("x")
        assert best is not None
        assert best.version == 1  # higher success rate

    @pytest.mark.asyncio
    async def test_tiebreak_by_cost(self, uc: EvolvePromptsUseCase):
        await uc.create_version("x", "v1")
        await uc.create_version("x", "v2")
        # Both 80% success, but v2 cheaper
        for _ in range(4):
            await uc.record_outcome("x", 1, success=True, cost_usd=0.10)
        await uc.record_outcome("x", 1, success=False, cost_usd=0.10)
        for _ in range(4):
            await uc.record_outcome("x", 2, success=True, cost_usd=0.01)
        await uc.record_outcome("x", 2, success=False, cost_usd=0.01)

        best = await uc.get_best_template("x")
        assert best is not None
        assert best.version == 2  # cheaper at same success rate


# ══════════════════════════════════════════════════════════════════
#  suggest_improvements
# ══════════════════════════════════════════════════════════════════


class TestSuggestImprovements:
    @pytest.mark.asyncio
    async def test_no_suggestions_single_version(self, uc: EvolvePromptsUseCase):
        await uc.create_version("x", "v1")
        suggestions = await uc.suggest_improvements("x")
        assert suggestions == []

    @pytest.mark.asyncio
    async def test_regression_detected(self, uc: EvolvePromptsUseCase):
        """Latest version underperforming older → revert suggestion."""
        await uc.create_version("x", "v1")
        await uc.create_version("x", "v2")
        # v1: 90% success
        for _ in range(9):
            await uc.record_outcome("x", 1, success=True, cost_usd=0.01)
        await uc.record_outcome("x", 1, success=False, cost_usd=0.01)
        # v2 (latest): 50% success
        for _ in range(5):
            await uc.record_outcome("x", 2, success=True, cost_usd=0.01)
        for _ in range(5):
            await uc.record_outcome("x", 2, success=False, cost_usd=0.01)

        suggestions = await uc.suggest_improvements("x")
        revert = [s for s in suggestions if "Revert" in s.suggestion]
        assert len(revert) >= 1
        assert "v1" in revert[0].suggestion

    @pytest.mark.asyncio
    async def test_high_failure_rate_detected(self, uc: EvolvePromptsUseCase):
        """Latest version < 50% success → rewrite suggestion."""
        await uc.create_version("x", "v1")
        await uc.create_version("x", "v2")
        # v2: 40% success (below 50%)
        for _ in range(4):
            await uc.record_outcome("x", 2, success=True, cost_usd=0.01)
        for _ in range(6):
            await uc.record_outcome("x", 2, success=False, cost_usd=0.01)

        suggestions = await uc.suggest_improvements("x")
        rewrite = [s for s in suggestions if "rewriting" in s.suggestion]
        assert len(rewrite) >= 1

    @pytest.mark.asyncio
    async def test_cost_regression_detected(self, uc: EvolvePromptsUseCase):
        """Latest costs 1.5x+ more without quality gain → cost suggestion."""
        await uc.create_version("x", "v1")
        await uc.create_version("x", "v2")
        # v1: 80% success, avg $0.01/task
        for _ in range(4):
            await uc.record_outcome("x", 1, success=True, cost_usd=0.01)
        await uc.record_outcome("x", 1, success=False, cost_usd=0.01)
        # v2: 80% success, avg $0.05/task (5x more expensive)
        for _ in range(4):
            await uc.record_outcome("x", 2, success=True, cost_usd=0.05)
        await uc.record_outcome("x", 2, success=False, cost_usd=0.05)

        suggestions = await uc.suggest_improvements("x")
        cost = [s for s in suggestions if "Cost" in s.suggestion]
        assert len(cost) >= 1

    @pytest.mark.asyncio
    async def test_no_suggestion_when_insufficient_samples(self, uc: EvolvePromptsUseCase):
        """Need min_samples (5) to generate suggestions."""
        await uc.create_version("x", "v1")
        await uc.create_version("x", "v2")
        # Only 2 outcomes each — below min_samples=5
        await uc.record_outcome("x", 1, success=True)
        await uc.record_outcome("x", 1, success=False)
        await uc.record_outcome("x", 2, success=False)
        await uc.record_outcome("x", 2, success=False)

        suggestions = await uc.suggest_improvements("x")
        assert suggestions == []

    @pytest.mark.asyncio
    async def test_no_regression_when_improvement(self, uc: EvolvePromptsUseCase):
        """No revert suggestion when latest outperforms older."""
        await uc.create_version("x", "v1")
        await uc.create_version("x", "v2")
        # v1: 60% success
        for _ in range(3):
            await uc.record_outcome("x", 1, success=True, cost_usd=0.01)
        for _ in range(2):
            await uc.record_outcome("x", 1, success=False, cost_usd=0.01)
        # v2: 90% success
        for _ in range(9):
            await uc.record_outcome("x", 2, success=True, cost_usd=0.01)
        await uc.record_outcome("x", 2, success=False, cost_usd=0.01)

        suggestions = await uc.suggest_improvements("x")
        revert = [s for s in suggestions if "Revert" in s.suggestion]
        assert revert == []


# ══════════════════════════════════════════════════════════════════
#  run_evolution
# ══════════════════════════════════════════════════════════════════


class TestRunEvolution:
    @pytest.mark.asyncio
    async def test_empty_returns_defaults(self, uc: EvolvePromptsUseCase):
        result = await uc.run_evolution()
        assert result.templates_analyzed == 0
        assert result.suggestions == []
        assert result.best_templates == {}

    @pytest.mark.asyncio
    async def test_single_name_analyzed(self, uc: EvolvePromptsUseCase):
        await uc.create_version("planner", "v1")
        result = await uc.run_evolution()
        assert result.templates_analyzed == 1
        assert "planner" in result.best_templates
        assert result.best_templates["planner"] == 1

    @pytest.mark.asyncio
    async def test_multiple_names_analyzed(self, uc: EvolvePromptsUseCase):
        await uc.create_version("planner", "v1")
        await uc.create_version("coder", "code v1")
        await uc.create_version("coder", "code v2")
        result = await uc.run_evolution()
        assert result.templates_analyzed == 2
        assert "planner" in result.best_templates
        assert "coder" in result.best_templates

    @pytest.mark.asyncio
    async def test_evolution_collects_suggestions(self, uc: EvolvePromptsUseCase):
        await uc.create_version("x", "v1")
        await uc.create_version("x", "v2")
        # v1: 90%, v2: 40% → should get revert + rewrite suggestions
        for _ in range(9):
            await uc.record_outcome("x", 1, success=True, cost_usd=0.01)
        await uc.record_outcome("x", 1, success=False, cost_usd=0.01)
        for _ in range(4):
            await uc.record_outcome("x", 2, success=True, cost_usd=0.01)
        for _ in range(6):
            await uc.record_outcome("x", 2, success=False, cost_usd=0.01)

        result = await uc.run_evolution()
        assert len(result.suggestions) >= 2  # revert + rewrite
        assert result.best_templates["x"] == 1  # v1 is best

    @pytest.mark.asyncio
    async def test_evolution_result_dataclass(self):
        r = PromptEvolutionResult()
        assert r.templates_analyzed == 0
        assert r.suggestions == []
        assert r.best_templates == {}


# ══════════════════════════════════════════════════════════════════
#  InMemoryPromptTemplateRepository
# ══════════════════════════════════════════════════════════════════


class TestInMemoryPromptTemplateRepo:
    @pytest.mark.asyncio
    async def test_save_and_get_latest(self):
        repo = InMemoryPromptTemplateRepository()
        t1 = PromptTemplate(name="x", version=1, content="v1")
        t2 = PromptTemplate(name="x", version=2, content="v2")
        await repo.save(t1)
        await repo.save(t2)
        latest = await repo.get_latest("x")
        assert latest is not None
        assert latest.version == 2

    @pytest.mark.asyncio
    async def test_get_latest_nonexistent(self):
        repo = InMemoryPromptTemplateRepository()
        assert await repo.get_latest("nope") is None

    @pytest.mark.asyncio
    async def test_get_by_name_and_version(self):
        repo = InMemoryPromptTemplateRepository()
        t = PromptTemplate(name="x", version=3, content="v3")
        await repo.save(t)
        found = await repo.get_by_name_and_version("x", 3)
        assert found is not None
        assert found.id == t.id

    @pytest.mark.asyncio
    async def test_get_by_name_and_version_miss(self):
        repo = InMemoryPromptTemplateRepository()
        assert await repo.get_by_name_and_version("x", 99) is None

    @pytest.mark.asyncio
    async def test_list_by_name_ordered(self):
        repo = InMemoryPromptTemplateRepository()
        for v in [1, 3, 2]:
            await repo.save(PromptTemplate(name="x", version=v, content=f"v{v}"))
        versions = await repo.list_by_name("x")
        assert [t.version for t in versions] == [3, 2, 1]

    @pytest.mark.asyncio
    async def test_list_by_name_filters(self):
        repo = InMemoryPromptTemplateRepository()
        await repo.save(PromptTemplate(name="a", version=1, content="a"))
        await repo.save(PromptTemplate(name="b", version=1, content="b"))
        assert len(await repo.list_by_name("a")) == 1

    @pytest.mark.asyncio
    async def test_list_all_ordered(self):
        repo = InMemoryPromptTemplateRepository()
        await repo.save(PromptTemplate(name="b", version=1, content="b1"))
        await repo.save(PromptTemplate(name="a", version=2, content="a2"))
        await repo.save(PromptTemplate(name="a", version=1, content="a1"))
        all_t = await repo.list_all()
        # Sorted by (name, -version) → a:2, a:1, b:1
        assert [(t.name, t.version) for t in all_t] == [
            ("a", 2),
            ("a", 1),
            ("b", 1),
        ]

    @pytest.mark.asyncio
    async def test_save_updates_existing(self):
        repo = InMemoryPromptTemplateRepository()
        t = PromptTemplate(name="x", version=1, content="orig")
        await repo.save(t)
        t.record_outcome(success=True, cost_usd=0.1)
        await repo.save(t)
        found = await repo.get_by_name_and_version("x", 1)
        assert found is not None
        assert found.success_count == 1
