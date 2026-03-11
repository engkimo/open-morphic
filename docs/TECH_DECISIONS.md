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

---

## TD-016: Model Tier Update — Gemini 3, O-series, Codex API

**Date**: 2026-02-25
**Status**: Accepted

### Decision

Update MODEL_TIERS to use latest models: Gemini 3 series, OpenAI O-series reasoning models. Add O-series temperature handling.

### Changes

| Tier | Before | After | Reason |
|---|---|---|---|
| LOW | `gemini/gemini-2.0-flash` | `gemini/gemini-3-flash-preview` | gemini-2.0-flash deprecated ("no longer available to new users") |
| MEDIUM | `gpt-4o-mini` | `o4-mini` | User requested O-series reasoning models |
| MEDIUM | `gemini/gemini-2.5-pro` | `gemini/gemini-3-pro-preview` | Gemini 3 is current generation |
| HIGH | `gpt-4o` | `o3` | User requested O-series reasoning models |

### O-series Temperature Handling

O-series models (o3, o4-mini) only support `temperature=1`. Passing any other value raises `UnsupportedParamsError`.

```python
# infrastructure/llm/litellm_gateway.py — complete() method
if resolved.startswith("o3") or resolved.startswith("o4"):
    kwargs.pop("temperature", None)
```

### is_available() Update

O-series model names don't contain "gpt", requiring prefix-based detection:

```python
if "gpt" in model or model.startswith("o3") or model.startswith("o4"):
    return self._settings.has_openai
```

### Codex API Models — Not Adopted

OpenAI Codex models (`codex-mini-latest`, `gpt-5-codex`, `gpt-5.1-codex`) were investigated but not adopted:

| Model | Issue |
|---|---|
| `codex-mini-latest` | Responses API only (not Chat Completions). LiteLLM bridge exists but is a workaround |
| `gpt-5-codex` family | Optimized for long-running agentic coding. Overkill for simple LLM completions |

O-series models (o3, o4-mini) are the correct choice for standard Chat Completions API usage. Codex models are designed for the Codex CLI agent runtime, not for direct API calls.

### Verification

All 11 cloud integration tests pass (0 skipped):
- Anthropic: 3/3 (Haiku, Sonnet, routing)
- OpenAI: 2/2 (o4-mini, o3)
- Gemini: 2/2 (3-flash, 3-pro)
- Cost tracking: 2/2
- Routing: 2/2

---

## TD-017: Memory Hierarchy — L1-L4 CPU-Cache Design

**Date**: 2026-02-25
**Status**: Accepted

### Decision

Implement a CPU-cache-inspired 4-layer memory hierarchy where each layer trades speed for capacity:

| Layer | Storage | Speed | Capacity | Persistence |
|---|---|---|---|---|
| **L1** | `collections.deque` (in-memory) | Instant | ~50 entries | No |
| **L2** | `MemoryRepository` (pgvector) | Fast | Unlimited | Yes |
| **L3** | `KnowledgeGraphPort` (Neo4j) | Medium | Unlimited | Yes |
| **L4** | `MemoryRepository` (cold filter) | Slow | Unlimited | Yes |

### Key Design Choices

| Choice | Rationale |
|---|---|
| L1 = `deque(maxlen=N)` | O(1) append/pop, bounded, no GC pressure |
| L3 is optional | `MemoryHierarchy` works without Neo4j (graceful degradation) |
| `KnowledgeGraphPort` as domain port | Domain layer doesn't know about Neo4j/Cypher |
| Token budget in `retrieve()` | Greedy selection with deduplication across layers |
| `_estimate_tokens = len(text) // 4` | Good enough for Phase 1. Real tokenizer in Phase 3 |
| Separator cost in ContextZipper | Newlines between selected messages counted against budget |

### ContextZipper Scoring

```
score = recency_weight * 0.4 + keyword_overlap * 0.6
```

- **Recency**: `(index + 1) / total_count` — most recent messages score higher
- **Keyword overlap**: `len(query_words ∩ text_words) / len(query_words)` — relevance to current query
- Selected messages reassembled in original chronological order

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| LLM-based summarization for compression | Too slow and expensive for real-time queries. Also lossy (information irreversible) |
| Single-layer vector search | No speed tiers. L1 in-memory is 100x faster than DB queries for recent context |
| L1 as `list` | Unbounded growth. `deque(maxlen=N)` auto-evicts oldest entries |
| Embedding-based L1 search | Overkill for ~50 entries. Simple keyword matching is sufficient |

### Verification

- 36 unit tests (in-memory fakes, 0.10s)
- 8 integration tests (real PostgreSQL + Neo4j, skip if unavailable)
- CC#1: add() → retrieve() returns relevant memories (5 tests)
- CC#4: 5000-token history → ≤500 tokens compression (2 tests)
- Total unit test suite: 221 → 257 tests, all passing (1.70s)

---

## TD-018: API DI Pattern — AppContainer over FastAPI Depends

**Date**: 2026-02-25
**Status**: Accepted

### Decision

Use a single `AppContainer` class stored on `app.state.container` for dependency injection, instead of FastAPI's `Depends()` chain pattern.

### Rationale

| Aspect | AppContainer | FastAPI Depends |
|---|---|---|
| Testability | Swap entire container in one line | Override individual dependencies |
| Simplicity | One class, explicit wiring | Chains of `Depends()` with closures |
| Visibility | All deps visible in constructor | Scattered across route decorators |
| Phase 1 fit | In-memory repos, no DB sessions | Depends shines with DB session lifecycle |

### Implementation

```python
class AppContainer:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.task_repo = InMemoryTaskRepository()
        self.cost_repo = InMemoryCostRepository()
        self.memory_repo = InMemoryMemoryRepository()
        self.ollama = OllamaManager(base_url=self.settings.ollama_base_url)
        self.cost_tracker = CostTracker(self.cost_repo)
        self.llm = LiteLLMGateway(ollama=self.ollama, cost_tracker=self.cost_tracker, settings=self.settings)
        self.intent_analyzer = IntentAnalyzer(llm=self.llm)
        self.task_engine = LangGraphTaskEngine(llm=self.llm, analyzer=self.intent_analyzer)
        self.create_task = CreateTaskUseCase(engine=self.task_engine, repo=self.task_repo)
        self.execute_task = ExecuteTaskUseCase(engine=self.task_engine, repo=self.task_repo)
        self.memory = MemoryHierarchy(memory_repo=self.memory_repo)
```

Routes access via `request.app.state.container`:
```python
def _container(request: Request):
    return request.app.state.container
```

Tests swap the container entirely:
```python
app = create_app(container=mock_container)
client = TestClient(app)
```

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| FastAPI `Depends()` chains | Over-engineering for in-memory repos. Better suited for DB session lifecycle |
| Module-level singletons | Untestable, no isolation between test cases |
| `dependency-injector` library | External dependency for a simple wiring problem |

### Future Migration Path

When PostgreSQL repos replace in-memory repos (Phase 3+), `AppContainer.__init__` will create DB sessions and pass them to repo constructors. No route code changes needed.

---

## TD-019: In-Memory Repositories as Phase 1 Production Backend

**Date**: 2026-02-25
**Status**: Accepted

### Decision

Use `InMemoryTaskRepository`, `InMemoryCostRepository`, and `InMemoryMemoryRepository` as the Phase 1 production backend. No Docker/DB required to run the server.

### Rationale

- **Zero-dependency startup**: `uvicorn interface.api.main:app` works immediately
- **Test reuse**: Same implementations used in unit tests — battle-tested
- **Clean Architecture payoff**: Repositories implement domain port ABCs. Swapping to PostgreSQL requires only changing `AppContainer.__init__`
- **Phase 1 scope**: Single-process, no persistence needed across restarts

### Implementation

```python
# infrastructure/persistence/in_memory.py
class InMemoryTaskRepository(TaskRepository):
    """Dict-backed. Sorted by created_at desc for list_all()."""

class InMemoryCostRepository(CostRepository):
    """List-backed. Exposes .records property for test introspection."""

class InMemoryMemoryRepository(MemoryRepository):
    """Dict-backed. Keyword-overlap search (no embeddings)."""
```

### Domain Port Additions

Two methods added to support API needs:
- `TaskRepository.list_all() -> list[TaskEntity]` — needed for GET /api/tasks
- `CostRepository.list_recent(limit: int = 50) -> list[CostRecord]` — needed for GET /api/cost/logs

### Risks

- Data lost on server restart (acceptable for Phase 1)
- No concurrent access safety (acceptable for single-process)
- Keyword search is crude (replaced by pgvector in Phase 3)

---

## TD-020: Phase 1 Foundation Complete — Architecture Retrospective

**Date**: 2026-02-25
**Status**: Record

### Summary

Phase 1 Foundation (7 sprints, 1.1→1.7) is complete. 298 unit tests + 26 integration tests, all passing.

### What Was Built

| Sprint | Deliverable | Tests |
|---|---|---|
| 1.1 Infrastructure | Domain entities, value objects, ports (ABC), services, config | 67 |
| 1.2 LLM Layer | OllamaManager, LiteLLMGateway, CostTracker, multi-provider routing | 51 |
| 1.3 Task Graph | LangGraphTaskEngine (DAG), IntentAnalyzer, CreateTask/ExecuteTask use cases | 16 |
| 1.3b LAEE | LocalExecutor, ApprovalEngine, RiskAssessor, AuditLog, UndoManager, 4 tool modules | 35 |
| 1.4 Context Eng. | KVCacheOptimizer, ObservationDiversifier, TodoManager, FileContext (Manus 5 principles) | 40 |
| 1.5 Semantic Memory | MemoryHierarchy (L1-L4), KnowledgeGraph, ContextZipper | 36 |
| 1.6 API + UI | FastAPI (4 routers + WebSocket), AppContainer DI, Next.js 15 dashboard | 34 |
| 1.7 E2E Tests | Failure recovery (retry/cascade/fallback), API round-trip (POST→GET→WS) | 19 |

### Architecture Decisions That Proved Correct

1. **Clean Architecture 4-layer**: Domain ports as ABCs enabled InMemory → (future) PostgreSQL swap with zero use-case changes
2. **Pydantic strict=True**: Caught type bugs at construction time, not at runtime
3. **TaskEntity by reference** (TD-012): Avoided serialization issues with LangGraph state
4. **Separate decompose/execute** (TD-013): Made retry logic clean — engine can re-execute without re-decomposing
5. **AppContainer DI** (TD-018): Single swap point for testing; TestClient gets full mock stack
6. **In-memory repos** (TD-019): Zero-dependency startup, no Docker needed for dev

### Technical Debt to Address in Phase 2

1. **No persistent storage**: In-memory repos lose data on restart → PostgreSQL + pgvector
2. **No Celery queue**: BackgroundTasks is single-process → Celery + Redis for production
3. **Keyword search only**: InMemoryMemoryRepository uses string matching → pgvector embeddings
4. **No auth/rate limiting**: API is fully open → add middleware in Phase 2
5. **Single Ollama model**: Always uses default model → implement full ModelTier routing

### Key Metrics

```
Unit tests:        298 (1.72s)
Integration tests:  26 (Ollama required)
Python files:      ~55
TypeScript files:  ~11
Domain ports:       8 ABC interfaces
Infrastructure:     6 port implementations (all in-memory for Phase 1)
API endpoints:     10 (4 task + 2 model + 2 cost + 1 memory + 1 health)
```

---

## TD-021: CLI v1 — Reuse AppContainer with Lazy Singleton

**Date**: 2026-02-25
**Status**: Accepted
**Sprint**: 2.9–2.11

### Decision

The CLI (`interface/cli/`) reuses the same `AppContainer` that the API uses, via a lazy singleton pattern in `main.py`. No separate CLI-specific container or DI framework.

### Architecture

```python
# interface/cli/main.py
_container_instance: Any = None

def _get_container() -> Any:
    global _container_instance
    if _container_instance is None:
        from interface.api.container import AppContainer
        _container_instance = AppContainer()
    return _container_instance
```

### Key Design Choices

| Choice | Rationale |
|---|---|
| **Reuse AppContainer** | Zero logic duplication — CLI and API call the same use cases via the same wiring |
| **Lazy singleton** | AppContainer is heavy (connects to Ollama). Only init when first command runs, not on `--help` |
| **`_set_container()` for testing** | Monkeypatch `_container_instance` in tests, same mock pattern as `test_api.py` |
| **`_run()` async wrapper** | typer commands are sync; `_run()` bridges to async use cases via `asyncio.run()` |
| **Event loop fallback** | `_run()` detects running event loop (pytest-asyncio) and falls back to `loop.run_until_complete()` |

### Async Bridge Pattern

```python
def _run(coro: Any) -> Any:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)       # Normal CLI execution
    return loop.run_until_complete(coro)  # Inside pytest-asyncio
```

This avoids `asyncio.run() cannot be called from a running event loop` errors in tests.

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| Separate `CLIContainer` | Duplicates wiring logic. AppContainer has no API-specific code |
| `click` instead of `typer` | typer provides type-safe arguments + auto-generated help. Wraps click underneath |
| Custom DI framework | Over-engineering. Lazy singleton + monkeypatch covers all needs |
| `nest_asyncio` for tests | Third-party dep for a test-only issue. Event loop detection is simpler |

---

## TD-022: CLI Test Strategy — Sync Store Access

**Date**: 2026-02-25
**Status**: Accepted
**Sprint**: 2.9–2.11

### Problem

CLI commands use `_run(asyncio.run(coro))` internally. When tests are `async def` (pytest-asyncio), the event loop is already running. Even with `_run()` fallback to `loop.run_until_complete()`, this fails because the loop is already executing the test coroutine.

### Decision

Tests that need pre-populated data access in-memory store internals directly instead of using `await repo.save()`:

```python
# ✅ Sync test — works with typer CliRunner
def test_list_populated(self, container):
    task = _make_task("task A")
    container.task_repo._store[task.id] = task  # Direct store access
    result = runner.invoke(app, ["task", "list"])
    assert "task A" in result.output

# ❌ Async test — fails with "event loop already running"
async def test_list_populated(self, container):
    await container.task_repo.save(task)  # Needs running loop
    result = runner.invoke(app, ["task", "list"])  # _run() can't nest
```

### Justification

- InMemoryRepository internals (`_store`, `_records`) are stable and controlled by our codebase
- Pattern is limited to CLI tests only — API tests use TestClient which handles async natively
- No production behavior change; only test setup mechanism differs

---

## TD-023: In-Memory Repos — Cross-Process Data Loss (Known Limitation)

**Date**: 2026-02-25
**Status**: Accepted (Phase 1 limitation)

### Behavior

Each `morphic` CLI invocation starts a new OS process → new `AppContainer` → new `InMemoryTaskRepository`. Data created by one invocation is invisible to the next:

```bash
$ morphic task create "fibonacci" --no-wait
Created: 980a5335-50fd-4a1c-...

$ morphic task list
No tasks found.    # ← Different process, empty store
```

### Why This Is Acceptable

1. **Phase 1 scope**: In-memory repos were chosen for zero-dependency startup (TD-019)
2. **Full flow works**: `morphic task create "..."` (without `--no-wait`) does create + execute + display in one process
3. **API is persistent**: The FastAPI server (`uvicorn`) is a long-running process — data persists across HTTP requests
4. **Clear migration path**: Replace `InMemory*Repository` with `Pg*Repository` in `AppContainer` — use cases and CLI commands require zero changes (Dependency Inversion)

### Resolution Plan

| Phase | Action |
|---|---|
| **Phase 2** (current) | CLI works end-to-end within a single invocation |
| **Phase 2+** | PostgreSQL + pgvector repositories replace in-memory |
| **Phase 2+** | `morphic task list` queries persistent DB — data survives across invocations |

### Resolution (Sprint 2-A)

**RESOLVED**: PostgreSQL repositories implemented in Sprint 2-A. Set `USE_POSTGRES=true` with Docker Compose running:

```bash
docker compose up -d
USE_POSTGRES=true morphic task create "fibonacci" --no-wait
USE_POSTGRES=true morphic task list   # ← Now persists across invocations
```

Default remains InMemory for zero-dependency development. See TD-024.

---

## TD-024: PG/InMemory Repository Switching

**Date**: 2026-02-26
**Status**: Accepted
**Sprint**: 2-A

### Decision

Switch between PostgreSQL and InMemory repositories via `Settings.use_postgres` flag (default: `False`). The AppContainer's `_create_repos()` method selects the implementation at startup.

### Implementation

```python
# interface/api/container.py
def _create_repos(self):
    if self.settings.use_postgres:
        return self._create_pg_repos()
    return (InMemoryTaskRepository(), InMemoryCostRepository(),
            InMemoryMemoryRepository(), InMemoryPlanRepository())
```

PG repos map domain entities ↔ ORM models:
- `PgTaskRepository`: TaskEntity ↔ TaskModel (subtasks stored as JSONB in `metadata_`)
- `PgCostRepository`: CostRecord ↔ CostLogModel (SQL aggregation for daily/monthly/local)
- `PgMemoryRepository`: MemoryEntry ↔ MemoryModel (ILIKE keyword search, embedding deferred)
- `PgPlanRepository`: ExecutionPlan ↔ PlanModel (steps stored as JSONB)

### Rationale

- **Backward compatible**: Existing tests and dev workflow unchanged (InMemory default)
- **Opt-in production**: `USE_POSTGRES=true` enables persistence with Docker Compose
- **Same interface**: All repos implement domain port ABCs — zero use-case changes

---

## TD-025: Celery Dispatch Gated by Settings Flag

**Date**: 2026-02-26
**Status**: Accepted
**Sprint**: 2-B

### Decision

Celery task dispatch is gated by `Settings.celery_enabled` (default: `False`). When disabled, task execution uses FastAPI's `BackgroundTasks` (single-process).

### Implementation

```python
# interface/api/routes/tasks.py
if c.settings.celery_enabled:
    from infrastructure.queue.tasks import execute_task_worker
    execute_task_worker.delay(str(task.id))
else:
    bg.add_task(_execute_bg, c, str(task.id))
```

The Celery worker (`infrastructure/queue/tasks.py`) creates its own `AppContainer` (with PG repos) to avoid shared state across processes.

### Rationale

- **No breaking changes**: Existing single-process flow unchanged by default
- **Production-ready**: Enable Celery + Redis for multi-worker async execution
- **Worker independence**: Each Celery worker has its own container, avoiding process-shared state issues

---

## TD-026: PlanStatus Enum — Domain Value Object

**Date**: 2026-02-26
**Status**: Accepted
**Sprint**: 2-C

### Decision

Add `PlanStatus(str, Enum)` to `domain/value_objects/status.py` with states: `proposed`, `approved`, `rejected`, `executing`, `completed`.

### State Machine

```
proposed → approved → executing → completed
proposed → rejected
```

### Rationale

- Consistent with existing `TaskStatus` pattern (str, Enum)
- `proposed` is the initial state — plan exists but awaits user decision
- `approved` triggers task creation + execution
- Clean separation from `TaskStatus` — plans and tasks have independent lifecycles

---

## TD-027: Cost Estimation — MODEL_COST_TABLE

**Date**: 2026-02-26
**Status**: Accepted
**Sprint**: 2-C

### Decision

Implement `CostEstimator` with a static `MODEL_COST_TABLE` mapping model names to per-1M-token input/output costs. Token count estimated from subtask description length.

### Cost Table (subset)

| Model | Input $/1M | Output $/1M |
|---|---|---|
| `ollama/*` | $0.00 | $0.00 |
| `claude-haiku-*` | $0.25 | $1.25 |
| `claude-sonnet-*` | $3.00 | $15.00 |
| `claude-opus-*` | $15.00 | $75.00 |
| `o4-mini` | $1.10 | $4.40 |

### Token Estimation Heuristic

```python
estimated_input = len(description) * 4    # ~4 tokens per char (conservative)
estimated_output = estimated_input * 2    # assume 2x output
```

### Rationale

- **LOCAL_FIRST emphasis**: All `ollama/*` models always $0.00 — reinforces cost advantage
- **Conservative estimates**: Overestimate rather than underestimate to avoid budget surprises
- **Simple heuristic**: Real tokenizer deferred to Phase 3. Character-based estimate is "good enough"
- **Budget checking**: `is_within_budget(plan, budget)` prevents accidental overspend

---

## TD-028: Pre-Phase 3 Codebase Cleanup — Ruff Lint + Format

**Date**: 2026-02-26
**Status**: Completed
**Sprint**: Pre-Phase 3 verification

### Decision

Before starting Phase 3, enforce `ruff check` (lint) and `ruff format` across the entire codebase. Fix all 79 lint errors and format 48 files.

### Issues Found and Resolved

| Rule | Count | Category | Fix |
|---|---|---|---|
| F401 | 21 | Unused imports | Auto-fix (`--fix`) |
| I001 | 12 | Unsorted imports | Auto-fix (`--fix`) |
| UP042 | 11 | `str, Enum` → `StrEnum` | Suppressed in pyproject.toml (Pydantic strict=True compatibility) |
| E501 | 8 | Line too long (>100) | Manual line breaks |
| B904 | 6 | `raise` without `from` in except | Added `from e` / `from None` |
| SIM117 | 5 | Nested `with` statements | Combined into single `with` |
| SIM105 | 4 | `try/except/pass` | Replaced with `contextlib.suppress()` |
| F841 | 3 | Unused variables | Removed assignments |
| F541 | 2 | f-string missing placeholders | Auto-fix |
| F821 | 2 | Undefined name (false positive) | Added `TYPE_CHECKING` import in schemas.py |
| SIM102 | 1 | Collapsible `if` | Combined conditions |
| UP037 | 2 | Quoted annotation | Auto-fix |
| UP017 | 1 | `datetime.timezone.utc` | Auto-fix |
| UP035 | 1 | Deprecated import | Auto-fix |

### Key Decisions

| Decision | Rationale |
|---|---|
| **Suppress UP042** | `class Foo(str, Enum)` pattern is intentional for Pydantic `strict=True`. `StrEnum` would work but changing all existing enums is unnecessary churn |
| **Fix F821 with TYPE_CHECKING** | Forward references in `schemas.py` used delayed imports. Moved to `if TYPE_CHECKING:` block for ruff compatibility while preserving runtime behavior |
| **Fix B904 with `from e`** | Exception chaining preserves traceback context. `raise HTTPException(...) from e` in API routes, `raise typer.Exit(...) from e` in CLI |

### Verification

```
ruff check:  All checks passed (0 errors)
ruff format: 139 files already formatted (48 reformatted in this pass)
Unit tests:  428 passed (2.82s)
Integration: 10 passed (15.69s, real Ollama)
```

### Config Change

```toml
# pyproject.toml
[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM"]
ignore = ["UP042"]  # Keep (str, Enum) pattern for Pydantic strict=True compatibility
```

---

## TD-029: Semantic Fingerprint — LSH-Based Vector Search

**Date**: 2026-02-26
**Status**: Accepted
**Sprint**: 3.1

### Decision

Implement LSH (Locality-Sensitive Hashing) based semantic search for memory retrieval, replacing keyword-only search. Key choices:

| Decision | Choice | Rationale |
|---|---|---|
| Embedding backend | Ollama `/api/embed` | LOCAL_FIRST, $0, uses existing Ollama install |
| Embedding model | `all-minilm` (384-dim) | Lightest/fastest. Configurable via `embedding_model` setting |
| Vector dimension | 384 (configurable) | Matches all-minilm. ORM corrected from 1536 |
| LSH hyperplanes | Seeded RNG (`seed=42`) | Deterministic across restarts, no file persistence |
| Domain purity | Embeddings stored in ORM only | MemoryEntry stays pure. Vectors live in `MemoryModel.embedding` |
| New domain port | `EmbeddingPort` ABC | Follows existing port pattern for dependency inversion |
| Fallback | Keyword search when no embedding | Full backward compatibility |
| New Python deps | `numpy` only | Ollama HTTP via existing `httpx`. Zero bloat |

### Architecture

```
EmbeddingPort (domain/ports)
    │
    └── OllamaEmbeddingAdapter (infrastructure/memory)
            │
            └── POST /api/embed → [384-dim vectors]

SemanticFingerprint (domain/services)   ← pure, no I/O
    │  lsh_hash(vector) → hex bucket key
    │  cosine_similarity(v1, v2) → float
    │
    └── SemanticBucketStore (infrastructure/memory)
            │  add(id, vector) → bucket
            │  find_similar(vector, top_k, threshold) → [(id, sim)]
            │  multi-probe: flip bits for neighbor buckets
            │
            └── InMemoryMemoryRepository (embedding_port=...)
                PgMemoryRepository (embedding_port=...)
```

### Files Created/Modified

- **Created**: `domain/ports/embedding.py`, `domain/services/semantic_fingerprint.py`, `infrastructure/memory/semantic_fingerprint.py`, `infrastructure/memory/embedding_adapters.py`, `migrations/versions/002_add_embedding_column.py`
- **Modified**: `shared/config.py` (embedding settings), `models.py` (Vector 1536→384), `in_memory.py` (optional embedding_port), `pg_memory_repository.py` (optional embedding_port + pgvector cosine_distance), `container.py` (DI wiring)
- **Tests**: 31 new tests (11 domain + 20 infrastructure), total 459 passing

---

## TD-030: ContextZipper v2 — Semantic-Aware Context Compression

**Date**: 2026-02-26
**Status**: Accepted
**Sprint**: 3.2

### Decision

Rewrite ContextZipper from sync keyword-only utility to async semantic-aware compressor with optional ports for embedding, memory, and knowledge graph augmentation.

| Decision | Choice | Rationale |
|---|---|---|
| `compress()` signature | **async** always | EmbeddingPort.embed() is async. No production callers to break (test-only today) |
| Scoring fallback | Cosine similarity (with port) → keyword overlap (without) | Backward compat when embedding unavailable |
| Budget allocation | **Facts-first**: [Facts] → [Memory] → [History] | Structured facts are highest-density info per token (CLAUDE.md principle) |
| Budget split | facts=20%, memory=30%, history=50% (configurable) | History gets most budget since it's the primary input |
| `ingest()` method | Stores to MemoryRepository (L2) | ContextZipper becomes the entry point for new messages |
| Constructor ports | Optional `embedding_port`, `memory_repo`, `knowledge_graph` | Same pattern as InMemoryMemoryRepository from Sprint 3.1 |
| Entity search | Per-word query splitting | `search_entities("Shimizu Python")` splits to individual word searches, deduplicates by entity ID |
| New deps | **None** | Reuses EmbeddingPort, MemoryRepository, KnowledgeGraphPort from existing codebase |

### Architecture

```
ContextZipper(embedding_port?, memory_repo?, knowledge_graph?)
    │
    ├── compress(history, query, max_tokens)
    │   ├── Phase 1: [Facts] from KG (20% budget)
    │   ├── Phase 2: [Memory] from L2 repo (30% budget)
    │   └── Phase 3: History scored by semantic/keyword (50% budget)
    │
    └── ingest(message, role) → memory_repo.add()
```

Output format when all sources available:
```
[Facts] Shimizu {'industry': 'construction'}
---
[Memory] Python is a popular programming language
---
conversation message 9: ...
conversation message 7: ...
```

### Files Modified

- **Modified**: `infrastructure/memory/context_zipper.py` (full rewrite: async, optional ports, semantic scoring, facts/memory augmentation, ingest())
- **Modified**: `tests/unit/infrastructure/test_memory.py` (10 existing tests → async, 16 new tests for v2 features)
- **Modified**: `interface/api/container.py` (wire ContextZipper with embedding_port + memory_repo)
- **Tests**: 16 new tests, total 475 passing

---

## TD-031: ForgettingCurve — Ebbinghaus Retention-Based L2 Memory Expiration

**Date**: 2026-02-26
**Status**: Accepted
**Sprint**: 3.3

### Decision

Implement automatic expiration of stale L2 semantic memories using Ebbinghaus-inspired retention scoring. Expired entries are promoted to L3 Knowledge Graph as `memory_fact` entities (if KG available), then deleted from L2.

| Decision | Choice | Rationale |
|---|---|---|
| Domain service | Pure math (`retention_score`, `is_expired`, `hours_since`) | Same pattern as `semantic_fingerprint.py` — no I/O, deterministic, 100% testable |
| Retention formula | `R = e^(-t / (S * 24))` where `S = 1.0 + access_count*0.5 + importance_score*2.0` | Ebbinghaus curve with stability factors for access frequency and importance |
| Expiry threshold | `score < threshold` (strict less-than) | At exact boundary, entry is NOT expired (conservative) |
| Promote strategy | Store content directly as KG entity (no LLM) | OSS-First, $0 cost, no LLM dependency. LLM summarization deferred to future sprint |
| KG optional | If no KG, expired memories are simply deleted | Matches existing graceful degradation pattern (TD-017) |
| Port enhancement | `list_by_type(memory_type, limit)` on MemoryRepository | Need to iterate L2 entries for compaction. Follows TaskRepository `list_by_status` pattern |
| Threshold config | Reuse `Settings.memory_retention_threshold=0.3` | Already exists in `shared/config.py` — no new config needed |
| Integration point | `MemoryHierarchy.compact()` → `ForgettingCurveManager` | Clean entry point; callers decide when to trigger (e.g., periodic, on-demand) |
| Manager location | `infrastructure/memory/forgetting_curve.py` | Uses ports (async I/O), not pure domain logic |

### Architecture

```
MemoryHierarchy.compact(threshold)
    │
    └── ForgettingCurveManager.compact()
        │
        ├── list_by_type(L2_SEMANTIC) ── MemoryRepository port
        │
        ├── For each entry:
        │   ├── ForgettingCurve.hours_since(last_accessed)
        │   ├── ForgettingCurve.is_expired(access_count, importance, hours, threshold)
        │   ├── If expired:
        │   │   ├── _promote_to_facts(entry) → KnowledgeGraphPort.add_entity()
        │   │   └── memory_repo.delete(entry.id)
        │   └── If not expired: skip
        │
        └── Return CompactResult(scanned, expired, promoted, deleted)
```

### Retention Score Examples

| access_count | importance | hours_elapsed | stability S | score R | expired? (threshold=0.3) |
|---|---|---|---|---|---|
| 1 | 0.5 | 0 | 2.5 | 1.000 | No |
| 1 | 0.5 | 24 | 2.5 | 0.670 | No |
| 1 | 0.0 | 48 | 1.5 | 0.264 | Yes |
| 10 | 1.0 | 48 | 8.0 | 0.904 | No |
| 1 | 0.0 | 500 | 1.5 | 0.000 | Yes |

### Files Created/Modified

- **Created**: `domain/services/forgetting_curve.py` (pure math: retention_score, is_expired, hours_since)
- **Created**: `infrastructure/memory/forgetting_curve.py` (ForgettingCurveManager + CompactResult dataclass)
- **Created**: `tests/unit/domain/test_forgetting_curve.py` (14 tests)
- **Created**: `tests/unit/infrastructure/test_forgetting_curve.py` (17 tests)
- **Modified**: `domain/ports/memory_repository.py` (added `list_by_type` abstract method)
- **Modified**: `infrastructure/persistence/in_memory.py` (implemented `list_by_type`)
- **Modified**: `infrastructure/persistence/pg_memory_repository.py` (implemented `list_by_type` with SQL WHERE + ORDER BY last_accessed ASC)
- **Modified**: `infrastructure/memory/memory_hierarchy.py` (added `compact()` method delegating to ForgettingCurveManager)
- **Modified**: `interface/api/container.py` (wired ForgettingCurveManager with memory_repo + threshold from settings)
- **Tests**: 31 new tests (14 domain + 17 infrastructure), total 506 passing

---

## TD-032: DeltaEncoder — Git-Style Delta State Tracking (Sprint 3.4, 2026-02-26)

### Context

Third compression strategy for Phase 3 Semantic Memory. Tracks state changes as deltas (like Git commits), enabling reconstruction of any point-in-time state without storing full snapshots.

### Decision

| Aspect | Choice | Rationale |
|---|---|---|
| Entity | `Delta` Pydantic entity (strict) | Consistent with all domain entities |
| Domain service | `DeltaEncoder` (all `@staticmethod`) | Follows ForgettingCurve pattern — pure logic, no I/O |
| Hash algorithm | SHA-256 of `json.dumps(sort_keys=True)` | Deterministic, order-independent — Manus principle 1 |
| Deletion | Tombstone (`None` value) | Explicit deletion records — reconstruct knows key was removed |
| Storage | `MemoryEntry` (L2_SEMANTIC) with `delta_*` metadata | Zero new ports — reuses existing MemoryRepository |
| Topic grouping | `metadata["delta_topic"]` | Namespace isolation for independent state streams |
| Seq numbering | Auto-increment per topic (0-based) | First delta auto-marked as base state |
| New dependencies | None | hashlib + json are stdlib |

### Alternatives Considered

| Option | Rejected Because |
|---|---|
| Separate DeltaRepository port | Over-engineering — MemoryEntry metadata is sufficient for MVP |
| Full snapshot storage | Wastes space — delta encoding is the whole point |
| Custom binary format | JSON is readable, debuggable, and sort_keys gives determinism |
| Event sourcing framework | Too heavy — we need simple key-value state tracking |

### Domain Service API

```python
class DeltaEncoder:
    @staticmethod hash_changes(changes: dict) -> str          # SHA-256 hex digest
    @staticmethod reconstruct(base, deltas, target_time?) -> dict  # Apply deltas in seq order
    @staticmethod create_delta(topic, seq, msg, changes, is_base?) -> Delta  # Factory
    @staticmethod compute_diff(old_state, new_state) -> dict   # Minimal diff with tombstones
```

### Infrastructure Manager API

```python
class DeltaEncoderManager:
    async record(topic, message, changes) -> DeltaRecordResult   # Auto-seq, persist
    async get_state(topic, target_time?) -> dict                 # Reconstruct via domain
    async get_history(topic) -> list[Delta]                      # Full delta chain
    async list_topics() -> list[str]                             # Unique topics
```

### Architecture

```
MemoryHierarchy.record_delta(topic, message, changes)
    │
    └── DeltaEncoderManager.record()
        │
        ├── _get_deltas_for_topic() ── MemoryRepository.list_by_type(L2_SEMANTIC)
        ├── DeltaEncoder.create_delta() ── domain pure logic
        ├── _delta_to_entry() ── Delta → MemoryEntry serialization
        └── memory_repo.add(entry)

MemoryHierarchy.get_state(topic, target_time?)
    │
    └── DeltaEncoderManager.get_state()
        │
        ├── _get_deltas_for_topic() ── filter by metadata["delta_topic"]
        └── DeltaEncoder.reconstruct({}, deltas, target_time)
```

### Delta ↔ MemoryEntry Serialization

```python
# Delta metadata keys stored in MemoryEntry.metadata:
delta_topic    = delta.topic          # str
delta_seq      = delta.seq            # int
delta_changes  = json.dumps(changes)  # str (JSON, sort_keys=True)
delta_hash     = delta.state_hash     # str (SHA-256 hex)
delta_is_base  = delta.is_base_state  # bool

# MemoryEntry.content = delta.message (human-readable description)
```

### Files Created/Modified

- **Created**: `domain/entities/delta.py` (Delta Pydantic entity, strict mode)
- **Created**: `domain/services/delta_encoder.py` (pure static: hash_changes, reconstruct, create_delta, compute_diff)
- **Created**: `infrastructure/memory/delta_encoder.py` (DeltaEncoderManager + DeltaRecordResult frozen dataclass)
- **Created**: `tests/unit/domain/test_delta_encoder.py` (34 tests)
- **Created**: `tests/unit/infrastructure/test_delta_encoder.py` (27 tests)
- **Modified**: `domain/entities/__init__.py` (export Delta)
- **Modified**: `infrastructure/memory/__init__.py` (export DeltaEncoderManager)
- **Modified**: `infrastructure/memory/memory_hierarchy.py` (added record_delta, get_state, get_state_history)
- **Modified**: `interface/api/container.py` (wired DeltaEncoderManager)
- **Tests**: 61 new tests (34 domain + 27 infrastructure), total 567 passing

---

## TD-033: HierarchicalSummarizer — 4-Level Tree Compression (Sprint 3.5)

**Date**: 2026-02-26
**Status**: Accepted

### Decision

Implement multi-level tree compression for memory entries. Each entry can have 4 levels of summarization (Level 0=original 100%, Level 1=~40%, Level 2=~15%, Level 3=~5%). Query-adaptive retrieval selects the deepest (most detailed) level that fits within the token budget.

| Component | Layer | Description |
|---|---|---|
| `HierarchicalSummarizer` (domain service) | domain | Pure static: `estimate_tokens`, `split_sentences`, `extract_summary`, `build_extractive_hierarchy`, `select_level`, `estimate_depth` |
| `HierarchicalSummaryManager` (infra manager) | infrastructure | Async manager: `summarize()`, `get_summary()`, `retrieve_at_depth()`. Optional LLM for abstractive, extractive fallback |
| `SummarizeResult` (frozen dataclass) | infrastructure | Return type: entry_id, levels_built, original_tokens, compressed_tokens, used_llm |

### Key Design Choices

1. **No new domain entity** — summaries stored in `MemoryEntry.metadata` (`hierarchy_summaries`, `hierarchy_token_counts` JSON keys). Follows DeltaEncoder's `delta_*` metadata pattern.
2. **Domain service = all static** — extractive summarization via sentence-boundary truncation. No LLM dependency.
3. **Optional LLMGateway** — abstractive summaries when LLM available, extractive fallback when not (follows KnowledgeGraphPort optional pattern).
4. **Per-entry storage** — all 4 levels stored in single MemoryEntry's metadata as JSON dicts.
5. **No new deps** — `re` (stdlib) for sentence splitting, `math` for ceil.
6. **4 levels fixed** — Level 0 (original, 100%), Level 1 (~40%), Level 2 (~15%), Level 3 (~5%).
7. **Skip re-summarization** — if `hierarchy_summaries` already exists in metadata, returns cached result.

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| Separate SummaryEntity | Over-engineering — metadata on existing MemoryEntry is sufficient |
| LLM-only summarization | Must work without LLM for $0/offline operation. Extractive fallback required |
| Variable number of levels | Adds complexity. 4 levels cover typical use cases (overview → full detail) |
| Store summaries as separate MemoryEntries | Complicates retrieval. Single-entry storage is simpler to query and manage |
| tiktoken/transformers for tokenization | Heavy dependencies. 4-chars-per-token approximation is sufficient for budget decisions |

### Domain Service API

```python
class HierarchicalSummarizer:
    NUM_LEVELS = 4
    LEVEL_RATIOS = {0: 1.0, 1: 0.40, 2: 0.15, 3: 0.05}

    @staticmethod estimate_tokens(text: str) -> int                    # ~4 chars/token
    @staticmethod split_sentences(text: str) -> list[str]              # Regex split on .!?\n
    @staticmethod extract_summary(content: str, ratio: float) -> str   # Keep first ratio of sentences
    @staticmethod build_extractive_hierarchy(content: str) -> dict[int, str]  # 4-level hierarchy
    @staticmethod select_level(level_token_counts, max_tokens) -> int  # Deepest fitting level
    @staticmethod estimate_depth(max_tokens, total_entry_tokens) -> int # Budget-ratio depth
```

### Infrastructure Manager API

```python
class HierarchicalSummaryManager:
    async summarize(entry_id: str) -> SummarizeResult | None    # Build 4-level hierarchy
    async get_summary(entry_id: str, level: int) -> str | None  # Get specific level
    async retrieve_at_depth(query: str, max_tokens: int) -> str # Depth-adaptive retrieval
```

### Architecture

```
MemoryHierarchy.summarize_entry(entry_id)
    │
    └── HierarchicalSummaryManager.summarize()
        │
        ├── memory_repo.get_by_id()
        ├── _has_hierarchy() check (skip if exists)
        ├── LLM path: _summarize_with_llm() → JSON parse → {0: orig, 1-3: summaries}
        │   └── fallback: build_extractive_hierarchy() on LLM error
        ├── No-LLM path: HierarchicalSummarizer.build_extractive_hierarchy()
        ├── Persist: hierarchy_summaries + hierarchy_token_counts in metadata
        └── Return SummarizeResult

MemoryHierarchy.retrieve_at_depth(query, max_tokens)
    │
    └── HierarchicalSummaryManager.retrieve_at_depth()
        │
        ├── memory_repo.search(query, top_k=10)
        ├── For each entry: select_level(token_counts, remaining_budget)
        └── Assemble parts within budget → join with "---"
```

### Metadata Serialization

```python
# Stored in MemoryEntry.metadata:
hierarchy_summaries    = '{"0": "original...", "1": "summary...", "2": "brief...", "3": "topic"}'
hierarchy_token_counts = '{"0": 500, "1": 200, "2": 75, "3": 25}'
```

### Files Created/Modified

- **Created**: `domain/services/hierarchical_summarizer.py` (pure static: 6 methods)
- **Created**: `infrastructure/memory/hierarchical_summarizer.py` (HierarchicalSummaryManager + SummarizeResult)
- **Created**: `tests/unit/domain/test_hierarchical_summarizer.py` (27 tests)
- **Created**: `tests/unit/infrastructure/test_hierarchical_summarizer.py` (24 tests)
- **Modified**: `infrastructure/memory/__init__.py` (export HierarchicalSummaryManager)
- **Modified**: `infrastructure/memory/memory_hierarchy.py` (added summarize_entry, retrieve_at_depth)
- **Modified**: `interface/api/container.py` (wired HierarchicalSummaryManager with optional LLM)
- **Tests**: 51 new tests (27 domain + 24 infrastructure), total 618 passing

---

## TD-038: Two-Tier Routing Architecture (Agent CLI Orchestration)

**Date**: 2026-02-27
**Status**: Accepted
**Sprint**: 4.1

### Decision

Introduce a two-tier routing architecture:

| Tier | Component | Selects | Location |
|---|---|---|---|
| Tier 1 (NEW) | `AgentEngineRouter` | Execution ENGINE (OpenHands, Claude Code, etc.) | `domain/services/` |
| Tier 2 (EXISTING) | `LiteLLMGateway` | LLM MODEL (claude-sonnet, qwen3, etc.) | `infrastructure/llm/` |

### Key Decisions

1. **ABC not Protocol**: `AgentEnginePort` uses ABC (consistent with all other ports: `LLMGateway`, `TaskRepository`, etc.)
2. **Domain router is pure**: `AgentEngineRouter` has static methods only, no I/O, no constructor dependencies (follows `RiskAssessor` pattern)
3. **TaskType extended**: Added `LONG_RUNNING_DEV` and `WORKFLOW_PIPELINE` to existing `TaskType` enum. Existing `TASK_MODEL_MAP.get()` calls fall through to default — zero impact on LiteLLMGateway
4. **AgentEngineType**: 6 members matching CLAUDE.md: OPENHANDS, CLAUDE_CODE, GEMINI_CLI, CODEX_CLI, ADK, OLLAMA
5. **Heuristic priority**: budget=0 → OLLAMA > hours>1 → OPENHANDS > tokens>100K → GEMINI_CLI > primary map
6. **Fallback chain**: Every engine has a defined fallback chain. OLLAMA is always the ultimate fallback (empty chain itself)

### Files Created/Modified

- **Created**: `domain/value_objects/agent_engine.py` (AgentEngineType enum, 6 members)
- **Created**: `domain/ports/agent_engine.py` (AgentEnginePort ABC + AgentEngineResult + AgentEngineCapabilities)
- **Created**: `domain/services/agent_engine_router.py` (pure static: select, get_fallback_chain, select_with_fallbacks)
- **Created**: `infrastructure/agent_cli/__init__.py` (empty package, drivers in Sprint 4.2+)
- **Created**: `tests/unit/domain/test_agent_engine_router.py` (36 tests)
- **Created**: `tests/unit/domain/test_agent_engine_port.py` (10 tests)
- **Modified**: `domain/value_objects/model_tier.py` (+2 TaskType members)
- **Modified**: `domain/value_objects/__init__.py` (export AgentEngineType)
- **Modified**: `domain/ports/__init__.py` (export AgentEnginePort, AgentEngineResult, AgentEngineCapabilities)
- **Modified**: `domain/services/__init__.py` (export AgentEngineRouter)
- **Tests**: 46 new tests, total 729 unit tests passing

---

## TD-039: Agent CLI Engine Drivers (5 Concrete Implementations)

**Date**: 2026-02-27
**Status**: Accepted
**Sprint**: 4.2

### Decision

Implement 5 concrete drivers in `infrastructure/agent_cli/` fulfilling the `AgentEnginePort` interface from TD-038. ADK driver deferred (requires `google-adk` pip dep; router fallback chain handles gracefully).

### Key Decisions

1. **SubprocessMixin** (`_subprocess_base.py`): 3 CLI drivers (Claude Code, Codex, Gemini) share `_run_cli()` + `_check_cli_exists()`. Mixin avoids diamond inheritance with ABC
2. **OllamaEngineDriver wraps LiteLLMGateway**: Reuses existing cost tracking, model routing. Auto-prefixes `ollama/` to model names
3. **OpenHandsDriver uses httpx REST**: POST create + GET poll pattern (not subprocess). Supports optional Bearer token auth
4. **Errors as `AgentEngineResult(success=False)`**: Never raise from `run_task()` — consistent with port contract
5. **No new pip dependencies**: subprocess (stdlib) + httpx (already available)
6. **+4 Settings fields**: `openhands_api_key`, `claude_code_cli_path`, `codex_cli_path`, `gemini_cli_path` — all optional with sensible defaults
7. **ADK skipped entirely**: Fallback chain handles: ADK -> GEMINI_CLI -> CLAUDE_CODE -> OLLAMA

### Driver Summary

| Driver | Engine Type | Transport | Key Capability |
|---|---|---|---|
| OllamaEngineDriver | OLLAMA | LiteLLMGateway (reuse) | $0 cost, local |
| ClaudeCodeDriver | CLAUDE_CODE | subprocess (`claude -p`) | 200K ctx, parallel, streaming |
| CodexCLIDriver | CODEX_CLI | subprocess (`codex exec`) | sandbox, MCP |
| GeminiCLIDriver | GEMINI_CLI | subprocess (`gemini -p`) | 2M ctx |
| OpenHandsDriver | OPENHANDS | httpx REST (POST+poll) | sandbox, parallel, streaming |

### Files Created/Modified

- **Created**: `infrastructure/agent_cli/_subprocess_base.py` (CLIResult + SubprocessMixin)
- **Created**: `infrastructure/agent_cli/ollama_driver.py`
- **Created**: `infrastructure/agent_cli/claude_code_driver.py`
- **Created**: `infrastructure/agent_cli/codex_cli_driver.py`
- **Created**: `infrastructure/agent_cli/gemini_cli_driver.py`
- **Created**: `infrastructure/agent_cli/openhands_driver.py`
- **Created**: `tests/unit/infrastructure/test_ollama_driver.py` (13 tests)
- **Created**: `tests/unit/infrastructure/test_claude_code_driver.py` (16 tests)
- **Created**: `tests/unit/infrastructure/test_codex_cli_driver.py` (16 tests)
- **Created**: `tests/unit/infrastructure/test_gemini_cli_driver.py` (16 tests)
- **Created**: `tests/unit/infrastructure/test_openhands_driver.py` (18 tests)
- **Modified**: `shared/config.py` (+4 fields)
- **Modified**: `infrastructure/agent_cli/__init__.py` (re-exports all 5 drivers)
- **Modified**: `interface/api/container.py` (+`_wire_agent_drivers()` method)
- **Tests**: 92 new tests, total 821 unit tests passing

---

## TD-040: ADK Driver — Google ADK via Python SDK (Sprint 4.5)

**Date**: 2026-03-05
**Status**: Accepted
**Sprint**: 4.5

### Decision

Implement `ADKDriver` using the Google ADK Python SDK (`google-adk`) as an **optional dependency** with try-import guard. Sprint 4.5 wraps a single `LlmAgent.run()` call; SequentialAgent/ParallelAgent workflows are Phase 5+ scope.

### Key Decisions

1. **Optional dependency**: `google-adk` added as `[adk]` extra in pyproject.toml, not a core dependency. Same pattern as neo4j/pgvector elsewhere in the codebase
2. **Try-import guard**: Module-level `_ADK_AVAILABLE` sentinel. When package missing, SDK classes assigned `None`. `is_available()` checks both `_enabled` flag and `_ADK_AVAILABLE`
3. **Error result, never raise**: `run_task()` returns `AgentEngineResult(success=False)` for disabled/not-installed/exception cases — consistent with all other drivers (TD-039)
4. **LlmAgent → Runner → run_async**: Single-agent wrapper using `InMemorySessionService`. No persistent sessions. Final response extracted from event stream via `is_final_response()`
5. **2M token context**: Capabilities report `max_context_tokens=2_000_000`, same as Gemini CLI driver. `supports_parallel=True`, `supports_mcp=True`, `cost_per_hour_usd=0.0`
6. **Default model**: `gemini-2.5-flash` (configurable via `adk_default_model` setting)

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| CLI subprocess (`gemini` binary) | Already covered by GeminiCLIDriver. ADK adds SDK-level features (SequentialAgent, ParallelAgent) not available via CLI |
| Core dependency | google-adk has heavy transitive deps. Optional extra keeps core install lean |
| Defer indefinitely | ADK is defined in domain (`AgentEngineType.ADK`) and router maps `WORKFLOW_PIPELINE → ADK`. Having the driver completes the engine matrix |

### Files Created/Modified

- **Created**: `infrastructure/agent_cli/adk_driver.py`
- **Created**: `tests/unit/infrastructure/test_adk_driver.py` (17 tests, 4 classes)
- **Modified**: `pyproject.toml` (+`adk` optional dep group)
- **Modified**: `shared/config.py` (+`adk_enabled`, `adk_default_model`)
- **Modified**: `infrastructure/agent_cli/__init__.py` (re-exports 6 drivers)
- **Modified**: `interface/api/container.py` (+ADK wiring)
- **Modified**: `tests/integration/test_agent_engines.py` (+ADK fixture, +TestADKEngineLive, updated counts)
- **Tests**: 17 new unit tests, total 881 unit tests passing

---

## TD-041: Knowledge File Management — Engine-Specific Context Injection (Sprint 4.6)

**Date**: 2026-03-05
**Status**: Accepted
**Sprint**: 4.6

### Decision

Inject engine-specific project context at the **use case layer** (`RouteToEngineUseCase.execute()`), not at the driver level. A new `KnowledgeFileLoader` (infrastructure) reads conventional files from the project root and the use case prepends context to the task string.

### Key Decisions

1. **Use case layer injection**: Context injection is orchestration logic, not driver logic. The `AgentEnginePort.run_task()` signature is unchanged — fully backward compatible. No ABC modifications required
2. **Conventional file mapping**: Static mapping from engine type to filename. Claude Code → `CLAUDE.md`, Codex CLI → `AGENTS.md`, Gemini CLI/ADK → `llms-full.txt`, Ollama/OpenHands → None
3. **Prepend format**: `f"{context}\n\n---\n\nTask: {task}"` — simple, clear separator between context and task. Empty/None context passes task unchanged
4. **`format_context()` combines sources**: Knowledge file content + optional extra context. Returns None when both are absent
5. **CLI + API surface**: `--context` / `-c` flag on `morphic engine run`, `context` field on `EngineRunRequest`. Both optional, default None
6. **Infrastructure placement**: `KnowledgeFileLoader` lives in `infrastructure/agent_cli/` alongside drivers — it reads the filesystem (I/O), so it belongs in infrastructure

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| Modify `AgentEnginePort.run_task()` signature | Breaking change to all 6 drivers. Context injection is orchestration, not engine concern |
| Per-driver knowledge loading | Duplicates logic across 6 drivers. Violates DRY. Use case is the single orchestration point |
| Domain port for knowledge files | Over-engineering — knowledge files are a thin filesystem read, not a domain concept |
| Auto-inject on every run | Not all tasks benefit from context. Explicit `context` param gives callers control |

### Engine → Knowledge File Mapping

| Engine | File | Rationale |
|---|---|---|
| CLAUDE_CODE | `CLAUDE.md` | Claude Code's native project context file |
| CODEX_CLI | `AGENTS.md` | Codex CLI's native agents context file |
| GEMINI_CLI | `llms-full.txt` | ADK convention for LLM knowledge base |
| ADK | `llms-full.txt` | Same as Gemini CLI (shared Google ecosystem) |
| OLLAMA | None | Local model, no project context convention |
| OPENHANDS | None | Docker sandbox, context handled internally |

### Files Created/Modified

- **Created**: `infrastructure/agent_cli/knowledge_loader.py`
- **Created**: `tests/unit/infrastructure/test_knowledge_loader.py` (13 tests, 3 classes)
- **Modified**: `application/use_cases/route_to_engine.py` (+`context` param, prepend logic)
- **Modified**: `interface/api/schemas.py` (+`context` field on `EngineRunRequest`)
- **Modified**: `interface/api/routes/engines.py` (pass `context=body.context`)
- **Modified**: `interface/cli/commands/engine.py` (+`--context` / `-c` flag)
- **Modified**: `tests/unit/application/test_route_to_engine.py` (+4 context injection tests)
- **Tests**: 17 new tests (13 loader + 4 context), total 898 unit tests passing

---

## TD-042: Tool Safety Scorer — Multi-Signal Scoring (Sprint 5.1)

**Date**: 2026-03-05
**Status**: Accepted
**Sprint**: 5.1

### Decision

Implement a pure domain service `ToolSafetyScorer` that computes a composite safety score from metadata signals and maps it to a `SafetyTier` enum. No I/O, no LLM dependency.

### Key Decisions

1. **SafetyTier as IntEnum**: `UNSAFE(0)`, `EXPERIMENTAL(1)`, `COMMUNITY(2)`, `VERIFIED(3)`. IntEnum allows comparison operators (`>=`, `<`) for threshold gating
2. **4-signal composite score**: Publisher trust (0.40), transport protocol (0.25), popularity (0.15), metadata completeness (0.20). Weights emphasize provenance over popularity
3. **Trusted publisher list**: `modelcontextprotocol`, `anthropic`, `google`, `microsoft`, `github`, `openai` — hardcoded in domain service, not configurable (security-sensitive)
4. **Suspicious pattern forced UNSAFE**: Regex patterns for `shell_exec`, `eval`, `rm -rf`, `sudo`, `curl.*|.*sh` force `SafetyTier.UNSAFE` regardless of score
5. **Transport trust map**: `stdio` (1.0) > `streamable-http` (0.8) > `sse` (0.7) > unknown (0.3). Local transports are more trustworthy
6. **ToolCandidate entity**: Pydantic strict model with all optional fields except `name` and `safety_tier`. Reused across all marketplace layers

### Tier Mapping

| Score Range | Tier |
|---|---|
| >= 0.70 | VERIFIED |
| >= 0.40 | COMMUNITY |
| >= 0.20 | EXPERIMENTAL |
| < 0.20 | UNSAFE |

### Files Created

- `domain/value_objects/tool_safety.py` — SafetyTier IntEnum
- `domain/entities/tool_candidate.py` — ToolCandidate Pydantic entity
- `domain/services/tool_safety_scorer.py` — ToolSafetyScorer (static methods)
- `tests/unit/domain/test_tool_candidate.py` — 8 tests
- `tests/unit/domain/test_tool_safety_scorer.py` — 14 tests

---

## TD-043: MCP Registry Client — HTTP Search Adapter (Sprint 5.2)

**Date**: 2026-03-05
**Status**: Accepted
**Sprint**: 5.2

### Decision

Implement `MCPRegistryClient` as the `ToolRegistryPort` adapter, querying `registry.modelcontextprotocol.io` via httpx GET. Each result is auto-scored by `ToolSafetyScorer`.

### Key Decisions

1. **Constructor injection**: `MCPRegistryClient(safety_scorer, base_url)` — scorer is injected, base_url defaults to MCP Registry
2. **Graceful error handling**: HTTP failures return empty `ToolSearchResult` with error message — never raises exceptions
3. **Dual response format**: Handles both list `[{...}]` and dict `{"results": [...]}` response formats from registry
4. **Auto-generated install commands**: Computes `install_command` from `package_name` and `transport` metadata
5. **No caching**: Phase 5 scope; caching is Phase 6 optimization

### Files Created

- `domain/ports/tool_registry.py` — ToolRegistryPort ABC + ToolSearchResult
- `infrastructure/marketplace/mcp_registry_client.py` — MCPRegistryClient
- `tests/unit/infrastructure/test_mcp_registry_client.py` — 14 tests

---

## TD-044: Tool Installer — Safety-Gated Subprocess Install (Sprint 5.3)

**Date**: 2026-03-05
**Status**: Accepted
**Sprint**: 5.3

### Decision

Implement `MCPToolInstaller` as the `ToolInstallerPort` adapter. Installs MCP tool packages via subprocess (`npm install -g` / `pip install`). Refuses `SafetyTier.UNSAFE` tools. Tracks installed tools in-memory.

### Key Decisions

1. **Safety gate**: `install()` returns failure for `SafetyTier.UNSAFE` tools — hard block, not configurable
2. **Subprocess execution**: Uses `asyncio.create_subprocess_exec` for npm/pip. Based on `SubprocessMixin` pattern from agent CLI drivers
3. **In-memory tracking**: `_installed: dict[str, ToolCandidate]` — no database table. Resets on process restart (sufficient for Phase 5)
4. **Sync `list_installed()` and `is_installed()`**: Synchronous methods returning from in-memory dict — no I/O needed
5. **Full vertical slice**: Port → Infra → Use Case → API → CLI in one sprint for rapid integration testing

### API Endpoints (8 total for Phase 5)

| Endpoint | Method | Sprint |
|---|---|---|
| `/api/marketplace/search` | GET | 5.3 |
| `/api/marketplace/install` | POST | 5.3 |
| `/api/marketplace/installed` | GET | 5.3 |
| `/api/marketplace/suggest` | POST | 5.4 |
| `/api/marketplace/{name}` | DELETE | 5.3 |
| `/api/models/pull` | POST | 5.5 |
| `/api/models/{name}` | DELETE | 5.5 |
| `/api/models/switch` | POST | 5.5 |

### Files Created

- `domain/ports/tool_installer.py` — ToolInstallerPort ABC + InstallResult
- `infrastructure/marketplace/tool_installer.py` — MCPToolInstaller
- `application/use_cases/install_tool.py` — InstallToolUseCase + InstallByNameResult
- `interface/api/routes/marketplace.py` — 5 marketplace endpoints
- `interface/cli/commands/marketplace.py` — 5 CLI commands
- Tests: 36 new (11 + 9 + 10 + 6)

---

## TD-045: Auto Tool Discoverer — Error-Pattern-Based Suggestions (Sprint 5.4)

**Date**: 2026-03-05
**Status**: Accepted
**Sprint**: 5.4

### Decision

Implement `FailureAnalyzer` (pure domain) + `DiscoverToolsUseCase` (application) for automatic tool suggestions when tasks fail. Uses regex pattern matching, not LLM inference (LLM-based = Phase 6).

### Key Decisions

1. **Pure domain FailureAnalyzer**: Static regex patterns map error keywords to MCP search queries. No I/O, no LLM. Examples: `FileNotFoundError` → `["filesystem", "file"]`, `database.*refused` → `["postgres", "database"]`
2. **Top-3 query limit**: At most 3 registry searches per failure, preventing API abuse
3. **Deduplication by name**: Same tool from different queries counted once, keeping highest score
4. **Sorted by safety_score descending**: Safest tools recommended first
5. **Optional task_description context**: Adds task-related keywords to error-extracted queries for better search relevance

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| LLM-based error analysis | Too expensive for every failure. Deferred to Phase 6 Self-Evolution |
| Keyword extraction (TF-IDF) | Over-engineering for Phase 5. Simple regex patterns cover 80% of common errors |

### Files Created

- `domain/services/failure_analyzer.py` — FailureAnalyzer (regex patterns)
- `application/use_cases/discover_tools.py` — DiscoverToolsUseCase + ToolSuggestions
- Tests: 21 new (12 + 9)

---

## TD-046: Ollama Manager Extended — Delete/Info/Switch/Running (Sprint 5.5)

**Date**: 2026-03-05
**Status**: Accepted
**Sprint**: 5.5

### Decision

Extend existing `OllamaManager` with `delete_model()`, `model_info()`, `get_running_models()`. Create `ManageOllamaUseCase` for orchestration. Add API/CLI endpoints.

### Key Decisions

1. **No new port**: `ManageOllamaUseCase` takes `OllamaManager` directly (same pattern as existing container). Ollama is a concrete infrastructure concern, not a domain abstraction
2. **Ollama API mapping**: `DELETE /api/delete` (delete), `POST /api/show` (info), `GET /api/ps` (running)
3. **Switch with auto-pull**: `switch_default()` pulls model if not locally available, then updates settings
4. **Settings mutation**: `ManageOllamaUseCase.switch_default()` mutates `settings.ollama_default_model` directly — consistent with existing pattern

### Files Created/Modified

- `application/use_cases/manage_ollama.py` — ManageOllamaUseCase
- Extended: `infrastructure/llm/ollama_manager.py` (+3 methods)
- Extended: `interface/api/routes/models.py` (+5 endpoints)
- Extended: `interface/cli/commands/model.py` (+3 commands)
- Tests: 16 new (6 manager + 10 use case)

---

## TD-047: Marketplace UI — Next.js Search + Model Management (Sprint 5.6)

**Date**: 2026-03-05
**Status**: Accepted
**Sprint**: 5.6

### Decision

Implement marketplace search UI and Ollama model management pages following established Next.js patterns (client components, raw Tailwind, CSS custom properties).

### Key Decisions

1. **Debounced search (400ms)**: `SearchBar` uses `useRef` timer to avoid excessive API calls during typing
2. **Two-tab marketplace**: Search (default) + Installed — single page with tab toggle, same pattern as Dashboard Execute/Plan toggle
3. **Confirm-before-uninstall**: `InstallButton` requires double-click for uninstall (first click shows "Confirm?")
4. **Safety badge colors**: Verified=emerald, Community=cyan, Experimental=yellow, Unsafe=red — consistent with CLAUDE.md theme spec
5. **Header navigation**: Added `Marketplace` and `Models` links to root `layout.tsx` header
6. **No external UI library**: Raw Tailwind CSS with CSS custom properties, consistent with all existing components

### Files Created

- `ui/app/marketplace/page.tsx` — Search + browse + installed tab
- `ui/app/marketplace/components/SearchBar.tsx` — Debounced search input
- `ui/app/marketplace/components/ToolCard.tsx` — Tool result card
- `ui/app/marketplace/components/SafetyBadge.tsx` — Safety tier badge
- `ui/app/marketplace/components/InstallButton.tsx` — Install/uninstall with confirm
- `ui/app/models/page.tsx` — Model pull/delete/switch + status
- Modified: `ui/app/layout.tsx` — Added nav links
- Modified: `ui/lib/api.ts` — Added marketplace + model API wrappers

---

## TD-048: Self-Evolution Engine — 3-Tier Architecture (Phase 6)

**Date**: 2026-03-05
**Status**: Accepted
**Sprint**: 6.1–6.5

### Decision

Implement a 3-tier self-evolution engine that learns from execution history at different time scales:

| Level | Name | Time Scale | Trigger | Component |
|---|---|---|---|---|
| 1 | Tactical | Seconds | Action fails | `TacticalRecovery` (pure domain service) |
| 2 | Strategic | Minutes | Periodic/manual | `UpdateStrategyUseCase` |
| 3 | Systemic | Hours | Periodic/manual | `SystemicEvolutionUseCase` |

### Key Decisions

1. **ExecutionRecord as immutable snapshot**: Each execution produces one record with task_type, engine, model, success, cost, duration, cache_hit_rate, user_rating. Append-only (Manus principle 3)
2. **TacticalRecovery is pure domain**: Static methods with regex pattern matching. No I/O, no constructor deps. Deterministic output
3. **JSONL persistence for strategies**: `StrategyStore` uses append-only JSONL files (`recovery_rules.jsonl`, `model_preferences.jsonl`, `engine_preferences.jsonl`). Filesystem as infinite context
4. **Min sample filter**: Requires configurable minimum samples (default 10) before computing preferences. Prevents overfitting on small data
5. **SystemicEvolution composes existing use cases**: Reuses `AnalyzeExecutionUseCase` + `UpdateStrategyUseCase` + `DiscoverToolsUseCase` (Phase 5). No duplication
6. **InMemory repository first**: `InMemoryExecutionRecordRepository` for dev/testing. PostgreSQL migration deferred

### Rationale

- 3-tier separation matches natural learning time scales (immediate → session → long-term)
- Pure domain service for Level 1 enables zero-latency in-task recovery
- JSONL persistence survives process restarts without DB dependency
- Composing Phase 5's DiscoverToolsUseCase for Level 3 avoids reimplementing tool gap detection

### Files Created

- `domain/entities/execution_record.py` — ExecutionRecord entity
- `domain/entities/strategy.py` — RecoveryRule, ModelPreference, EnginePreference
- `domain/value_objects/evolution.py` — EvolutionLevel enum
- `domain/ports/execution_record_repository.py` — ABC + ExecutionStats
- `domain/services/tactical_recovery.py` — Level 1 pure logic
- `application/use_cases/analyze_execution.py` — Level 1-2 analytics
- `application/use_cases/update_strategy.py` — Level 2 learning
- `application/use_cases/systemic_evolution.py` — Level 3 evolution
- `infrastructure/persistence/in_memory_execution_record.py` — InMemory repo
- `infrastructure/evolution/strategy_store.py` — JSONL persistence
- `interface/api/routes/evolution.py` — 5 API endpoints
- `interface/cli/commands/evolution.py` — 4 CLI commands
- `ui/app/evolution/page.tsx` — Dashboard scaffold
- Tests: 11 test files (~174 new tests)

---

## TD-049: Phase 6 Complete — Architecture Retrospective

**Date**: 2026-03-05
**Status**: Record

### Summary

Phase 6 Self-Evolution (5 sprints, 6.1→6.5) is complete. 1162 unit tests + 37 integration tests, all passing. 0 failures (including fix of 19 pre-existing MCP server test failures).

### What Was Built

| Sprint | Deliverable | Key Metric |
|---|---|---|
| 6.1 | ExecutionRecord + EvolutionLevel + ABC + AnalyzeExecution | Domain foundation |
| 6.2 | TacticalRecovery (Level 1) | Pure domain, 0 I/O |
| 6.3 | Strategy entities + StrategyStore + UpdateStrategy (Level 2) | JSONL persistence |
| 6.4 | SystemicEvolution (Level 3) | Composes Phase 5 DiscoverTools |
| 6.5 | API (5 endpoints) + CLI (4 commands) + UI scaffold | Full vertical slice |

### Architecture Decisions That Proved Correct

1. **Clean Architecture composability**: SystemicEvolutionUseCase trivially composes AnalyzeExecution + UpdateStrategy + DiscoverTools with zero coupling
2. **JSONL for strategy persistence**: Simple, debuggable, append-only. No DB migration needed
3. **Pure domain TacticalRecovery**: Testable without mocks, can be called synchronously in action loops
4. **Configurable min_samples**: Prevents overfitting. Sensible defaults with env var override

### Technical Debt to Address

1. **InMemory execution records**: Lose data on restart → PostgreSQL migration in future
2. **No auto-recording hook**: ExecutionRecords must be manually recorded → hook into ExecuteTaskUseCase
3. **No background scheduling**: Strategy updates are manual → Celery/APScheduler periodic jobs
4. **Regex-only pattern matching**: TacticalRecovery uses regex → LLM-powered analysis in future
5. **UI is scaffold**: Evolution dashboard needs charts, real-time updates, export

### Key Metrics

```
Unit tests:          1162 (4.82s), 0 failures
Integration tests:    37
Python files:        ~80
TypeScript files:    ~18
Domain ports:        14 ABC interfaces
Domain services:     10 (incl. tactical_recovery)
Use cases:           12
API endpoints:       ~30
CLI subcommands:     ~25
```

---

## TD-050: Unified Cognitive Layer (UCL) — Beyond A2A

**Date**: 2026-03-10
**Status**: Accepted (Phase 7 redesign)

### Problem

The original Phase 7 plan was "A2A Protocol + Benchmarks" — standard agent-to-agent task delegation. But the real problem is deeper: **every AI agent is a cognitive island**.

```
Current reality:
  Claude Code ──── own context, own memory, own task state
  Cursor     ──── own context, own memory, own task state
  Gemini     ──── own context, own memory, own task state
  ChatGPT    ──── own context, own memory, own task state

  Human = the "bus" connecting these islands (copy-paste, re-explain, repeat)
```

A2A solves task delegation ("Agent A asks Agent B to do X") but does NOT solve:
- **Memory sharing**: Agent B doesn't know what Agent A learned
- **Task continuity**: Agent B can't pick up where Agent A left off
- **Decision context**: Agent B doesn't know WHY Agent A made certain choices

### Decision

Replace Phase 7's simple A2A protocol with a **Unified Cognitive Layer (UCL)** — a shared substrate for memory, task state, and context across all agent engines.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                   Unified Cognitive Layer (UCL)                      │
│                                                                     │
│  ┌─────────────────────┐     ┌─────────────────────┐               │
│  │  Shared Task State   │     │  Shared Memory       │               │
│  │                     │     │  (4-type hierarchy)  │               │
│  │  • Active goals     │     │                     │               │
│  │  • SubTask progress │     │  • Episodic:  what happened          │
│  │  • Decisions made   │     │  • Semantic:  what we know           │
│  │  • Artifacts        │     │  • Procedural: how to do things     │
│  │  • Blockers         │     │  • Working:   what we're doing now  │
│  └─────────────────────┘     └─────────────────────┘               │
│                                                                     │
│  ┌─────────────────────┐     ┌─────────────────────┐               │
│  │  Context Adapters    │     │  Insight Extractor   │               │
│  │  (per-engine, bidi) │     │  (post-execution)   │               │
│  │                     │     │                     │               │
│  │  UCL → engine fmt   │     │  engine output → UCL │               │
│  │  CLAUDE.md, AGENTS  │     │  facts, decisions,  │               │
│  │  .md, llms-full.txt │     │  artifacts, errors  │               │
│  └─────────────────────┘     └─────────────────────┘               │
│                                                                     │
│  ┌─────────────────────┐     ┌─────────────────────┐               │
│  │  Agent Affinity      │     │  Conflict Resolver   │               │
│  │  (context-fit score)│     │  (confidence-weight) │               │
│  │                     │     │                     │               │
│  │  "Who knows most    │     │  Agent A says X,    │               │
│  │   about this topic?"│     │  Agent B says Y     │               │
│  │                     │     │  → resolve by score  │               │
│  └─────────────────────┘     └─────────────────────┘               │
└─────────────────────────────────────────────────────────────────────┘
         ↕                    ↕                    ↕
   Claude Code           Gemini CLI           Codex CLI ...
```

### 4 Memory Types

| Type | Purpose | Example | Maps to Existing |
|---|---|---|---|
| **Episodic** | What happened (cross-agent history) | "Claude Code refactored auth.py in Sprint 3" | L2 MemoryRepository |
| **Semantic** | What we know (project world model) | "API uses JWT, DB is PostgreSQL" | L3 KnowledgeGraphPort |
| **Procedural** | How to do things (learned workflows) | "Tests go in tests/unit/, run with uv run pytest" | RecoveryRule, Strategy |
| **Working** | What we're doing now (active context) | Current goals, blockers, in-progress tasks | L1 ActiveContext + TaskEntity |

### Shared Task State

Beyond memory, agents share **task state** — not just "what task to do" but full lifecycle:

```python
class SharedTaskState:
    """Cross-agent task awareness. Any agent can see and continue any task."""
    goal: str                          # What we're trying to achieve
    subtasks: list[SubTask]            # Current decomposition with statuses
    decisions: list[Decision]          # WHY choices were made (not just WHAT)
    artifacts: dict[str, str]          # Files created, outputs generated
    blockers: list[str]               # What's preventing progress
    agent_history: list[AgentAction]   # Which agent did what (audit trail)
```

Key capability: **Task handoff** — Agent A partially completes, UCL captures state, Agent B continues seamlessly.

### Context Adapter Pattern

Each engine speaks a different "context language". Adapters translate bidirectionally:

| Engine | Inject Format | Extract Targets |
|---|---|---|
| Claude Code | CLAUDE.md + compressed memory | Decisions, code changes, reasoning |
| Codex CLI | AGENTS.md + task context | Code output, test results |
| Gemini CLI | Full context dump (2M allows it) | Research findings, analysis |
| ADK | Workflow state + tool results | Pipeline outputs, errors |
| OpenHands | REST task description + sandbox state | Artifacts, test results |
| Ollama | Heavily compressed (small window) | Draft outputs |

This is analogous to **device drivers in an OS** — the kernel has a unified I/O model, each driver translates to hardware-specific protocols.

### Insight Extraction Pipeline

After every agent execution, structured insights flow back to UCL:

```
Agent execution completes
    → Extract structured facts (entities, relationships)
    → Extract decisions (what was chosen and why)
    → Extract artifacts (files created/modified)
    → Extract errors (what failed and potential fixes)
    → Conflict check (does this contradict existing memory?)
    → Store in appropriate memory type (episodic/semantic/procedural)
    → Update shared task state (progress, blockers)
```

### Agent Affinity Scoring

Not just "which engine is cheapest" but "which engine knows most about this topic":

```python
affinity_score = (
    context_familiarity * 0.40    # Has this engine worked on related tasks?
    + recency * 0.25              # How recently did it work on this area?
    + success_rate * 0.20         # How often does it succeed with this task type?
    + cost_efficiency * 0.15      # Cost per quality unit
)
```

### Builds on Existing Foundations

| Existing Component | Role in UCL |
|---|---|
| SemanticFingerprint (LSH) | Content-addressable key for deduplication across agents |
| ContextZipper | Per-engine compression with token budgets |
| ContextBridge | Evolves into Context Adapters (already has 4-platform export) |
| ForgettingCurve | Governs UCL memory lifecycle |
| DeltaEncoder | Tracks shared state changes (Git-style) |
| HierarchicalSummarizer | Multi-level UCL views for different context windows |
| StrategyStore (JSONL) | Persists agent affinity and procedural memory |
| ExecutionRecord | Feeds insight extraction pipeline |
| AgentEngineRouter | Extended with affinity scoring |

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| Simple A2A (task delegation only) | Doesn't solve memory sharing or context continuity |
| Shared vector DB only | No task state sharing, no structured facts, no conflict resolution |
| Single mega-agent (one model does everything) | No model excels at everything. Specialization + unification > generalization |
| MCP-only integration | MCP is tool-level, not cognition-level. Agents need shared understanding, not just shared tools |

### Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Extraction quality varies by engine | Structured output templates per engine, fallback to keyword extraction |
| Memory conflicts across agents | Confidence-weighted resolution + human-in-the-loop for high-stakes |
| Context adapter maintenance burden | Abstract adapter interface, most logic shared |
| Over-sharing sensitive information | Memory classification (RiskLevel applied to memories) |
| Performance overhead of extraction | Async post-execution, non-blocking |

---

## TD-051: Shared Task State — Cross-Agent Task Continuity

**Date**: 2026-03-10
**Status**: Accepted (Phase 7, Sprint 7.2)

### Decision

Extend TaskEntity with cross-agent awareness: decisions log, artifact tracking, and agent action history. Any agent can see full task state and continue where another left off.

### Design

```python
# New domain entities (domain/entities/cognitive.py)

class Decision(BaseModel):
    """Records WHY a choice was made, not just WHAT."""
    model_config = ConfigDict(strict=True, validate_assignment=True)
    description: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    agent_engine: AgentEngineType
    timestamp: datetime
    confidence: float = Field(ge=0.0, le=1.0)

class AgentAction(BaseModel):
    """Audit trail of which agent did what."""
    model_config = ConfigDict(strict=True, validate_assignment=True)
    agent_engine: AgentEngineType
    action_type: str = Field(min_length=1)   # "execute", "plan", "review", "handoff"
    summary: str = Field(min_length=1)
    timestamp: datetime
    cost_usd: float = Field(ge=0.0)

class SharedTaskState(BaseModel):
    """Cross-agent task awareness."""
    model_config = ConfigDict(strict=True, validate_assignment=True)
    task_id: str = Field(min_length=1)
    decisions: list[Decision] = Field(default_factory=list)
    artifacts: dict[str, str] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    agent_history: list[AgentAction] = Field(default_factory=list)
```

### Rationale

- **Decisions**: Without recording WHY, the next agent makes the same mistake or contradicts
- **Artifacts**: Agent B needs to know what files Agent A created/modified
- **Agent history**: Full audit trail enables affinity scoring and debugging
- **Blockers**: Shared blocker awareness prevents duplicate failed attempts

### Integration with TaskEntity

SharedTaskState is a **companion** to TaskEntity, not a replacement. TaskEntity stays clean (domain). SharedTaskState is managed by UCL (application layer).

```
TaskEntity (domain)  ←→  SharedTaskState (UCL)
    goal, subtasks            decisions, artifacts, agent_history
    status, cost              blockers, handoff context
```

---

## TD-052: Context Adapter Pattern — OS Device Driver Analogy

**Date**: 2026-03-10
**Status**: Accepted (Phase 7, Sprint 7.2)

### Problem

Each agent engine speaks a different "context language":
- Claude Code expects CLAUDE.md markdown
- Codex CLI expects AGENTS.md format
- Gemini CLI can accept 2M tokens of XML-tagged context
- Ollama needs ultra-compact context (small window)
- OpenHands receives REST task descriptions
- ADK uses workflow-state XML

UCL needs bidirectional translation: inject shared state into each engine's format, and extract insights from each engine's output.

### Decision

Create a `ContextAdapterPort` ABC with `inject_context()` and `extract_insights()` methods, implemented by 6 engine-specific adapters. Shared regex patterns and formatters live in `_base.py`.

### Architecture

```
ContextAdapterPort (domain/ports/)
    │
    ├── inject_context(state, memory, max_tokens) → str
    │   Translates UCL SharedTaskState + memory into engine-specific format
    │
    └── extract_insights(output) → list[AdapterInsight]
        Extracts structured insights from raw engine output
```

Analogous to **OS device drivers**: the kernel (UCL) has a unified I/O model, each driver (adapter) translates to hardware-specific protocols.

### Per-Engine Format Choices

| Engine | Inject Format | Rationale |
|---|---|---|
| Claude Code | `# Morphic-Agent Shared Context` markdown | Matches CLAUDE.md convention |
| Gemini CLI | `<morphic-context>` XML blocks | XML tags help structure in 2M window |
| Codex CLI | `# AGENTS.md` flat markdown | Matches Codex AGENTS.md convention |
| Ollama | Ultra-compact key: value lines | Minimizes tokens for small context window |
| OpenHands | `# Task Context` REST description | Matches OpenHands task input format |
| ADK | `<workflow-context>` XML | Matches ADK workflow state pattern |

### Extraction Strategy

Regex-based keyword extraction (Phase 1). Patterns in `_base.py`:
- `_DECISION_PATTERN`: "decided/chose/selected/went with..."
- `_ERROR_PATTERN`: "error/failed/exception/traceback..."
- `_FILE_PATTERN`: "created/modified/wrote file..."
- `_FACT_PATTERN`: "uses/requires/depends on..."

LLM-enhanced extraction planned for Sprint 7.3.

### Confidence Calibration

Engine-specific confidence scores reflect model quality:
- Codex file artifacts: 0.9 (code-centric engine, high reliability)
- Claude Code decisions: 0.7 (strong reasoning)
- Gemini facts: 0.7 (research-focused)
- Ollama all insights: 0.4-0.6 (smaller models, lower reliability)

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| Single format for all engines | Wastes context window (Ollama), underutilizes capacity (Gemini 2M) |
| LLM-only extraction | Too slow for post-execution pipeline, regex sufficient for Phase 1 |
| Engine-specific ports (no shared ABC) | Prevents polymorphic adapter registry and unified testing |

---

## TD-053: InMemorySharedTaskStateRepository — Dev-First Persistence

**Date**: 2026-03-10
**Status**: Accepted (Phase 7, Sprint 7.2)

### Decision

Implement `SharedTaskStateRepository` as in-memory dict store for dev/testing. PG migration planned when persistence across restarts is needed.

### Design

- `dict[str, SharedTaskState]` storage keyed by `task_id`
- `list_active()` returns states with blockers OR updated within 24h
- All methods are async (consistent with DB-backed interface)
- `append_action()` delegates to `SharedTaskState.add_action()` (entity method)
- No-op on missing task_id (graceful degradation)

### Rationale

- Matches existing pattern (`InMemoryExecutionRecordRepository`)
- Zero infrastructure cost for development
- Port interface unchanged when migrating to PG

---

## TD-054: MemoryClassifier — Regex-Based Cognitive Type Classification

**Date**: 2026-03-11
**Status**: Accepted (Phase 7, Sprint 7.3)

### Decision

Pure static domain service using 4 pre-compiled regex patterns to classify free text into `CognitiveMemoryType`. Priority order: PROCEDURAL > SEMANTIC > WORKING > EPISODIC (default fallback).

### Design

- `classify(text)` → first-match wins (O(4) regexes)
- `classify_with_confidence(text)` → count hits per category, best category wins. Confidence = min(0.3 + hits × 0.2, 0.9)
- Keyword groups:
  - PROCEDURAL: "how to", "steps to", "strategy", "best practice", "always", "never", "avoid", "prefer"
  - SEMANTIC: "uses", "requires", "depends on", "version", "is a", "configured with", "supports"
  - WORKING: "currently", "in progress", "next step", "blocked", "pending", "remaining"
  - EPISODIC: "decided", "created", "failed", "error", "completed", "installed", "fixed"

### Rationale

- Regex is deterministic, fast, and zero-cost (no LLM needed)
- Priority ordering handles multi-category overlap predictably
- Hit-count confidence enables downstream use (e.g., reclassification threshold in InsightExtractor)
- Pure static → easy to test, no mocking required

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| LLM-based classification | Too slow for inline pipeline; regex sufficient for Phase 1 |
| ML classifier (sklearn) | Adds dependency; insufficient training data at this stage |
| Single-label only (no confidence) | Loses information needed by InsightExtractor reclassification logic |

---

## TD-055: ConflictResolver — Jaccard + Negation Conflict Detection

**Date**: 2026-03-11
**Status**: Accepted (Phase 7, Sprint 7.3)

### Decision

Pure static domain service that detects contradictions between `ExtractedInsight` items using three criteria, then resolves via confidence comparison.

### Design

**Conflict detection** (all three must be true):
1. Different `source_engine` (same engine can't conflict with itself)
2. Jaccard overlap ≥ 0.4 on non-negation, non-stopword tokens
3. Exactly one side contains negation words ("not", "never", "instead", "replaced", etc.)

**Resolution**: higher confidence wins; tie → first insight (stable ordering).

**API**:
- `detect_conflicts(insights)` → `list[ConflictPair]` (pairwise, O(n²))
- `resolve(a, b)` → winner
- `resolve_all(insights)` → `(survivors, conflicts)` — removes losers in-place

### Rationale

- Jaccard on content tokens gives topic similarity without embeddings
- Negation contrast is a reliable signal for contradiction ("uses X" vs "not use X")
- O(n²) is acceptable: typical insight lists are 5-20 items
- Confidence-based resolution is simple, explainable, and deterministic

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| Embedding-based similarity | Requires embedding port; overkill for regex-extracted insights |
| LLM-based contradiction detection | Too slow for inline pipeline |
| Voting (majority wins) | Doesn't apply — typically only 2 conflicting sources |
| Keep all (no resolution) | Conflicting facts in memory degrade downstream quality |

---

## TD-056: Insight Extraction Pipeline — Extract → Resolve → Store → Update

**Date**: 2026-03-11
**Status**: Accepted (Phase 7, Sprint 7.3)

### Decision

A 4-stage pipeline connecting context adapter extraction to memory storage and task state updates:

1. **Extract**: `InsightExtractor` looks up engine-specific adapter, calls `extract_insights()`, deduplicates by normalised content
2. **Reclassify**: Insights with confidence < 0.5 get reclassified via `MemoryClassifier.classify_with_confidence()`
3. **Conflict resolve**: `ConflictResolver.resolve_all()` removes losers, logs conflicts
4. **Store**: Each survivor → `MemoryEntry` in `MemoryRepository` (with CognitiveMemoryType→MemoryType mapping)
5. **Update state**: "decision"-tagged → `SharedTaskState.add_decision()`, "artifact"/"file"-tagged → `state.add_artifact()`

### CognitiveMemoryType → MemoryType Mapping

| CognitiveMemoryType | MemoryType |
|---|---|
| EPISODIC | L2_SEMANTIC |
| PROCEDURAL | L2_SEMANTIC |
| SEMANTIC | L3_FACTS |
| WORKING | L1_ACTIVE |

### Integration with ExecuteTaskUseCase

- Optional `extract_insights: ExtractInsightsUseCase | None` parameter
- `_safe_extract_insights()` gathers subtask results + errors, wrapped in try/except
- Extraction failure never blocks task execution (fire-and-forget safety)

### Container Wiring

- 6 context adapters → `InsightExtractor` → `ExtractInsightsUseCase` → `ExecuteTaskUseCase`
- `InMemorySharedTaskStateRepository` added to `AppContainer`

### Rationale

- Pipeline is the "nervous system" connecting extraction (Sprint 7.2) to storage (Phase 3)
- Fire-and-forget ensures extraction bugs never degrade core task execution
- Reclassification threshold (0.5) compensates for low-quality adapter extractions (e.g., Ollama at 0.3-0.6)
- Tag-based routing ("decision", "artifact", "file") enables structured state updates without LLM

---

## TD-057: AgentAffinityRepository — Separate Port for Affinity Scores

**Date:** 2026-03-11 | **Sprint:** 7.4 | **Status:** Accepted

### Decision

Create a dedicated `AgentAffinityRepository` port (ABC) separate from `SharedTaskStateRepository`. Five methods: `get(engine, topic)`, `get_by_topic(topic)`, `get_by_engine(engine)`, `upsert(score)`, `list_all()`.

### Alternatives Considered

1. **Add affinity methods to SharedTaskStateRepository** — rejected because access patterns differ fundamentally (engine×topic keyed vs task_id keyed).
2. **In-memory only, no port** — rejected because JSONL persistence needed for cross-session learning.

### Rationale

- Engine×topic keyed access pattern is a different domain concept from task state (1:N engine:topic vs 1:1 task)
- Two implementations: `InMemoryAgentAffinityRepository` (fast, dev) and `JSONLAffinityStore` (persistent, prod)
- JSONL follows established `StrategyStore` pattern: lazy-load + full-overwrite on upsert

---

## TD-058: TopicExtractor — Keyword-Based Topic Classification

**Date:** 2026-03-11 | **Sprint:** 7.4 | **Status:** Accepted

### Decision

Pure static domain service. Extracts normalized topic from task text using pre-compiled regex patterns. 10 topics (frontend, backend, database, devops, testing, security, ml, data, documentation, refactoring). Falls back to `"general"`. Topic with most keyword matches wins.

### Alternatives Considered

1. **LLM-based topic extraction** — rejected: adds latency and cost to every routing decision; keyword matching is sufficient for affinity bucketing.
2. **Embedding-based clustering** — rejected: over-engineered for the current need; can be added later as an enhancement.

### Rationale

- Zero-cost, zero-latency topic extraction suitable for every routing call
- Deterministic: same input → same topic (important for affinity consistency)
- Extensible: add new topics by adding keyword entries

---

## TD-059: select_with_affinity() — Affinity-Aware Engine Reranking

**Date:** 2026-03-11 | **Sprint:** 7.4 | **Status:** Accepted

### Decision

Add `select_with_affinity()` static method to `AgentEngineRouter`. Pipeline:
1. Compute base chain via `select_with_fallbacks()`
2. Budget=0 → `[OLLAMA]` (unchanged)
3. Rank affinities via `AgentAffinityScorer.rank()` (filters by min_samples)
4. Top score >= boost_threshold (0.6) → promote to front of chain
5. OLLAMA always last, dedup preserved

### Key Design Choices

- **Additive, not replacement**: `select_with_affinity()` builds on `select_with_fallbacks()`, which is untouched
- **Threshold gate** (0.6): prevents low-confidence affinity from overriding heuristic routing
- **min_samples** (3): prevents single-run flukes from biasing routing
- **Configurable**: both thresholds exposed in Settings

### Rationale

- Affinity data is sparse initially (cold start); threshold + min_samples prevent premature optimization
- OLLAMA-last invariant maintained for cost safety
- Static method: no state, pure logic, easy to test

---

## TD-060: HandoffTaskUseCase — Cross-Agent Task Handoff

**Date:** 2026-03-11 | **Sprint:** 7.4 | **Status:** Accepted

### Decision

New use case: `HandoffTaskUseCase` with `handoff(HandoffRequest) -> HandoffResult`. Flow:
1. Load/create SharedTaskState
2. Record "handoff" AgentAction on source engine
3. Add Decision (reason for handoff)
4. Merge request artifacts into state
5. Persist intermediate state
6. Build context (adapter-injected or plain text fallback)
7. Execute via `RouteToEngineUseCase.execute()` with target as preferred_engine
8. Record "received_handoff" AgentAction on target
9. Optional insight extraction (fire-and-forget)
10. Persist final state

### Key Design Choices

- **Composes RouteToEngineUseCase** — doesn't duplicate engine selection/fallback logic
- **State persisted twice** — before execution (captures handoff intent) and after (captures result)
- **target_engine optional** — can specify target or let router decide (affinity-aware)
- **Adapter-injected context** — uses ContextAdapterPort for engine-specific formatting when available
- **Plain text fallback** — builds readable context from state when no adapter available

### Rationale

- Handoff is the core UCL differentiator: tasks survive engine transitions with full state preservation
- Fire-and-forget insight extraction: handoff success is never blocked by extraction bugs
- Error boundary: entire handoff wrapped in try/except with HandoffResult.error for graceful degradation

---

## TD-061: UCL Interface Layer — API + CLI + UI (Sprint 7.5)

**Date:** 2026-03-11 | **Sprint:** 7.5 | **Status:** Accepted

### Decision

Expose all UCL components (SharedTaskState, AgentAffinity, Handoff, Insights) through 3 interface layers: FastAPI API, typer CLI, and Next.js UI. Follow existing patterns from evolution/engines/marketplace interfaces.

### Key Design Choices

| Choice | Rationale |
|---|---|
| **Schemas in `schemas.py`** | Centralized API schemas (same file as all other schemas), TYPE_CHECKING imports for domain types |
| **`from_state()`/`from_affinity()`/`from_result()`/`from_insight()` classmethods** | Factory pattern consistent with all existing response schemas |
| **Separate router file** (`routes/cognitive.py`) | One module per domain area, consistent with engines/marketplace/evolution |
| **CLI patch target** (`commands.cognitive._get_container`) | Python binding semantics: `from main import _get_container` creates local binding; must patch the local reference, not the source module |
| **Tab UI** (states + affinity) | Two primary UCL views in single page; handoff/insights are API-only (no dedicated UI yet) |
| **`AgentAffinityScorer.score()`** in API | Computed score included in response alongside raw affinity dimensions |

### Architecture

```
API:   /api/cognitive/state          GET (list), GET/{id}, DELETE/{id}
       /api/cognitive/affinity       GET (?topic, ?engine filters)
       /api/cognitive/handoff        POST (full handoff flow)
       /api/cognitive/insights/extract POST (extract + store)

CLI:   morphic cognitive state [TASK_ID]   — list or show
       morphic cognitive delete TASK_ID    — delete state
       morphic cognitive affinity          — list (--topic, --engine)
       morphic cognitive handoff           — execute handoff (--task-id, --source, --reason)
       morphic cognitive insights          — extract insights (--task-id, --engine, --output)

UI:    /cognitive                    — tab view: Shared States | Affinity Scores
       StateCard + StateDetail       — state browsing
       AffinityTable                 — scored affinity table
```

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| Separate schemas file for cognitive | Inconsistent with existing pattern; all schemas in one file |
| GraphQL for UCL queries | Over-engineering; REST is sufficient and consistent with existing API |
| Dedicated handoff UI page | Handoff is typically programmatic (agent-to-agent); API-only is appropriate for now |

---

## TD-062: Integration Testing + Benchmarks (Sprint 7.6)

**Date**: 2026-03-11
**Status**: Accepted

### Decision

Sprint 7.6 implements two benchmark suites, 13 cross-engine integration tests, and a full benchmark interface (API + CLI + UI) to validate Phase 7 UCL completion criteria.

### Key Design Choices

| Choice | Rationale |
|---|---|
| `benchmarks/` top-level package | Benchmarks are project-wide concerns, not tied to a single layer |
| AdapterScore as frozen dataclass (not Pydantic) | Pure domain-free benchmark utilities; score is a computed property |
| Continuity benchmark: inject→count (not inject→extract roundtrip) | Counting string fragments in injected context is deterministic; extract roundtrip depends on adapter regex which varies |
| Dedup benchmark: async (uses InsightExtractor) | InsightExtractor is async; dedup measures real pipeline behavior |
| 3 dedup scenarios: overlapping_facts, unique_outputs, case_variation | Covers the main dedup cases: exact overlap, no overlap, near-duplicate |
| A2A protocol skipped | UCL already provides cross-engine communication via ContextAdapters + HandoffTaskUseCase; separate A2A protocol would duplicate functionality |
| BenchmarkResultResponse.from_result() classmethod | Consistent with existing schema patterns (from_state, from_affinity, from_insight) |
| Integration tests use _FakeEngine(AgentEnginePort) | Controllable output without real LLM calls; each engine returns deterministic text |

### Benchmark Results

```
Context Continuity:  97.2% overall (target >85%)
  - All 6 adapters scored 83-100%
  - Reference state: 5 decisions, 4 artifacts, 3 blockers
  - Ollama adapter: lowest score due to ultra-compact format

Memory Dedup:        57.1% overall (target >50%)
  - overlapping_facts:  High dedup (same facts from different engines)
  - unique_outputs:     Low dedup (genuinely different content)
  - case_variation:     Medium dedup (near-duplicates caught)
```

### Architecture

```
benchmarks/
  context_continuity.py   AdapterScore + ContinuityResult + run_benchmark()
  dedup_accuracy.py       DedupScore + DedupResult + async run_benchmark()
  runner.py               BenchmarkSuiteResult + async run_all()

interface/api/routes/benchmarks.py   POST /api/benchmarks/{run|continuity|dedup}
interface/cli/commands/benchmark.py  morphic benchmark {run|continuity|dedup}
ui/app/benchmarks/page.tsx           Dashboard with ScoreBar + tables

tests/integration/test_ucl_cross_engine.py   13 tests (6 classes)
tests/unit/interface/test_benchmark_api.py   7 tests
tests/unit/interface/test_benchmark_cli.py   4 tests
```

### Rejected Alternatives

| Alternative | Rejection Reason |
|---|---|
| Roundtrip-based continuity scoring (inject→extract→compare) | Ollama's ultra-compact format loses detail in extract; count-based scoring is more robust |
| Separate A2A protocol implementation | UCL ContextAdapters + HandoffTask already cover agent-to-agent communication needs |
| Benchmark results persistence (DB) | Not needed yet; benchmarks run on-demand and return results directly |

---

## TD-063: Sprint 5.7 — Model Management Test Coverage + Auto-Discovery Trigger

**Date**: 2026-03-12
**Status**: Accepted
**Sprint**: 5.7a, 5.7b

### Decision

Two gaps closed to complete Phase 5:

1. **Sprint 5.7a — Model management interface-layer test coverage**: `_MockContainer` in test_api.py and test_cli.py lacked `manage_ollama` wiring, so 4 API endpoints (pull/delete/switch/info) and 3 CLI commands (delete/switch/info) had zero interface-layer tests. Added `manage_ollama` mock to both containers and wrote 15 tests (9 API + 6 CLI).

2. **Sprint 5.7b — Auto-discovery trigger on task failure**: `DiscoverToolsUseCase` existed but `ExecuteTaskUseCase` never called it. Added optional `discover_tools` parameter (same pattern as `extract_insights`) and `_safe_suggest_tools()` fire-and-forget method. Triggered on FAILED or FALLBACK status after insight extraction. 8 new tests.

### Key Design Choices

| Choice | Rationale |
|---|---|
| Fire-and-forget pattern | Mirrors `_safe_extract_insights()`: wrapped in try/except, never blocks task execution |
| Optional parameter (None default) | Backward-compatible; existing tests and callers unaffected |
| Trigger on FAILED + FALLBACK | Both indicate tool gaps; SUCCESS tasks don't need suggestions |
| Combined error string | Concatenates all failed subtask errors to give DiscoverToolsUseCase full failure context |
| Container wiring (1-line) | `discover_tools=self.discover_tools` added to ExecuteTaskUseCase constructor in container.py |

### Files Modified

- `tests/unit/interface/test_api.py` — +manage_ollama mock, +9 tests (TestModelManagementEndpoints)
- `tests/unit/interface/test_cli.py` — +manage_ollama mock, +6 tests (TestModelManagementCommands)
- `application/use_cases/execute_task.py` — +discover_tools param, +_safe_suggest_tools()
- `interface/api/container.py` — +discover_tools= wiring (1 line)
- `tests/unit/application/test_execute_task.py` — +8 tests (TestExecuteTaskWithToolSuggestion)
