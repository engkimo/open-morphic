# Morphic-Agent Technical Decisions

> Record the rationale behind design decisions. Enable future traceability of "why we chose this."

---

## TD-001: Storage Unification — pgvector + Redis (queue) + Neo4j

**Date**: 2026-02-24
**Status**: Accepted

### Decision

Unify Phase 1 storage backends into three services:

| Service | Role | Rationale |
|---|---|---|
| **PostgreSQL 16 + pgvector** | Main DB + vector search | Relational data and vector search in one service. No Qdrant needed |
| **Redis 7** | Task queue (Celery broker/backend) | Queue-only. Not used as general cache |
| **Neo4j 5 Community** | L3 Knowledge Graph | Graph traversal for entities/relations. Cypher queries, ACID, persistence |

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| Qdrant (vector DB) | pgvector sufficient for Phase 1 scale. Fewer services = lower operational cost |
| Redis as general cache | Prevents role bloat. KV-Cache optimization done at LLM layer (LiteLLM disk cache) |
| NetworkX (in-memory graph) | No persistence. Lost on process restart. Neo4j has persistence + query language |
| SQLite | Poor concurrent access. Not suitable for async multi-worker execution |

### Risks and Mitigations

- **pgvector search accuracy**: No issue at Phase 1 scale (~100K vectors). Re-evaluate Qdrant migration at Phase 3
- **Neo4j operational cost**: Community Edition is $0. Docker Compose startup only
- **Redis single point of failure**: Phase 1 is local dev only. Consider Sentinel/Cluster for production

---

## TD-002: LangGraph as DAG Engine

**Date**: 2026-02-24
**Status**: Accepted

### Decision

Adopt LangGraph as the foundation for the task graph engine.

### Rationale

- **StateGraph**: Built-in state management + conditional edges + checkpoints
- **Human-in-the-Loop**: `interrupt_before` / `interrupt_after` for interactive planning
- **Parallel node execution**: `Send` API for dynamic parallel task generation
- **Persistence**: PostgreSQL checkpointer for saving graph state to DB

### Risks

- **LangChain ecosystem coupling**: LangGraph has some LangChain dependencies
- **Mitigation**: Create a thin wrapper at `core/task_graph/engine.py`. Don't expose LangGraph API directly. Enable future replacement

---

## TD-003: Bootstrap Semantic Memory with mem0

**Date**: 2026-02-24
**Status**: Accepted (Phase 1 only)

### Decision

Implement L2 Semantic Cache using mem0 for Phase 1. Gradually migrate to LSH + ContextZipper in Phase 3.

### Rationale

- mem0 is `pip install mem0ai` — instant setup
- Automatically extracts facts from conversations + stores in vector DB
- Can use pgvector as backend
- "Solves 80% of memory problems" (Phase 1 approach)

### Migration Path

```
Phase 1: mem0 (auto-extraction + pgvector)
Phase 3: mem0 + SemanticFingerprint(LSH) + ContextZipper
Phase 3+: Custom implementation to replace mem0 (only if needed)
```

---

## TD-004: LOCAL_FIRST Architecture — Ollama + LiteLLM

**Date**: 2026-02-24
**Status**: Accepted

### Decision

LLM calls always prioritize Ollama (local). API fallback based on budget and task complexity.

### Routing Logic

```
1. Ollama running AND task is free-tier compatible → Ollama (cost: $0)
2. Ollama insufficient OR quality needed → LiteLLM API routing
   - low tier:  Claude Haiku / Gemini Flash
   - medium:    Claude Sonnet / GPT-4o-mini
   - high:      Claude Opus / GPT-4o
3. Budget exhausted → Force Ollama fallback (accept quality degradation)
```

### LiteLLM's Role

- Unified API for 100+ models
- Swap models by just changing model name in `completion()`
- `success_callback` for automatic cost tracking
- `cache={"type": "disk"}` for KV-Cache optimization

---

## TD-005: Python Package Management with uv

**Date**: 2026-02-24
**Status**: Accepted

### Decision

Adopt uv instead of pip / poetry / pdm.

### Rationale

- Rust-based, 10-100x faster than pip
- Lockfile (`uv.lock`) guarantees build reproducibility
- `uv run` auto-manages virtualenv
- `uv add` for single-command dependency addition

---

## TD-006: Frontend — Next.js 15 + Shadcn/ui + React Flow

**Date**: 2026-02-24
**Status**: Accepted

### Decision

| Technology | Role |
|---|---|
| Next.js 15 (App Router) | Framework. RSC optimal for data-heavy dashboards |
| Shadcn/ui | UI components. High dark theme compatibility |
| React Flow | Task graph DAG visualization (full implementation in Phase 2) |
| Recharts | Cost trend graphs |

### UI Theme

Per CLAUDE.md `morphicAgentTheme`:
- Background: `#0A0A0F` (deep space black)
- Accent: `#6366F1` (indigo)
- LOCAL FREE badge: `#34D399` (bright green)

---

## TD-007: Monorepo Structure

**Date**: 2026-02-24
**Status**: Accepted

### Decision

Manage Python backend + Next.js frontend in a single repository.

### Structure

```
morphic-agent/
├── domain/        # Pure business logic (Clean Architecture Layer 1)
├── application/   # Use cases (Layer 3)
├── infrastructure/# Port implementations (Layer 2)
├── interface/     # API + CLI entry points (Layer 4)
├── shared/        # Cross-cutting (config)
├── ui/            # Next.js 15
├── tests/         # Python tests
├── docs/          # Documentation
├── docker-compose.yml
├── pyproject.toml
└── CLAUDE.md
```

### Rationale

- Single team in early development. Split repos create more management overhead
- docker-compose for one-command startup
- Single CI/CD pipeline
- Re-evaluate monorepo tools (turborepo etc.) or repo splitting at Phase 5+

---

## TD-008: Local Autonomous Execution Engine (LAEE) — Direct Local PC Control

**Date**: 2026-02-25
**Status**: Accepted

### Decision

Build an execution layer (LAEE) that directly operates the user's local PC from Phase 1. Execute on the **real machine** (not Docker sandbox), with safety controlled by a 3-tier approval model under user's own responsibility.

### Rationale

- 80% of real use cases are "do something on my PC" (env setup, file ops, browser automation)
- OpenHands' Docker sandbox is safe but can't touch local environment
- OpenClaw-style "PC as hands" ability is the true power of AI agents
- 3-tier approval model balances risk and usability

### Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Approval model | 3-tier (full-auto / confirm-destructive / confirm-all) | Inspired by Codex CLI 3-tier model. User selects own risk level |
| Risk assessment | 5-tier (SAFE→CRITICAL) | Auto-detection from tool name + argument patterns. Detects sudo, rm -rf, etc. |
| Log format | JSONL append-only | Manus principle 3 compliant. Queryable via grep/jq |
| Undo approach | Stack-based | Reversible operations only. fs_delete uses trash→permanent two-stage |
| Browser | Playwright (OSS) | Chromium/Firefox/WebKit support. Headless + headed |
| GUI automation | AppleScript (macOS) | Native. Add xdotool for Linux support |
| Scheduler | APScheduler (OSS) | Python-native. Cron + interval + one-shot |
| Process management | psutil (OSS) | Cross-platform CPU/memory/process info |

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| All operations in Docker sandbox | Can't touch local environment. Covers only 20% of use cases |
| No approval, full auto only | No safety guarantees. Risk of beginners running rm -rf / |
| Selenium (browser) | Playwright is faster, more stable, better API design |
| macOS Accessibility API only | AppleScript more concise. Fallback to Accessibility API for complex operations |

### Risks and Mitigations

- **rm -rf and fatal operations**: CRITICAL risk auto-detection + confirm-destructive mode default
- **Credential leakage**: ~/.ssh, ~/.aws, .env paths auto-classified as CRITICAL
- **Browser security**: Headless mode default. Auth site operations are MEDIUM+
- **Cron runaway**: Max concurrent job limit (LAEE_MAX_CONCURRENT_SHELLS)
- **User responsibility**: Explicit warning displayed when selecting full-auto mode

---

## TD-009: Clean Architecture + TDD

**Date**: 2026-02-25
**Status**: Accepted

### Decision

Build the entire project using Clean Architecture (4-layer separation) with TDD (Test-Driven Development).

### 4-Layer Structure

```
domain/          Layer 1: Pure business logic (zero framework dependencies)
                 - entities/ (pure Pydantic models, strict=True)
                 - value_objects/ (Enum, immutable types)
                 - ports/ (ABC — dependency inversion interfaces)
                 - services/ (domain services — pure functions)

application/     Layer 3: Use cases
                 - use_cases/ (orchestration of domain operations)
                 - dto/ (inter-layer data transfer)

infrastructure/  Layer 2: Port implementations
                 - persistence/ (SQLAlchemy ORM, pgvector, Neo4j)
                 - llm/ (LiteLLM, Ollama)
                 - local_execution/ (LAEE tool implementations)
                 - memory/ (mem0, vector DB)

interface/       Layer 4: Entry points
                 - api/ (FastAPI routes)
                 - cli/ (CLI commands — typer + rich)

shared/          Cross-cutting concerns
                 - config.py (pydantic-settings)

tests/
  unit/          Domain + application tests (no DB, fast)
  integration/   Infrastructure tests (DB required)
  e2e/           Full-stack integration tests
```

### Dependency Rules

```
Interface → Application → Domain ← Infrastructure
                                    (Dependency Inversion)

✅ infrastructure/ implements domain/ports/ ABCs
✅ application/ uses domain/ entities and ports
✅ interface/ calls application/ use cases
❌ domain/ depends on NO other layer
❌ domain/ never imports SQLAlchemy, FastAPI, LiteLLM
```

### TDD Process

```
1. Red:   Write tests first (domain layer is pure — immediately testable)
2. Green: Minimum implementation to pass tests
3. Refactor: Clean up (tests protect against regression)

Test breakdown:
- unit/domain/       → No DB, 0.03s for 67 tests (actual)
- unit/application/  → Ports mocked, no DB
- integration/       → Docker Compose required
- e2e/               → Full infra + UI
```

### Rationale

| Aspect | Reason |
|---|---|
| Testability | Domain layer needs no DB/API — immediately testable. TDD-friendly |
| Swappability | LLM/DB/tools swappable via ports. Ollama→Claude API switch in infrastructure only |
| Long-term maintainability | Business logic (domain) never polluted by framework concerns |
| TDD fit | Pure domain layer needs no mocks for testing. Ideal TDD structure |

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| Flat package (everything in `core/`) | Domain and infra mix. SQLAlchemy changes cascade to business logic |
| Hexagonal (Ports & Adapters only) | Clean Architecture has clearer layer responsibilities |
| Full DDD (Domain-Driven Design) | Currently one Bounded Context — overkill. Re-evaluate at scale |

---

## TD-010: OSS-First Principle

**Date**: 2026-02-25
**Status**: Accepted

### Decision

Maximize use of established OSS libraries. Custom code is written ONLY for domain-specific logic that no OSS covers.

### Rationale

- Reduce code surface area → fewer bugs, less maintenance
- OSS libraries are battle-tested by communities
- Avoid the "single-file code generation" anti-pattern (generating large amounts of custom code that becomes unmaintainable)
- Focus engineering effort on the unique value proposition (orchestration logic, memory hierarchy, risk assessment)

### OSS Dependency Map

| Component | OSS Library | Custom Code | Notes |
|---|---|---|---|
| Task DAG | **LangGraph** | Thin wrapper only | Use built-in StateGraph, Send, checkpointer |
| LLM routing | **LiteLLM** | Routing logic only | 100+ model unified API, cost tracking callbacks |
| Structured output | **Instructor** | None | Pydantic-validated LLM responses |
| Semantic memory | **mem0** | Hierarchy management | Auto-extraction + pgvector backend |
| Vector search | **pgvector** | None | PostgreSQL extension |
| Knowledge graph | **Neo4j** driver | Query builder only | Cypher queries, ACID, persistence |
| ORM | **SQLAlchemy** + **Alembic** | None | Async engine, migrations |
| API framework | **FastAPI** | Route definitions | WebSocket support |
| CLI framework | **typer** + **rich** | Command definitions | Auto-completion, beautiful output |
| Browser automation | **Playwright** | None | Chromium/Firefox/WebKit |
| File watching | **watchdog** | None | Cross-platform file system events |
| Scheduling | **APScheduler** | None | Cron + interval + one-shot |
| Process management | **psutil** | None | Cross-platform process/system info |
| Configuration | **pydantic-settings** | None | Typed env var loading |
| Task queue | **Celery** + **Redis** | None | Async distributed task execution |
| Logging | **structlog** | None | Structured JSON logging |

### What Remains Custom (and Why)

| Custom Module | Why Not OSS |
|---|---|
| `domain/services/risk_assessor.py` | Project-specific 5-tier risk classification for 40+ LAEE tools |
| `domain/services/approval_engine.py` | Project-specific 3-mode × 5-risk approval matrix |
| `domain/entities/*` | Domain models are inherently project-specific |
| `AgentCLIRouter` | No OSS covers multi-agent-CLI routing with cost awareness |
| `ContextZipper` | Custom query-adaptive compression (Phase 3) |

### Rules

1. Before writing a new module, search PyPI/npm/MCP Registry for existing solutions
2. If an OSS library covers 80%+ of the requirement, use it and adapt
3. Custom code must be in `domain/` or `application/` — infrastructure should be OSS wrappers
4. Prefer stdlib when external dependencies are unnecessary (e.g., `subprocess`, `pathlib`)
5. Pin major versions in `pyproject.toml` to avoid breaking changes

---

## TD-011: CLI as First-Class Interface

**Date**: 2026-02-25
**Status**: Accepted (Design only — implementation in Phase 2)

### Decision

Design the CLI (`interface/cli/`) as a first-class interface alongside the API (`interface/api/`). Both call the same `application/use_cases/` layer. CLI implementation is planned for Phase 2.

### Rationale

- CLI enables scriptable automation, CI/CD integration, and power-user workflows
- Clean Architecture makes this trivial — CLI is just another entry point calling use cases
- Many users prefer terminal-based tools (Claude Code, Codex CLI, gh CLI precedent)
- CLI can work without the UI server running (lighter resource usage)

### Technology Choice

| Library | Role | Why |
|---|---|---|
| **typer** | CLI framework | Auto-generates help/completion. Built on click. Type-safe with Python type hints |
| **rich** | Terminal formatting | Tables, progress bars, syntax highlighting, markdown rendering |

### Planned CLI Commands

```bash
# Task management
morphic task create "Build a REST API"     # Create + execute task
morphic task list                           # List tasks with status
morphic task show <id>                      # Task detail + subtask tree
morphic task cancel <id>                    # Cancel running task

# LLM / Model management
morphic model list                          # Available models (Ollama + API)
morphic model status                        # Ollama health check
morphic model pull <name>                   # Pull Ollama model

# Cost management
morphic cost summary                        # Daily/monthly cost + local rate
morphic cost budget set 50                  # Set monthly budget

# Memory
morphic memory search "project deadline"    # Semantic memory search
morphic memory stats                        # Memory hierarchy stats

# LAEE (local execution)
morphic exec "create test directory"        # Execute local action
morphic exec --mode confirm-all "..."       # With approval mode
morphic audit log                           # View audit log
morphic audit stats                         # Execution statistics

# Configuration
morphic config show                         # Current config
morphic config set LOCAL_FIRST true         # Update setting
```

### Architecture Integration

```
interface/
├── api/              # FastAPI routes (HTTP/WebSocket)
│   ├── routes/
│   │   └── tasks.py  # POST /api/tasks → CreateTaskUseCase
│   └── main.py
│
└── cli/              # typer commands (terminal)
    ├── main.py       # typer.Typer() app
    ├── commands/
    │   ├── task.py   # morphic task ... → CreateTaskUseCase (same use case!)
    │   ├── model.py  # morphic model ...
    │   ├── cost.py   # morphic cost ...
    │   ├── memory.py # morphic memory ...
    │   └── exec.py   # morphic exec ...
    └── formatters.py # rich-based output formatting
```

Both `api/routes/tasks.py` and `cli/commands/task.py` call the same `CreateTaskUseCase`. No logic duplication.

### Implementation Timeline

- **Phase 1**: API + UI (web-first for visual task graph)
- **Phase 2**: CLI foundation (task, model, cost commands)
- **Phase 3+**: CLI-only workflows, REPL mode, piping support

---

## TD-012: Task Graph Engine — Entity Reference Pattern

**Date**: 2026-02-25
**Status**: Accepted

### Decision

Hold TaskEntity by reference on the LangGraphTaskEngine instance during execution, rather than serializing it into the LangGraph AgentState.

### Problem

LangGraph's StateGraph requires state to be a TypedDict. Domain entities use Pydantic `strict=True` which rejects string→Enum coercion during deserialization. Serializing TaskEntity into the state would require:
1. `model_dump()` → loses Enum instances (becomes strings)
2. `model_validate()` from dict → fails under strict mode for Enum fields

### Solution

```python
class LangGraphTaskEngine(TaskEngine):
    _task: TaskEntity | None = None  # Held by reference during execute()

    async def execute(self, task: TaskEntity) -> TaskEntity:
        self._task = task  # Reference, not copy
        graph = self._build_graph()
        await graph.ainvoke(minimal_state)  # State has ready_ids, history, cost only
        return self._task  # Mutated in-place by graph nodes
```

AgentState is minimal (no domain objects):
```python
class AgentState(TypedDict):
    ready_ids: list[str]
    history: Annotated[list[dict], operator.add]
    status: str
    cost_so_far: float
```

### Rationale

| Aspect | Benefit |
|---|---|
| No serialization overhead | Avoids Pydantic strict-mode issues entirely |
| Domain integrity | TaskEntity stays valid throughout execution |
| Simple graph | AgentState is trivial, no complex reducers needed |
| No race conditions | asyncio.gather touches different SubTask objects (GIL safe) |

### Trade-offs

- Engine is not stateless during execution (holds `_task` reference)
- Cannot use LangGraph checkpointing with TaskEntity (acceptable — we persist via TaskRepository)
- Not suitable for distributed execution (single-process only — acceptable for Phase 1)

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| Serialize TaskEntity to dict in state | Pydantic strict-mode rejects string Enum on reconstruct |
| Use `strict=False` for SubTask | Weakens domain validation guarantees |
| Add `from_state_dict()` to SubTask | Pollutes domain entity with infrastructure concerns |

---

## TD-013: Decomposition + Execution Separation

**Date**: 2026-02-25
**Status**: Accepted

### Decision

Separate task decomposition (goal → subtasks) from task execution (run subtasks through DAG) into two distinct use cases.

### Architecture

```
CreateTaskUseCase                    ExecuteTaskUseCase
    │                                    │
    ▼                                    ▼
TaskEngine.decompose()              TaskEngine.execute()
    │                                    │
    ▼                                    ▼
IntentAnalyzer (LLM call)           LangGraph DAG
    │                                    │
    ▼                                    ▼
list[SubTask]                        TaskEntity (updated)
    │
    ▼
TaskEntity (persisted)
```

### Rationale

- **Single Responsibility**: Each use case has one job
- **Flexible scheduling**: Create now, execute later (or re-execute on failure)
- **Testability**: Decomposition tested independently from DAG execution
- **Clean graph**: LangGraph only handles execution flow, not decomposition (simpler state machine)

### Implementation

The original IMPLEMENTATION_PLAN had decomposition nodes (`analyze_intent`, `plan_tasks`) inside the graph. The implemented design moves these to `IntentAnalyzer.decompose()`, called by `CreateTaskUseCase`. The graph only has execution nodes (`select_ready` → `execute_batch` → `finalize`).

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| `click` alone | typer adds type-hint-based auto-generation on top of click |
| `argparse` | Too low-level for complex subcommand structure |
| CLI only (no API) | Task graph visualization requires web UI |
| `textual` TUI | Over-engineering for Phase 2. Can add later if demand exists |

---

## TD-014: Default Ollama Model — qwen3-coder:30b

**Date**: 2026-02-25
**Status**: Accepted

### Decision

Use `qwen3-coder:30b` as the default Ollama model (top of FREE tier), replacing `qwen3:8b`.

### Rationale

- **Coding quality**: qwen3-coder:30b is a coding-specialized model with significantly better structured output (JSON) and code generation than qwen3:8b
- **User's 32GB RAM**: Machine has sufficient RAM (30b model requires ~18GB)
- **Integration test results**: 10/10 integration tests pass with qwen3-coder:30b, including LLM decomposition (IntentAnalyzer)
- **Model availability check**: `is_available()` now verifies the specific model is installed in Ollama, not just that Ollama is running

### Changes

| File | Change |
|---|---|
| `shared/config.py` | `ollama_default_model = "qwen3-coder:30b"` |
| `infrastructure/llm/litellm_gateway.py` | FREE tier: `["ollama/qwen3-coder:30b", "ollama/qwen3:8b", ...]` |
| `infrastructure/llm/litellm_gateway.py` | `is_available()`: checks installed model list, not just Ollama running status |
| `tests/unit/infrastructure/test_litellm_gateway.py` | All assertions updated + new `test_ollama_unavailable_when_not_installed` |
| `tests/integration/test_live_smoke.py` | `qwen3_model` fixture auto-detects best available model |

### Fallback

If `qwen3-coder:30b` is not installed, the router cascades to `qwen3:8b` → `deepseek-r1:8b` → `llama3.2:3b` (FREE tier order).

---

## TD-015: Disable qwen3 Thinking Mode for LiteLLM

**Date**: 2026-02-25
**Status**: Accepted (Workaround)

### Problem

qwen3 family models (qwen3:8b, qwen3-coder:30b) use a "thinking mode" by default. When thinking mode is active:
1. Ollama API puts reasoning output in `message.thinking` field
2. `message.content` is often empty
3. LiteLLM reads only `message.content`, not `message.thinking`
4. Result: ~66% of responses return empty content via LiteLLM

### Decision

Disable thinking mode for all Ollama models by passing `extra_body={"think": False}` in LiteLLM calls.

### Implementation

```python
# infrastructure/llm/litellm_gateway.py — complete() method
if resolved.startswith("ollama/"):
    kwargs["api_base"] = self._settings.ollama_base_url
    kwargs.setdefault("extra_body", {})["think"] = False
```

### Alternatives Tested and Rejected

| Approach | Result |
|---|---|
| `/no_think` in system prompt | Still used thinking mode (~66% empty) |
| `/no_think` at end of user message | Still used thinking mode (~66% empty) |
| `think: false` in Ollama API directly | **Works (3/3 success)** |
| `extra_body={'think': False}` via LiteLLM | **Works (3/3 success)** ← Adopted |

### Risks

- This disables reasoning capability of qwen3 models. For tasks requiring deep reasoning, cloud models (Claude Sonnet/Opus) are routed via task type
- If a future LiteLLM version adds native thinking output support, this workaround can be removed
- IntentAnalyzer also strips `<think>...</think>` tags via regex as a defense-in-depth measure
