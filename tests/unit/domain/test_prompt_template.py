"""Tests for PromptTemplate entity — versioned prompt with performance tracking."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.entities.prompt_template import PromptTemplate
from domain.value_objects.model_tier import TaskType


class TestPromptTemplateCreation:
    def test_create_minimal(self):
        t = PromptTemplate(name="planner", version=1, content="You are a planner.")
        assert t.name == "planner"
        assert t.version == 1
        assert t.content == "You are a planner."
        assert t.task_type is None
        assert t.success_count == 0
        assert t.failure_count == 0
        assert t.total_cost_usd == 0.0
        assert t.id  # auto-generated uuid

    def test_create_with_task_type(self):
        t = PromptTemplate(
            name="coder",
            version=2,
            content="Write code.",
            task_type=TaskType.CODE_GENERATION,
        )
        assert t.task_type == TaskType.CODE_GENERATION

    def test_unique_ids(self):
        a = PromptTemplate(name="x", version=1, content="a")
        b = PromptTemplate(name="x", version=1, content="a")
        assert a.id != b.id


class TestPromptTemplateValidation:
    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            PromptTemplate(name="", version=1, content="ok")

    def test_empty_content_rejected(self):
        with pytest.raises(ValidationError):
            PromptTemplate(name="ok", version=1, content="")

    def test_version_zero_rejected(self):
        with pytest.raises(ValidationError):
            PromptTemplate(name="ok", version=0, content="ok")

    def test_negative_version_rejected(self):
        with pytest.raises(ValidationError):
            PromptTemplate(name="ok", version=-1, content="ok")

    def test_negative_success_count_rejected(self):
        with pytest.raises(ValidationError):
            PromptTemplate(name="ok", version=1, content="ok", success_count=-1)

    def test_negative_cost_rejected(self):
        with pytest.raises(ValidationError):
            PromptTemplate(name="ok", version=1, content="ok", total_cost_usd=-0.01)


class TestPromptTemplateMetrics:
    def test_sample_count_zero(self):
        t = PromptTemplate(name="x", version=1, content="c")
        assert t.sample_count == 0

    def test_sample_count_sums(self):
        t = PromptTemplate(name="x", version=1, content="c", success_count=3, failure_count=2)
        assert t.sample_count == 5

    def test_success_rate_zero_samples(self):
        t = PromptTemplate(name="x", version=1, content="c")
        assert t.success_rate == 0.0

    def test_success_rate_all_success(self):
        t = PromptTemplate(name="x", version=1, content="c", success_count=10, failure_count=0)
        assert t.success_rate == 1.0

    def test_success_rate_mixed(self):
        t = PromptTemplate(name="x", version=1, content="c", success_count=7, failure_count=3)
        assert t.success_rate == pytest.approx(0.7)

    def test_avg_cost_zero_samples(self):
        t = PromptTemplate(name="x", version=1, content="c")
        assert t.avg_cost_usd == 0.0

    def test_avg_cost_computed(self):
        t = PromptTemplate(
            name="x",
            version=1,
            content="c",
            success_count=4,
            failure_count=1,
            total_cost_usd=0.50,
        )
        assert t.avg_cost_usd == pytest.approx(0.10)


class TestRecordOutcome:
    def test_record_success(self):
        t = PromptTemplate(name="x", version=1, content="c")
        t.record_outcome(success=True, cost_usd=0.05)
        assert t.success_count == 1
        assert t.failure_count == 0
        assert t.total_cost_usd == pytest.approx(0.05)

    def test_record_failure(self):
        t = PromptTemplate(name="x", version=1, content="c")
        t.record_outcome(success=False, cost_usd=0.03)
        assert t.success_count == 0
        assert t.failure_count == 1
        assert t.total_cost_usd == pytest.approx(0.03)

    def test_record_multiple_outcomes(self):
        t = PromptTemplate(name="x", version=1, content="c")
        for _ in range(7):
            t.record_outcome(success=True, cost_usd=0.01)
        for _ in range(3):
            t.record_outcome(success=False, cost_usd=0.02)
        assert t.sample_count == 10
        assert t.success_rate == pytest.approx(0.7)
        assert t.total_cost_usd == pytest.approx(0.13)
        assert t.avg_cost_usd == pytest.approx(0.013)

    def test_record_outcome_zero_cost(self):
        t = PromptTemplate(name="x", version=1, content="c")
        t.record_outcome(success=True)
        assert t.success_count == 1
        assert t.total_cost_usd == 0.0
