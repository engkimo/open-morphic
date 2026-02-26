# Morphic-Agent Architecture

> Clean Architecture (4-layer) + TDD + Pydantic Strict Mode + OSS-First
>
> **Phase 1 Foundation: COMPLETE** (2026-02-25) — 7/7 sprints done
> **Phase 2 Parallel & Planning + CLI: COMPLETE** (2026-02-26) — All 6 sprints (2-A through 2-F) + CLI v1
> **Phase 3 Sprint 3.1–3.3: COMPLETE** (2026-02-26) — SemanticFingerprint LSH → ContextZipper v2 → ForgettingCurve — 506 unit tests + 26 integration tests

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
| Embedding | **Ollama** `/api/embed` | OllamaEmbeddingAdapter (Sprint 3.1) |
| LSH bucketing | **numpy** | SemanticFingerprint + SemanticBucketStore (Sprint 3.1) |
| Vector search | **pgvector** | Cosine distance queries (Sprint 3.1) |
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
| `domain/services/semantic_fingerprint.py` | LSH hash + cosine similarity is pure math (Sprint 3.1) |
| `domain/services/forgetting_curve.py` | Ebbinghaus retention scoring R=e^(-t/S) is pure math (Sprint 3.3) |
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
│   │   ├── cost.py                 # CostRecord (strict)
│   │   └── plan.py                 # PlanStep, ExecutionPlan (strict)
│   ├── value_objects/
│   │   ├── status.py               # TaskStatus, SubTaskStatus, ObservationStatus, MemoryType, PlanStatus
│   │   ├── risk_level.py           # RiskLevel (5-tier IntEnum)
│   │   ├── approval_mode.py        # ApprovalMode (3-tier)
│   │   └── model_tier.py           # ModelTier, TaskType
│   ├── ports/
│   │   ├── task_repository.py      # TaskRepository ABC
│   │   ├── task_engine.py          # TaskEngine ABC (decompose + execute)
│   │   ├── llm_gateway.py          # LLMGateway ABC + LLMResponse
│   │   ├── local_executor.py       # LocalExecutor ABC (LAEE)
│   │   ├── audit_logger.py         # AuditLogger ABC
│   │   ├── memory_repository.py    # MemoryRepository ABC (+ list_by_type, Sprint 3.3)
│   │   ├── cost_repository.py      # CostRepository ABC
│   │   ├── plan_repository.py      # PlanRepository ABC
│   │   └── embedding.py            # EmbeddingPort ABC (Sprint 3.1)
│   └── services/
│       ├── risk_assessor.py        # 40+ tool risk mapping + escalation
│       ├── approval_engine.py      # 3-mode × 5-risk approval matrix
│       ├── semantic_fingerprint.py # LSH hash + cosine similarity (Sprint 3.1)
│       └── forgetting_curve.py    # Ebbinghaus retention scoring R=e^(-t/S) (Sprint 3.3)
│
├── application/                     # Layer 3: Use Cases
│   ├── use_cases/
│   │   ├── create_task.py          # CreateTaskUseCase (decompose + persist)
│   │   ├── execute_task.py         # ExecuteTaskUseCase (run DAG + persist)
│   │   ├── cost_estimator.py       # CostEstimator (per-model token pricing)
│   │   ├── interactive_plan.py     # InteractivePlanUseCase (create/approve/reject)
│   │   └── background_planner.py   # BackgroundPlannerUseCase (advisory monitoring)
│   └── dto/                         # (stub — Sprint 1.4)
│
├── infrastructure/                  # Layer 2: Port Implementations
│   ├── persistence/
│   │   ├── database.py              # Async SQLAlchemy engine + session
│   │   ├── models.py                # ORM models (Vector(384) for embedding)
│   │   ├── in_memory.py             # InMemory repos (optional embedding_port)
│   │   ├── pg_task_repository.py    # PgTaskRepository (TaskEntity ↔ TaskModel)
│   │   ├── pg_cost_repository.py    # PgCostRepository (SQL aggregation)
│   │   ├── pg_memory_repository.py  # PgMemoryRepository (pgvector cosine + ILIKE fallback)
│   │   └── pg_plan_repository.py    # PgPlanRepository (ExecutionPlan ↔ PlanModel)
│   ├── llm/                         # Sprint 1.2: LLM Layer
│   │   ├── ollama_manager.py        # Ollama lifecycle (health, model pull, RAM recommend)
│   │   ├── litellm_gateway.py       # LLMGateway impl (LOCAL_FIRST routing + LiteLLM)
│   │   └── cost_tracker.py          # CostRepository wrapper + budget checking
│   ├── task_graph/                  # Sprint 1.3: Task Graph Engine
│   │   ├── state.py                 # AgentState TypedDict (LangGraph state)
│   │   ├── intent_analyzer.py       # LLM goal → subtask decomposition
│   │   └── engine.py                # LangGraphTaskEngine (DAG + parallel + retry)
│   ├── queue/                       # Sprint 2-B: Celery + Redis
│   │   ├── celery_app.py            # Celery app factory (Redis broker/backend)
│   │   └── tasks.py                 # execute_task_worker Celery task
│   ├── local_execution/             # Sprint 1.3b + 2-E: LAEE
│   │   ├── executor.py              # LocalExecutor (risk → approve → execute → audit)
│   │   ├── audit_log.py             # JsonlAuditLogger (append-only JSONL)
│   │   ├── undo_manager.py          # Stack-based undo for reversible ops
│   │   └── tools/
│   │       ├── shell_tools.py       # shell_exec, shell_background, shell_stream, shell_pipe
│   │       ├── fs_tools.py          # fs_read, fs_write, fs_edit, fs_delete, fs_move, fs_glob, fs_tree
│   │       ├── system_tools.py      # process_list, process_kill, resource_info, clipboard, notify
│   │       ├── dev_tools.py         # dev_git, dev_docker, dev_pkg_install, dev_env_setup
│   │       ├── browser_tools.py     # navigate, click, type, screenshot, extract, pdf (Playwright)
│   │       ├── gui_tools.py         # applescript, open_app, screenshot_ocr, accessibility (macOS)
│   │       └── cron_tools.py        # schedule, once, list, cancel (APScheduler)
│   └── memory/                      # Sprint 1.5 + 3.1–3.3: Semantic Memory
│       ├── memory_hierarchy.py      # L1-L4 unified manager (deque→repo→KG→cold) + compact()
│       ├── context_zipper.py        # Query-adaptive compression (v2: async, semantic, Sprint 3.2)
│       ├── forgetting_curve.py      # ForgettingCurveManager + CompactResult (Sprint 3.3)
│       ├── knowledge_graph.py       # Neo4j adapter (L3)
│       ├── semantic_fingerprint.py  # SemanticBucketStore (LSH bucketing, Sprint 3.1)
│       └── embedding_adapters.py    # OllamaEmbeddingAdapter (POST /api/embed, Sprint 3.1)
│
├── interface/                       # Layer 4: Entry Points
│   ├── api/                         # Sprint 1.6: FastAPI + WebSocket
│   │   ├── main.py                  # create_app() factory + lifespan + CORS
│   │   ├── container.py             # AppContainer DI (Settings → repos → use cases)
│   │   ├── schemas.py               # 14 Pydantic request/response models
│   │   ├── websocket.py             # /ws/tasks/{id} (poll + delta-only sends + recommendations)
│   │   └── routes/
│   │       ├── tasks.py             # POST, GET, GET/{id}, DELETE /api/tasks (+ Celery dispatch)
│   │       ├── plans.py             # POST, GET, approve, reject /api/plans
│   │       ├── models.py            # GET /api/models, GET /api/models/status
│   │       ├── cost.py              # GET /api/cost, GET /api/cost/logs
│   │       └── memory.py            # GET /api/memory/search?q=
│   └── cli/                         # Sprint 2.9-2.11: typer + rich
│       ├── main.py                  # typer app, _get_container() lazy singleton, _run() async bridge
│       ├── formatters.py            # Rich tables, trees, status styles (all output isolated here)
│       └── commands/
│           ├── task.py              # morphic task {create|list|show|cancel}
│           ├── model.py             # morphic model {list|status|pull}
│           ├── cost.py              # morphic cost {summary|budget}
│           └── plan.py              # morphic plan {create|list|show|approve|reject}
│
├── shared/
│   └── config.py                    # pydantic-settings (all env vars)
│
├── ui/                              # Sprint 1.6 + 2-F: Next.js 15 (bun, Tailwind CSS 4, @xyflow/react)
│   ├── lib/
│   │   ├── theme.ts                 # morphicAgentTheme design tokens
│   │   └── api.ts                   # Typed fetch wrappers + WebSocket + Plan API
│   ├── app/
│   │   ├── layout.tsx               # Dark theme root layout (Geist font)
│   │   ├── globals.css              # CSS variables matching design spec
│   │   ├── page.tsx                 # Dashboard (Execute/Plan toggle + GoalInput + TaskList)
│   │   ├── tasks/[id]/page.tsx      # Task detail + TaskGraph with live WebSocket
│   │   └── plans/[id]/page.tsx      # Plan review page (approve/reject)
│   └── components/
│       ├── GoalInput.tsx            # Textarea + Execute button (Enter to submit)
│       ├── TaskList.tsx             # Task cards with status icons + FREE badge
│       ├── TaskDetail.tsx           # Subtask tree with status dots
│       ├── TaskGraph.tsx            # React Flow DAG visualizer (SubTaskNode + status colors)
│       ├── PlanningView.tsx         # Plan steps table + cost display + approve/reject
│       ├── CostMeter.tsx            # Budget bar + daily/monthly/local stats
│       └── ModelStatus.tsx          # Ollama status dot + model list
│
├── tests/
│   └── unit/
│       ├── domain/
│       │   ├── test_entities.py             # 37 tests (16 behavior + 21 strict validation)
│       │   ├── test_risk_assessor.py        # 19 tests (5 risk tiers + escalation)
│       │   ├── test_approval_engine.py      # 11 tests (3 modes × risk levels)
│       │   ├── test_semantic_fingerprint.py # 11 tests (LSH hash, cosine sim, Sprint 3.1)
│       │   └── test_forgetting_curve.py   # 14 tests (retention score, expiry, hours_since, Sprint 3.3)
│       ├── application/
│       │   ├── test_create_task.py      # 5 tests (decompose, save, status, deps)
│       │   └── test_execute_task.py     # 6 tests (success, fallback, failed, cost)
│       ├── infrastructure/
│       │   ├── test_ollama_manager.py   # 14 tests (health, list, ensure, recommend)
│       │   ├── test_cost_tracker.py     # 13 tests (record, queries, budget)
│       │   ├── test_litellm_gateway.py  # 24 tests (route, complete, available, O-series temp)
│       │   ├── test_intent_analyzer.py  # 6 tests (decompose, deps, JSON parse)
│       │   ├── test_task_graph_engine.py # 9 tests (parallel, retry, cascade)
│       │   ├── test_local_execution.py  # 35 tests (8 completion criteria)
│       │   ├── test_failure_recovery.py # 7 tests (retry, cascade, partial, persistence)
│       │   ├── test_memory.py           # 36 tests (hierarchy, zipper, knowledge graph)
│       │   ├── test_semantic_search.py  # 20 tests (BucketStore, OllamaAdapter, vector search, Sprint 3.1)
│       │   └── test_forgetting_curve.py # 17 tests (compact, promote, score, list_by_type, Sprint 3.3)
│       └── interface/
│           ├── test_api.py              # 22 tests (CRUD, WebSocket, CORS, models, cost, memory)
│           ├── test_api_e2e.py          # 12 tests (HTTP round-trip: POST→execute→GET→verify)
│           └── test_cli.py              # 20 tests (3 foundation + 9 task + 5 model + 3 cost)
│   └── integration/
│       ├── test_live_smoke.py           # 10 tests (real Ollama + real filesystem)
│       ├── test_cloud_llm.py            # 11 tests (Anthropic + OpenAI + Gemini + cost + routing)
│       └── test_e2e_pipeline.py         # 5 tests (Goal → Decompose → DAG → Result)
│
├── migrations/                      # Alembic async migrations (001 initial + 002 embedding)
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
| `PlanStatus` | `str, Enum` | proposed, approved, rejected, executing, completed |
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
├── cost_repository.py      # Cost tracking queries
└── embedding.py            # Text-to-vector embedding (Sprint 3.1)
```

### 4. Services are Pure Functions

Domain services (`risk_assessor.py`, `approval_engine.py`, `semantic_fingerprint.py`, `forgetting_curve.py`) have:
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
| **Unit/Domain** | `tests/unit/domain/` | None | ~0.03s (101 tests) | Entities, value objects, services, LSH fingerprint, forgetting curve |
| **Unit/Application** | `tests/unit/application/` | Mocked ports | Fast (46 tests) | Use case orchestration, cost estimator, planning |
| **Unit/Infra** | `tests/unit/infrastructure/` | Mocked ports | ~1.2s (301 tests) | LLM gateway, cost, task graph, LAEE, memory, PG repos, Celery, browser/gui/cron, semantic search, forgetting curve |
| **Unit/Interface** | `tests/unit/interface/` | Mock container | ~1.4s (58 tests) | API, WebSocket, CORS, CLI commands, plan endpoints |
| **Integration** | `tests/integration/` | Ollama running | ~18s (10 tests) | Real LLM inference, real filesystem |
| **E2E** | `tests/e2e/` | Full stack | Slowest | API/CLI → Use Case → DB round-trips |

### TDD Process

```
1. Red:      Write test that fails
2. Green:    Write minimum code to pass
3. Refactor: Clean up while tests protect

Current: 506 unit tests (2.8s) + 26 integration tests (10+11+5), 100% pass
Lint: ruff check 0 errors, ruff format 150 files clean
Default model: qwen3-coder:30b (thinking mode disabled via extra_body)
Cloud providers verified: Anthropic (Haiku/Sonnet), OpenAI (o4-mini/o3), Gemini (3-flash/3-pro)
```
