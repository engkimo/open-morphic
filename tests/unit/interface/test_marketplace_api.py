"""Tests for marketplace API routes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from application.use_cases.install_tool import InstallByNameResult, InstallToolUseCase
from domain.entities.tool_candidate import ToolCandidate
from domain.ports.tool_installer import InstallResult
from domain.ports.tool_registry import ToolSearchResult
from domain.value_objects.tool_safety import SafetyTier
from interface.api.main import create_app


def _candidate(name: str = "filesystem") -> ToolCandidate:
    return ToolCandidate(
        name=name,
        publisher="modelcontextprotocol",
        description="Read and write files",
        safety_tier=SafetyTier.VERIFIED,
        safety_score=0.85,
    )


@pytest.fixture
def mock_use_case() -> AsyncMock:
    uc = AsyncMock(spec=InstallToolUseCase)
    uc.list_installed = MagicMock(return_value=[])
    return uc


@pytest.fixture
def client(mock_use_case: AsyncMock) -> TestClient:
    container = MagicMock()
    container.install_tool = mock_use_case
    app = create_app(container=container)
    return TestClient(app)


class TestMarketplaceAPI:
    def test_search(self, client: TestClient, mock_use_case: AsyncMock) -> None:
        mock_use_case.search.return_value = ToolSearchResult(
            query="filesystem",
            candidates=[_candidate()],
            total_count=1,
        )
        resp = client.get("/api/marketplace/search?q=filesystem")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["candidates"][0]["name"] == "filesystem"

    def test_search_with_limit(self, client: TestClient, mock_use_case: AsyncMock) -> None:
        mock_use_case.search.return_value = ToolSearchResult(
            query="test", candidates=[], total_count=0
        )
        resp = client.get("/api/marketplace/search?q=test&limit=3")
        assert resp.status_code == 200

    def test_install_success(self, client: TestClient, mock_use_case: AsyncMock) -> None:
        mock_use_case.install_by_name.return_value = InstallByNameResult(
            search_result=ToolSearchResult(query="fs", candidates=[_candidate()], total_count=1),
            install_result=InstallResult(tool_name="filesystem", success=True, message="ok"),
        )
        resp = client.post("/api/marketplace/install", json={"name": "filesystem"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_install_not_found(self, client: TestClient, mock_use_case: AsyncMock) -> None:
        mock_use_case.install_by_name.return_value = InstallByNameResult(
            search_result=ToolSearchResult(query="x", candidates=[], total_count=0),
            install_result=None,
        )
        resp = client.post("/api/marketplace/install", json={"name": "x"})
        assert resp.status_code == 404

    def test_list_installed(self, client: TestClient, mock_use_case: AsyncMock) -> None:
        mock_use_case.list_installed.return_value = [_candidate()]
        resp = client.get("/api/marketplace/installed")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_uninstall_success(self, client: TestClient, mock_use_case: AsyncMock) -> None:
        mock_use_case.uninstall.return_value = InstallResult(
            tool_name="filesystem", success=True, message="removed"
        )
        resp = client.delete("/api/marketplace/filesystem")
        assert resp.status_code == 200

    def test_uninstall_not_found(self, client: TestClient, mock_use_case: AsyncMock) -> None:
        mock_use_case.uninstall.return_value = InstallResult(
            tool_name="x", success=False, error="Not installed"
        )
        resp = client.delete("/api/marketplace/x")
        assert resp.status_code == 404

    def test_search_empty_query_invalid(self, client: TestClient) -> None:
        resp = client.get("/api/marketplace/search")
        assert resp.status_code == 422

    def test_install_empty_name_invalid(self, client: TestClient) -> None:
        resp = client.post("/api/marketplace/install", json={"name": ""})
        assert resp.status_code == 422

    def test_search_error_from_registry(self, client: TestClient, mock_use_case: AsyncMock) -> None:
        mock_use_case.search.return_value = ToolSearchResult(
            query="test", candidates=[], total_count=0, error="Connection refused"
        )
        resp = client.get("/api/marketplace/search?q=test")
        assert resp.status_code == 200
        assert resp.json()["error"] == "Connection refused"
