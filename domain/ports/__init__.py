"""Ports — Abstract interfaces for Dependency Inversion.

Domain defines WHAT it needs. Infrastructure provides HOW.
Dependencies always point inward: Infrastructure → Application → Domain.
"""

from domain.ports.audit_logger import AuditLogger
from domain.ports.cost_repository import CostRepository
from domain.ports.embedding import EmbeddingPort
from domain.ports.llm_gateway import LLMGateway
from domain.ports.local_executor import LocalExecutorPort
from domain.ports.memory_repository import MemoryRepository
from domain.ports.task_repository import TaskRepository

__all__ = [
    "AuditLogger",
    "CostRepository",
    "EmbeddingPort",
    "LLMGateway",
    "LocalExecutorPort",
    "MemoryRepository",
    "TaskRepository",
]
