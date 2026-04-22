"""Marketplace Live integration tests — Sprint 20.2 (TD-122).

Tests the tool discovery and marketplace pipeline against the real
MCP Registry (registry.modelcontextprotocol.io). Network-dependent tests
are auto-skipped when registry is unreachable.

Run:
    uv run pytest tests/integration/test_marketplace_live.py -v -s
"""

from __future__ import annotations

import httpx
import pytest

from application.use_cases.discover_tools import DiscoverToolsUseCase
from application.use_cases.install_tool import InstallToolUseCase
from domain.entities.tool_candidate import ToolCandidate
from domain.services.failure_analyzer import FailureAnalyzer
from domain.services.tool_safety_scorer import ToolSafetyScorer
from domain.value_objects.tool_safety import SafetyTier
from infrastructure.marketplace.mcp_registry_client import MCPRegistryClient
from infrastructure.marketplace.tool_installer import MCPToolInstaller

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Network check
# ---------------------------------------------------------------------------


def _registry_reachable() -> bool:
    try:
        resp = httpx.get(
            "https://registry.modelcontextprotocol.io/v0.1/servers?limit=1",
            timeout=5.0,
        )
        return resp.status_code == 200
    except Exception:
        return False


_HAS_NETWORK = _registry_reachable()
_skip_no_network = pytest.mark.skipif(not _HAS_NETWORK, reason="MCP Registry unreachable")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def scorer() -> ToolSafetyScorer:
    return ToolSafetyScorer()


@pytest.fixture
def registry(scorer: ToolSafetyScorer) -> MCPRegistryClient:
    return MCPRegistryClient(safety_scorer=scorer, timeout=10.0)


@pytest.fixture
def installer() -> MCPToolInstaller:
    return MCPToolInstaller()


@pytest.fixture
def discover(registry: MCPRegistryClient) -> DiscoverToolsUseCase:
    return DiscoverToolsUseCase(registry=registry)


@pytest.fixture
def install_uc(registry: MCPRegistryClient, installer: MCPToolInstaller) -> InstallToolUseCase:
    return InstallToolUseCase(registry=registry, installer=installer)


# ===========================================================================
# Network-dependent tests (real MCP Registry)
# ===========================================================================


@_skip_no_network
async def test_search_returns_results(registry: MCPRegistryClient) -> None:
    """Searching for 'fetch' returns at least one tool from real registry."""
    result = await registry.search("fetch", limit=5)
    assert result.error is None
    assert result.total_count >= 1
    assert len(result.candidates) >= 1

    first = result.candidates[0]
    assert first.name
    assert isinstance(first.safety_score, float)
    assert first.safety_score >= 0.0


@_skip_no_network
async def test_search_results_are_safety_scored(
    registry: MCPRegistryClient,
) -> None:
    """Every candidate from registry has been safety-scored."""
    result = await registry.search("filesystem", limit=5)
    assert result.error is None

    for candidate in result.candidates:
        assert candidate.safety_score >= 0.0
        assert candidate.safety_tier in list(SafetyTier)


@_skip_no_network
async def test_search_with_query(registry: MCPRegistryClient) -> None:
    """Search with a specific query returns relevant results."""
    result = await registry.search("github", limit=3)
    assert result.error is None
    assert isinstance(result.candidates, list)


@_skip_no_network
async def test_discover_tools_from_real_error(
    discover: DiscoverToolsUseCase,
) -> None:
    """Tool discovery pipeline: error -> queries -> real registry -> suggestions."""
    result = await discover.suggest_for_failure(
        error_message="FileNotFoundError: [Errno 2] No such file: '/tmp/data.csv'",
        task_description="Process CSV data files",
        max_results=3,
    )

    assert len(result.queries_used) >= 1
    assert isinstance(result.suggestions, list)


@_skip_no_network
async def test_install_use_case_search(
    install_uc: InstallToolUseCase,
) -> None:
    """InstallToolUseCase can search real registry."""
    result = await install_uc.search("fetch", limit=3)
    assert result.error is None
    assert isinstance(result.candidates, list)


# ===========================================================================
# Network-independent tests (no registry needed)
# ===========================================================================


async def test_trusted_publisher_gets_high_score(
    scorer: ToolSafetyScorer,
) -> None:
    """Tools from trusted publishers like 'anthropic' get high safety score."""
    candidate = ToolCandidate(
        name="test-tool",
        publisher="Anthropic",
        description="An official tool",
        transport="stdio",
        source_url="https://github.com/anthropics/test",
        install_command="npx test-tool",
    )

    scored = scorer.score(candidate)
    assert scored.safety_score >= 0.70
    assert scored.safety_tier == SafetyTier.VERIFIED


async def test_suspicious_tool_gets_unsafe(scorer: ToolSafetyScorer) -> None:
    """Tools with suspicious names are marked UNSAFE."""
    candidate = ToolCandidate(
        name="keylogger-tool",
        description="A keylog capture tool",
    )

    scored = scorer.score(candidate)
    assert scored.safety_tier == SafetyTier.UNSAFE
    assert scored.safety_score == 0.0


async def test_failure_analyzer_extracts_queries() -> None:
    """FailureAnalyzer extracts search queries from error messages."""
    analyzer = FailureAnalyzer()

    queries = analyzer.extract_queries("FileNotFoundError: No such file or directory")
    assert len(queries) >= 1
    assert any("filesystem" in q or "file" in q for q in queries)

    queries = analyzer.extract_queries(
        "psycopg2.OperationalError: could not connect to database server"
    )
    assert len(queries) >= 1


async def test_installer_blocks_unsafe(installer: MCPToolInstaller) -> None:
    """Installer refuses tools below safety threshold."""
    unsafe_tool = ToolCandidate(
        name="bad-tool",
        safety_tier=SafetyTier.UNSAFE,
        safety_score=0.0,
        install_command="pip install bad-tool",
    )

    result = await installer.install(unsafe_tool)
    assert not result.success
    assert "Blocked" in (result.error or "")


async def test_installer_handles_no_install_command(
    installer: MCPToolInstaller,
) -> None:
    """Installer gracefully fails when no install command is available."""
    tool = ToolCandidate(
        name="no-command-tool",
        safety_tier=SafetyTier.COMMUNITY,
        safety_score=0.5,
        install_command="",
    )

    result = await installer.install(tool)
    assert not result.success
    assert "No install command" in (result.error or "")


async def test_installer_list_initially_empty(
    installer: MCPToolInstaller,
) -> None:
    """Installer starts with no installed tools."""
    assert len(installer.list_installed()) == 0
    assert not installer.is_installed("anything")


async def test_transport_trust_scoring(scorer: ToolSafetyScorer) -> None:
    """Different transports receive different trust scores."""
    stdio_scored = scorer.score(ToolCandidate(name="a", transport="stdio"))
    http_scored = scorer.score(ToolCandidate(name="b", transport="http"))

    assert stdio_scored.safety_score > http_scored.safety_score


async def test_popularity_bonus(scorer: ToolSafetyScorer) -> None:
    """High-download tools get higher safety scores."""
    popular = scorer.score(ToolCandidate(name="pop", download_count=15000, transport="stdio"))
    unpopular = scorer.score(ToolCandidate(name="unpop", download_count=5, transport="stdio"))

    assert popular.safety_score > unpopular.safety_score


async def test_metadata_completeness_bonus(scorer: ToolSafetyScorer) -> None:
    """Tools with complete metadata get higher scores."""
    complete = scorer.score(
        ToolCandidate(
            name="full",
            description="A well-documented tool",
            source_url="https://github.com/example/full",
            install_command="npx full",
            transport="stdio",
        )
    )
    bare = scorer.score(ToolCandidate(name="bare", transport="stdio"))

    assert complete.safety_score > bare.safety_score
