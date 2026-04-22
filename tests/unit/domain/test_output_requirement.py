"""Tests for OutputRequirement VO and OutputRequirementClassifier service."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from domain.entities.fractal_engine import PlanNode
from domain.ports.llm_gateway import LLMGateway, LLMResponse
from domain.services.output_requirement_classifier import OutputRequirementClassifier
from domain.value_objects.output_requirement import OutputRequirement

# ── OutputRequirement enum ─────────────────────────────────


class TestOutputRequirement:
    def test_values(self):
        assert OutputRequirement.TEXT == "text"
        assert OutputRequirement.FILE_ARTIFACT == "file"
        assert OutputRequirement.CODE_ARTIFACT == "code"
        assert OutputRequirement.DATA_ARTIFACT == "data"

    def test_all_four_members(self):
        assert len(OutputRequirement) == 4

    def test_string_enum(self):
        assert isinstance(OutputRequirement.TEXT, str)
        assert OutputRequirement.FILE_ARTIFACT.value == "file"


# ── PlanNode.output_requirement ────────────────────────────


class TestPlanNodeOutputRequirement:
    def test_default_is_none(self):
        node = PlanNode(description="Do something")
        assert node.output_requirement is None

    def test_set_to_file(self):
        node = PlanNode(description="Create report")
        node.output_requirement = OutputRequirement.FILE_ARTIFACT
        assert node.output_requirement == OutputRequirement.FILE_ARTIFACT

    def test_set_to_code(self):
        node = PlanNode(
            description="Write Python script",
            output_requirement=OutputRequirement.CODE_ARTIFACT,
        )
        assert node.output_requirement == OutputRequirement.CODE_ARTIFACT


# ── OutputRequirementClassifier ────────────────────────────


def _llm_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="test-model",
        prompt_tokens=10,
        completion_tokens=10,
        cost_usd=0.0,
    )


class TestOutputRequirementClassifier:
    @pytest.fixture
    def llm(self) -> AsyncMock:
        return AsyncMock(spec=LLMGateway)

    @pytest.fixture
    def classifier(self, llm: AsyncMock) -> OutputRequirementClassifier:
        return OutputRequirementClassifier(llm=llm)

    async def test_classify_text(self, classifier, llm):
        llm.complete.return_value = _llm_response(
            json.dumps({"requirement": "text", "reason": "Factual question"})
        )
        result = await classifier.classify("What is the capital of Japan?")
        assert result == OutputRequirement.TEXT

    async def test_classify_file(self, classifier, llm):
        llm.complete.return_value = _llm_response(
            json.dumps({"requirement": "file", "reason": "Slide creation needed"})
        )
        result = await classifier.classify("Create a presentation about Hikawa Shrine")
        assert result == OutputRequirement.FILE_ARTIFACT

    async def test_classify_code(self, classifier, llm):
        llm.complete.return_value = _llm_response(
            json.dumps({"requirement": "code", "reason": "Script output needed"})
        )
        result = await classifier.classify("Write a Python Fibonacci script")
        assert result == OutputRequirement.CODE_ARTIFACT

    async def test_classify_data(self, classifier, llm):
        llm.complete.return_value = _llm_response(
            json.dumps({"requirement": "data", "reason": "External data fetch"})
        )
        result = await classifier.classify("Analyze stock prices for AAPL this month")
        assert result == OutputRequirement.DATA_ARTIFACT

    async def test_fallback_on_error(self, classifier, llm):
        llm.complete.side_effect = RuntimeError("LLM unavailable")
        result = await classifier.classify("Create slides")
        assert result == OutputRequirement.TEXT  # safe default

    async def test_parse_with_think_tags(self, classifier, llm):
        llm.complete.return_value = _llm_response(
            '<think>Analyzing...</think>{"requirement": "file", "reason": "Slides"}'
        )
        result = await classifier.classify("Make a PPTX")
        assert result == OutputRequirement.FILE_ARTIFACT

    async def test_parse_unknown_value_defaults_to_text(self, classifier, llm):
        llm.complete.return_value = _llm_response(
            json.dumps({"requirement": "unknown_type", "reason": "Unclear"})
        )
        result = await classifier.classify("Do something")
        assert result == OutputRequirement.TEXT

    async def test_parse_garbage_defaults_to_text(self, classifier, llm):
        llm.complete.return_value = _llm_response("Not valid JSON at all")
        # _parse should catch JSON parse error and return TEXT
        result = await classifier.classify("Something")
        # The complete call won't raise, but _parse returns TEXT for unparseable
        assert result == OutputRequirement.TEXT

    async def test_custom_model_passed_to_llm(self, classifier, llm):
        classifier._model = "custom/model"
        llm.complete.return_value = _llm_response(
            json.dumps({"requirement": "text", "reason": "Simple"})
        )
        await classifier.classify("Hello")
        llm.complete.assert_called_once()
        call_kwargs = llm.complete.call_args
        assert call_kwargs.kwargs.get("model") == "custom/model"
