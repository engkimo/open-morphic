"""Agent Engine integration tests — real engine execution.

Run with: uv run pytest tests/integration/test_agent_engines.py -v -s
Requires: Ollama running (minimum), optional CLIs: claude, codex, gemini, Docker (OpenHands)

Tests skip gracefully when engines are unavailable (same pattern as test_cloud_llm.py).
Completion criteria verified:
  1. Same task across multiple engines with result comparison
  2. Task-type-based automatic engine selection
  3. Availability check + fallback in live environment
"""

from __future__ import annotations

import asyncio
import os
import shutil

import httpx
import pytest

from application.use_cases.route_to_engine import RouteToEngineUseCase
from domain.ports.agent_engine import AgentEnginePort, AgentEngineResult
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType
from infrastructure.agent_cli.claude_code_driver import ClaudeCodeDriver
from infrastructure.agent_cli.codex_cli_driver import CodexCLIDriver
from infrastructure.agent_cli.gemini_cli_driver import GeminiCLIDriver
from infrastructure.agent_cli.ollama_driver import OllamaEngineDriver
from infrastructure.agent_cli.openhands_driver import OpenHandsDriver
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.litellm_gateway import LiteLLMGateway
from infrastructure.llm.ollama_manager import OllamaManager
from shared.config import Settings

# ── Shared helpers ──

SIMPLE_TASK = "What is 2+2? Answer with just the number."

# Known error patterns that indicate env/auth issues, not code bugs
_SKIP_ERROR_PATTERNS = [
    "nested",
    "cannot be launched inside",
    "unauthorized",
    "401",
    "authentication",
    "invalid api key",
    "quota",
    "rate limit",
    "failed to refresh token",
]


def _cli_available(binary: str) -> bool:
    """Check if a CLI binary is on PATH."""
    return shutil.which(binary) is not None


def _is_env_error(result: AgentEngineResult) -> bool:
    """Check if failure is due to environment/auth, not a code bug."""
    if result.success:
        return False
    error = (result.error or "").lower() + (result.output or "").lower()
    return any(pat in error for pat in _SKIP_ERROR_PATTERNS)


def _in_claude_session() -> bool:
    """Detect if running inside an existing Claude Code session."""
    return bool(os.environ.get("CLAUDECODE"))


async def _openhands_available(base_url: str) -> bool:
    """Check if OpenHands REST API is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/")
            return resp.status_code == 200
    except (httpx.ConnectError, httpx.TimeoutException, Exception):
        return False


class _InMemoryCostRepo:
    """Minimal in-memory CostRepository for integration tests."""

    def __init__(self) -> None:
        self._records: list = []

    async def save(self, record) -> None:
        self._records.append(record)

    async def get_daily_total(self) -> float:
        return sum(r.cost_usd for r in self._records)

    async def get_monthly_total(self) -> float:
        return sum(r.cost_usd for r in self._records)

    async def get_local_usage_rate(self) -> float:
        if not self._records:
            return 0.0
        local = sum(1 for r in self._records if r.is_local)
        return local / len(self._records)


# ── Module-scoped fixtures ──


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="module")
async def ollama() -> OllamaManager:
    return OllamaManager()


@pytest.fixture(scope="module")
def cost_repo() -> _InMemoryCostRepo:
    return _InMemoryCostRepo()


@pytest.fixture(scope="module")
def gateway(
    ollama: OllamaManager, cost_repo: _InMemoryCostRepo, settings: Settings
) -> LiteLLMGateway:
    cost_tracker = CostTracker(cost_repo)
    return LiteLLMGateway(ollama=ollama, cost_tracker=cost_tracker, settings=settings)


@pytest.fixture(scope="module")
def ollama_driver(gateway: LiteLLMGateway, ollama: OllamaManager) -> OllamaEngineDriver:
    return OllamaEngineDriver(gateway=gateway, ollama=ollama)


@pytest.fixture(scope="module")
def claude_driver(settings: Settings) -> ClaudeCodeDriver:
    return ClaudeCodeDriver(
        enabled=settings.claude_code_sdk_enabled,
        cli_path=settings.claude_code_cli_path,
    )


@pytest.fixture(scope="module")
def codex_driver(settings: Settings) -> CodexCLIDriver:
    return CodexCLIDriver(
        enabled=settings.codex_cli_enabled,
        cli_path=settings.codex_cli_path,
    )


@pytest.fixture(scope="module")
def gemini_driver(settings: Settings) -> GeminiCLIDriver:
    return GeminiCLIDriver(
        enabled=settings.gemini_cli_enabled,
        cli_path=settings.gemini_cli_path,
    )


@pytest.fixture(scope="module")
def openhands_driver(settings: Settings) -> OpenHandsDriver:
    return OpenHandsDriver(
        base_url=settings.openhands_base_url,
        model=settings.openhands_model,
        api_key=settings.openhands_api_key,
    )


@pytest.fixture(scope="module")
def all_drivers(
    ollama_driver: OllamaEngineDriver,
    claude_driver: ClaudeCodeDriver,
    codex_driver: CodexCLIDriver,
    gemini_driver: GeminiCLIDriver,
    openhands_driver: OpenHandsDriver,
) -> dict[AgentEngineType, AgentEnginePort]:
    return {
        AgentEngineType.OLLAMA: ollama_driver,
        AgentEngineType.CLAUDE_CODE: claude_driver,
        AgentEngineType.CODEX_CLI: codex_driver,
        AgentEngineType.GEMINI_CLI: gemini_driver,
        AgentEngineType.OPENHANDS: openhands_driver,
    }


# Function-scoped fixture for use case (needs fresh state per test)
@pytest.fixture
def use_case(
    all_drivers: dict[AgentEngineType, AgentEnginePort],
) -> RouteToEngineUseCase:
    return RouteToEngineUseCase(drivers=all_drivers)


# ══════════════════════════════════════════════════════════
# Ollama Engine Live Tests
# ══════════════════════════════════════════════════════════


class TestOllamaEngineLive:
    """Baseline engine — Ollama local, always $0."""

    async def test_simple_task(
        self, ollama_driver: OllamaEngineDriver, ollama: OllamaManager
    ) -> None:
        if not await ollama.is_running():
            pytest.skip("Ollama not running")
        result = await ollama_driver.run_task(SIMPLE_TASK, timeout_seconds=60.0)
        assert result.success, f"Ollama failed: {result.error}"
        assert result.output, "Output should not be empty"
        assert "4" in result.output
        assert result.engine == AgentEngineType.OLLAMA
        print(f"\n  Ollama: {result.output[:80]}")
        print(f"  Duration: {result.duration_seconds:.2f}s, Cost: ${result.cost_usd:.4f}")

    async def test_zero_cost(
        self, ollama_driver: OllamaEngineDriver, ollama: OllamaManager
    ) -> None:
        if not await ollama.is_running():
            pytest.skip("Ollama not running")
        result = await ollama_driver.run_task(SIMPLE_TASK, timeout_seconds=60.0)
        assert result.success
        assert result.cost_usd == 0.0, f"Ollama should be free, got ${result.cost_usd}"

    async def test_availability(
        self, ollama_driver: OllamaEngineDriver, ollama: OllamaManager
    ) -> None:
        available = await ollama_driver.is_available()
        ollama_running = await ollama.is_running()
        assert available == ollama_running
        print(f"\n  Ollama available: {available}")


# ══════════════════════════════════════════════════════════
# Claude Code Engine Live Tests
# ══════════════════════════════════════════════════════════


class TestClaudeCodeEngineLive:
    """Claude Code CLI headless execution."""

    async def test_simple_task(self, claude_driver: ClaudeCodeDriver) -> None:
        if not await claude_driver.is_available():
            pytest.skip("Claude CLI not available")
        if _in_claude_session():
            pytest.skip("Cannot nest Claude Code sessions")
        result = await claude_driver.run_task(SIMPLE_TASK, timeout_seconds=120.0)
        if _is_env_error(result):
            pytest.skip(f"Claude Code env error: {result.error}")
        assert result.success, f"Claude Code failed: {result.error}"
        assert result.output, "Output should not be empty"
        assert result.engine == AgentEngineType.CLAUDE_CODE
        print(f"\n  Claude Code: {result.output[:120]}")
        print(f"  Duration: {result.duration_seconds:.2f}s")

    async def test_capabilities(self, claude_driver: ClaudeCodeDriver) -> None:
        caps = claude_driver.get_capabilities()
        assert caps.engine_type == AgentEngineType.CLAUDE_CODE
        assert caps.max_context_tokens == 200_000
        assert caps.supports_parallel is True
        assert caps.supports_mcp is True

    async def test_availability_matches_cli(self, claude_driver: ClaudeCodeDriver) -> None:
        available = await claude_driver.is_available()
        cli_exists = _cli_available("claude")
        # available implies cli_exists (but enabled flag can also affect it)
        if available:
            assert cli_exists, "Available should imply CLI exists"
        print(f"\n  Claude Code available: {available}, CLI exists: {cli_exists}")


# ══════════════════════════════════════════════════════════
# Codex CLI Engine Live Tests
# ══════════════════════════════════════════════════════════


class TestCodexCLIEngineLive:
    """OpenAI Codex CLI exec execution."""

    async def test_simple_task(self, codex_driver: CodexCLIDriver) -> None:
        if not await codex_driver.is_available():
            pytest.skip("Codex CLI not available")
        result = await codex_driver.run_task(SIMPLE_TASK, timeout_seconds=120.0)
        if _is_env_error(result):
            pytest.skip(f"Codex env/auth error: {result.error}")
        assert result.success, f"Codex failed: {result.error}"
        assert result.output, "Output should not be empty"
        assert result.engine == AgentEngineType.CODEX_CLI
        print(f"\n  Codex CLI: {result.output[:120]}")
        print(f"  Duration: {result.duration_seconds:.2f}s")

    async def test_capabilities(self, codex_driver: CodexCLIDriver) -> None:
        caps = codex_driver.get_capabilities()
        assert caps.engine_type == AgentEngineType.CODEX_CLI
        assert caps.max_context_tokens == 128_000
        assert caps.supports_sandbox is True
        assert caps.supports_mcp is True

    async def test_availability_matches_cli(self, codex_driver: CodexCLIDriver) -> None:
        available = await codex_driver.is_available()
        cli_exists = _cli_available("codex")
        if available:
            assert cli_exists
        print(f"\n  Codex CLI available: {available}, CLI exists: {cli_exists}")


# ══════════════════════════════════════════════════════════
# Gemini CLI Engine Live Tests
# ══════════════════════════════════════════════════════════


class TestGeminiCLIEngineLive:
    """Gemini CLI 2M token context engine."""

    async def test_simple_task(self, gemini_driver: GeminiCLIDriver) -> None:
        if not await gemini_driver.is_available():
            pytest.skip("Gemini CLI not available")
        result = await gemini_driver.run_task(SIMPLE_TASK, timeout_seconds=120.0)
        assert result.success, f"Gemini failed: {result.error}"
        assert result.output, "Output should not be empty"
        assert result.engine == AgentEngineType.GEMINI_CLI
        print(f"\n  Gemini CLI: {result.output[:120]}")
        print(f"  Duration: {result.duration_seconds:.2f}s")

    async def test_capabilities(self, gemini_driver: GeminiCLIDriver) -> None:
        caps = gemini_driver.get_capabilities()
        assert caps.engine_type == AgentEngineType.GEMINI_CLI
        assert caps.max_context_tokens == 2_000_000
        assert caps.cost_per_hour_usd == 0.0

    async def test_availability_matches_cli(self, gemini_driver: GeminiCLIDriver) -> None:
        available = await gemini_driver.is_available()
        cli_exists = _cli_available("gemini")
        if available:
            assert cli_exists
        print(f"\n  Gemini CLI available: {available}, CLI exists: {cli_exists}")


# ══════════════════════════════════════════════════════════
# OpenHands Engine Live Tests
# ══════════════════════════════════════════════════════════


class TestOpenHandsEngineLive:
    """OpenHands REST API + Docker sandbox engine."""

    async def test_simple_task(self, openhands_driver: OpenHandsDriver, settings: Settings) -> None:
        if not await _openhands_available(settings.openhands_base_url):
            pytest.skip("OpenHands not running")
        result = await openhands_driver.run_task(SIMPLE_TASK, timeout_seconds=120.0)
        assert result.success, f"OpenHands failed: {result.error}"
        assert result.output, "Output should not be empty"
        assert result.engine == AgentEngineType.OPENHANDS
        print(f"\n  OpenHands: {result.output[:120]}")
        print(f"  Duration: {result.duration_seconds:.2f}s")

    async def test_capabilities(self, openhands_driver: OpenHandsDriver) -> None:
        caps = openhands_driver.get_capabilities()
        assert caps.engine_type == AgentEngineType.OPENHANDS
        assert caps.supports_sandbox is True
        assert caps.supports_parallel is True

    async def test_availability_matches_docker(
        self, openhands_driver: OpenHandsDriver, settings: Settings
    ) -> None:
        available = await openhands_driver.is_available()
        reachable = await _openhands_available(settings.openhands_base_url)
        assert available == reachable
        print(f"\n  OpenHands available: {available}, API reachable: {reachable}")


# ══════════════════════════════════════════════════════════
# Availability Detection Tests (always run)
# ══════════════════════════════════════════════════════════


class TestAvailabilityDetection:
    """Verify is_available() accuracy across all engines."""

    async def test_ollama_availability(self, ollama_driver: OllamaEngineDriver) -> None:
        available = await ollama_driver.is_available()
        assert isinstance(available, bool)
        print(f"\n  Ollama: {available}")

    async def test_claude_code_availability(self, claude_driver: ClaudeCodeDriver) -> None:
        available = await claude_driver.is_available()
        assert isinstance(available, bool)
        # Cross-check: if CLI not on PATH, should not be available
        if not _cli_available("claude"):
            assert not available, "Should not be available without CLI"
        print(f"\n  Claude Code: {available}")

    async def test_codex_availability(self, codex_driver: CodexCLIDriver) -> None:
        available = await codex_driver.is_available()
        assert isinstance(available, bool)
        if not _cli_available("codex"):
            assert not available, "Should not be available without CLI"
        print(f"\n  Codex CLI: {available}")

    async def test_gemini_availability(self, gemini_driver: GeminiCLIDriver) -> None:
        available = await gemini_driver.is_available()
        assert isinstance(available, bool)
        if not _cli_available("gemini"):
            assert not available, "Should not be available without CLI"
        print(f"\n  Gemini CLI: {available}")

    async def test_openhands_availability(
        self, openhands_driver: OpenHandsDriver, settings: Settings
    ) -> None:
        available = await openhands_driver.is_available()
        assert isinstance(available, bool)
        reachable = await _openhands_available(settings.openhands_base_url)
        assert available == reachable
        print(f"\n  OpenHands: {available}")


# ══════════════════════════════════════════════════════════
# Cross-Engine Live Tests — Completion Criteria 1
# ══════════════════════════════════════════════════════════


class TestCrossEngineLive:
    """Run the same task across all available engines and compare results.

    Completion Criteria 1: Same task across multiple engines with result comparison.
    """

    async def test_simple_task_across_available_engines(
        self, all_drivers: dict[AgentEngineType, AgentEnginePort]
    ) -> None:
        """Execute SIMPLE_TASK on every available engine, compare results."""
        results: dict[AgentEngineType, AgentEngineResult] = {}

        for engine_type, driver in all_drivers.items():
            if not await driver.is_available():
                continue
            try:
                result = await driver.run_task(SIMPLE_TASK, timeout_seconds=120.0)
                results[engine_type] = result
            except Exception as exc:
                print(f"\n  {engine_type.value}: EXCEPTION — {exc}")

        if not results:
            pytest.skip("No engines available")

        # Print comparison table
        print("\n  ┌─────────────────┬─────────┬──────────┬──────────┬─────────────────┐")
        print("  │ Engine          │ Success │ Duration │ Cost     │ Output (30ch)   │")
        print("  ├─────────────────┼─────────┼──────────┼──────────┼─────────────────┤")
        for engine_type, result in results.items():
            name = engine_type.value[:15].ljust(15)
            success = "OK" if result.success else "FAIL"
            dur = f"{result.duration_seconds:.2f}s".rjust(6)
            cost = f"${result.cost_usd:.4f}".rjust(7)
            out = result.output.replace("\n", " ")[:15] if result.output else ""
            print(f"  │ {name} │ {success:7s} │ {dur:>8s} │ {cost:>8s} │ {out:15s} │")
        print("  └─────────────────┴─────────┴──────────┴──────────┴─────────────────┘")

        # Separate successful results from env/auth failures
        succeeded = {k: v for k, v in results.items() if v.success}
        env_failed = {k: v for k, v in results.items() if _is_env_error(v)}
        real_failed = {k: v for k, v in results.items() if not v.success and not _is_env_error(v)}

        # Env/auth failures are expected, log but don't fail
        for et, r in env_failed.items():
            print(f"  {et.value}: env/auth skip — {r.error}")

        # Real (non-env) failures are bugs
        for et, r in real_failed.items():
            msg = f"{et.value} failed (not env): {r.error}"
            raise AssertionError(msg)

        if not succeeded:
            pytest.skip("All available engines failed due to env/auth")

        # Validate successful results
        for engine_type, result in succeeded.items():
            assert result.output, f"{engine_type.value} output empty"
            assert "4" in result.output, f"{engine_type.value} missing '4': {result.output[:80]}"
            assert result.engine == engine_type
            assert result.duration_seconds > 0

    async def test_ollama_is_cheapest(
        self, all_drivers: dict[AgentEngineType, AgentEnginePort]
    ) -> None:
        """Ollama should always report cost_usd == 0.0."""
        ollama = all_drivers[AgentEngineType.OLLAMA]
        if not await ollama.is_available():
            pytest.skip("Ollama not running")

        result = await ollama.run_task(SIMPLE_TASK, timeout_seconds=60.0)
        assert result.success
        assert result.cost_usd == 0.0, f"Ollama cost should be $0, got ${result.cost_usd}"

        # Any other engine that succeeds should have cost >= 0
        for engine_type, driver in all_drivers.items():
            if engine_type == AgentEngineType.OLLAMA:
                continue
            if not await driver.is_available():
                continue
            other_result = await driver.run_task(SIMPLE_TASK, timeout_seconds=120.0)
            if other_result.success:
                assert other_result.cost_usd >= 0.0

    async def test_consistent_result_structure(
        self, all_drivers: dict[AgentEngineType, AgentEnginePort]
    ) -> None:
        """All engines should return properly typed AgentEngineResult fields."""
        for engine_type, driver in all_drivers.items():
            if not await driver.is_available():
                continue

            result = await driver.run_task(SIMPLE_TASK, timeout_seconds=120.0)

            # Type checks
            assert isinstance(result, AgentEngineResult)
            assert isinstance(result.engine, AgentEngineType)
            assert isinstance(result.success, bool)
            assert isinstance(result.output, str)
            assert isinstance(result.artifacts, list)
            assert isinstance(result.cost_usd, (int, float))
            assert isinstance(result.duration_seconds, (int, float))
            assert isinstance(result.metadata, dict)
            assert result.error is None or isinstance(result.error, str)
            assert result.model_used is None or isinstance(result.model_used, str)
            print(f"\n  {engine_type.value}: structure OK")


# ══════════════════════════════════════════════════════════
# Routing Live Tests — Completion Criteria 2 & 3
# ══════════════════════════════════════════════════════════


class TestRoutingLive:
    """Verify automatic engine selection and fallback behavior.

    Completion Criteria 2: Task-type-based automatic engine selection.
    Completion Criteria 3: Availability check + fallback in live environment.
    """

    async def test_zero_budget_routes_to_ollama(
        self,
        use_case: RouteToEngineUseCase,
        ollama_driver: OllamaEngineDriver,
    ) -> None:
        """budget=0 must always route to OLLAMA."""
        if not await ollama_driver.is_available():
            pytest.skip("Ollama not running")

        result = await use_case.execute(
            task=SIMPLE_TASK,
            task_type=TaskType.COMPLEX_REASONING,
            budget=0.0,
            timeout_seconds=60.0,
        )
        assert result.success, f"Ollama failed: {result.error}"
        assert result.engine == AgentEngineType.OLLAMA
        assert result.cost_usd == 0.0
        print(f"\n  budget=0 → {result.engine.value}, cost=${result.cost_usd:.4f}")

    async def test_simple_qa_routes_to_ollama(
        self,
        use_case: RouteToEngineUseCase,
        ollama_driver: OllamaEngineDriver,
    ) -> None:
        """SIMPLE_QA with budget should route to OLLAMA (primary engine)."""
        if not await ollama_driver.is_available():
            pytest.skip("Ollama not running")

        result = await use_case.execute(
            task=SIMPLE_TASK,
            task_type=TaskType.SIMPLE_QA,
            budget=10.0,
            timeout_seconds=60.0,
        )
        assert result.success, f"Failed: {result.error}"
        # SIMPLE_QA primary is OLLAMA per AgentEngineRouter
        assert result.engine == AgentEngineType.OLLAMA
        print(f"\n  SIMPLE_QA → {result.engine.value}")

    async def test_complex_reasoning_with_budget(
        self,
        use_case: RouteToEngineUseCase,
        all_drivers: dict[AgentEngineType, AgentEnginePort],
        ollama_driver: OllamaEngineDriver,
    ) -> None:
        """COMPLEX_REASONING should try Claude Code first, fallback on unavailability.

        Note: is_available() checks CLI binary existence, but run_task()
        may still fail due to env issues (nested session, auth).
        The fallback chain should eventually reach Ollama.
        """
        if not await ollama_driver.is_available():
            pytest.skip("Ollama not running (needed as ultimate fallback)")

        result = await use_case.execute(
            task=SIMPLE_TASK,
            task_type=TaskType.COMPLEX_REASONING,
            budget=50.0,
            timeout_seconds=120.0,
        )
        # The chain is CLAUDE_CODE → CODEX_CLI → GEMINI_CLI → OLLAMA.
        # Engines may fail due to env/auth; result should be from
        # whichever engine first succeeds (or OLLAMA as last resort).
        assert result.success, f"Fallback chain failed: {result.error}"
        # Result engine must be one from the COMPLEX_REASONING chain
        assert result.engine in (
            AgentEngineType.CLAUDE_CODE,
            AgentEngineType.CODEX_CLI,
            AgentEngineType.GEMINI_CLI,
            AgentEngineType.OLLAMA,
        )
        print(f"\n  COMPLEX_REASONING → {result.engine.value}")

    async def test_fallback_when_primary_unavailable(
        self,
        all_drivers: dict[AgentEngineType, AgentEnginePort],
        ollama_driver: OllamaEngineDriver,
    ) -> None:
        """LONG_RUNNING_DEV primary=OpenHands; if unavailable, fallback should succeed."""
        if not await ollama_driver.is_available():
            pytest.skip("Ollama not running (needed as ultimate fallback)")

        # Build use case with all drivers
        uc = RouteToEngineUseCase(drivers=all_drivers)

        result = await uc.execute(
            task=SIMPLE_TASK,
            task_type=TaskType.LONG_RUNNING_DEV,
            budget=50.0,
            timeout_seconds=120.0,
        )
        assert result.success, f"All engines failed: {result.error}"

        openhands_available = await all_drivers[AgentEngineType.OPENHANDS].is_available()
        if openhands_available:
            assert result.engine == AgentEngineType.OPENHANDS
        else:
            # Should have fallen back (chain: CLAUDE_CODE → CODEX_CLI → OLLAMA)
            assert result.engine != AgentEngineType.OPENHANDS
        print(
            f"\n  LONG_RUNNING_DEV → {result.engine.value}"
            f" (OpenHands available: {openhands_available})"
        )

    async def test_list_engines_shows_real_availability(
        self,
        use_case: RouteToEngineUseCase,
    ) -> None:
        """list_engines() should return exactly 5 engines with accurate availability."""
        statuses = await use_case.list_engines()
        assert len(statuses) == 5, f"Expected 5 engines, got {len(statuses)}"

        engine_types = {s.engine_type for s in statuses}
        expected = {
            AgentEngineType.OLLAMA,
            AgentEngineType.CLAUDE_CODE,
            AgentEngineType.CODEX_CLI,
            AgentEngineType.GEMINI_CLI,
            AgentEngineType.OPENHANDS,
        }
        assert engine_types == expected

        # Cross-validate availability
        print("\n  Engine availability:")
        for status in statuses:
            print(f"    {status.engine_type.value:15s} → {status.available}")
            # Capabilities should not be None
            assert status.capabilities is not None
            assert status.capabilities.engine_type == status.engine_type


# ══════════════════════════════════════════════════════════
# Disabled Driver Behavior Tests
# ══════════════════════════════════════════════════════════


class TestDisabledDriverBehavior:
    """Verify drivers behave correctly when explicitly disabled."""

    async def test_disabled_claude_returns_failure(self) -> None:
        driver = ClaudeCodeDriver(enabled=False)
        assert not await driver.is_available()
        result = await driver.run_task(SIMPLE_TASK)
        assert not result.success
        assert result.error and "disabled" in result.error.lower()

    async def test_disabled_codex_returns_failure(self) -> None:
        driver = CodexCLIDriver(enabled=False)
        assert not await driver.is_available()
        result = await driver.run_task(SIMPLE_TASK)
        assert not result.success
        assert result.error and "disabled" in result.error.lower()
