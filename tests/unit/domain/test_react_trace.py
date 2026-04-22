"""Tests for ReAct trace entities."""

import pytest
from pydantic import ValidationError

from domain.entities.react_trace import ReactStep, ReactTrace, ToolCallRecord


class TestToolCallRecord:
    def test_valid_creation(self):
        tc = ToolCallRecord(id="call_1", tool_name="web_search", arguments={"query": "hello"})
        assert tc.id == "call_1"
        assert tc.tool_name == "web_search"
        assert tc.arguments == {"query": "hello"}

    def test_empty_id_rejected(self):
        with pytest.raises(ValidationError):
            ToolCallRecord(id="", tool_name="web_search")

    def test_empty_tool_name_rejected(self):
        with pytest.raises(ValidationError):
            ToolCallRecord(id="call_1", tool_name="")

    def test_default_arguments(self):
        tc = ToolCallRecord(id="call_1", tool_name="shell_exec")
        assert tc.arguments == {}


class TestReactStep:
    def test_valid_step(self):
        step = ReactStep(step_number=0, thought="Let me search")
        assert step.step_number == 0
        assert step.thought == "Let me search"
        assert step.tool_calls == []
        assert step.observations == []
        assert step.error is None

    def test_negative_step_number_rejected(self):
        with pytest.raises(ValidationError):
            ReactStep(step_number=-1)

    def test_with_tool_calls(self):
        tc = ToolCallRecord(id="c1", tool_name="web_search", arguments={"query": "test"})
        step = ReactStep(step_number=1, tool_calls=[tc], observations=["result"])
        assert len(step.tool_calls) == 1
        assert len(step.observations) == 1

    def test_with_error(self):
        step = ReactStep(step_number=0, error="timeout")
        assert step.error == "timeout"


class TestReactTrace:
    def test_empty_trace(self):
        trace = ReactTrace()
        assert trace.steps == []
        assert trace.final_answer is None
        assert trace.terminated_reason is None
        assert trace.total_iterations == 0

    def test_total_iterations(self):
        trace = ReactTrace(
            steps=[ReactStep(step_number=0), ReactStep(step_number=1), ReactStep(step_number=2)],
            final_answer="done",
            terminated_reason="final_answer",
        )
        assert trace.total_iterations == 3

    def test_valid_terminated_reasons(self):
        for reason in ("final_answer", "max_iterations", "error"):
            trace = ReactTrace(terminated_reason=reason)
            assert trace.terminated_reason == reason

    def test_invalid_terminated_reason_rejected(self):
        with pytest.raises(ValidationError):
            ReactTrace(terminated_reason="invalid")

    def test_mutability(self):
        trace = ReactTrace()
        trace.steps.append(ReactStep(step_number=0))
        trace.final_answer = "answer"
        trace.terminated_reason = "final_answer"
        assert trace.total_iterations == 1
