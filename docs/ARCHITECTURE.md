# Morphic-Agent Architecture

> Clean Architecture (4-layer) + TDD + Pydantic Strict Mode + OSS-First

---

## Layer Overview

```
Interface → Application → Domain ← Infrastructure
                                    (Dependency Inversion)
```

```
┌──────────────────────────────────────────────────────────────┐
│  interface/          Layer 4: Entry Points                    │
│  ├── api/            FastAPI routes, WebSocket handlers       │
│  └── cli/            typer CLI commands + rich formatting     │
├──────────────────────────────────────────────────────────────┤
│  application/        Layer 3: Use Cases                       │
│  ├── use_cases/      Orchestration of domain operations       │
│  └── dto/            Data Transfer Objects between layers     │
├──────────────────────────────────────────────────────────────┤
│  domain/             Layer 1: Pure Business Logic             │
│  ├── entities/       Pydantic models (strict=True)           │
│  ├── value_objects/  Enums, immutable types                   │
│  ├── ports/          ABC interfaces (Dependency Inversion)    │
│  └── services/       Pure domain services (no I/O)           │
├──────────────────────────────────────────────────────────────┤
│  infrastructure/     Layer 2: Port Implementations            │
│  ├── persistence/    SQLAlchemy ORM, pgvector, Neo4j         │
│  ├── llm/            LiteLLM, Ollama adapters                │
│  ├── local_execution/ LAEE tool implementations              │
│  └── memory/         mem0, vector DB adapters                │
├──────────────────────────────────────────────────────────────┤
│  shared/             Cross-cutting Concerns                   │
│  └── config.py       pydantic-settings (env vars)            │
├──────────────────────────────────────────────────────────────┤
│  tests/                                                       │
│  ├── unit/domain/    No DB, no I/O. Fast (0.03s for 67)     │
│  ├── unit/application/ Ports mocked, no DB                   │
│  ├── integration/    Docker Compose required                  │
│  └── e2e/            Full stack                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Dependency Rules

### Allowed

| From | To | Example |
|---|---|---|
| `interface/` | `application/` | API route calls use case |
| `application/` | `domain/` | Use case uses entity + port |
| `infrastructure/` | `domain/` | Adapter implements port ABC |
| Any layer | `shared/` | Config, logging |

### Forbidden

| From | To | Why |
|---|---|---|
| `domain/` | `infrastructure/` | Domain must be pure. No SQLAlchemy, no HTTP, no LiteLLM |
| `domain/` | `application/` | Domain has zero outward dependencies |
| `domain/` | `interface/` | Domain has zero outward dependencies |
| `application/` | `infrastructure/` | Use cases depend on ports (ABCs), not implementations |
| `interface/` | `infrastructure/` | Interface calls use cases, not adapters directly |

### Dependency Inversion in Practice

```python
# domain/ports/task_repository.py — defines the interface
class TaskRepository(ABC):
    @abstractmethod
    async def save(self, task: TaskEntity) -> None: ...

# infrastructure/persistence/pg_task_repository.py — implements it
class PgTaskRepository(TaskRepository):
    async def save(self, task: TaskEntity) -> None:
        # SQLAlchemy code here — domain doesn't know about this

# application/use_cases/create_task.py — depends on the port
class CreateTaskUseCase:
    def __init__(self, repo: TaskRepository):  # ABC, not PgTaskRepository
        self._repo = repo
```

---

## CLI + API: Dual Interface Design

Both CLI and API are first-class interfaces. They call the **same use cases** with zero logic duplication.

```
┌─────────────────────────────────────────────────────────┐
│                      interface/                          │
│                                                          │
│  ┌── api/ ──────────────┐  ┌── cli/ ──────────────────┐ │
│  │ FastAPI + WebSocket   │  │ typer + rich              │ │
│  │                       │  │                           │ │
│  │ POST /api/tasks  ─────┼──┼── morphic task create ───┤ │
│  │ GET  /api/cost   ─────┼──┼── morphic cost summary ──┤ │
│  │ GET  /api/models ─────┼──┼── morphic model list ────┤ │
│  └───────────────────────┘  └───────────────────────────┘ │
│              │                          │                  │
│              └──────────┬───────────────┘                  │
│                         ▼                                  │
│              application/use_cases/                        │
│              ├── create_task.py                            │
│              ├── cost_summary.py                           │
│              └── list_models.py                            │
└─────────────────────────────────────────────────────────┘
```

### CLI Architecture (Phase 2)

```
interface/cli/
├── main.py            # typer.Typer() app, entry point: `morphic`
├── commands/
│   ├── task.py        # morphic task {create|list|show|cancel}
│   ├── model.py       # morphic model {list|status|pull}
│   ├── cost.py        # morphic cost {summary|budget}
│   ├── memory.py      # morphic memory {search|stats}
│   └── exec.py        # morphic exec "..." (LAEE)
└── formatters.py      # rich-based tables, progress bars, syntax highlighting
```

### Why Both?

| Interface | Best For |
|---|---|
| **API + UI** | Visual task graph, real-time monitoring, non-technical users |
| **CLI** | Scriptable automation, CI/CD, power users, lightweight environments |

---

## OSS Dependency Map

Custom code is minimized. Every infrastructure component wraps an established OSS library.

### Infrastructure Layer — All OSS

| Component | OSS Library | What We Write |
|---|---|---|
| Task DAG | **LangGraph** | Wrapper + state definitions |
| LLM routing | **LiteLLM** | Routing logic + cost callbacks |
| Structured output | **Instructor** | Schema definitions only |
| Semantic memory | **mem0** | Hierarchy management |
| Vector search | **pgvector** | None (SQL queries) |
| Knowledge graph | **Neo4j** driver | Cypher query builder |
| ORM + migrations | **SQLAlchemy** + **Alembic** | Models + migration scripts |
| API framework | **FastAPI** | Route handlers |
| CLI framework | **typer** + **rich** | Command handlers + formatters |
| Browser automation | **Playwright** | Tool wrappers |
| File watching | **watchdog** | Event handlers |
| Scheduling | **APScheduler** | Job definitions |
| Process management | **psutil** | Read-only wrappers |
| Configuration | **pydantic-settings** | Settings class |
| Task queue | **Celery** + **Redis** | Task definitions |
| Logging | **structlog** | Config only |

### Domain Layer — Custom (Intentionally)

| Module | Why Custom |
|---|---|
| `domain/entities/*` | Business models are inherently project-specific |
| `domain/services/risk_assessor.py` | 40+ tool risk classification is domain logic |
| `domain/services/approval_engine.py` | 3×5 approval matrix is domain logic |
| `domain/value_objects/*` | Project-specific enums and types |
| `domain/ports/*` | Interface definitions are project-specific |

**Rule**: If something exists in PyPI/npm and covers 80%+ of the need, use it. Only write custom code for domain logic.

---

## Current File Map

```
morphic-agent/
├── domain/                          # Layer 1: Pure Business Logic
│   ├── entities/
│   │   ├── task.py                  # TaskEntity, SubTask (strict)
│   │   ├── execution.py            # Action, Observation, UndoAction (strict)
│   │   ├── memory.py               # MemoryEntry (strict)
│   │   └── cost.py                 # CostRecord (strict)
│   ├── value_objects/
│   │   ├── status.py               # TaskStatus, SubTaskStatus, ObservationStatus, MemoryType
│   │   ├── risk_level.py           # RiskLevel (5-tier IntEnum)
│   │   ├── approval_mode.py        # ApprovalMode (3-tier)
│   │   └── model_tier.py           # ModelTier, TaskType
│   ├── ports/
│   │   ├── task_repository.py      # TaskRepository ABC
│   │   ├── task_engine.py          # TaskEngine ABC (decompose + execute)
│   │   ├── llm_gateway.py          # LLMGateway ABC + LLMResponse
│   │   ├── local_executor.py       # LocalExecutor ABC (LAEE)
│   │   ├── audit_logger.py         # AuditLogger ABC
│   │   ├── memory_repository.py    # MemoryRepository ABC
│   │   └── cost_repository.py      # CostRepository ABC
│   └── services/
│       ├── risk_assessor.py        # 40+ tool risk mapping + escalation
│       └── approval_engine.py      # 3-mode × 5-risk approval matrix
│
├── application/                     # Layer 3: Use Cases
│   ├── use_cases/
│   │   ├── create_task.py          # CreateTaskUseCase (decompose + persist)
│   │   └── execute_task.py         # ExecuteTaskUseCase (run DAG + persist)
│   └── dto/                         # (stub — Sprint 1.4)
│
├── infrastructure/                  # Layer 2: Port Implementations
│   ├── persistence/
│   │   ├── database.py              # Async SQLAlchemy engine + session
│   │   └── models.py                # ORM models (separate from domain entities)
│   ├── llm/                         # Sprint 1.2: LLM Layer
│   │   ├── ollama_manager.py        # Ollama lifecycle (health, model pull, RAM recommend)
│   │   ├── litellm_gateway.py       # LLMGateway impl (LOCAL_FIRST routing + LiteLLM)
│   │   └── cost_tracker.py          # CostRepository wrapper + budget checking
│   ├── task_graph/                  # Sprint 1.3: Task Graph Engine
│   │   ├── state.py                 # AgentState TypedDict (LangGraph state)
│   │   ├── intent_analyzer.py       # LLM goal → subtask decomposition
│   │   └── engine.py                # LangGraphTaskEngine (DAG + parallel + retry)
│   └── local_execution/             # Sprint 1.3b: LAEE
│       ├── executor.py              # LocalExecutor (risk → approve → execute → audit)
│       ├── audit_log.py             # JsonlAuditLogger (append-only JSONL)
│       ├── undo_manager.py          # Stack-based undo for reversible ops
│       └── tools/
│           ├── shell_tools.py       # shell_exec, shell_background, shell_stream, shell_pipe
│           ├── fs_tools.py          # fs_read, fs_write, fs_edit, fs_delete, fs_move, fs_glob, fs_tree
│           ├── system_tools.py      # process_list, process_kill, resource_info, clipboard, notify
│           └── dev_tools.py         # dev_git, dev_docker, dev_pkg_install, dev_env_setup
│
├── interface/                       # Layer 4: Entry Points
│   ├── api/                         # (stub — Sprint 1.6)
│   └── cli/                         # (stub — Phase 2)
│
├── shared/
│   └── config.py                    # pydantic-settings (all env vars)
│
├── tests/
│   └── unit/
│       ├── domain/
│       │   ├── test_entities.py         # 37 tests (16 behavior + 21 strict validation)
│       │   ├── test_risk_assessor.py    # 19 tests (5 risk tiers + escalation)
│       │   └── test_approval_engine.py  # 11 tests (3 modes × risk levels)
│       ├── application/
│       │   ├── test_create_task.py      # 5 tests (decompose, save, status, deps)
│       │   └── test_execute_task.py     # 6 tests (success, fallback, failed, cost)
│       └── infrastructure/
│           ├── test_ollama_manager.py   # 14 tests (health, list, ensure, recommend)
│           ├── test_cost_tracker.py     # 13 tests (record, queries, budget)
│           ├── test_litellm_gateway.py  # 22 tests (route, complete, available, model check)
│           ├── test_intent_analyzer.py  # 6 tests (decompose, deps, JSON parse)
│           ├── test_task_graph_engine.py # 9 tests (parallel, retry, cascade)
│           └── test_local_execution.py  # 35 tests (8 completion criteria)
│   └── integration/
│       └── test_live_smoke.py           # 10 tests (real Ollama + real filesystem)
│
├── migrations/                      # Alembic async migrations
├── docker-compose.yml               # PostgreSQL+pgvector, Redis, Neo4j
├── pyproject.toml                   # uv project, ruff, pytest, mypy
└── CLAUDE.md                        # Project constitution
```

---

## Domain Layer Design Principles

### 1. Entities are Pure Pydantic

- `ConfigDict(strict=True)` — no type coercion
- `ConfigDict(validate_assignment=True)` — validates on attribute mutation
- All status fields use `str, Enum` value objects (not raw strings)
- Numeric fields have `Field(ge=0)` constraints
- String fields have `Field(min_length=1)` where empty is invalid

### 2. Value Objects are Immutable Enums

| Value Object | Type | Values |
|---|---|---|
| `TaskStatus` | `str, Enum` | pending, running, success, failed, fallback |
| `SubTaskStatus` | `str, Enum` | pending, running, success, failed |
| `ObservationStatus` | `str, Enum` | success, error, denied, timeout |
| `MemoryType` | `str, Enum` | l1_active, l2_semantic, l3_facts, l4_cold |
| `RiskLevel` | `IntEnum` | SAFE(0), LOW(1), MEDIUM(2), HIGH(3), CRITICAL(4) |
| `ApprovalMode` | `str, Enum` | full-auto, confirm-destructive, confirm-all |
| `ModelTier` | `str, Enum` | free, low, medium, high |
| `TaskType` | `str, Enum` | simple_qa, code_generation, etc. |

### 3. Ports Define Boundaries

Every external dependency (DB, LLM, filesystem) is accessed through an ABC port:

```
domain/ports/
├── task_repository.py      # CRUD for tasks
├── llm_gateway.py          # LLM completions
├── local_executor.py       # LAEE tool execution
├── audit_logger.py         # Append-only audit log
├── memory_repository.py    # Semantic memory CRUD
└── cost_repository.py      # Cost tracking queries
```

### 4. Services are Pure Functions

Domain services (`risk_assessor.py`, `approval_engine.py`) have:
- No constructor dependencies (no injected ports)
- No I/O operations
- Deterministic output for given input
- 100% testable without mocks

---

## Infrastructure Layer Notes

### ORM ≠ Domain Entity

Domain entities (`domain/entities/`) and ORM models (`infrastructure/persistence/models.py`) are deliberately separate:

| Domain Entity | ORM Model | Why Separate |
|---|---|---|
| `TaskEntity` (Pydantic) | `TaskModel` (SQLAlchemy) | Domain stays pure. ORM concerns don't leak into business logic |
| `MemoryEntry` (Pydantic) | `MemoryModel` (SQLAlchemy) | Different serialization needs |
| `CostRecord` (Pydantic) | `CostLogModel` (SQLAlchemy) | ORM has DB-specific features |

Mapping between domain entities and ORM models happens in repository implementations (infrastructure layer).

---

## Testing Strategy

| Test Type | Location | Dependencies | Speed | What It Tests |
|---|---|---|---|---|
| **Unit/Domain** | `tests/unit/domain/` | None | ~0.03s (67 tests) | Entities, value objects, services |
| **Unit/Application** | `tests/unit/application/` | Mocked ports | Fast (11 tests) | Use case orchestration |
| **Unit/Infra** | `tests/unit/infrastructure/` | Mocked ports | ~1.0s (99 tests) | LLM gateway, cost, task graph, LAEE |
| **Integration** | `tests/integration/` | Ollama running | ~18s (10 tests) | Real LLM inference, real filesystem |
| **E2E** | `tests/e2e/` | Full stack | Slowest | API/CLI → Use Case → DB round-trips |

### TDD Process

```
1. Red:      Write test that fails
2. Green:    Write minimum code to pass
3. Refactor: Clean up while tests protect

Current: 177 unit tests (1.30s) + 10 integration tests (17.79s), 100% pass
Default model: qwen3-coder:30b (thinking mode disabled via extra_body)
```
