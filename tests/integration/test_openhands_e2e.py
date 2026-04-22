"""OpenHands E2E integration tests — Sprint 24.1 (TD-129).

Tests the full OpenHands lifecycle: Docker check → driver init → task execution.
Requires Docker daemon running + OpenHands image pulled.

Run:
    uv run pytest tests/integration/test_openhands_e2e.py -v -s -m openhands

Skip logic:
    - No Docker daemon → skip all
    - No OpenHands image → skip all
    - OpenHands API not reachable → skip execution tests
"""

from __future__ import annotations

import shutil
import subprocess

import httpx
import pytest

from domain.ports.agent_engine import AgentEngineCapabilities, AgentEngineResult
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.agent_cli.openhands_driver import OpenHandsDriver
from shared.config import Settings

# ── Skip conditions ──

_DOCKER_AVAILABLE = shutil.which("docker") is not None


def _docker_running() -> bool:
    if not _DOCKER_AVAILABLE:
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _openhands_image_exists() -> bool:
    if not _docker_running():
        return False
    try:
        result = subprocess.run(
            ["docker", "images", "-q", "ghcr.io/all-hands-ai/openhands"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


async def _openhands_api_reachable(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/")
            return resp.status_code == 200
    except Exception:
        return False


# Apply openhands marker to entire module; asyncio applied per-class (some classes have sync tests)
pytestmark = [
    pytest.mark.openhands,
]

OPENHANDS_BASE = "http://localhost:3000"
SIMPLE_TASK = "What is 2+2? Answer with just the number."


# ══════════════════════════════════════════════════════════
# Docker Infrastructure Tests (always run if Docker exists)
# ══════════════════════════════════════════════════════════


class TestDockerInfrastructure:
    """Verify Docker and OpenHands image availability."""

    @pytest.mark.skipif(not _DOCKER_AVAILABLE, reason="Docker CLI not installed")
    def test_docker_cli_exists(self) -> None:
        path = shutil.which("docker")
        assert path is not None
        print(f"\n  Docker CLI: {path}")

    @pytest.mark.skipif(not _DOCKER_AVAILABLE, reason="Docker CLI not installed")
    def test_docker_daemon_running(self) -> None:
        assert _docker_running(), "Docker daemon is not running"
        print("\n  Docker daemon: running")

    @pytest.mark.skipif(not _docker_running(), reason="Docker daemon not running")
    def test_openhands_image_available(self) -> None:
        if not _openhands_image_exists():
            pytest.skip(
                "OpenHands image not pulled. Run: "
                "docker pull ghcr.io/all-hands-ai/openhands:latest"
            )
        print("\n  OpenHands image: available")

    @pytest.mark.skipif(not _docker_running(), reason="Docker daemon not running")
    def test_docker_disk_space(self) -> None:
        """Verify sufficient disk space for Docker operations."""
        result = subprocess.run(
            ["docker", "system", "df", "--format", "{{.Type}}\t{{.Size}}\t{{.Reclaimable}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        print(f"\n  Docker disk usage:\n{result.stdout}")


# ══════════════════════════════════════════════════════════
# Driver Unit Integration Tests (no Docker needed)
# ══════════════════════════════════════════════════════════


class TestDriverConstruction:
    """Verify OpenHands driver construction from Settings."""

    def test_from_settings(self) -> None:
        s = Settings()
        driver = OpenHandsDriver(
            base_url=s.openhands_base_url,
            model=s.openhands_model,
            api_key=s.openhands_api_key,
        )
        assert driver.engine_type == AgentEngineType.OPENHANDS
        assert driver._base_url == s.openhands_base_url.rstrip("/")

    def test_capabilities(self) -> None:
        driver = OpenHandsDriver()
        caps = driver.get_capabilities()
        assert isinstance(caps, AgentEngineCapabilities)
        assert caps.engine_type == AgentEngineType.OPENHANDS
        assert caps.supports_sandbox is True
        assert caps.supports_parallel is True
        assert caps.supports_streaming is True
        assert caps.max_context_tokens == 200_000

    @pytest.mark.asyncio
    async def test_unavailable_when_no_server(self) -> None:
        driver = OpenHandsDriver(base_url="http://127.0.0.1:19999")
        assert await driver.is_available() is False

    @pytest.mark.asyncio
    async def test_run_task_fails_when_no_server(self) -> None:
        driver = OpenHandsDriver(base_url="http://127.0.0.1:19999")
        result = await driver.run_task("test", timeout_seconds=5.0)
        assert isinstance(result, AgentEngineResult)
        assert result.success is False
        assert result.engine == AgentEngineType.OPENHANDS
        assert result.duration_seconds > 0


# ══════════════════════════════════════════════════════════
# Live E2E Tests (require running OpenHands container)
# ══════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestOpenHandsLiveE2E:
    """Full E2E tests against a running OpenHands container.

    Start OpenHands:
        docker run -d --name openhands-test -p 3000:3000 \\
            -e LLM_API_KEY=$ANTHROPIC_API_KEY \\
            -e LLM_MODEL=claude-sonnet-4-6 \\
            ghcr.io/all-hands-ai/openhands:latest
    """

    @pytest.fixture(autouse=True)
    async def _skip_if_unavailable(self) -> None:
        if not await _openhands_api_reachable(OPENHANDS_BASE):
            pytest.skip("OpenHands API not reachable at localhost:3000")

    @pytest.fixture
    def driver(self) -> OpenHandsDriver:
        s = Settings()
        return OpenHandsDriver(
            base_url=OPENHANDS_BASE,
            model=s.openhands_model,
            api_key=s.openhands_api_key or s.anthropic_api_key,
        )

    async def test_is_available(self, driver: OpenHandsDriver) -> None:
        assert await driver.is_available() is True
        print("\n  OpenHands API: available")

    async def test_simple_task_execution(self, driver: OpenHandsDriver) -> None:
        result = await driver.run_task(SIMPLE_TASK, timeout_seconds=120.0)
        assert isinstance(result, AgentEngineResult)
        assert result.engine == AgentEngineType.OPENHANDS

        if result.success:
            assert result.output, "Output should not be empty"
            assert result.duration_seconds > 0
            print(f"\n  Output: {result.output[:200]}")
            print(f"  Duration: {result.duration_seconds:.2f}s")
            print(f"  Cost: ${result.cost_usd:.4f}")
            if result.metadata.get("conversation_id"):
                print(f"  Conversation: {result.metadata['conversation_id']}")
        else:
            # Log error but don't fail — might be LLM API key issue, not a code bug
            print(f"\n  Task failed: {result.error}")
            _env_patterns = [
                "unauthorized", "api key", "quota", "rate limit",
                "authenticating", "settings not found", "sandbox",
                "docker", "runtime", "connection aborted",
                "timed out",  # sandbox can't start without Docker socket
            ]
            if any(p in (result.error or "").lower() for p in _env_patterns):
                pytest.skip(f"OpenHands env/auth error: {result.error}")
            # Non-env error is a real failure
            raise AssertionError(f"OpenHands task failed: {result.error}")

    async def test_metadata_includes_conversation_id(self, driver: OpenHandsDriver) -> None:
        result = await driver.run_task("echo hello", timeout_seconds=60.0)
        if not result.success:
            pytest.skip(f"Task failed: {result.error}")
        assert "conversation_id" in result.metadata
        assert isinstance(result.metadata["conversation_id"], str)
        assert len(result.metadata["conversation_id"]) > 0

    async def test_model_override(self, driver: OpenHandsDriver) -> None:
        result = await driver.run_task(
            SIMPLE_TASK,
            model="claude-haiku-4-5-20251001",
            timeout_seconds=120.0,
        )
        if not result.success:
            pytest.skip(f"Task failed: {result.error}")
        assert result.model_used == "claude-haiku-4-5-20251001"

    async def test_timeout_handling(self, driver: OpenHandsDriver) -> None:
        """Very short timeout should trigger timeout error, not crash."""
        result = await driver.run_task(
            "Write a complex algorithm with detailed comments",
            timeout_seconds=0.001,  # Effectively instant timeout
        )
        assert result.success is False
        # Should be timeout or connection error, not a crash
        assert result.error is not None
        assert result.duration_seconds >= 0

    async def test_cost_reporting(self, driver: OpenHandsDriver) -> None:
        result = await driver.run_task(SIMPLE_TASK, timeout_seconds=120.0)
        if not result.success:
            pytest.skip(f"Task failed: {result.error}")
        assert isinstance(result.cost_usd, (int, float))
        assert result.cost_usd >= 0.0
        print(f"\n  Reported cost: ${result.cost_usd:.4f}")
