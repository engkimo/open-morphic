"""Tests for AnswerExtractor — LLM output cleaning."""

from domain.services.answer_extractor import AnswerExtractor
from domain.value_objects.task_complexity import TaskComplexity


class TestAnswerExtractor:
    def test_empty_input(self) -> None:
        assert AnswerExtractor.extract("", TaskComplexity.SIMPLE) == ""

    def test_strip_think_tags_simple(self) -> None:
        raw = "<think>Let me calculate 1+1...</think>2"
        assert AnswerExtractor.extract(raw, TaskComplexity.SIMPLE) == "2"

    def test_strip_think_tags_complex(self) -> None:
        raw = "<think>reasoning...</think>Here is the full solution."
        result = AnswerExtractor.extract(raw, TaskComplexity.COMPLEX)
        assert result == "Here is the full solution."
        assert "<think>" not in result

    def test_strip_preamble_the_answer_is(self) -> None:
        raw = "The answer is 42"
        assert AnswerExtractor.extract(raw, TaskComplexity.SIMPLE) == "42"

    def test_strip_preamble_sure(self) -> None:
        raw = "Sure! Here is the answer: 42"
        assert AnswerExtractor.extract(raw, TaskComplexity.SIMPLE) == "42"

    def test_strip_preamble_certainly(self) -> None:
        raw = "Certainly! 7"
        assert AnswerExtractor.extract(raw, TaskComplexity.SIMPLE) == "7"

    def test_strip_preamble_here_is(self) -> None:
        raw = "Here's the answer: 100"
        assert AnswerExtractor.extract(raw, TaskComplexity.SIMPLE) == "100"

    def test_no_preamble_stripping_for_complex(self) -> None:
        raw = "The answer is 42 because of the following reasons..."
        result = AnswerExtractor.extract(raw, TaskComplexity.COMPLEX)
        assert "42" in result
        assert "reasons" in result

    def test_strip_trailing_explanation_simple(self) -> None:
        raw = "42\nThis is because 6 times 7 equals 42.\nLet me explain further."
        result = AnswerExtractor.extract(raw, TaskComplexity.SIMPLE)
        assert result == "42"

    def test_preserve_multiline_for_complex(self) -> None:
        raw = "Step 1: Do X\nStep 2: Do Y\nStep 3: Do Z"
        result = AnswerExtractor.extract(raw, TaskComplexity.COMPLEX)
        assert "Step 1" in result
        assert "Step 3" in result

    def test_combined_think_and_preamble(self) -> None:
        raw = "<think>hmm let me think</think>The answer is: 99"
        result = AnswerExtractor.extract(raw, TaskComplexity.SIMPLE)
        assert result == "99"

    def test_preserves_code_block_for_medium(self) -> None:
        raw = "```python\ndef fib(n):\n    pass\n```"
        result = AnswerExtractor.extract(raw, TaskComplexity.MEDIUM)
        assert "```python" in result
