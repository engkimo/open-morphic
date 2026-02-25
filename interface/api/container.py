"""DI Container — wires all dependencies for the FastAPI application.

Single object stored on app.state.container. Swappable for testing.
"""

from __future__ import annotations

from application.use_cases.create_task import CreateTaskUseCase
from application.use_cases.execute_task import ExecuteTaskUseCase
from infrastructure.llm.cost_tracker import CostTracker
from infrastructure.llm.litellm_gateway import LiteLLMGateway
from infrastructure.llm.ollama_manager import OllamaManager
from infrastructure.memory.memory_hierarchy import MemoryHierarchy
from infrastructure.persistence.in_memory import (
    InMemoryCostRepository,
    InMemoryMemoryRepository,
    InMemoryTaskRepository,
)
from infrastructure.task_graph.engine import LangGraphTaskEngine
from infrastructure.task_graph.intent_analyzer import IntentAnalyzer
from shared.config import Settings


class AppContainer:
    """Composes all dependencies. Created once at app startup."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

        # Repositories (in-memory for Phase 1)
        self.task_repo = InMemoryTaskRepository()
        self.cost_repo = InMemoryCostRepository()
        self.memory_repo = InMemoryMemoryRepository()

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

        # Memory
        self.memory = MemoryHierarchy(memory_repo=self.memory_repo)
