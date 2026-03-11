"""DI Container — wires all dependencies for the FastAPI application.

Single object stored on app.state.container. Swappable for testing.
"""

from __future__ import annotations

import logging

from application.use_cases.analyze_execution import AnalyzeExecutionUseCase
from application.use_cases.background_planner import BackgroundPlannerUseCase
from application.use_cases.cost_estimator import CostEstimator
from application.use_cases.create_task import CreateTaskUseCase
from application.use_cases.discover_tools import DiscoverToolsUseCase
from application.use_cases.execute_task import ExecuteTaskUseCase
from application.use_cases.extract_insights import ExtractInsightsUseCase
from application.use_cases.handoff_task import HandoffTaskUseCase
from application.use_cases.install_tool import InstallToolUseCase
from application.use_cases.interactive_plan import InteractivePlanUseCase
from application.use_cases.manage_ollama import ManageOllamaUseCase
from application.use_cases.route_to_engine import RouteToEngineUseCase
from application.use_cases.systemic_evolution import SystemicEvolutionUseCase
from application.use_cases.update_strategy import UpdateStrategyUseCase
from domain.ports.agent_affinity_repository import AgentAffinityRepository
from domain.ports.agent_engine import AgentEnginePort
from domain.ports.context_adapter import ContextAdapterPort
from domain.ports.cost_repository import CostRepository
from domain.ports.embedding import EmbeddingPort
from domain.ports.execution_record_repository import ExecutionRecordRepository
from domain.ports.memory_repository import MemoryRepository
from domain.ports.plan_repository import PlanRepository
from domain.ports.shared_task_state_repository import SharedTaskStateRepository
from domain.ports.task_repository import TaskRepository
from domain.value_objects.agent_engine import AgentEngineType
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.litellm_gateway import LiteLLMGateway
from infrastructure.llm.ollama_manager import OllamaManager
from infrastructure.marketplace import MCPRegistryClient, MCPToolInstaller
from infrastructure.mcp.client import MCPClient
from infrastructure.memory.context_bridge import ContextBridge
from infrastructure.memory.context_zipper import ContextZipper
from infrastructure.memory.delta_encoder import DeltaEncoderManager
from infrastructure.memory.forgetting_curve import ForgettingCurveManager
from infrastructure.memory.hierarchical_summarizer import HierarchicalSummaryManager
from infrastructure.memory.memory_hierarchy import MemoryHierarchy
from infrastructure.persistence.in_memory import (
    InMemoryCostRepository,
    InMemoryMemoryRepository,
    InMemoryPlanRepository,
    InMemoryTaskRepository,
)
from infrastructure.task_graph.engine import LangGraphTaskEngine
from infrastructure.task_graph.intent_analyzer import IntentAnalyzer
from shared.config import Settings

logger = logging.getLogger(__name__)


class AppContainer:
    """Composes all dependencies. Created once at app startup."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

        # Embedding port (optional — only created when backend != "none")
        self.embedding_port: EmbeddingPort | None = self._create_embedding_port()

        # Repositories — PG or InMemory based on settings
        repos = self._create_repos()
        self.task_repo: TaskRepository = repos["task"]
        self.cost_repo: CostRepository = repos["cost"]
        self.memory_repo: MemoryRepository = repos["memory"]
        self.plan_repo: PlanRepository = repos["plan"]

        # LLM infrastructure
        self.ollama = OllamaManager(base_url=self.settings.ollama_base_url)
        self.cost_tracker = CostTracker(self.cost_repo)
        self.llm = LiteLLMGateway(
            ollama=self.ollama,
            cost_tracker=self.cost_tracker,
            settings=self.settings,
        )

        # Task graph
        self.intent_analyzer = IntentAnalyzer(llm=self.llm)
        self.task_engine = LangGraphTaskEngine(
            llm=self.llm,
            analyzer=self.intent_analyzer,
        )

        # Use cases
        self.create_task = CreateTaskUseCase(
            engine=self.task_engine,
            repo=self.task_repo,
        )
        # Planning
        self.cost_estimator = CostEstimator()
        self.interactive_plan = InteractivePlanUseCase(
            engine=self.task_engine,
            cost_estimator=self.cost_estimator,
            plan_repo=self.plan_repo,
            task_repo=self.task_repo,
        )

        # Background planner
        self.background_planner = BackgroundPlannerUseCase(
            llm=self.llm,
            task_repo=self.task_repo,
        )

        # Memory
        self.memory = MemoryHierarchy(memory_repo=self.memory_repo)
        self.context_zipper = ContextZipper(
            embedding_port=self.embedding_port,
            memory_repo=self.memory_repo,
        )
        self.forgetting_curve = ForgettingCurveManager(
            memory_repo=self.memory_repo,
            knowledge_graph=None,  # KG wired when available
            threshold=self.settings.memory_retention_threshold,
        )
        self.delta_encoder = DeltaEncoderManager(
            memory_repo=self.memory_repo,
        )
        self.hierarchical_summarizer = HierarchicalSummaryManager(
            memory_repo=self.memory_repo,
            llm_gateway=self.llm,
        )
        self.context_bridge = ContextBridge(
            memory=self.memory,
            context_zipper=self.context_zipper,
            delta_encoder=self.delta_encoder,
            default_max_tokens=self.settings.context_bridge_default_tokens,
        )

        # MCP client (optional — lazy, connects on demand)
        self.mcp_client: MCPClient | None = MCPClient() if self.settings.mcp_enabled else None

        # Marketplace (Sprint 5.3)
        from domain.services.tool_safety_scorer import ToolSafetyScorer

        self._safety_scorer = ToolSafetyScorer()
        self.mcp_registry = MCPRegistryClient(
            safety_scorer=self._safety_scorer,
            base_url=self.settings.mcp_registry_url,
        )
        self.tool_installer = MCPToolInstaller(
            safety_threshold=self.settings.marketplace_safety_threshold_tier,
        )
        self.install_tool = InstallToolUseCase(
            registry=self.mcp_registry,
            installer=self.tool_installer,
        )
        self.discover_tools = DiscoverToolsUseCase(
            registry=self.mcp_registry,
        )

        # Ollama management (Sprint 5.5)
        self.manage_ollama = ManageOllamaUseCase(
            ollama=self.ollama,
            settings=self.settings,
        )

        # Agent CLI drivers (Sprint 4.2)
        self.agent_drivers: dict[AgentEngineType, AgentEnginePort] = self._wire_agent_drivers()

        # UCL: Context Adapters + Shared State (Sprint 7.2-7.3)
        self._context_adapters: dict[AgentEngineType, ContextAdapterPort] = (
            self._wire_context_adapters()
        )
        self.shared_task_state_repo: SharedTaskStateRepository = (
            self._create_shared_task_state_repo()
        )
        from infrastructure.cognitive.insight_extractor import InsightExtractor

        self.insight_extractor = InsightExtractor(adapters=self._context_adapters)
        self.extract_insights = ExtractInsightsUseCase(
            extractor=self.insight_extractor,
            memory_repo=self.memory_repo,
            task_state_repo=self.shared_task_state_repo,
        )

        # Affinity store (Sprint 7.4)
        self.affinity_repo: AgentAffinityRepository = self._create_affinity_repo()

        # Engine routing use case (Sprint 4.3, enhanced Sprint 7.4)
        self.route_to_engine = RouteToEngineUseCase(
            drivers=self.agent_drivers,
            context_adapters=self._context_adapters,
            affinity_repo=self.affinity_repo,
            task_state_repo=self.shared_task_state_repo,
            affinity_min_samples=self.settings.affinity_min_samples,
            affinity_boost_threshold=self.settings.affinity_boost_threshold,
        )

        # Task handoff use case (Sprint 7.4)
        self.handoff_task = HandoffTaskUseCase(
            route_to_engine=self.route_to_engine,
            task_state_repo=self.shared_task_state_repo,
            context_adapters=self._context_adapters,
            insight_extractor=self.extract_insights,
        )

        # Re-wire execute_task with insight extraction
        self.execute_task = ExecuteTaskUseCase(
            engine=self.task_engine,
            repo=self.task_repo,
            extract_insights=self.extract_insights,
        )

        # Evolution (Phase 6)
        self.execution_record_repo: ExecutionRecordRepository = self._create_execution_record_repo()
        from infrastructure.evolution.strategy_store import StrategyStore

        self.strategy_store = StrategyStore(
            base_dir=self.settings.evolution_strategy_dir,
        )
        self.analyze_execution = AnalyzeExecutionUseCase(
            repo=self.execution_record_repo,
        )
        self.update_strategy = UpdateStrategyUseCase(
            execution_repo=self.execution_record_repo,
            strategy_store=self.strategy_store,
            min_samples=self.settings.evolution_min_samples,
        )
        self.systemic_evolution = SystemicEvolutionUseCase(
            analyze_execution=self.analyze_execution,
            update_strategy=self.update_strategy,
            discover_tools=self.discover_tools if self.settings.marketplace_enabled else None,
        )

    def _wire_context_adapters(self) -> dict[AgentEngineType, ContextAdapterPort]:
        """Create UCL context adapters for all engine types."""
        from infrastructure.cognitive.adapters import (
            ADKContextAdapter,
            ClaudeCodeContextAdapter,
            CodexContextAdapter,
            GeminiContextAdapter,
            OllamaContextAdapter,
            OpenHandsContextAdapter,
        )

        return {
            AgentEngineType.CLAUDE_CODE: ClaudeCodeContextAdapter(),
            AgentEngineType.GEMINI_CLI: GeminiContextAdapter(),
            AgentEngineType.CODEX_CLI: CodexContextAdapter(),
            AgentEngineType.OPENHANDS: OpenHandsContextAdapter(),
            AgentEngineType.ADK: ADKContextAdapter(),
            AgentEngineType.OLLAMA: OllamaContextAdapter(),
        }

    def _create_affinity_repo(self) -> AgentAffinityRepository:
        """Create affinity repository (in-memory for now)."""
        from infrastructure.cognitive.affinity_store import InMemoryAgentAffinityRepository

        return InMemoryAgentAffinityRepository()

    def _create_shared_task_state_repo(self) -> SharedTaskStateRepository:
        """Create SharedTaskState repository (in-memory for now)."""
        from infrastructure.persistence.shared_task_state_repo import (
            InMemorySharedTaskStateRepository,
        )

        return InMemorySharedTaskStateRepository()

    def _wire_agent_drivers(self) -> dict[AgentEngineType, AgentEnginePort]:
        """Create all agent engine drivers based on settings."""
        from infrastructure.agent_cli import (
            ADKDriver,
            ClaudeCodeDriver,
            CodexCLIDriver,
            GeminiCLIDriver,
            OllamaEngineDriver,
            OpenHandsDriver,
        )

        drivers: dict[AgentEngineType, AgentEnginePort] = {
            AgentEngineType.OLLAMA: OllamaEngineDriver(
                gateway=self.llm,
                ollama=self.ollama,
            ),
            AgentEngineType.CLAUDE_CODE: ClaudeCodeDriver(
                enabled=self.settings.claude_code_sdk_enabled,
                cli_path=self.settings.claude_code_cli_path,
            ),
            AgentEngineType.CODEX_CLI: CodexCLIDriver(
                enabled=self.settings.codex_cli_enabled,
                cli_path=self.settings.codex_cli_path,
            ),
            AgentEngineType.GEMINI_CLI: GeminiCLIDriver(
                enabled=self.settings.gemini_cli_enabled,
                cli_path=self.settings.gemini_cli_path,
            ),
            AgentEngineType.OPENHANDS: OpenHandsDriver(
                base_url=self.settings.openhands_base_url,
                model=self.settings.openhands_model,
                api_key=self.settings.openhands_api_key,
            ),
            AgentEngineType.ADK: ADKDriver(
                enabled=self.settings.adk_enabled,
                model=self.settings.adk_default_model,
            ),
        }
        return drivers

    def _create_execution_record_repo(self) -> ExecutionRecordRepository:
        """Create execution record repository (in-memory for now)."""
        from infrastructure.persistence.in_memory_execution_record import (
            InMemoryExecutionRecordRepository,
        )

        return InMemoryExecutionRecordRepository()

    def _create_embedding_port(self) -> EmbeddingPort | None:
        """Create embedding port based on settings. Returns None if disabled."""
        if self.settings.embedding_backend == "none":
            return None
        if self.settings.embedding_backend == "ollama":
            from infrastructure.memory.embedding_adapters import OllamaEmbeddingAdapter

            return OllamaEmbeddingAdapter(
                base_url=self.settings.ollama_base_url,
                model=self.settings.embedding_model,
                dimensions=self.settings.embedding_dimensions,
            )
        logger.warning("Unknown embedding_backend: %s", self.settings.embedding_backend)
        return None

    def _create_repos(self) -> dict:
        """Pick PG or InMemory based on settings.use_postgres."""
        if self.settings.use_postgres:
            return self._create_pg_repos()
        return {
            "task": InMemoryTaskRepository(),
            "cost": InMemoryCostRepository(),
            "memory": InMemoryMemoryRepository(embedding_port=self.embedding_port),
            "plan": InMemoryPlanRepository(),
        }

    def _create_pg_repos(self) -> dict:
        """Create PostgreSQL-backed repositories."""
        from sqlalchemy.ext.asyncio import (
            AsyncSession,
            async_sessionmaker,
            create_async_engine,
        )

        from infrastructure.persistence.pg_cost_repository import PgCostRepository
        from infrastructure.persistence.pg_memory_repository import PgMemoryRepository
        from infrastructure.persistence.pg_plan_repository import PgPlanRepository
        from infrastructure.persistence.pg_task_repository import PgTaskRepository

        self._engine = create_async_engine(
            self.settings.database_url,
            echo=self.settings.is_development,
            pool_size=5,
            max_overflow=10,
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        return {
            "task": PgTaskRepository(self._session_factory),
            "cost": PgCostRepository(self._session_factory),
            "memory": PgMemoryRepository(self._session_factory, embedding_port=self.embedding_port),
            "plan": PgPlanRepository(self._session_factory),
        }

    async def init(self) -> None:
        """Initialize database (create tables if PG). Call in app lifespan."""
        if self.settings.use_postgres:
            from infrastructure.persistence.models import Base

            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """Dispose DB engine on shutdown."""
        if self.settings.use_postgres and hasattr(self, "_engine"):
            await self._engine.dispose()
