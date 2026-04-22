"""Tests for SubtaskTypeClassifier — TD-155."""

from __future__ import annotations

from domain.services.subtask_type_classifier import SubtaskTypeClassifier
from domain.value_objects.model_tier import TaskType


class TestSubtaskTypeClassifier:
    """Verify topic+complexity → TaskType inference."""

    # ── Code generation tasks (backend/frontend/database/testing) ──

    def test_backend_api_task(self) -> None:
        assert (
            SubtaskTypeClassifier.infer("Implement FastAPI REST API endpoints")
            == TaskType.CODE_GENERATION
        )

    def test_frontend_react_task(self) -> None:
        assert (
            SubtaskTypeClassifier.infer("Build React component for user dashboard")
            == TaskType.CODE_GENERATION
        )

    def test_database_schema_task(self) -> None:
        assert (
            SubtaskTypeClassifier.infer("Create PostgreSQL migration for users table")
            == TaskType.CODE_GENERATION
        )

    def test_testing_task(self) -> None:
        assert (
            SubtaskTypeClassifier.infer("Write pytest unit tests for auth module")
            == TaskType.CODE_GENERATION
        )

    # ── Complex reasoning tasks (ml/security/refactoring) ──

    def test_ml_task(self) -> None:
        assert (
            SubtaskTypeClassifier.infer("Fine-tune transformer model for NLP classification")
            == TaskType.COMPLEX_REASONING
        )

    def test_security_task(self) -> None:
        assert (
            SubtaskTypeClassifier.infer("Review authentication flow for OAuth vulnerabilities")
            == TaskType.COMPLEX_REASONING
        )

    def test_refactoring_task(self) -> None:
        assert (
            SubtaskTypeClassifier.infer("Refactor the payment module to reduce complexity")
            == TaskType.COMPLEX_REASONING
        )

    # ── Long context tasks (data) ──

    def test_data_pipeline_task(self) -> None:
        assert (
            SubtaskTypeClassifier.infer("Build ETL data pipeline with pandas and Spark")
            == TaskType.LONG_CONTEXT
        )

    # ── File operation tasks (docs/devops) ──

    def test_documentation_task(self) -> None:
        assert (
            SubtaskTypeClassifier.infer("Write README documentation for the API")
            == TaskType.FILE_OPERATION
        )

    def test_devops_task(self) -> None:
        assert (
            SubtaskTypeClassifier.infer("Set up Docker deployment with nginx")
            == TaskType.FILE_OPERATION
        )

    # ── Overrides ──

    def test_requires_tools_override(self) -> None:
        """Tool-requiring tasks → WEB_SEARCH (Gemini CLI with Grounding)."""
        result = SubtaskTypeClassifier.infer("Search for the latest Python packages")
        assert result == TaskType.WEB_SEARCH

    def test_complex_override(self) -> None:
        """Multi-concern complex tasks → COMPLEX_REASONING."""
        result = SubtaskTypeClassifier.infer(
            "Refactor the full-stack application with new database schema, "
            "authentication, and deployment pipeline"
        )
        assert result == TaskType.COMPLEX_REASONING

    # ── Fallbacks ──

    def test_simple_general_task(self) -> None:
        assert (
            SubtaskTypeClassifier.infer("Calculate fibonacci numbers")
            == TaskType.SIMPLE_QA
        )

    def test_empty_string(self) -> None:
        assert SubtaskTypeClassifier.infer("") == TaskType.SIMPLE_QA

    def test_none_like_whitespace(self) -> None:
        assert SubtaskTypeClassifier.infer("   ") == TaskType.SIMPLE_QA

    # ── Japanese input ──

    def test_japanese_tool_requiring(self) -> None:
        """Japanese search keywords → WEB_SEARCH (Gemini CLI with Grounding)."""
        result = SubtaskTypeClassifier.infer("最新のPythonフレームワークを検索して比較する")
        assert result == TaskType.WEB_SEARCH
