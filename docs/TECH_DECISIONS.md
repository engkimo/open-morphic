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
