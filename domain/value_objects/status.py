"""Status value objects — strict Enum types for all domain status fields."""

from enum import Enum


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    FALLBACK = "fallback"


class SubTaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DEGRADED = "degraded"


class ObservationStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    DENIED = "denied"
    TIMEOUT = "timeout"


class MemoryType(str, Enum):
    L1_ACTIVE = "l1_active"
    L2_SEMANTIC = "l2_semantic"
    L3_FACTS = "l3_facts"
    L4_COLD = "l4_cold"


class PlanStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
