"""Tests for TopicExtractor — pure domain service for topic classification.

Sprint 7.4: Affinity-Aware Routing + Task Handoff
"""

from __future__ import annotations

from domain.services.topic_extractor import TopicExtractor


class TestTopicExtractorExtract:
    """extract() — keyword-based topic classification."""

    def test_empty_string_returns_general(self) -> None:
        assert TopicExtractor.extract("") == "general"

    def test_whitespace_only_returns_general(self) -> None:
        assert TopicExtractor.extract("   ") == "general"

    def test_no_keywords_returns_general(self) -> None:
        assert TopicExtractor.extract("do something random") == "general"

    def test_frontend_keywords(self) -> None:
        assert TopicExtractor.extract("Build a React component with Tailwind CSS") == "frontend"

    def test_backend_keywords(self) -> None:
        assert TopicExtractor.extract("Create a FastAPI endpoint for the REST API") == "backend"

    def test_database_keywords(self) -> None:
        assert TopicExtractor.extract("Write a PostgreSQL migration for the schema") == "database"

    def test_devops_keywords(self) -> None:
        assert TopicExtractor.extract("Set up Docker and Kubernetes deployment") == "devops"

    def test_testing_keywords(self) -> None:
        assert TopicExtractor.extract("Write pytest unit tests with mock fixtures") == "testing"

    def test_security_keywords(self) -> None:
        assert TopicExtractor.extract("Implement OAuth authentication and JWT") == "security"

    def test_ml_keywords(self) -> None:
        assert TopicExtractor.extract("Train a deep learning model with PyTorch") == "ml"

    def test_highest_match_wins(self) -> None:
        """When multiple topics match, the one with more keyword hits wins."""
        # "test" matches testing, but "React", "CSS", "frontend" match frontend more
        result = TopicExtractor.extract("test the React CSS frontend component")
        assert result == "frontend"

    def test_case_insensitive(self) -> None:
        assert TopicExtractor.extract("DEPLOY TO KUBERNETES WITH DOCKER") == "devops"

    def test_documentation_keywords(self) -> None:
        assert TopicExtractor.extract("Update the documentation and README") == "documentation"

    def test_refactoring_keywords(self) -> None:
        assert TopicExtractor.extract("Refactor and optimize code quality") == "refactoring"


class TestTopicExtractorKnownTopics:
    """known_topics() — list of recognized topics."""

    def test_returns_sorted_list(self) -> None:
        topics = TopicExtractor.known_topics()
        assert topics == sorted(topics)

    def test_contains_expected_topics(self) -> None:
        topics = TopicExtractor.known_topics()
        assert "frontend" in topics
        assert "backend" in topics
        assert "database" in topics
        assert "testing" in topics

    def test_returns_non_empty(self) -> None:
        assert len(TopicExtractor.known_topics()) >= 10
