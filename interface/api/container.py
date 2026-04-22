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
from domain.ports.fractal_learning_repository import FractalLearningRepository
from domain.ports.memory_repository import MemoryRepository
from domain.ports.plan_repository import PlanRepository
from domain.ports.shared_task_state_repository import SharedTaskStateRepository
from domain.ports.task_engine import TaskEngine
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
from infrastructure.task_graph.react_executor import ReactExecutor
from shared.config import Settings
from shared.event_bus import TaskEventBus

logger = logging.getLogger(__name__)


class AppContainer:
    """Composes all dependencies. Created once at app startup."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

        # SSE event bus for real-time task streaming (TD-161)
        self.event_bus = TaskEventBus()

        # Embedding port (optional — only created when backend != "none")
        self.embedding_port: EmbeddingPort | None = self._create_embedding_port()

        # Repositories — PG or InMemory based on settings
        repos = self._create_repos()
        self.task_repo: TaskRepository = repos["task"]
        self.cost_repo: CostRepository = repos["cost"]
        self.memory_repo: MemoryRepository = repos["memory"]
        self.plan_repo: PlanRepository = repos["plan"]

        # Learning repo — set by _create_task_engine() when fractal mode,
        # or defaults to InMemory for non-fractal access (CLI).
        self.learning_repo: FractalLearningRepository | None = None

        # LLM infrastructure
        self.ollama = OllamaManager(base_url=self.settings.ollama_base_url)
        self.cost_tracker = CostTracker(self.cost_repo)
        self.llm = LiteLLMGateway(
            ollama=self.ollama,
            cost_tracker=self.cost_tracker,
            settings=self.settings,
        )

        # Task graph (route_to_engine wired later after it's created)
        self.intent_analyzer = IntentAnalyzer(
            llm=self.llm,
            role_assignment=self.settings.discussion_role_assignment,
        )
        self.react_executor = self._create_react_executor()
        self._langgraph_engine = LangGraphTaskEngine(
            llm=self.llm,
            analyzer=self.intent_analyzer,
            react_executor=self.react_executor,
            discussion_max_rounds=self.settings.discussion_max_rounds,
            discussion_rotate_models=self.settings.discussion_rotate_models,
            discussion_adaptive=self.settings.discussion_adaptive,
            discussion_convergence_threshold=self.settings.discussion_convergence_threshold,
            discussion_min_rounds=self.settings.discussion_min_rounds,
            task_budget=self.settings.default_task_budget_usd,
        )
        self.task_engine = self._create_task_engine()

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
        from infrastructure.cognitive.hybrid_memory_classifier import HybridMemoryClassifier
        from infrastructure.cognitive.insight_extractor import InsightExtractor

        self.memory_classifier = HybridMemoryClassifier(
            llm_gateway=self.llm,
            confidence_threshold=0.5,
        )
        self.insight_extractor = InsightExtractor(
            adapters=self._context_adapters,
            embedding_port=self.embedding_port,
            memory_classifier=self.memory_classifier,
            semantic_dedup_threshold=self.settings.semantic_dedup_threshold,
            token_dedup_threshold=self.settings.token_dedup_threshold,
        )
        self.extract_insights = ExtractInsightsUseCase(
            extractor=self.insight_extractor,
            memory_repo=self.memory_repo,
            task_state_repo=self.shared_task_state_repo,
        )

        # Affinity store (Sprint 7.4)
        self.affinity_repo: AgentAffinityRepository = self._create_affinity_repo()

        # Engine routing use case (Sprint 4.3, enhanced Sprint 7.4, BUG-002/003 Sprint 23.1)
        self.route_to_engine = RouteToEngineUseCase(
            drivers=self.agent_drivers,
            context_adapters=self._context_adapters,
            affinity_repo=self.affinity_repo,
            task_state_repo=self.shared_task_state_repo,
            affinity_min_samples=self.settings.affinity_min_samples,
            affinity_boost_threshold=self.settings.affinity_boost_threshold,
            cost_tracker=self.cost_tracker,
        )

        # Sprint 12.2: Wire RouteToEngineUseCase into task engine
        # Always wire to the LangGraph engine (inner engine for both modes)
        self._langgraph_engine._route_to_engine = self.route_to_engine

        # Task handoff use case (Sprint 7.4)
        self.handoff_task = HandoffTaskUseCase(
            route_to_engine=self.route_to_engine,
            task_state_repo=self.shared_task_state_repo,
            context_adapters=self._context_adapters,
            insight_extractor=self.extract_insights,
        )

        # A2A Protocol (Phase 14)
        from application.use_cases.manage_a2a_conversation import ManageA2AConversationUseCase
        from application.use_cases.send_a2a_message import SendA2AMessageUseCase
        from infrastructure.a2a.in_memory_agent_registry import InMemoryAgentRegistry
        from infrastructure.a2a.in_memory_broker import InMemoryA2ABroker

        self.a2a_broker = InMemoryA2ABroker()
        self.agent_registry = InMemoryAgentRegistry()
        self.send_a2a_message = SendA2AMessageUseCase(
            broker=self.a2a_broker,
            registry=self.agent_registry,
        )
        self.manage_a2a_conversation = ManageA2AConversationUseCase(
            broker=self.a2a_broker,
        )
        self.a2a_conversations: dict[str, object] = {}  # conversation_id → A2AConversation

        # Evolution (Phase 6) — create repo before execute_task so it can record
        self.execution_record_repo: ExecutionRecordRepository = self._create_execution_record_repo()

        # Re-wire execute_task with insight extraction + auto-discovery + recording
        self.execute_task = ExecuteTaskUseCase(
            engine=self.task_engine,
            repo=self.task_repo,
            extract_insights=self.extract_insights,
            discover_tools=self.discover_tools,
            install_tool=self.install_tool,
            execution_record_repo=self.execution_record_repo,
            default_model=self.settings.ollama_default_model,
            event_bus=self.event_bus,
            max_skill_retries=1,
        )
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

    def _create_task_engine(self) -> TaskEngine:
        """Select task engine based on config: langgraph (default) or fractal."""
        if self.settings.execution_engine != "fractal":
            # Ensure learning_repo is available for CLI even in non-fractal mode
            if self.learning_repo is None:
                from infrastructure.fractal.in_memory_learning_repo import (
                    InMemoryFractalLearningRepository,
                )

                self.learning_repo = InMemoryFractalLearningRepository()
            return self._langgraph_engine

        from infrastructure.fractal.fractal_engine import FractalTaskEngine
        from infrastructure.fractal.in_memory_learning_repo import InMemoryFractalLearningRepository
        from infrastructure.fractal.llm_plan_evaluator import LLMPlanEvaluator
        from infrastructure.fractal.llm_planner import LLMPlanner
        from infrastructure.fractal.llm_result_evaluator import LLMResultEvaluator

        # Learning repo must be created before planner (planner uses it)
        if self.settings.use_postgres and hasattr(self, "_session_factory"):
            from infrastructure.persistence.pg_fractal_learning_repository import (
                PgFractalLearningRepository,
            )

            learning_repo = PgFractalLearningRepository(self._session_factory)
        else:
            learning_repo = InMemoryFractalLearningRepository()
        self.learning_repo = learning_repo  # Expose for CLI access

        planner = LLMPlanner(
            llm=self.llm,
            candidates_per_node=self.settings.fractal_candidates_per_node,
            max_depth=self.settings.fractal_max_depth,
            learning_repo=learning_repo,
        )
        plan_evaluator = LLMPlanEvaluator(
            llm=self.llm,
            models=(
                [m.strip() for m in self.settings.fractal_plan_eval_models.split(",") if m.strip()]
                if self.settings.fractal_plan_eval_models
                else None
            ),
            min_score=self.settings.fractal_plan_eval_min_score,
        )
        result_evaluator = LLMResultEvaluator(
            llm=self.llm,
            ok_threshold=self.settings.fractal_result_eval_ok_threshold,
            retry_threshold=self.settings.fractal_result_eval_retry_threshold,
        )

        # Living Fractal: reflection evaluator for dynamic node spawning (TD-163)
        from infrastructure.fractal.llm_reflection_evaluator import LLMReflectionEvaluator

        reflection_evaluator = LLMReflectionEvaluator(llm=self.llm)

        # TD-167: SIMPLE task bypass — LLM intent analysis classifier
        from infrastructure.fractal.bypass_classifier import FractalBypassClassifier

        bypass_classifier = FractalBypassClassifier(llm=self.llm)

        # Output-aware evaluation: classify goal output requirements
        from domain.services.output_requirement_classifier import OutputRequirementClassifier

        output_classifier = OutputRequirementClassifier(llm=self.llm)

        logger.info(
            "FractalTaskEngine enabled (depth=%d, retries=%d, reflect=%d, bypass=on)",
            self.settings.fractal_max_depth,
            self.settings.fractal_max_retries,
            self.settings.fractal_max_reflection_rounds,
        )
        return FractalTaskEngine(
            planner=planner,
            plan_evaluator=plan_evaluator,
            result_evaluator=result_evaluator,
            inner_engine=self._langgraph_engine,
            max_depth=self.settings.fractal_max_depth,
            max_retries=self.settings.fractal_max_retries,
            max_plan_attempts=self.settings.fractal_max_plan_attempts,
            plan_eval_min_score=self.settings.fractal_plan_eval_min_score,
            result_eval_ok_threshold=self.settings.fractal_result_eval_ok_threshold,
            result_eval_retry_threshold=self.settings.fractal_result_eval_retry_threshold,
            budget_usd=self.settings.default_task_budget_usd,
            learning_repo=learning_repo,
            reflection_evaluator=reflection_evaluator,
            max_reflection_rounds=self.settings.fractal_max_reflection_rounds,
            max_total_nodes=self.settings.fractal_max_total_nodes,
            bypass_classifier=bypass_classifier,
            skip_gate2_for_terminal_success=True,  # TD-168: ~30s savings per node
            parallel_node_execution=True,  # TD-169: asyncio.gather for batches
            skip_reflection_for_single_success=True,  # TD-171: ~30s savings
            cache_planner_candidates=True,  # TD-173: skip LLM on repeat goals
            max_concurrent_nodes=self.settings.fractal_max_concurrent_nodes,  # TD-175
            throttle_delay_ms=self.settings.fractal_throttle_delay_ms,  # TD-175
            output_classifier=output_classifier,
            max_execution_seconds=self.settings.fractal_max_execution_seconds,  # TD-181
        )

    def _create_react_executor(self) -> ReactExecutor | None:
        """Create ReactExecutor if enabled in settings."""
        if not self.settings.react_enabled:
            return None

        from domain.value_objects.approval_mode import ApprovalMode
        from infrastructure.local_execution.audit_log import JsonlAuditLogger
        from infrastructure.local_execution.executor import LocalExecutor
        from infrastructure.local_execution.tools.tool_schemas import get_openai_tools

        mode_map = {
            "full-auto": ApprovalMode.FULL_AUTO,
            "confirm-destructive": ApprovalMode.CONFIRM_DESTRUCTIVE,
            "confirm-all": ApprovalMode.CONFIRM_ALL,
        }
        approval_mode = mode_map.get(
            self.settings.laee_approval_mode, ApprovalMode.CONFIRM_DESTRUCTIVE
        )
        audit_logger = JsonlAuditLogger(log_path=self.settings.laee_audit_log_path)
        local_executor = LocalExecutor(
            approval_mode=approval_mode,
            audit_logger=audit_logger,
            undo_enabled=self.settings.laee_undo_enabled,
        )

        # Sprint 12.4: MCP client for external tool routing
        mcp_client = MCPClient() if self.settings.mcp_enabled else None

        return ReactExecutor(
            llm=self.llm,
            executor=local_executor,
            tool_schemas=get_openai_tools(),
            max_iterations=self.settings.react_max_iterations,
            mcp_client=mcp_client,
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
        """Create affinity repository — PG if available, else in-memory."""
        if self.settings.use_postgres and hasattr(self, "_session_factory"):
            from infrastructure.persistence.pg_agent_affinity_repository import (
                PgAgentAffinityRepository,
            )

            return PgAgentAffinityRepository(self._session_factory)

        from infrastructure.cognitive.affinity_store import InMemoryAgentAffinityRepository

        return InMemoryAgentAffinityRepository()

    def _create_shared_task_state_repo(self) -> SharedTaskStateRepository:
        """Create SharedTaskState repository — PG if available, else in-memory."""
        if self.settings.use_postgres and hasattr(self, "_session_factory"):
            from infrastructure.persistence.pg_shared_task_state_repository import (
                PgSharedTaskStateRepository,
            )

            return PgSharedTaskStateRepository(self._session_factory)

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
                api_key=self.settings.google_gemini_api_key or None,
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
        """Create execution record repository — PG if available, else in-memory."""
        if self.settings.use_postgres and hasattr(self, "_session_factory"):
            from infrastructure.persistence.pg_execution_record_repository import (
                PgExecutionRecordRepository,
            )

            return PgExecutionRecordRepository(self._session_factory)

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
        """Pick PG, SQLite, or InMemory based on settings."""
        if self.settings.use_postgres:
            return self._create_pg_repos()
        if self.settings.use_sqlite:
            return self._create_sqlite_repos()
        return {
            "task": InMemoryTaskRepository(),
            "cost": InMemoryCostRepository(),
            "memory": InMemoryMemoryRepository(embedding_port=self.embedding_port),
            "plan": InMemoryPlanRepository(),
        }

    def _create_sqlite_repos(self) -> dict:
        """Create SQLite-backed repositories (persistent, no Docker required)."""
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
            self.settings.sqlite_url,
            echo=self.settings.is_development,
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        # Reuse PG repos — portable GUID/PortableJSON types handle dialect
        return {
            "task": PgTaskRepository(self._session_factory),
            "cost": PgCostRepository(self._session_factory),
            "memory": PgMemoryRepository(
                self._session_factory, embedding_port=self.embedding_port,
            ),
            "plan": PgPlanRepository(self._session_factory),
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
        """Initialize database (create tables if PG/SQLite) and connect MCP servers."""
        if self.settings.use_postgres or self.settings.use_sqlite:
            from infrastructure.persistence.models import Base

            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        # Sprint 12.4: Auto-connect configured MCP servers
        await self._connect_mcp_servers()

    async def _connect_mcp_servers(self) -> None:
        """Auto-connect configured MCP servers and register tools in ReactExecutor."""
        import json as _json

        if not self.react_executor or not self.settings.mcp_enabled:
            return
        try:
            servers = _json.loads(self.settings.mcp_servers)
        except (ValueError, TypeError):
            return
        if not isinstance(servers, list) or not servers:
            return

        mcp = self.react_executor.mcp_client
        if mcp is None:
            return

        for server_cfg in servers:
            name = server_cfg.get("name", "")
            command = server_cfg.get("command", "")
            args = server_cfg.get("args", [])
            if not name or not command:
                continue
            try:
                await mcp.connect(server_name=name, command=command, args=args)
                tools = await mcp.list_tools(server_name=name)
                self.react_executor.register_mcp_tools(name, tools)
                logger.info("MCP server %s connected — %d tools", name, len(tools))
            except Exception:
                logger.warning("Failed to connect MCP server %s", name, exc_info=True)

        # Log total tool availability for observability
        logger.info(
            "Tool availability: %d LAEE + %d MCP = %d total",
            self.react_executor.laee_tool_count,
            self.react_executor.mcp_tool_count,
            self.react_executor.laee_tool_count + self.react_executor.mcp_tool_count,
        )

    async def close(self) -> None:
        """Dispose DB engine and disconnect MCP servers on shutdown."""
        # Disconnect MCP servers
        if self.react_executor and self.react_executor.mcp_client:
            mcp = self.react_executor.mcp_client
            import contextlib

            for server in list(getattr(mcp, "connected_servers", [])):
                with contextlib.suppress(Exception):
                    await mcp.disconnect(server)

        if (self.settings.use_postgres or self.settings.use_sqlite) and hasattr(self, "_engine"):
            await self._engine.dispose()
