"""Tests for TaskComplexityClassifier — goal complexity assessment."""

from domain.services.task_complexity import TaskComplexityClassifier
from domain.value_objects.task_complexity import TaskComplexity


class TestTaskComplexityEnum:
    def test_values(self) -> None:
        assert TaskComplexity.SIMPLE == "simple"
        assert TaskComplexity.MEDIUM == "medium"
        assert TaskComplexity.COMPLEX == "complex"

    def test_all_members(self) -> None:
        assert len(TaskComplexity) == 3


class TestClassifySimple:
    """SIMPLE tasks: single action, 1 subtask."""

    def test_short_goal(self) -> None:
        assert TaskComplexityClassifier.classify("FizzBuzz") == TaskComplexity.SIMPLE

    def test_short_japanese(self) -> None:
        assert TaskComplexityClassifier.classify("FizzBuzzを書いて") == TaskComplexity.SIMPLE

    def test_fibonacci(self) -> None:
        result = TaskComplexityClassifier.classify("Implement fibonacci in Python")
        assert result == TaskComplexity.SIMPLE

    def test_write_function(self) -> None:
        result = TaskComplexityClassifier.classify("Write a function to sort a list")
        assert result == TaskComplexity.SIMPLE

    def test_fix_bug(self) -> None:
        result = TaskComplexityClassifier.classify("Fix the login bug in auth.py")
        assert result == TaskComplexity.SIMPLE

    def test_explain(self) -> None:
        result = TaskComplexityClassifier.classify("Explain how quicksort works")
        assert result == TaskComplexity.SIMPLE

    def test_hello_world(self) -> None:
        result = TaskComplexityClassifier.classify("Create a hello world program")
        assert result == TaskComplexity.SIMPLE

    def test_calculator(self) -> None:
        result = TaskComplexityClassifier.classify("Build a calculator")
        assert result == TaskComplexity.SIMPLE

    def test_palindrome(self) -> None:
        result = TaskComplexityClassifier.classify("Write a palindrome checker")
        assert result == TaskComplexity.SIMPLE

    def test_short_few_words(self) -> None:
        result = TaskComplexityClassifier.classify("Print numbers 1 to 100")
        assert result == TaskComplexity.SIMPLE


class TestClassifyMedium:
    """MEDIUM tasks: 2-3 subtasks."""

    def test_api_with_tests(self) -> None:
        result = TaskComplexityClassifier.classify("Create a REST API endpoint with unit tests")
        assert result == TaskComplexity.MEDIUM

    def test_two_concerns(self) -> None:
        result = TaskComplexityClassifier.classify(
            "Build a user authentication system with database integration"
        )
        assert result == TaskComplexity.MEDIUM

    def test_api_with_db(self) -> None:
        result = TaskComplexityClassifier.classify(
            "Create an API endpoint that reads from the database"
        )
        assert result == TaskComplexity.MEDIUM


class TestClassifyComplex:
    """COMPLEX tasks: 3-5 subtasks."""

    def test_multi_concern(self) -> None:
        result = TaskComplexityClassifier.classify(
            "Build a REST API with authentication, database integration, and comprehensive tests"
        )
        assert result == TaskComplexity.COMPLEX

    def test_fullstack(self) -> None:
        result = TaskComplexityClassifier.classify(
            "Create a full-stack web application with user authentication"
        )
        assert result == TaskComplexity.COMPLEX

    def test_refactor(self) -> None:
        result = TaskComplexityClassifier.classify(
            "Refactor the entire payment processing module to use the new API"
        )
        assert result == TaskComplexity.COMPLEX

    def test_many_concerns(self) -> None:
        result = TaskComplexityClassifier.classify(
            "Build API with auth, database, testing, and deployment pipeline"
        )
        assert result == TaskComplexity.COMPLEX

    def test_microservice(self) -> None:
        result = TaskComplexityClassifier.classify(
            "Design a microservice architecture for the order processing system"
        )
        assert result == TaskComplexity.COMPLEX


class TestRecommendedSubtaskRange:
    def test_simple_range(self) -> None:
        assert TaskComplexityClassifier.recommended_subtask_range(TaskComplexity.SIMPLE) == (1, 1)

    def test_medium_range(self) -> None:
        assert TaskComplexityClassifier.recommended_subtask_range(TaskComplexity.MEDIUM) == (2, 3)

    def test_complex_range(self) -> None:
        assert TaskComplexityClassifier.recommended_subtask_range(TaskComplexity.COMPLEX) == (3, 5)


class TestCountConcerns:
    def test_no_concerns(self) -> None:
        assert TaskComplexityClassifier._count_concerns("hello world") == 0

    def test_single_concern(self) -> None:
        assert TaskComplexityClassifier._count_concerns("build an API") >= 1

    def test_multiple_concerns(self) -> None:
        count = TaskComplexityClassifier._count_concerns(
            "REST API with auth and database and tests"
        )
        assert count >= 3

    def test_case_insensitive(self) -> None:
        assert TaskComplexityClassifier._count_concerns(
            "REST API"
        ) == TaskComplexityClassifier._count_concerns("rest api")
