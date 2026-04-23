"""Ports — Abstract interfaces for Dependency Inversion.

Domain defines WHAT it needs. Infrastructure provides HOW.
Dependencies always point inward: Infrastructure → Application → Domain.
"""

from domain.ports.a2a_broker import A2AMessageBroker
from domain.ports.agent_affinity_repository import AgentAffinityRepository
from domain.ports.agent_engine import (
    AgentEngineCapabilities,
    AgentEnginePort,
    AgentEngineResult,
)
from domain.ports.agent_registry import AgentRegistryPort
from domain.ports.audit_logger import AuditLogger
from domain.ports.cost_repository import CostRepository
from domain.ports.embedding import EmbeddingPort
from domain.ports.engine_cost_recorder import EngineCostRecorderPort
from domain.ports.execution_record_repository import (
    ExecutionRecordRepository,
    ExecutionStats,
)
from domain.ports.fractal_learning_repository import FractalLearningRepository
from domain.ports.insight_extractor import ExtractedInsight, InsightExtractorPort
from domain.ports.llm_gateway import LLMGateway
from domain.ports.local_executor import LocalExecutorPort
from domain.ports.mcp_client import MCPClientPort
from domain.ports.memory_repository import MemoryRepository
from domain.ports.ollama_manager import OllamaManagerPort
from domain.ports.plan_evaluator import PlanEvaluatorPort
from domain.ports.planner import PlannerPort
from domain.ports.result_evaluator import ResultEvaluatorPort
from domain.ports.shared_task_state_repository import SharedTaskStateRepository
from domain.ports.strategy_repository import StrategyRepository
from domain.ports.task_repository import TaskRepository
from domain.ports.tool_installer import InstallResult, ToolInstallerPort
from domain.ports.tool_registry import ToolRegistryPort, ToolSearchResult

__all__ = [
    "A2AMessageBroker",
    "AgentAffinityRepository",
    "AgentRegistryPort",
    "AgentEngineCapabilities",
    "AgentEnginePort",
    "AgentEngineResult",
    "AuditLogger",
    "CostRepository",
    "EmbeddingPort",
    "EngineCostRecorderPort",
    "ExecutionRecordRepository",
    "ExecutionStats",
    "FractalLearningRepository",
    "ExtractedInsight",
    "InsightExtractorPort",
    "InstallResult",
    "LLMGateway",
    "LocalExecutorPort",
    "MCPClientPort",
    "MemoryRepository",
    "OllamaManagerPort",
    "PlanEvaluatorPort",
    "PlannerPort",
    "ResultEvaluatorPort",
    "SharedTaskStateRepository",
    "StrategyRepository",
    "TaskRepository",
    "ToolInstallerPort",
    "ToolRegistryPort",
    "ToolSearchResult",
]
