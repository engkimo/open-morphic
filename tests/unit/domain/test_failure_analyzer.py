"""Tests for FailureAnalyzer domain service."""

from __future__ import annotations

from domain.services.failure_analyzer import FailureAnalyzer


class TestFailureAnalyzer:
    def setup_method(self) -> None:
        self.analyzer = FailureAnalyzer()

    def test_file_not_found(self) -> None:
        queries = self.analyzer.extract_queries("FileNotFoundError: config.yaml")
        assert "filesystem" in queries

    def test_permission_denied(self) -> None:
        queries = self.analyzer.extract_queries("PermissionError: [Errno 13] Permission denied")
        assert "filesystem" in queries

    def test_database_error(self) -> None:
        error = "psycopg2.OperationalError: connection refused on 5432"
        queries = self.analyzer.extract_queries(error)
        assert "postgres" in queries or "database" in queries

    def test_redis_error(self) -> None:
        queries = self.analyzer.extract_queries("ConnectionRefusedError: connection refused 6379")
        assert "redis" in queries

    def test_http_error(self) -> None:
        queries = self.analyzer.extract_queries("httpx.TimeoutException: timeout on HTTP request")
        assert "http-client" in queries or "fetch" in queries

    def test_git_error(self) -> None:
        queries = self.analyzer.extract_queries("fatal: repository not found")
        assert "git" in queries

    def test_docker_error(self) -> None:
        queries = self.analyzer.extract_queries("docker: image not found")
        assert "docker" in queries

    def test_module_not_found(self) -> None:
        queries = self.analyzer.extract_queries("ModuleNotFoundError: No module named 'pandas'")
        assert "package-manager" in queries

    def test_auth_error(self) -> None:
        queries = self.analyzer.extract_queries("401 Unauthorized: Invalid token")
        assert "auth" in queries

    def test_no_match_returns_empty(self) -> None:
        queries = self.analyzer.extract_queries("Something went wrong")
        assert queries == []

    def test_deduplication(self) -> None:
        queries = self.analyzer.extract_queries("file not found, also Permission denied on file")
        assert queries.count("filesystem") == 1

    def test_with_context_adds_task_keywords(self) -> None:
        queries = self.analyzer.extract_queries_with_context(
            "timeout error",
            task_description="Search the web for travel info",
        )
        assert "web-search" in queries
