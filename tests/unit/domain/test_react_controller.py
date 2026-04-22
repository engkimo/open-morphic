"""Tests for ReactController pure logic."""

from domain.services.react_controller import ReactController


class TestShouldContinue:
    def test_final_answer_no_tools(self):
        cont, reason = ReactController.should_continue(
            step_count=1, max_iterations=10, has_tool_calls=False, has_final_answer=True
        )
        assert not cont
        assert reason == "final_answer"

    def test_tool_calls_continues(self):
        cont, reason = ReactController.should_continue(
            step_count=1, max_iterations=10, has_tool_calls=True, has_final_answer=False
        )
        assert cont
        assert reason == "continue"

    def test_max_iterations_stops(self):
        cont, reason = ReactController.should_continue(
            step_count=10, max_iterations=10, has_tool_calls=True, has_final_answer=False
        )
        assert not cont
        assert reason == "max_iterations"

    def test_max_iterations_exact_boundary(self):
        cont, reason = ReactController.should_continue(
            step_count=5, max_iterations=5, has_tool_calls=False, has_final_answer=False
        )
        assert not cont
        assert reason == "max_iterations"

    def test_no_tools_no_answer_treated_as_final(self):
        cont, reason = ReactController.should_continue(
            step_count=1, max_iterations=10, has_tool_calls=False, has_final_answer=False
        )
        assert not cont
        assert reason == "final_answer"

    def test_tool_calls_with_final_answer_continues(self):
        # If LLM returns both tools AND text, continue with tools
        cont, reason = ReactController.should_continue(
            step_count=1, max_iterations=10, has_tool_calls=True, has_final_answer=True
        )
        assert cont
        assert reason == "continue"

    def test_step_zero(self):
        cont, reason = ReactController.should_continue(
            step_count=0, max_iterations=10, has_tool_calls=True, has_final_answer=False
        )
        assert cont
        assert reason == "continue"


class TestBuildToolResultMessage:
    def test_format(self):
        msg = ReactController.build_tool_result_message(
            tool_call_id="call_123",
            tool_name="web_search",
            result="Found 3 results",
        )
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "call_123"
        assert msg["name"] == "web_search"
        assert msg["content"] == "Found 3 results"

    def test_empty_result(self):
        msg = ReactController.build_tool_result_message(
            tool_call_id="call_1",
            tool_name="shell_exec",
            result="",
        )
        assert msg["content"] == ""
