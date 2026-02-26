# Morphic-Agent Architecture

> Clean Architecture (4-layer) + TDD + Pydantic Strict Mode + OSS-First
>
> **Phase 1 Foundation: COMPLETE** (2026-02-25) — 7/7 sprints done
> **Phase 2 Parallel & Planning + CLI: COMPLETE** (2026-02-26) — All 6 sprints (2-A through 2-F) + CLI v1
> **Phase 3 Semantic Memory & Context Bridge: COMPLETE** (2026-02-26) — Week 5: SemanticFingerprint LSH → ContextZipper v2 → ForgettingCurve → DeltaEncoder → HierarchicalSummarizer | Week 6: Context Bridge → MCP Server → MCP Client → L1-L4 Integration — 725 tests (699 unit + 26 integration)

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
| MCP server/client | **mcp** (FastMCP) | 6 tools + 2 resources, client adapter |
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
| `domain/services/delta_encoder.py` | Git-style delta hashing/reconstruction/diffing is pure logic (Sprint 3.4) |
| `domain/services/hierarchical_summarizer.py` | 4-level tree compression: extractive summarization + level selection is pure logic (Sprint 3.5) |
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
│   │   ├── delta.py                # Delta — Git-style state change record (strict, Sprint 3.4)
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
│   │   ├── embedding.py            # EmbeddingPort ABC (Sprint 3.1)
│   │   └── mcp_client.py           # MCPClientPort ABC (Sprint 3.8)
│   └── services/
│       ├── risk_assessor.py        # 40+ tool risk mapping + escalation
│       ├── approval_engine.py      # 3-mode × 5-risk approval matrix
│       ├── semantic_fingerprint.py # LSH hash + cosine similarity (Sprint 3.1)
│       ├── forgetting_curve.py    # Ebbinghaus retention scoring R=e^(-t/S) (Sprint 3.3)
│       ├── delta_encoder.py      # hash_changes, reconstruct, create_delta, compute_diff (Sprint 3.4)
│       └── hierarchical_summarizer.py # estimate_tokens, split_sentences, extract_summary, build_hierarchy, select_level (Sprint 3.5)
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
│   ├── memory/                      # Sprint 1.5 + 3.1–3.5: Semantic Memory
│   │   ├── memory_hierarchy.py      # L1-L4 unified manager + compact() + record_delta/get_state + summarize_entry/retrieve_at_depth
│   │   ├── context_zipper.py        # Query-adaptive compression (v2: async, semantic, Sprint 3.2)
│   │   ├── forgetting_curve.py      # ForgettingCurveManager + CompactResult (Sprint 3.3)
│   │   ├── delta_encoder.py         # DeltaEncoderManager + DeltaRecordResult (Sprint 3.4)
│   │   ├── hierarchical_summarizer.py # HierarchicalSummaryManager + SummarizeResult (Sprint 3.5)
│   │   ├── context_bridge.py        # ContextBridge + ExportResult — 4 platform formatters (Sprint 3.6)
│   │   ├── knowledge_graph.py       # Neo4j adapter (L3)
│   │   ├── semantic_fingerprint.py  # SemanticBucketStore (LSH bucketing, Sprint 3.1)
│   │   └── embedding_adapters.py    # OllamaEmbeddingAdapter (POST /api/embed, Sprint 3.1)
│   └── mcp/                         # Sprint 3.7–3.8: Model Context Protocol
│       ├── server.py                # create_mcp_server() — FastMCP, 6 tools + 2 resources
│       └── client.py               # MCPClient, MCPToolAdapter, discover_and_register
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
│   │       └── memory.py            # GET /api/memory/search?q= + GET /api/memory/export?platform=
│   └── cli/                         # Sprint 2.9-2.11: typer + rich
│       ├── main.py                  # typer app, _get_container() lazy singleton, _run() async bridge
│       ├── formatters.py            # Rich tables, trees, status styles (all output isolated here)
│       └── commands/
│           ├── task.py              # morphic task {create|list|show|cancel}
│           ├── model.py             # morphic model {list|status|pull}
│           ├── cost.py              # morphic cost {summary|budget}
│           ├── plan.py              # morphic plan {create|list|show|approve|reject}
│           └── mcp.py               # morphic mcp server (stdio/streamable-http)
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
│       │   ├── test_forgetting_curve.py   # 14 tests (retention score, expiry, hours_since, Sprint 3.3)
│       │   ├── test_delta_encoder.py     # 34 tests (hash, reconstruct, diff, entity validation, Sprint 3.4)
│       │   └── test_hierarchical_summarizer.py # 27 tests (tokens, sentences, extract, hierarchy, select, depth, Sprint 3.5)
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
│       │   ├── test_forgetting_curve.py # 17 tests (compact, promote, score, list_by_type, Sprint 3.3)
│       │   ├── test_delta_encoder.py   # 27 tests (record, get_state, history, topics, roundtrip, Sprint 3.4)
│       │   ├── test_hierarchical_summarizer.py # 24 tests (extractive, LLM, get_summary, retrieve_at_depth, Sprint 3.5)
│       │   ├── test_context_bridge.py  # 25 tests (4 platforms, export_all, budget, graceful degradation, Sprint 3.6)
│       │   ├── test_mcp_server.py      # 19 tests (factory, 6 tools, 2 resources, degradation, Sprint 3.7)
│       │   └── test_mcp_client.py      # 21 tests (port, connect, tools, resources, adapter, discover, Sprint 3.8)
│       └── interface/
│           ├── test_api.py              # 22 tests (CRUD, WebSocket, CORS, models, cost, memory)
│           ├── test_api_e2e.py          # 12 tests (HTTP round-trip: POST→execute→GET→verify)
│           └── test_cli.py              # 20 tests (3 foundation + 9 task + 5 model + 3 cost)
│   └── integration/
│       ├── test_live_smoke.py           # 10 tests (real Ollama + real filesystem)
│       ├── test_cloud_llm.py            # 11 tests (Anthropic + OpenAI + Gemini + cost + routing)
│       ├── test_e2e_pipeline.py         # 5 tests (Goal → Decompose → DAG → Result)
│       └── test_memory_hierarchy_full.py # 16 tests (L1-L4 full lifecycle, compression interplay, edge cases, cross-component, Sprint 3.10)
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
├── embedding.py            # Text-to-vector embedding (Sprint 3.1)
└── mcp_client.py           # MCP client connections (Sprint 3.8)
```

### 4. Services are Pure Functions

Domain services (`risk_assessor.py`, `approval_engine.py`, `semantic_fingerprint.py`, `forgetting_curve.py`, `delta_encoder.py`, `hierarchical_summarizer.py`) have:
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

## Context Bridge & MCP (Phase 3, Week 6)

### Cross-Platform Context Bridge (Sprint 3.6)

Exports Morphic-Agent memory/context in platform-specific formats. Infrastructure-only (no domain port).

```
ContextBridge
├── export(platform, query, max_tokens) → ExportResult
└── export_all(query, max_tokens)       → list[ExportResult]
    │
    ├── _gather_context()  → compose MemoryHierarchy + ContextZipper + DeltaEncoder
    └── _format_{platform}()
        ├── claude_code  → CLAUDE.md markdown (## Context / ## Current State / ## Recent Memory)
        ├── chatgpt      → Custom Instructions (What to know / How to respond)
        ├── cursor        → .cursorrules numbered rules + project context
        └── gemini        → <morphic-context> XML tags with structured sections
```

All ports optional — graceful degradation when memory/zipper/delta unavailable.

### MCP Server (Sprint 3.7)

Exposes Morphic-Agent memory as MCP tools/resources via FastMCP (`mcp[cli]>=1.25,<2`).

```
create_mcp_server(container) → FastMCP("morphic-agent")

Tools (6):
├── memory_search    → container.memory.retrieve()
├── memory_add       → container.memory.add()
├── context_compress → container.context_zipper.compress()
├── delta_get_state  → container.delta_encoder.get_state()
├── delta_record     → container.delta_encoder.record()
└── context_export   → container.context_bridge.export()

Resources (2):
├── memory://topics          → delta_encoder.list_topics()
└── memory://state/{topic}   → delta_encoder.get_state(topic)
```

CLI: `morphic mcp server [--transport stdio|streamable-http] [--port 8100]`

### MCP Client (Sprint 3.8)

Connects to external MCP servers, discovers tools, adapts them for LAEE.

```
MCPClientPort (domain ABC)
    │
    └── MCPClient (infrastructure)
        ├── connect(name, command, args)  → stdio ClientSession
        ├── list_tools(server)            → tool specs
        ├── call_tool(server, tool, args) → result
        └── disconnect(server)

MCPToolAdapter
    wraps MCP tool as callable with prefix: mcp_{server}_{tool}

discover_and_register(client, configs) → list[MCPToolAdapter]
    batch connect + list tools + create adapters
```

---

## Testing Strategy

| Test Type | Location | Dependencies | Speed | What It Tests |
|---|---|---|---|---|
| **Unit/Domain** | `tests/unit/domain/` | None | ~0.03s (162 tests) | Entities, value objects, services, LSH fingerprint, forgetting curve, delta encoder, hierarchical summarizer |
| **Unit/Application** | `tests/unit/application/` | Mocked ports | Fast (46 tests) | Use case orchestration, cost estimator, planning |
| **Unit/Infra** | `tests/unit/infrastructure/` | Mocked ports | ~1.2s (417 tests) | LLM gateway, cost, task graph, LAEE, memory, PG repos, Celery, browser/gui/cron, semantic search, forgetting curve, delta encoder, hierarchical summarizer, context bridge, MCP server/client |
| **Unit/Interface** | `tests/unit/interface/` | Mock container | ~1.4s (58 tests) | API, WebSocket, CORS, CLI commands, plan endpoints |
| **Integration** | `tests/integration/` | Ollama running | ~18s (26 tests) | Real LLM inference, real filesystem, L1-L4 memory hierarchy |
| **E2E** | `tests/e2e/` | Full stack | Slowest | API/CLI → Use Case → DB round-trips |

### TDD Process

```
1. Red:      Write test that fails
2. Green:    Write minimum code to pass
3. Refactor: Clean up while tests protect

Current: 699 unit tests + 26 integration tests = 725 total, 100% pass
Lint: ruff check 0 errors, ruff format 150 files clean
Default model: qwen3-coder:30b (thinking mode disabled via extra_body)
Cloud providers verified: Anthropic (Haiku/Sonnet), OpenAI (o4-mini/o3), Gemini (3-flash/3-pro)
```
