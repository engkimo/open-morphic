"""DI Container — wires all dependencies for the FastAPI application.

Single object stored on app.state.container. Swappable for testing.
"""

from __future__ import annotations

import logging

from application.use_cases.background_planner import BackgroundPlannerUseCase
from application.use_cases.cost_estimator import CostEstimator
from application.use_cases.create_task import CreateTaskUseCase
from application.use_cases.execute_task import ExecuteTaskUseCase
from application.use_cases.interactive_plan import InteractivePlanUseCase
from domain.ports.cost_repository import CostRepository
from domain.ports.embedding import EmbeddingPort
from domain.ports.memory_repository import MemoryRepository
from domain.ports.plan_repository import PlanRepository
from domain.ports.task_repository import TaskRepository
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.litellm_gateway import LiteLLMGateway
from infrastructure.llm.ollama_manager import OllamaManager
from infrastructure.memory.context_zipper import ContextZipper
from infrastructure.memory.forgetting_curve import ForgettingCurveManager
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
        self.execute_task = ExecuteTaskUseCase(
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
