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

---

## TD-064: Sprint 8.1 — Close the Self-Evolution Loop

**Date**: 2026-03-12
**Status**: Accepted
**Sprint**: 8.1

### Decision

`ExecuteTaskUseCase` now auto-records an `ExecutionRecord` after every task execution. This closes the broken loop where Phase 6's `AnalyzeExecutionUseCase`, `UpdateStrategyUseCase`, and `SystemicEvolutionUseCase` had zero data to learn from.

### Problem

- `ExecuteTaskUseCase` ran tasks but never created `ExecutionRecord` entries
- Phase 6 evolution pipeline was fully built but starved of input data
- `RouteToEngineUseCase` already recorded affinity scores after engine execution — that pattern worked, but task-level recording was missing

### Key Design Choices

| Choice | Rationale |
|---|---|
| Optional `execution_record_repo` parameter (None default) | Backward-compatible; existing tests and callers unaffected |
| Optional `default_model` parameter | Captures which model ran; defaults to `ollama/qwen3:8b` |
| `time.monotonic()` for duration | Monotonic clock avoids wall-clock drift issues |
| Fire-and-forget `_safe_record_execution()` | Mirrors `_safe_extract_insights()` pattern: wrapped in try/except, never blocks task execution |
| `_infer_task_type()` via TopicExtractor | Reuses existing `TopicExtractor.extract()` + static dict mapping (10 topics → TaskType). Default: `SIMPLE_QA` |
| Container ordering fix | Moved `execution_record_repo` creation before `execute_task` in `AppContainer.__init__()` |

### Topic → TaskType Mapping

| Topic | TaskType |
|---|---|
| frontend, backend, database, testing, refactoring | CODE_GENERATION |
| devops, documentation | FILE_OPERATION |
| ml, security | COMPLEX_REASONING |
| data | LONG_CONTEXT |
| general (default) | SIMPLE_QA |

### Files Modified

- `application/use_cases/execute_task.py` — +`execution_record_repo`/`default_model` params, +`_safe_record_execution()`, +`_infer_task_type()`, +`_TOPIC_TO_TASK_TYPE` mapping
- `interface/api/container.py` — reordered `execution_record_repo` creation, +2 params to ExecuteTaskUseCase
- `tests/unit/application/test_execute_task.py` — +7 tests (TestExecuteTaskAutoRecording)

---

## TD-065: Settings-Driven Default Ollama Model (Sprint 8.2)

**Date**: 2026-03-14
**Status**: Accepted
**Sprint**: 8.2

### Problem

`LiteLLMGateway` hardcoded `MODEL_TIERS[ModelTier.FREE][0]` (`ollama/qwen3-coder:30b`) as the default model in 4 places: `route()` budget-exhausted path, `route()` LOCAL_FIRST shortcut, `route()` ultimate fallback, and `complete()` when no model is specified. The `.env` setting `OLLAMA_DEFAULT_MODEL=qwen3:8b` was completely ignored, causing 500 errors when only `qwen3:8b` was installed.

### Decision

Add `_default_free_model` property to `LiteLLMGateway` that reads from `Settings.ollama_default_model`. Replace all 4 hardcoded `MODEL_TIERS[ModelTier.FREE][0]` references with `self._default_free_model`.

### Rationale

| Choice | Rationale |
|---|---|
| Property `_default_free_model` | Single source of truth, DRY |
| Reads from `Settings.ollama_default_model` | Respects `.env` override, matches user's actual installed model |
| `MODEL_TIERS[FREE]` list unchanged | Tier list still used for `is_available()` cascade and `list_models()`. Only fallback paths changed |
| Test fixture explicit `ollama_default_model=` | Tests no longer depend on `.env` contents — deterministic |

### Files Modified

- `infrastructure/llm/litellm_gateway.py` — +`_default_free_model` property, 4 fallback references updated
- `tests/unit/infrastructure/test_litellm_gateway.py` — `DEFAULT_OLLAMA` → `"ollama/qwen3:8b"`, explicit `ollama_default_model` in settings fixture

---

## TD-066: E2E Smoke Test Suite + Shell Script (Sprint 8.2)

**Date**: 2026-03-14
**Status**: Accepted
**Sprint**: 8.2

### Decision

Add automated production verification infrastructure:

1. **`scripts/smoke_test.sh`** — bash/curl-based smoke test (21 checks across 9 phases, ~10 seconds)
2. **`tests/e2e/test_api_smoke.py`** — pytest/httpx-based E2E test suite (29 tests, auto-skips when API is down)

### Scope

| Category | # Checks | Coverage |
|---|---|---|
| Health | 1 | `/api/health` |
| Task CRUD | 2 | List, 404 on missing |
| Models | 3 | Status, list, running |
| Cost | 2 | Summary, logs |
| Engines | 2 | List (6 engines), Ollama status |
| Marketplace | 3 | Search, installed, suggest |
| Evolution | 3 | Stats, failures, preferences |
| UCL (Cognitive) | 4 | States, affinity, insights, state after insight |
| Benchmarks | 3 | Continuity, dedup, run all |
| Plans | 2 | List, 404 on missing |
| Memory | 2 | Search, export |
| Task Execution (Ollama) | 2 | Full pipeline (create→execute→poll→verify), plan→approve |
| Error Handling | 1 | 404 on nonexistent task |
| **Total** | **29 pytest + 21 shell** | All 42 API endpoints covered |

### Key Design Choices

| Choice | Rationale |
|---|---|
| `pytestmark = skipif(not _api_reachable())` | E2E tests auto-skip when server is down — safe to include in default test path |
| Separate `slow_client` fixture (120s timeout) | Ollama inference can take >60s; regular tests use 30s |
| Shell script returns `exit $FAIL` | CI/CD-friendly — non-zero exit on any failure |
| Shell script uses color output + summary | Developer-friendly — quick visual pass/fail |

### Files Created

- `scripts/smoke_test.sh` — 21 curl-based checks, executable
- `tests/e2e/test_api_smoke.py` — 29 pytest tests, auto-skip capable

---

## TD-067: Smart Decomposition — Task Complexity Classifier (Phase 9 / Sprint 9.1) ✅

**Date**: 2026-03-14
**Status**: Planned
**Sprint**: 9.1

### Problem

`IntentAnalyzer` always decomposes goals into 2-5 subtasks via LLM, regardless of task complexity. This causes:

1. **Over-decomposition**: "FizzBuzzを" → 5 subtasks splitting algorithm logic (divisible by 3, divisible by 5, etc.) instead of 1 "write and run the code" subtask
2. **Wasted tokens**: Simple tasks consume 2-5x more LLM calls than necessary for decomposition + execution
3. **Misaligned subtask descriptions**: Subtasks describe algorithm steps ("output Fizz") rather than actionable work ("write Python code and execute")

The root cause is the prompt instruction `"2-5 subtasks for most goals"` which forces decomposition even when none is needed.

### Decision

1. Add `TaskComplexityClassifier` as a pure domain service (`domain/services/task_complexity.py`)
2. Classify goals into `simple` / `medium` / `complex` using keyword heuristics + structural analysis
3. Simple tasks skip LLM decomposition entirely — goal is wrapped as a single action-oriented subtask
4. Medium/complex tasks use an improved prompt that produces meaningful, action-oriented subtask descriptions

### Classification Heuristics

| Complexity | Criteria | Decomposition |
|---|---|---|
| **simple** | Single concept, no "and"/"then" conjunctions, common patterns (FizzBuzz, sort, fibonacci, hello world) | 1 subtask, no LLM call for decomposition |
| **medium** | 2-3 concepts or mild conjunction ("X with Y") | 2-3 subtasks via LLM |
| **complex** | Multiple concepts, explicit multi-step ("build X, then Y, then Z"), large scope keywords (API, system, architecture) | 3-5 subtasks via LLM |

### Rationale

| Choice | Rationale |
|---|---|
| Domain service (not infrastructure) | Complexity classification is pure business logic — no I/O, no LLM dependency |
| Keyword heuristics (not LLM) | Avoids extra LLM call for classification. LLM decomposition cost for simple tasks is the problem we're solving |
| Action-oriented subtask descriptions | "Write and execute Python FizzBuzz code" is directly executable. "Output Fizz when divisible by 3" requires interpretation |
| Backward compatible | `decompose()` signature unchanged. Callers unaffected |

### Files Planned

- `domain/services/task_complexity.py` — TaskComplexityClassifier (pure function)
- `infrastructure/task_graph/intent_analyzer.py` — Complexity-aware decomposition + improved prompts
- `tests/unit/domain/test_task_complexity.py` — Classifier unit tests
- `tests/unit/infrastructure/test_intent_analyzer.py` — Updated decomposition tests

---

## TD-068: LAEE Code Execution in Task Engine (Phase 9 / Sprint 9.2) ✅

**Date**: 2026-03-14
**Status**: Planned
**Sprint**: 9.2

### Problem

`LangGraphTaskEngine._execute_batch()` sends subtask descriptions to LLM and stores the text response as `subtask.result`. Code is never executed. The LAEE infrastructure (40+ tools including `shell_exec`, `shell_background`, `shell_stream`) exists but is completely disconnected from the task execution pipeline.

Example: User asks "FizzBuzzを" → LLM responds with `{"result": "Fizz", "status": "success"}` text — no actual Python code runs, no real output.

### Decision

1. Add `CodeExecutor` class in `infrastructure/task_graph/code_executor.py`
2. After LLM response, `CodeExecutor.extract_code()` detects fenced code blocks (```python, ```bash, etc.)
3. If code is detected, execute via LAEE `shell_exec` with configurable timeout (default 30s)
4. Add `code` and `execution_output` optional fields to `SubTask` entity (backward compatible)
5. Modify `execute_one()` execution prompt to instruct LLM to produce runnable code blocks
6. Non-coding tasks (Q&A, summaries) pass through without code execution

### Execution Flow

```
execute_one(subtask):
  1. LLM.complete(subtask.description) → response
  2. CodeExecutor.extract(response.content) → code_blocks[]
  3. if code_blocks:
       for block in code_blocks:
         result = shell_exec(block.code, timeout=30s)
       subtask.code = block.code
       subtask.execution_output = result.stdout
  4. subtask.result = response.content (always preserved)
```

### Safety

| Concern | Mitigation |
|---|---|
| Infinite loops | 30s execution timeout (configurable via `LAEE_CODE_TIMEOUT`) |
| Dangerous commands (rm -rf, sudo) | LAEE ApprovalEngine checks RiskLevel before execution |
| Resource exhaustion | Single-process execution, no fork bombs |
| File system writes | Respects LAEE approval mode (confirm-destructive by default) |

### Rationale

| Choice | Rationale |
|---|---|
| Reuse LAEE `shell_exec` | No new execution infrastructure needed. Audit log, approval mode, undo stack all inherited |
| Optional fields on SubTask | Backward compatible — existing tasks/tests unaffected |
| Extract code from markdown | LLMs naturally produce fenced code blocks. Standard format across all models |
| Preserve `result` alongside `code`/`output` | Text explanation is still valuable. Code + output are supplementary |

### Files Planned

- `infrastructure/task_graph/code_executor.py` — CodeExecutor: extract + execute
- `domain/entities/task.py` — +`code`, +`execution_output` fields
- `infrastructure/task_graph/engine.py` — Wire CodeExecutor into `execute_one()`
- `interface/api/schemas.py` — +`code`, +`execution_output` on SubTaskResponse
- `tests/unit/infrastructure/test_code_executor.py` — Extraction + mock execution tests

---

## TD-069: UI Result Formatting — Structured Subtask Display (Phase 9 / Sprint 9.3) ✅

**Date**: 2026-03-14
**Status**: Planned
**Sprint**: 9.3

### Problem

`TaskDetail.tsx` renders `st.result` as raw text via `<div className="text-xs text-text-muted">{st.result}</div>`. When LLM returns JSON or code, users see unformatted strings. `TaskGraph.tsx` nodes show `d.result.slice(0, 60)` — truncated raw data.

### Decision

1. Create `CodeBlock.tsx` component with syntax highlighting (highlight.js or shiki)
2. Create `ExecutionResult.tsx` component showing code + output + status in structured layout
3. Refactor `TaskDetail.tsx` to detect and render `code`/`execution_output` fields from Sprint 9.2
4. Add `resultParser.ts` utility to detect JSON, code blocks, and plain text in legacy `result` strings
5. Improve `TaskGraph.tsx` node labels to show clean descriptions instead of truncated raw data

### Rendering Logic

```
if subtask.code:
  render <CodeBlock code={code} language={lang} />
  if subtask.execution_output:
    render <ExecutionResult output={execution_output} />
elif subtask.result is JSON:
  render pretty-printed JSON
else:
  render plain text
```

### Rationale

| Choice | Rationale |
|---|---|
| highlight.js over shiki | Runtime highlighting, no build-time dependency. Smaller bundle for this use case |
| Separate CodeBlock component | Reusable across TaskDetail, TaskGraph tooltips, future views |
| resultParser for legacy data | Existing tasks stored before Sprint 9.2 lack `code`/`execution_output` fields. Parser handles both formats |

### Files Planned

- `ui/components/CodeBlock.tsx` — Syntax-highlighted code display
- `ui/components/ExecutionResult.tsx` — Code + output + status layout
- `ui/components/TaskDetail.tsx` — Refactored to use new components
- `ui/components/TaskGraph.tsx` — Improved node rendering
- `ui/lib/resultParser.ts` — Detect and categorize result content

---

## TD-070: Interactive Planning as Default Task Flow (Phase 9 / Sprint 9.4) ✅

**Date**: 2026-03-14
**Status**: Accepted
**Sprint**: 9.4

### Problem

`POST /api/tasks` immediately creates a TaskEntity and dispatches execution to background. The `InteractivePlanUseCase` exists with full plan creation, approval, and rejection logic, but is never used in the default task creation flow. Users get no opportunity to review, modify, or reject plans before execution begins.

This contradicts the project's stated Devin-style Interactive Planning philosophy:
> "実行前に計画+コード引用で提示" / "コスト見積もり付きで人間確認"

### Decision

1. Add `PLANNING_MODE` setting with three values: `interactive` (default), `auto`, `disabled`
2. `interactive`: `POST /api/tasks` creates a plan, returns for review. `POST /api/plans/{id}/approve` triggers execution
3. `auto`: Create plan → auto-approve simple tasks (complexity=simple from TD-067) → manual review for medium/complex
4. `disabled`: Current behavior preserved (immediate create + execute)
5. Plan review UI page with approve/reject buttons, cost estimate, subtask preview

### API Flow Changes

```
Current:
  POST /api/tasks {goal} → 201 TaskResponse (execution already dispatched)

Interactive (new default):
  POST /api/tasks {goal} → 201 PlanResponse (plan created, awaiting approval)
  POST /api/plans/{id}/approve → 201 TaskResponse (execution dispatched)

Auto:
  POST /api/tasks {goal}
    → if simple: auto-approve → 201 TaskResponse
    → if medium/complex: 201 PlanResponse (awaiting approval)
```

### Rationale

| Choice | Rationale |
|---|---|
| 3-mode setting | Backward compatible. Users can opt into old behavior with `disabled` |
| Auto-approve for simple tasks | 1-subtask coding tasks don't need review. Reduces friction |
| Reuse existing InteractivePlanUseCase | No new use case needed — existing plan create/approve/reject works |
| `interactive` as new default | Aligns with stated philosophy. Old users can set `disabled` |

### Files Planned

- `interface/api/routes/tasks.py` — Plan-first flow based on PLANNING_MODE
- `shared/config.py` — +`PLANNING_AUTO_APPROVE_SIMPLE` setting
- `ui/app/tasks/` — Plan review page with approve/reject
- `tests/unit/interface/test_tasks_planning.py` — Plan-first flow tests

---

## TD-071: Full-Stack Structured Logging (Phase 9 / Sprint 9.5) ✅

**Date**: 2026-03-14
**Status**: Accepted
**Sprint**: 9.5

### Problem

Debugging and tracing requests across the Morphic-Agent stack is difficult. Backend modules use ad-hoc `print()` or no logging at all. Frontend has zero logging — API calls, WebSocket connections, and errors are invisible. There is no centralized logging configuration; each module would need to independently configure handlers and formats.

### Decision

1. **Backend**: Centralized logging config in `shared/logging.py` with structured format `HH:MM:SS | LEVEL | module | message`
2. **Backend**: Add `logging.getLogger(__name__)` to all key modules: LLM gateway, task engine, intent analyzer, code executor, API routes (tasks, plans), CLI entry point
3. **Frontend**: Client-side logger (`ui/lib/logger.ts`) with `[Morphic]` prefix, level filtering via `NEXT_PUBLIC_LOG_LEVEL` env var
4. **Frontend**: API call tracing in `ui/lib/api.ts` — request method/path, response status, timing (ms), WebSocket lifecycle
5. **Config**: `log_level` setting in `shared/config.py` (default: `INFO`), applied at startup via `setup_logging()`
6. **Noise reduction**: Third-party loggers (httpx, httpcore, litellm, urllib3, asyncio) suppressed to WARNING level

### Logging Coverage

| Module | What is logged |
|---|---|
| `litellm_gateway.py` | LLM call (model, temp, max_tokens), response (tokens, cost), fallback warnings |
| `engine.py` | Decomposition start, subtask execution, code execution results, retries, failures, finalization |
| `intent_analyzer.py` | Complexity classification, LLM decomposition call, subtask count |
| `code_executor.py` | Block extraction count, execution start/success/timeout/failure |
| `routes/tasks.py` | Request lifecycle, planning mode decision, auto-approve |
| `routes/plans.py` | Create (goal, model), approve, reject |
| `cli/main.py` | Logging init at startup |
| `ui/lib/api.ts` | API method/path, status/timing, WebSocket connect/message/close/error |

### Files Changed

- `shared/logging.py` — **NEW**: centralized logging configuration
- `shared/config.py` — +`log_level: str = "INFO"`
- `infrastructure/llm/litellm_gateway.py` — +structured logging
- `infrastructure/task_graph/engine.py` — +structured logging
- `infrastructure/task_graph/intent_analyzer.py` — +structured logging
- `infrastructure/task_graph/code_executor.py` — +structured logging
- `interface/api/main.py` — +`setup_logging()` in lifespan
- `interface/api/routes/tasks.py` — +request lifecycle logging
- `interface/api/routes/plans.py` — +operation logging
- `interface/cli/main.py` — +`setup_logging()` at startup
- `ui/lib/logger.ts` — **NEW**: client-side logger with level filtering
- `ui/lib/api.ts` — +API call tracing with timing

### Rationale

| Choice | Rationale |
|---|---|
| `logging.getLogger(__name__)` per module | Standard Python pattern; hierarchical control via root logger |
| Centralized `setup_logging()` | Single call at startup, no per-module config duplication |
| Suppress third-party loggers | litellm/httpx flood logs at INFO level |
| Frontend `console.*` wrapper | No build-time dependency; level filtering via env var |
| Timing in API calls | Identify slow endpoints and LLM latency at a glance |

---

## TD-072: Complexity-Aware Execution Prompts (Phase 10 / Sprint 10.1)

**Date**: 2026-03-17
**Status**: Accepted
**Sprint**: 10.1

### Problem

All subtasks use the same `temperature=0.7, max_tokens=4096` and have no format instruction. Simple tasks like "1+1=?" return verbose multi-paragraph explanations instead of just "2".

### Decision

1. `ExecutionPromptBuilder` (pure domain service): maps `TaskComplexity` to `ExecutionConfig` with appropriate `temperature`, `max_tokens`, and format instructions
2. `AnswerExtractor` (pure domain service): strips `<think>` tags, preambles, and trailing explanations from LLM output, with aggressive cleaning for SIMPLE tasks
3. `SubTask.complexity` field added (defaults to `None` → treated as MEDIUM for backward compat)
4. `IntentAnalyzer` stamps complexity on subtasks after decomposition
5. `engine.py` uses builder for prompt construction and extractor for result cleaning
6. KV-cache compliant: system prompt starts with stable prefix, format instruction appended after

### Parameters by Complexity

| Complexity | Temperature | max_tokens | Format |
|---|---|---|---|
| SIMPLE | 0.15 | 512 | "ONLY the direct answer. No explanation." |
| MEDIUM | 0.4 | 2048 | "Concise solution with brief context." |
| COMPLEX | 0.7 | 4096 | "Detailed, thorough response with reasoning." |

---

## TD-073: React Flow Node Redesign (Phase 10 / Sprint 10.2)

**Date**: 2026-03-17
**Status**: Accepted
**Sprint**: 10.2

### Problem

Task graph visualization is flat (linear `y: i*100`), nodes truncate text without ellipsis (`.slice(0,50)`), fixed 400px height, and full-border coloring is visually noisy.

### Decision

1. Depth-based DAG layout via `computeNodeDepths()` — nodes positioned by dependency depth (`x = depth * X_GAP`)
2. `truncateWithEllipsis()` with native `title` tooltip for full text
3. Dynamic graph height: `max(300, min(700, subtasks * 110 + 100))`
4. Left accent border (4px) for status color, subtle border on other sides
5. `smoothstep` edge type for cleaner curves
6. Complexity badge on nodes
7. Min node width increased to 280px

---

## TD-074: Result Display Restructure (Phase 10 / Sprint 10.3)

**Date**: 2026-03-17
**Status**: Accepted
**Sprint**: 10.3

### Problem

Results show raw LLM output without answer/reasoning separation. Simple task answers are displayed the same as complex responses — small text, no visual hierarchy.

### Decision

1. `parseResultWithComplexity()` in `resultParser.ts`: extracts `<think>` tags as reasoning, returns `{answer, reasoning, parsed}`
2. SIMPLE tasks: large accent-colored answer box, reasoning suppressed
3. MEDIUM/COMPLEX tasks: structured result with code block detection + collapsible `<details>` for reasoning
4. Backward compatible: missing `complexity` field renders as non-simple (existing behavior)

---

## TD-075: Semantic Dedup in InsightExtractor (Phase 11 / Sprint 11.1)

**Date**: 2026-03-17
**Status**: Accepted
**Sprint**: 11.1

### Problem

InsightExtractor dedup uses exact-match (case-insensitive) which misses paraphrased duplicates. "Created file: config.yaml" vs "File config.yaml created" are the same fact but survive dedup. Dedup accuracy for overlapping facts: 57.1%.

### Decision

1. `InsightExtractor.__init__` accepts optional `EmbeddingPort` and `semantic_dedup_threshold` (default 0.85)
2. `_semantic_dedup(insights)`: embed all insight contents → pairwise cosine similarity → drop lower-confidence member of pairs with similarity >= threshold
3. When `embedding_port=None`: fall back to existing `_exact_dedup()` (backward compatible)
4. When embedding call fails: graceful degradation to exact-match
5. Config settings: `semantic_dedup_enabled`, `semantic_dedup_threshold` in `shared/config.py`

### Reused Components

| Component | Role |
|---|---|
| `EmbeddingPort` (domain/ports) | ABC for text→vector |
| `SemanticFingerprint.cosine_similarity()` | Pure static similarity computation |
| `OllamaEmbeddingAdapter` | Production embedding backend |
| `FakeEmbeddingPort` pattern (tests) | Deterministic test vectors |

---

## TD-076: Hybrid Memory Classifier (Phase 11 / Sprint 11.2)

**Date**: 2026-03-17
**Status**: Accepted
**Sprint**: 11.2

### Problem

`MemoryClassifier` is regex-only — it cannot handle synonyms, paraphrases, or nuanced text that doesn't match hardcoded patterns. Confidence falls to 0.3 (default) for unrecognized text.

### Decision

1. New `MemoryClassifierPort` ABC in `domain/ports/memory_classifier.py`: `classify(content) → (CognitiveMemoryType, float)`
2. `HybridMemoryClassifier(MemoryClassifierPort)` in infrastructure:
   - Step 1: Run existing `MemoryClassifier` regex logic (fast, free)
   - Step 2: If confidence < threshold (0.5) → LLM fallback via `LLMGateway.complete()`
   - Step 3: If LLM unavailable → return regex result (graceful degradation)
3. Domain purity: LLM calls only in infrastructure. Domain has ABC only
4. `InsightExtractor` updated to accept `MemoryClassifierPort` for reclassification
5. Existing `MemoryClassifier` is not modified — `HybridMemoryClassifier` delegates to it internally

### Key Design Choices

| Choice | Rationale |
|---|---|
| Regex-first, not LLM-first | Cost efficiency — regex handles 70%+ of cases for free |
| `classify()` is sync, `classify_async()` for hybrid | Port contract stays simple; async only when LLM needed |
| Confidence boost to >= 0.7 on LLM success | LLM classification is more reliable than regex default |
| Graceful degradation on LLM failure | Never worse than regex-only baseline |

---

## TD-077: ReAct Loop — Iterative Tool-Calling Execution (Phase 12 / Sprint 12.1)

**Date**: 2026-03-18
**Status**: Accepted
**Sprint**: 12.1

### Problem

Subtask execution is single-shot: one LLM call → answer. No ability to reason, call tools, observe results, and iterate. The agent cannot autonomously gather information or verify its answers.

### Decision

1. `ReactExecutor` implements Think → Act → Observe loop (max 10 iterations)
2. `ReactTrace` captures full execution trace (steps, tool_calls, observations)
3. `ReactController` (pure domain) decides whether to continue or stop
4. `ToolSchema.to_openai_tool()` converts to OpenAI-compatible format for any LLM
5. Observation truncation at 3000 chars prevents context explosion
6. `LLMGateway.complete_with_tools()` added as new port method

### Key Design Choices

| Choice | Rationale |
|---|---|
| MAX_ITERATIONS = 10 | Prevents infinite loops while allowing sufficient reasoning |
| Observation truncation (3000 chars) | Context-aware — preserves key info, prevents token budget blow |
| OpenAI tool format as standard | Broad LLM compatibility (Claude, GPT, Gemini, Ollama) |
| Stateless ReactController | Pure domain logic, fully testable |
| ToolCallResult in LLMResponse | Clean separation: gateway parses, executor orchestrates |

---

## TD-078: Tool Schema Registry — 38 LAEE Tools (Phase 12 / Sprint 12.2)

**Date**: 2026-03-18
**Status**: Accepted
**Sprint**: 12.2

### Problem

ReAct executor needs tool definitions in OpenAI-compatible JSON schema format. 38 LAEE tools exist but lack structured schemas.

### Decision

1. Hand-written JSON schemas in `infrastructure/local_execution/tools/tool_schemas.py`
2. 38 tool definitions: shell(4), filesystem(7), web(2), browser(5), system(5), dev(4), GUI(3), cron(4)
3. `ToolSelector` (domain service) maps `TaskType` → tool subset for focused tool profiles
4. `_filter_tools()` in ReactExecutor enables fine-grained security control

### Key Design Choices

| Choice | Rationale |
|---|---|
| Hand-written schemas (not auto-generated) | Precise descriptions improve LLM tool selection accuracy |
| Task-type based tool profiles | Smaller tool sets reduce hallucinated tool calls |
| Filter at executor level | Security: restrict available tools per subtask |

---

## TD-079: Web Search + Fetch Tools (Phase 12 / Sprint 12.3)

**Date**: 2026-03-18
**Status**: Accepted
**Sprint**: 12.3

### Problem

Agent needs web access for information retrieval without requiring API keys.

### Decision

1. `web_search()`: DuckDuckGo HTML search — API-key-free, parses HTML results
2. `web_fetch()`: HTTP GET + HTML tag stripping for content extraction
3. Both integrated as standard LAEE tools usable by ReAct loop

### Key Design Choices

| Choice | Rationale |
|---|---|
| DuckDuckGo HTML (not API) | Zero cost, no API key, no rate limiting |
| HTML tag stripping (not readability) | Minimal dependencies; good enough for most content |
| LAEE integration | Consistent tool interface with shell/fs/browser tools |

---

## TD-080: LiteLLM Tool Calling Integration (Phase 12 / Sprint 12.4)

**Date**: 2026-03-18
**Status**: Accepted
**Sprint**: 12.4

### Problem

`LLMGateway.complete_with_tools()` needs a production implementation supporting diverse LLM providers with different tool-calling quirks.

### Decision

1. `LiteLLMGateway.complete_with_tools()` — unified tool calling across providers
2. Model-specific quirks handled: o3/o4 no temperature param, Ollama think=False
3. JSON argument parsing with graceful fallback on malformed args
4. Per-call cost tracking for tool-augmented interactions

### Key Design Choices

| Choice | Rationale |
|---|---|
| LiteLLM as universal adapter | Already used for `complete()` — consistent interface |
| Quirk handling per provider | Prevents runtime errors from provider differences |
| Graceful JSON fallback | LLM may return malformed JSON in arguments |

---

## TD-081: Model-Aware Subtask Decomposition (Phase 12 / Sprint 12.5)

**Date**: 2026-03-19
**Status**: Accepted
**Sprint**: 12.5

### Problem

Users request specific models ("use GPT and Claude to...") but the system has no way to extract model preferences from natural language or route subtasks to specific models.

### Decision

1. `ModelPreference` value object: `models` tuple + `clean_goal` + `collaboration_mode`
2. `ModelPreferenceExtractor` (pure domain service): regex-based model alias extraction
3. Alias mapping: "gpt"→"o4-mini", "claude"→"claude-sonnet-4-6", "gemini"→"gemini/gemini-3-pro-preview"
4. English + Japanese support (handles particles: と, や, で)
5. `SubTask.preferred_model` field stamps which model should execute
6. Multi-model goals → per-model subtasks (static decomposition)

### Key Design Choices

| Choice | Rationale |
|---|---|
| Pure regex (no LLM) | Instant, deterministic, zero cost |
| Longest-first alias matching | "chatgpt" matches before "gpt" |
| Japanese particle cleanup | Natural goal text after alias removal |
| De-duplicated model IDs | "GPT and ChatGPT" → single o4-mini |

---

## TD-082: Dynamic Multi-Model Decomposition via LLM (Phase 12 / Sprint 12.6)

**Date**: 2026-03-20
**Status**: Accepted
**Sprint**: 12.6

### Problem

Sprint 12.5's multi-model decomposition copies the same goal to each model. "GPT, Gemini, Claude で映画チケットを探して" produces 3 identical subtasks. Each model's strengths are ignored — no differentiation or collaboration strategy.

### Decision

1. `CollaborationMode` enum: PARALLEL, COMPARISON, DIVERSE, AUTO
2. `ModelCapabilityRegistry`: static model-id → capability description mapping
3. `_llm_multi_model_decompose()` in IntentAnalyzer: LLM-based intelligent decomposition
4. Mode-specific guidance injected into prompt (synthesis, comparison, diverse angles)
5. `_parse_multi_model_response()`: JSON parsing with round-robin fallback for unknown models
6. LLM failure → graceful fallback to existing static `_create_per_model_subtasks()`
7. Collaboration mode detected from keywords: 比較/vs → COMPARISON, それぞれ → DIVERSE, 一緒に → PARALLEL

### Key Design Choices

| Choice | Rationale |
|---|---|
| Collaboration mode in ModelPreference | Extracted from same goal text, single responsibility |
| Priority: COMPARISON > DIVERSE > PARALLEL | Most structured mode wins on keyword conflict |
| Static capability descriptions | Stable, cacheable, no LLM cost for registry |
| Round-robin fallback for unknown models | Simpler than re-calling LLM; ensures all models get subtasks |
| LLM failure → static fallback | Robustness: never fails to produce subtasks |
| model=None for decomposition LLM | LOCAL_FIRST principle — lightweight prompt suits Ollama |

---

## TD-083: Two Worlds Integration — Engine ↔ ReAct ↔ Tools E2E (Phase 12.7)

**Date**: 2026-03-20
**Status**: Accepted
**Sprint**: 12.7 (6 sub-sprints)

### Problem

"Two Worlds" gap: Phase 1 execution pipeline (POST /tasks → IntentAnalyzer → Engine → LLM) was disconnected from Phase 3-12 infrastructure (RouteToEngineUseCase, ReactExecutor tools, MCP, ConflictResolver). Subtask execution was single-shot LLM call with no tool usage, no per-engine routing, no cross-model validation, no quality degradation detection.

### Decision

Six integration sprints connecting World A (execution) to World B (infrastructure):

1. **Sprint 12.1 — tools_used/data_sources stamping**: ReactResult carries tool names and extracted URLs. Engine stamps them onto SubTask after execution.

2. **Sprint 12.2 — Per-engine routing**: `_resolve_engine_type()` maps model IDs → AgentEngineType. Cloud models route through `RouteToEngineUseCase`; Ollama/unknown skip to ReAct. Fallback to ReAct on engine failure.

3. **Sprint 12.3 — Discussion phase**: Multi-model tasks trigger LLM synthesis in `_finalize()`. `_DISCUSSION_PROMPT` template aggregates per-model results. Synthesis subtask appended with `[Synthesis]` prefix.

4. **Sprint 12.4 — MCP integration**: ReactExecutor accepts `mcp_client` and routes MCP-registered tool calls to MCPClient instead of LAEE. `register_mcp_tools()` converts MCP tool descriptions to OpenAI format. Container auto-connects configured MCP servers.

5. **Sprint 12.5 — DEGRADED validation**: New `SubTaskStatus.DEGRADED` for "completed but without expected tools". `TaskComplexityClassifier.requires_tools()` detects tool-requiring goals (JP + EN patterns). DEGRADED counts as terminal and partial success in `is_complete` / `success_rate`.

6. **Sprint 12.6 — Auto-upgrade**: When Ollama produces no tool calls for a tool-requiring task, engine retries with `_AUTO_UPGRADE_MODELS` (claude-sonnet-4-6 → o4-mini → gemini/gemini-2.5-flash). Skipped when `preferred_model` is explicitly set.

### Key Design Choices

| Choice | Rationale |
|---|---|
| `executed_via_engine` boolean flag | Prevents double-execution when engine route succeeds |
| DEGRADED as terminal status | Allows pipeline to continue; downstream knows quality is reduced |
| `_DATA_SOURCE_TOOLS` frozenset | Only extract URLs from tools that access real data sources |
| Fire-and-forget MCP connection | MCP failures don't block app startup |
| `_pick_upgrade_model()` with ordered fallback | Tries cheapest cloud model first |
| Discussion only for 2+ distinct models | Single-model tasks don't need cross-validation |

### Files Modified

- `domain/value_objects/status.py` — +DEGRADED enum member
- `domain/entities/task.py` — +tools_used/data_sources fields, DEGRADED in is_complete/success_rate/get_ready_subtasks
- `domain/services/task_complexity.py` — +requires_tools() with JP+EN patterns
- `infrastructure/task_graph/react_executor.py` — +tools_used/data_sources collection, +MCP routing, +register_mcp_tools()
- `infrastructure/task_graph/engine.py` — +_resolve_engine_type(), +auto-upgrade, +per-engine routing, +discussion phase, +DEGRADED validation
- `interface/api/container.py` — +MCP wiring, +route_to_engine injection, +_connect_mcp_servers()
- `interface/api/schemas.py` — +tools_used/data_sources in SubTaskResponse
- `tests/unit/domain/test_degraded_status.py` (NEW) — 9 tests
- `tests/unit/domain/test_requires_tools.py` (NEW) — 17 tests
- `tests/unit/infrastructure/test_react_tools_tracking.py` (NEW) — 5 tests
- `tests/unit/infrastructure/test_engine_two_worlds.py` (NEW) — 10 tests

---

## TD-084: Activate Engine Routing — Autonomous Agent Runtime Delegation (Sprint 12.2 Revisited)

**Date**: 2026-03-21
**Status**: Accepted
**Sprint**: 12.2 (revisited — previously deferred)

### Problem

Sprint 12.2 was originally deferred with the rationale "user model preference = LLM API, not engine runtime." All subtasks were executed via `LiteLLMGateway.complete()` (single text completion) even when engine drivers (Claude Code SDK, Gemini CLI, etc.) were fully implemented and wired.

This contradicted the project's core vision: engine drivers are **autonomous agent runtimes** that can write code, execute it, use tools, and iterate — not just LLM API wrappers. The `use_engine_route = False` hardcode on `engine.py:209` rendered all engine infrastructure dead code in the execution pipeline.

### Decision

Activate engine routing by changing `use_engine_route` from hardcoded `False` to:

```python
use_engine_route = (
    self._route_to_engine is not None
    and engine_type is not None
)
```

**Execution priority chain:**
1. **Engine routing** (autonomous agent): When `preferred_model` maps to an `AgentEngineType`, delegate to the corresponding engine driver via `RouteToEngineUseCase`. The engine driver (Claude Code CLI, Gemini CLI, etc.) executes autonomously.
2. **ReactExecutor** (tool-augmented LLM): Fallback when engine fails or is unavailable. Provides tool-calling via LAEE.
3. **Direct LLM** (text completion): Last resort for simple tasks without ReactExecutor.

### Key Design Choices

| Choice | Rationale |
|---|---|
| No engine-specific exceptions | Generic: all engines with resolved `engine_type` attempt routing. No hardcoded "skip Ollama" — let the capability chain handle it |
| Fallback via `executed_via_engine` flag | If engine fails, existing ReactExecutor/direct LLM paths execute seamlessly |
| RouteToEngineUseCase handles availability | Engine drivers check `is_available()` (CLI installed, API key set, etc.) and skip gracefully |
| Unchanged for `preferred_model=None` | Tasks without explicit model preference bypass engine routing entirely |

### Files Modified

- `infrastructure/task_graph/engine.py` — `use_engine_route = False` → conditional activation; updated comment block
- `tests/unit/infrastructure/test_task_graph_engine.py` — +6 tests (TestEngineRouting class: success, ReactExecutor fallback, direct LLM fallback, no preferred_model, unknown model, multi-engine parallel)
- `tests/unit/infrastructure/test_engine_two_worlds.py` — 2 tests updated to reflect engine routing activation (assert_called instead of assert_not_called)

### Test Count

1,934 → 1,940 (+6 new tests). 0 failures, lint clean.

---

## TD-085: Pipeline Robustness — Smart Auto-Upgrade + Engine Observability

**Date**: 2026-03-21
**Status**: Accepted

### Decision

Three improvements to the task execution pipeline:

1. **Smart auto-upgrade model selection**: `_pick_upgrade_model()` now checks `LLMGateway.is_available()` for each candidate (Claude → GPT → Gemini) instead of blindly returning the first.

2. **Engine output URL extraction**: When engine routing succeeds, URLs are extracted from the output text via regex and set as `subtask.data_sources`. This provides observability into what data the autonomous engine referenced.

3. **DEGRADED validation skip for engine-routed subtasks**: Engine drivers are autonomous runtimes that handle tools internally. The `tools_used` field tracks LAEE/ReAct tool calls, not internal engine operations. Engine-routed subtasks (`engine_used` set) now skip DEGRADED validation.

### Rationale

- Auto-upgrade without availability checking fails silently when the user lacks the API key for the selected model
- Engine output may contain URLs from web searches the engine performed internally — capturing these as `data_sources` improves traceability
- Applying DEGRADED status to engine-routed subtasks is semantically wrong: the engine is an autonomous runtime, not a tool-calling LLM

### Test Count

1,940 → 1,950 (+10 new tests). 0 failures, lint clean.

---

## TD-086: Iterative Multi-Agent Discussion Protocol (Sprint 13.1)

**Date**: 2026-03-21
**Status**: Accepted

### Decision

Refactor the single-shot discussion phase into a configurable multi-round iterative discussion:

- **Round 1**: Synthesis (same as before — collect results, ConflictResolver, LLM synthesis)
- **Round 2+**: Different model critiques and refines the previous round's synthesis
- **Model rotation**: Each round uses a different model for diverse perspectives
- **Configurable**: `DISCUSSION_MAX_ROUNDS` (default: 1, backward compatible) and `DISCUSSION_ROTATE_MODELS` (default: true)

### Architecture

```
Round 1: Ollama (LOCAL_FIRST, $0) → Initial synthesis
Round 2: Claude (cloud) → Critique + refine
Round 3: GPT (cloud) → Final refinement
→ Final synthesis subtask captures the last round's result
```

When no cloud model is available, subsequent rounds still run with the default model. If a round fails, the last successful synthesis is used.

### Rationale

- The original single-shot synthesis was not true multi-agent discussion — it was a merge
- Iterative discussion enables: diverse perspectives, error correction, refinement
- Model rotation ensures each round brings a different "viewpoint" (different training data, biases)
- Backward compatible: `discussion_max_rounds=1` produces identical behavior to before

### Files Changed

| File | Change |
|------|--------|
| `shared/config.py` | +`discussion_max_rounds`, +`discussion_rotate_models` |
| `infrastructure/task_graph/engine.py` | +`_CRITIQUE_PROMPT`, +`_pick_discussion_model()`, refactored `_run_discussion()` for N rounds |
| `interface/api/container.py` | Wire discussion config to engine |
| `tests/unit/infrastructure/test_engine_two_worlds.py` | +9 tests for iterative discussion |

### Test Count

1,950 → 1,959 (+9 new tests). 0 failures, lint clean.

---

## TD-087: Engine-Routed Discussion — Autonomous Agent Runtimes in Discussion Phase (Sprint 13.2)

**Date**: 2026-03-21
**Status**: Accepted
**Sprint**: 13.2

### Problem

Discussion rounds in `_run_discussion()` used `self._llm.complete()` — a single LLM text completion call. This treated discussion as "text-in, text-out", ignoring the project's core concept: **engine drivers are autonomous agent runtimes** that can write code, execute it, search the web, and iterate.

The discussion phase was the last major component still bypassing engine routing. Subtask execution already used `RouteToEngineUseCase` (TD-084), but discussion synthesis/critique did not.

### Decision

Each discussion round now tries engine routing first, falling back to direct LLM API:

1. **Resolve engine type** from the selected discussion model via `_resolve_engine_type()`
2. **If engine available**: delegate the full discussion prompt as an autonomous task via `self._route_to_engine.execute()`
   - Engine receives the complete context (model outputs, conflicts, previous synthesis)
   - Engine can write code, execute it, search, iterate autonomously
   - On success: capture output, model, cost, engine_used
3. **If engine fails or unavailable**: fall back to `self._llm.complete()` (identical to Sprint 13.1 behavior)
4. **Synthesis subtask** now records `engine_used` and includes engine label in description

### Rationale

- **Core concept alignment**: The project's differentiator is that agents are autonomous runtimes, not just LLM API wrappers. Discussion should leverage the same capability.
- **Richer analysis**: Claude Code CLI can write analysis scripts, execute them, iterate. This produces deeper critique than a single text completion.
- **Backward compatible**: When `route_to_engine` is None or model doesn't map to an engine, behavior is identical to Sprint 13.1.
- **Generic framework**: No specialization for any test scenario. Any engine runtime can participate in discussion.

### Execution Priority in Discussion Rounds

```
Discussion Round N:
  1. Resolve engine type from discussion model
  2. Try engine routing (autonomous agent runtime)
     → Success: use engine output
     → Failure: fall through
  3. Fallback: direct LLM API completion
```

### Files Changed

| File | Change |
|------|--------|
| `infrastructure/task_graph/engine.py` | `_run_discussion()`: engine routing before LLM, `engine_used` on synthesis subtask, engine label in description |
| `tests/unit/infrastructure/test_engine_two_worlds.py` | +5 tests: `TestEngineRoutedDiscussion` (engine success, failure fallback, exception safety, backward compat, cost tracking) |

### Test Count

1,964 → 1,969 (+5 new tests). 0 failures, lint clean.

---

## TD-088: Dynamic Agent Role Assignment — Free-Form Roles from User Input or LLM Generation (Sprint 13.3)

**Date**: 2026-03-21
**Status**: Accepted
**Sprint**: 13.3

### Problem

Multi-agent discussion had no way to assign differentiated roles (e.g. "researcher", "critic", "賛成派") to participating agents. All agents approached the same task from the same perspective, reducing discussion diversity.

### Decision

Roles are **free-form strings** — no enums, no presets, no hardcoded role types. The framework provides only the extraction and injection mechanism.

**Role sources (priority order):**
1. **User-specified** — regex extraction from goal text via `DiscussionRoleExtractor` (4 patterns)
2. **LLM-generated** — LLM decomposition includes `"role"` field in JSON output when `role_assignment=True`
3. **None** — no role assigned, backward-compatible behavior

**4 regex patterns for user-specified roles:**
| Pattern | Example | Extracted |
|---------|---------|-----------|
| `role:/roles:/役割:` | `role: optimist, pessimist` | `["optimist", "pessimist"]` |
| `Xとして` | `賛成派として、反対派として` | `["賛成派", "反対派"]` |
| `Xの立場で/視点で/観点で` | `消費者の立場で、生産者の立場で` | `["消費者", "生産者"]` |
| `as a [role]` | `as a researcher, as a critic` | `["researcher", "critic"]` |

**Role injection points (all 3 execution paths + discussion):**
- Engine routing: `role_prefix + config.user_prompt`
- ReAct: `role_prefix + config.system_prompt + TOOL_USAGE_INSTRUCTION`
- Direct LLM: `role_prefix + config.system_prompt` in system message
- Discussion: `role_tag` in model_outputs (e.g. `[claude-sonnet-4-6, role: analyst]`)

### Rationale

| Choice | Rationale |
|--------|-----------|
| Free-form strings (not enums) | User asked for generalization — roles depend on the task, not the framework |
| Regex extraction (pure domain) | Zero I/O, zero external dependencies, fully deterministic |
| Model name filtering in として | `claudeとして` is model reference, not a role |
| User roles override LLM roles | User intent always takes priority |
| `discussion_role_assignment` config | Opt-out possible for users who don't want auto-generated roles |
| Wrap-around assignment | If 3 subtasks but 2 roles, role[i % len(roles)] distributes evenly |

### Files Changed

| File | Change |
|------|--------|
| `domain/entities/task.py` | `role: str \| None = None` field on SubTask |
| `domain/services/discussion_role_extractor.py` | **NEW** — DiscussionRoleExtractor with 4 regex patterns + LLM prompt builder |
| `domain/services/__init__.py` | Export DiscussionRoleExtractor |
| `shared/config.py` | `discussion_role_assignment: bool = True` |
| `infrastructure/task_graph/intent_analyzer.py` | `_assign_roles()`, role_field/role_instruction in multi-model prompt, parse role from JSON |
| `infrastructure/task_graph/engine.py` | Role prefix injection in all 3 paths + discussion role tags |
| `interface/api/container.py` | Pass `role_assignment` setting to IntentAnalyzer |
| `tests/unit/domain/test_discussion_role_extractor.py` | **NEW** — 25 tests |
| `tests/unit/infrastructure/test_engine_roles.py` | **NEW** — 10 tests |
| `tests/unit/infrastructure/test_intent_analyzer.py` | +7 tests in TestRoleAssignment |

### Test Count

1,969 → 1,992 (+23 new tests). 0 failures, lint clean.

---

## TD-089: Artifact-Aware Planning & Inter-Round Artifact Sharing

**Date**: 2026-03-22
**Status**: Planned

### Context

Multi-agent discussion and subtask execution currently pass only text between rounds/subtasks. When Agent A writes code or collects data in Round 1, Agent B in Round 2 receives only a text summary — not the actual code, execution output, or structured data. This prevents true collaborative development where agents build on each other's work.

### Decision

Add a generic artifact system to planning and execution:

1. **SubTask artifacts** — `input_artifacts: dict[str, str]` and `output_artifacts: dict[str, str]` on SubTask entity
2. **PlanStep artifact flow** — `produces: list[str]` and `consumes: list[str]` on PlanStep entity
3. **Planning-phase awareness** — IntentAnalyzer LLM prompt includes artifact flow instructions so decomposition plans which subtask produces/consumes what
4. **Execution-phase injection** — `_execute_batch()` chains previous subtask output_artifacts into next subtask input_artifacts
5. **Discussion-phase artifacts** — each discussion round's output (code blocks, URLs, data) becomes an artifact for the next round

### Design Constraints

| Constraint | Rationale |
|-----------|-----------|
| `dict[str, str]` (key=name, value=content) | Maximally generic — code, URLs, JSON, text all fit. No type-specific schemas |
| Artifact names are free-form strings | Same philosophy as roles (TD-088) — framework provides mechanism, not policy |
| No file-system persistence in Phase 1 | Artifacts live in memory during execution. Persist to DB only in execution record |
| Backward-compatible | Empty artifacts = current behavior. No breaking changes |

### Implementation Plan (Two Sub-Sprints)

**Sprint 13.4a — Planning Phase (artifact-aware decomposition)**:
- Domain: add fields to SubTask + PlanStep
- IntentAnalyzer: artifact flow in LLM decomposition prompt + static fallback
- Tests: artifact field validation + planning flow

**Sprint 13.4b — Runtime Phase (artifact passing)**:
- Engine: inject input_artifacts into subtask prompt, extract output_artifacts from result
- Discussion: round output → artifact → next round input
- Code block / URL / data extraction from engine output

### Rationale

| Choice | Rationale |
|--------|-----------|
| Plan before runtime | Planning awareness enables smarter decomposition — LLM can design artifact dependencies |
| Generic dict over typed artifacts | Avoid specializing for specific task patterns (coding vs research vs analysis) |
| Extract from output (not require) | Engines are autonomous — they may or may not produce structured output. Extract what's available |
| Two sub-sprints | Incremental delivery: planning alone is useful for visibility even before runtime sharing works |

---

## TD-090: Artifact Runtime Extraction — Smart Parsing from Engine Output

**Date**: 2026-03-22
**Status**: Accepted
**Sprint**: 13.4b

### Context

Sprint 13.4a added artifact-aware planning with `input_artifacts`/`output_artifacts` on SubTask. However, the runtime extraction (`_extract_output_artifacts`) was naive — it simply assigned `result`, `code`, `execution_output` to artifact keys in positional order. For engine-routed subtasks where all content (code blocks, URLs, JSON data, analysis text) is in the `result` field, the extractor couldn't distinguish structured content types.

### Decision

Create a pure domain service `ArtifactExtractor` that:

1. **Parses** raw text output into structured categories:
   - Code blocks (fenced ```lang ... ``` via regex)
   - URLs (http/https patterns, deduplicated)
   - JSON blocks (```json fences, validated via `json.loads`)
2. **Matches** extracted content to artifact keys using keyword heuristics:
   - CODE keywords: `code`, `implementation`, `script`, `function`, `snippet`, etc.
   - URL keywords: `url`, `link`, `endpoint`, etc.
   - DATA keywords: `data`, `json`, `result`, `schema`, etc.
3. **Falls back** to positional assignment for unmatched keys (backwards compatible with Sprint 13.4a)

### Design Constraints

| Constraint | Rationale |
|-----------|-----------|
| Pure domain service (no I/O) | Follows existing pattern (AnswerExtractor, TopicExtractor) — zero external deps |
| Keyword heuristics, NOT LLM-based | Runtime extraction must be instant and $0. No API calls for parsing |
| Backwards compatible | All Sprint 13.4a tests pass unchanged. New behavior is strictly additive |
| Generic keywords only | No scenario-specific terms. Framework capability, not use-case specialization |
| Priority order: code > url > data | When a key like "source_code" matches both URL ("source") and CODE ("code"), code wins |

### Implementation

- `domain/services/artifact_extractor.py` — `ArtifactExtractor` with `extract()`, `match_to_keys()`, `extract_and_match()`
- `infrastructure/task_graph/engine.py` — `_extract_output_artifacts()` rewritten to combine result + code + execution_output and delegate to ArtifactExtractor
- +34 tests (29 domain + 5 engine integration)

### Rationale

| Choice | Rationale |
|--------|-----------|
| Keyword heuristics over embedding similarity | Instant, deterministic, zero-cost. Good enough for artifact routing — LLM already chose the key names during planning |
| Combined text (result + wrapped code + exec_output) | For engine-routed subtasks, all content is in `result`. For direct LLM, `code` field needs wrapping in fences for consistent extraction |
| Positional fallback for unmatched keys | Ensures no regression. Keys like "exec_out" that don't match any category still get their positional value |
| Code blocks returned without fences | Raw code is more composable. Consumers can add fences if needed for display |

---

## TD-091: Adaptive Discussion Strategy — Convergence Detection

**Date**: 2026-03-22
**Status**: Accepted
**Sprint**: 13.5

### Context

Sprint 13.1 introduced configurable N-round discussion with `discussion_max_rounds`. However, the round count was fixed — identical outputs still triggered additional rounds, wasting cost. Conversely, there was no mechanism to detect when agents had reached consensus and stop early.

### Decision

Add convergence detection to the discussion loop via a pure domain service `ConvergenceDetector`. When `discussion_adaptive=True`, the engine checks after each round (≥ min_rounds) whether the discussion has stabilized, and stops early if so.

### Implementation

| Component | Detail |
|-----------|--------|
| `domain/services/convergence_detector.py` | Pure static service — Jaccard similarity + agreement/divergence signal density + length stability |
| `ConvergenceResult` | Frozen dataclass: `converged`, `similarity`, `agreement_score`, `divergence_score`, `signals` |
| `should_continue()` | High-level decision: always continue < min_rounds, always stop ≥ max_rounds, check convergence between |
| Config | `discussion_adaptive` (default False), `discussion_convergence_threshold` (0.85), `discussion_min_rounds` (1) |
| Engine integration | `_run_discussion()` calls `ConvergenceDetector.should_continue()` after each round, breaks on convergence |

### Convergence formula

```
effective_score = jaccard_similarity + (agreement_density * 0.15) - (divergence_density * 0.2)
converged = effective_score >= threshold
```

Three signals combined:
1. **Jaccard word overlap** — primary signal (are the texts saying the same thing?)
2. **Agreement keywords** — boosts convergence ("agree", "confirm", "correct", "一致", "問題なし")
3. **Divergence keywords** — suppresses convergence ("disagree", "incorrect", "instead", "矛盾")

### Rationale

| Choice | Rationale |
|--------|-----------|
| Pure domain service, not LLM-based | Zero cost, deterministic, fast. LLM-based convergence assessment would add latency and cost per round |
| Jaccard over embedding similarity | No embedding dependency needed. Word overlap is sufficient for detecting stabilized discussion output |
| Opt-in via `discussion_adaptive=False` default | Backward compatible. Fixed-round behavior preserved for users who want predictable round counts |
| Separate `min_rounds` from `max_rounds` | Allows "run at least 2 rounds, then check convergence up to 5" pattern |
| Bilingual signal keywords (EN + JP) | Framework is used in both languages; both should be recognized |

---

## TD-092: Engine Cost Tracking from Usage Metadata

**Date**: 2026-03-22
**Status**: Accepted

### Decision

Add `EngineCostCalculator` domain service to compute cost from engine CLI `usage` metadata, and integrate it into all 4 CLI drivers (Claude Code, Codex, Gemini, OpenHands). Also install Gemini CLI and document MCP_SERVERS configuration.

### Implementation

| Component | Detail |
|-----------|--------|
| `domain/services/engine_cost_calculator.py` | Pure static service — model pricing table + token-based cost calculation |
| `calculate(model, usage)` | Returns `float` cost_usd from `prompt_tokens`/`completion_tokens` dict |
| `calculate_detailed(model, usage)` | Returns `UsageCost` with input/output breakdown |
| `estimate_from_duration(rate, seconds)` | Fallback: hourly rate × duration |
| CLI drivers | All 4 drivers now call `EngineCostCalculator.calculate()` after JSON parse |
| `.env.example` | Added `MCP_SERVERS` and `MCP_ENABLED` with format documentation |
| Gemini CLI | Installed v0.34.0 via `npm install -g @google/gemini-cli` |

### Pricing model

```
model → (input_per_M, output_per_M) lookup
cost = (prompt_tokens / 1M) × input_price + (completion_tokens / 1M) × output_price
```

Resolution order: direct key → alias map → substring match → default ($3/$15 per M).
Ollama models always return $0.0.

### Rationale

| Choice | Rationale |
|--------|-----------|
| Domain service (not infrastructure) | Pure math, no I/O — token counts + pricing = dollars |
| Pricing in code, not config | Pricing changes rarely; code review on update is better than silent config drift |
| Driver-level integration | Each driver knows its JSON format; extracting usage at the source is cleanest |
| Alias + substring matching | Model strings vary (e.g., `claude-sonnet-4-6-20260301`); flexible matching avoids missed cost tracking |
| Fallback to default pricing | Unknown future models still get reasonable cost estimates rather than $0 |

---

## TD-093: Claude Code CLI — `--setting-sources user` flag to prevent CLAUDE.md contamination

**Date**: 2026-03-22
**Status**: Accepted
**Trigger**: Live test (adaptive discussion) showed Claude Code CLI auto-ingesting the project's CLAUDE.md (~95KB) into its context, causing confused responses that mixed Morphic-Agent architecture with task output.

### Problem

When `claude -p <task>` is invoked from the project directory, Claude Code automatically reads `CLAUDE.md` and `.windsurfrules` as "project sources." This injected ~95KB of Morphic-Agent project context into every engine-routed task, contaminating results.

### Decision

Add `--setting-sources user` to the `claude -p` command to exclude project and enterprise sources. Only user-level settings (e.g., `~/.claude/settings.json`) are loaded.

### Changes

| File | Change |
|------|--------|
| `infrastructure/agent_cli/claude_code_driver.py` | Added `"--setting-sources", "user"` to command list |
| `tests/unit/infrastructure/test_claude_code_driver.py` | Updated `test_command_shape` expected command |

### Final command shape

```
["claude", "-p", <task>, "--output-format", "json", "--max-turns", "10", "--setting-sources", "user"]
```

---

## TD-094: Gemini CLI — API key injection + auth-aware `is_available()`

**Date**: 2026-03-22
**Status**: Accepted
**Trigger**: Live test showed Gemini CLI binary exists (v0.34.0) but execution failed with auth error. `is_available()` returned True (binary check only), masking the real issue.

### Problem

1. **Missing API key**: `.env` has `GOOGLE_GEMINI_API_KEY` but the Gemini CLI expects `GEMINI_API_KEY` in the subprocess environment. Since `SubprocessMixin._run_cli()` didn't pass `env`, the subprocess inherited the parent's `os.environ` which lacked `GEMINI_API_KEY`.
2. **Incomplete availability check**: `is_available()` only checked binary existence, not authentication readiness.

### Decision

| Change | Rationale |
|--------|-----------|
| Add `env` param to `SubprocessMixin._run_cli()` | Generic, backward-compatible (`None` = inherit parent env). Enables any driver to customize subprocess env. |
| Add `api_key` param to `GeminiCLIDriver.__init__()` | Explicit DI for testability. Falls back to `GEMINI_API_KEY` then `GOOGLE_GEMINI_API_KEY` from env. |
| `_build_env()` injects `GEMINI_API_KEY` into subprocess env | Ensures the CLI receives the key regardless of which env var name the config uses. |
| `is_available()` checks API key presence | Prevents false-positive availability. Engine router falls back immediately instead of waiting for auth failure. |
| DI container passes `google_gemini_api_key` from settings | Connects pydantic-settings config to driver constructor. |

### Changes

| File | Change |
|------|--------|
| `infrastructure/agent_cli/_subprocess_base.py` | `_run_cli()` accepts optional `env: dict` param |
| `infrastructure/agent_cli/gemini_cli_driver.py` | `api_key` constructor param, `_resolve_api_key()`, `_build_env()`, auth-aware `is_available()` |
| `interface/api/container.py` | DI wiring: pass `api_key=settings.google_gemini_api_key` |
| `tests/unit/infrastructure/test_gemini_cli_driver.py` | +5 tests (api_key stored, no-key unavailable, GOOGLE_GEMINI_API_KEY env, GEMINI_API_KEY env, env injection) |

### API key resolution order

```
1. Constructor api_key argument (from DI / settings)
2. os.environ["GEMINI_API_KEY"]
3. os.environ["GOOGLE_GEMINI_API_KEY"]
```

### Test count after TD-093 + TD-094

**2,137 unit tests + 50 integration, 0 failures (19 pre-existing MCP lib), lint clean.**

---

## TD-095: Gemini CLI — LiteLLM model prefix stripping + JSON output parsing

**Date**: 2026-03-23
**Status**: Accepted
**Trigger**: Live test Round 7 showed Gemini engine routing always fell back to Ollama despite `gemini_cli` being available. Direct `POST /api/engines/run` with `engine=gemini_cli` + `model=gemini/gemini-3-pro-preview` also fell back.

### Problem

1. **Model prefix mismatch**: LiteLLM uses `gemini/gemini-3-pro-preview` format, but the Gemini CLI `-m` flag expects bare model names (`gemini-3-pro-preview`). Passing the prefixed name caused `ModelNotFoundError` (HTTP 404) with exit code 1.
2. **JSON output field mismatch**: Driver parsed `data.get("result")` but Gemini CLI outputs `data["response"]`. The output fell back to raw JSON string instead of the actual response text.
3. **No usage/model extraction from stats**: Gemini CLI returns token usage in `stats.models.<model>.tokens` (not a top-level `usage` key), so cost tracking returned $0.00.

### Decision

| Change | Rationale |
|--------|-----------|
| Strip provider prefix from model before `-m` flag | Generic: `model.split("/", 1)[-1]`. Works for any `provider/model` format. Gemini CLI receives bare name. |
| Parse `response` key with `result` fallback | Matches Gemini CLI's actual output format. Backward-compatible with any tool that uses `result`. |
| Extract `stats.models` for token aggregation | Aggregates `input` + `candidates` tokens across all models (utility_router + main). Picks `main` role model as `model_used`. |

### Changes

| File | Change |
|------|--------|
| `infrastructure/agent_cli/gemini_cli_driver.py` | Prefix stripping in `run_task()`, `response` key parsing, `stats.models` token aggregation |
| `tests/unit/infrastructure/test_gemini_cli_driver.py` | +5 tests (prefix stripping, no-prefix passthrough, response key, stats.models parsing) |
| `tests/unit/infrastructure/test_mcp_server.py` | `_FakeSettings` — added missing `discussion_role_assignment`, `discussion_adaptive`, `discussion_convergence_threshold`, `discussion_min_rounds`, `google_gemini_api_key` |

### Live verification (Round 7)

| Subtask | Engine | Model | Cost | Topic correct? |
|---------|--------|-------|------|----------------|
| 1 (Gemini) | `gemini_cli` ✅ | gemini/gemini-3-pro-preview | $0.0309 | ✅ |
| 2 (Claude) | `claude_code` ✅ | claude-sonnet-4-6 | $0.0051 | ❌ (artifact chaining gap) |
| 4 (Discussion R3) | `ollama` | ollama/qwen3:8b | $0.0373 | ✅ |

### Test count after TD-095

**2,160 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-096: Artifact Chaining — Dependency Inference from Artifact Flow

**Date**: 2026-03-23
**Status**: Accepted
**Sprint**: 14.4
**Trigger**: Live test Round 7 showed subtask 2 (Claude) didn't receive artifacts from subtask 1 (Gemini). Root cause: `dependencies=[]` caused parallel execution via `asyncio.gather`, so `_inject_artifacts()` found no completed subtasks.

### Problem

`_apply_artifact_flow()` set `input_artifacts` and `output_artifacts` but did NOT set `dependencies`. When the LLM omitted `deps` (or the static fallback was used), all subtasks ran in parallel. Since `_inject_artifacts()` only finds artifacts from **completed** subtasks, parallel execution meant no artifacts were available for injection.

Additionally, `_create_per_model_subtasks()` (static fallback) never called `_apply_artifact_flow()`, so fallback subtasks had no artifact schemas at all — both `_inject_artifacts()` and `_extract_output_artifacts()` short-circuited on empty schemas.

### Decision

| Change | Rationale |
|--------|-----------|
| Infer dependencies from LLM-specified produces/consumes | Build producer map (artifact→index), add dependency for each consumer→producer pair. Generic: works for any DAG shape, not just linear. |
| Infer dependencies from linear chain | When inferring `step_N_output`, set `subtask[i].dependencies = [subtask[i-1].id]`. Natural: if B consumes A's output, B should wait for A. |
| Deduplicate with `if dep_id not in st.dependencies` | When LLM provides both `deps` and `produces/consumes`, avoid duplicate dependency entries. |
| Static fallback calls `_apply_artifact_flow()` | `_create_per_model_subtasks()` now gets artifact chain + dependencies, fixing the entire fallback path. |

### Three code paths fixed

1. **LLM provides produces/consumes but omits deps** → dependencies inferred from artifact flow
2. **LLM provides neither produces/consumes nor deps** → linear chain inference provides both artifacts and dependencies
3. **Static fallback** → `_create_per_model_subtasks()` calls `_apply_artifact_flow()` with empty maps → linear chain inferred

### Files Changed

| File | Change |
|------|--------|
| `infrastructure/task_graph/intent_analyzer.py` | `_apply_artifact_flow()`: producer→consumer dependency inference for both LLM-specified and linear chain paths. `_create_per_model_subtasks()`: calls `_apply_artifact_flow()`. |
| `tests/unit/infrastructure/test_intent_analyzer_artifacts.py` | +8 new tests (dep inference from LLM flow, linear chain, multi-producer, dedup, static fallback chain) |
| `tests/unit/infrastructure/test_intent_analyzer.py` | Updated `test_no_dependencies` → `test_no_explicit_deps_infers_linear_chain` (reflects TD-096 behavior) |

### Test count after TD-096

**2,172 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-097: Plan Approval — Dependency Re-inference from Artifact Flow

**Date**: 2026-03-23
**Status**: Accepted
**Sprint**: 14.5
**Trigger**: TD-096 correctly inferred dependencies during `IntentAnalyzer.decompose()`, but the planning flow (`create_plan` → PlanStep → `approve_plan` → new SubTask) lost them because PlanSteps don't carry dependency IDs and `approve_plan` generates new SubTask UUIDs.

### Problem

The planning flow (Interactive/Auto mode) has a PlanStep intermediate:

```
decompose() → SubTasks (with deps) → PlanSteps (no deps) → approve_plan() → NEW SubTasks (no deps)
```

`PlanStep` stores `produces`/`consumes` (artifact names) but NOT `dependencies` (SubTask IDs). When `approve_plan()` creates fresh SubTasks with new UUIDs, TD-096's inferred dependencies referencing OLD IDs become stale. Result: all subtasks execute in parallel despite correct artifact schemas.

This only affects Interactive/Auto planning mode. The legacy DISABLED mode (`CreateTaskUseCase`) uses `decompose()` subtasks directly — no ID remapping issue.

### Decision

| Change | Rationale |
|--------|-----------|
| Extract `ArtifactDependencyResolver` domain service | Pure domain logic (no external deps). Shared between `IntentAnalyzer._apply_artifact_flow()` and `InteractivePlanUseCase.approve_plan()`. Avoids duplication. |
| Call resolver in `approve_plan()` after SubTask creation | Re-infers dependencies from the artifacts that PlanStep correctly preserved (`produces`/`consumes` → `output_artifacts`/`input_artifacts`). Uses the new SubTask IDs. |
| Refactor `_apply_artifact_flow()` to delegate dep inference | Sets artifact maps (LLM-specified or linear chain), then delegates dependency resolution to the shared service. Removes inline dependency logic. |

### Files Changed

| File | Change |
|------|--------|
| `domain/services/artifact_dependency_resolver.py` | NEW — `resolve(subtasks)`: infer deps from artifact flow or linear chain fallback |
| `application/use_cases/interactive_plan.py` | `approve_plan()`: call `ArtifactDependencyResolver.resolve()` after creating SubTasks |
| `infrastructure/task_graph/intent_analyzer.py` | `_apply_artifact_flow()`: delegate dep inference to resolver. Removed debug logging. |
| `tests/unit/domain/test_artifact_dependency_resolver.py` | NEW — 12 tests (artifact chain, diamond, dedup, linear, empty, plan approval simulation) |
| `tests/unit/application/test_interactive_plan.py` | +2 tests (approve with artifacts, approve without artifacts) |

### Test count after TD-097

**2,186 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-098: Ollama Engine — Reject Non-Installed Models for Correct Fallback

**Date**: 2026-03-23
**Status**: Accepted
**Sprint**: 14.5
**Trigger**: Live test showed o4-mini requests silently falling back to `ollama/qwen3:8b` instead of reaching the OpenAI API via ReactExecutor/LiteLLM.

### Problem

When Codex CLI fails for o4-mini, the engine fallback chain routes to OllamaEngineDriver. The driver blindly adds `ollama/` prefix (`ollama/o4-mini`) and calls LiteLLMGateway, which detects the model isn't installed and silently falls back to `ollama/qwen3:8b`. Since the Ollama engine "succeeds" (with the wrong model), the chain stops and never reaches ReactExecutor → LiteLLM API with the correct model.

### Decision

| Change | Rationale |
|--------|-----------|
| Check installed models before execution | `OllamaEngineDriver.run_task()` calls `ollama.list_models()` and returns `success=False` if the requested model isn't installed. |
| Chain continues to ReactExecutor | When Ollama rejects, the engine chain exhausts → falls through to ReAct/LiteLLM which correctly calls o4-mini via OpenAI API. |

### Files Changed

| File | Change |
|------|--------|
| `infrastructure/agent_cli/ollama_driver.py` | `run_task()`: check `list_models()` before execution, return failure for non-installed models |
| `tests/unit/infrastructure/test_ollama_driver.py` | Mock `list_models`, +2 new tests (reject non-Ollama, accept installed) |

### Test count after TD-098

**2,188 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-099: Fractal Recursive Engine — Domain Model Foundation

**Date**: 2026-03-23
**Status**: Accepted
**Sprint**: 15.1
**Trigger**: NEXT_DESIGN.md specifies a fractal recursive engine architecture where every execution node is an engine instance with dual evaluation gates.

### Problem

The current execution pipeline (IntentAnalyzer → LangGraphTaskEngine → Engine routing) is linear. NEXT_DESIGN.md requires a recursive architecture where each node can spawn sub-engines, plans are evaluated by multiple LLMs before execution (Gate ①), and results are evaluated after execution (Gate ②) with failure propagation across nesting levels.

### Decision

Implement the fractal engine domain model as a foundation layer, following existing Clean Architecture patterns (zero external dependencies in domain):

| Component | Type | Purpose |
|-----------|------|---------|
| `NodeState` | Value Object | VISIBLE, PRUNED, FAILED, CONDITIONAL (iceberg states) |
| `PlanEvalDecision` | Value Object | APPROVED, REJECTED (Gate ① outcome) |
| `ResultEvalDecision` | Value Object | OK, RETRY, REPLAN (Gate ② outcome) |
| `EvalAxis` | Value Object | COMPLETENESS, FEASIBILITY, SAFETY |
| `PlanNode` | Entity | Execution node with nesting_level, retry control |
| `CandidateNode` | Entity | Node with iceberg state tracking |
| `ExecutionPlan` | Entity | Visible nodes + candidate space |
| `PlanEvaluation` | Entity | Gate ① scores per axis |
| `ResultEvaluation` | Entity | Gate ② OK/RETRY/REPLAN decision |
| `PlannerPort` | Port | Generate candidate node sequences |
| `PlanEvaluatorPort` | Port | Multi-LLM plan evaluation |
| `ResultEvaluatorPort` | Port | Post-execution result evaluation |
| `CandidateSpaceManager` | Service | Select, prune, activate conditional nodes |
| `FailurePropagator` | Service | Level N → N-1 failure bubbling |
| `NestingDepthController` | Service | Max depth + budget control |

### Files Changed

| File | Change |
|------|--------|
| `domain/value_objects/fractal_engine.py` | NEW: NodeState, PlanEvalDecision, ResultEvalDecision, EvalAxis |
| `domain/entities/fractal_engine.py` | NEW: PlanNode, CandidateNode, ExecutionPlan, PlanEvaluation, ResultEvaluation |
| `domain/ports/planner.py` | NEW: PlannerPort |
| `domain/ports/plan_evaluator.py` | NEW: PlanEvaluatorPort |
| `domain/ports/result_evaluator.py` | NEW: ResultEvaluatorPort |
| `domain/services/candidate_space_manager.py` | NEW: CandidateSpaceManager |
| `domain/services/failure_propagator.py` | NEW: FailurePropagator + PropagationReport |
| `domain/services/nesting_depth_controller.py` | NEW: NestingDepthController |
| `domain/*/\__init__.py` | Updated exports |
| `tests/unit/domain/test_fractal_engine_entities.py` | NEW: 23 tests |
| `tests/unit/domain/test_fractal_engine_services.py` | NEW: 25 tests |

### Test count after TD-099

**2,236 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-100: Fractal Engine — LLM Planner (PlannerPort Implementation)

**Date**: 2026-03-25
**Status**: Accepted
**Sprint**: 15.2
**Trigger**: Sprint 15.1 defined PlannerPort; Sprint 15.2 implements the first infrastructure layer piece — the LLM-powered planner that generates candidate node sequences.

### Problem

The fractal engine domain model (TD-099) defines `PlannerPort` as an abstraction for generating candidate execution steps from a goal. An infrastructure implementation is needed that leverages LLMs to decompose goals into ordered candidate nodes with scoring, conditional fallbacks, and terminal detection.

### Decision

Implement `LLMPlanner(PlannerPort)` in `infrastructure/fractal/llm_planner.py` with:

| Design Choice | Detail |
|---------------|--------|
| JSON extraction | Module-level `_extract_json()` — strips `<think>` tags, markdown blocks, finds JSON array. Same proven pattern as `IntentAnalyzer._extract_json` but decoupled. |
| Prompt structure | KV-cache friendly: stable system prefix (JSON schema + rules) + dynamic suffix (direction, nesting level, candidates count, parent context) |
| Terminal detection | Hybrid: LLM's `is_terminal` field respected + hard override at `nesting_level >= max_depth - 1` (prevents infinite recursion) |
| Conditional nodes | LLM outputs `condition` field — `null` = VISIBLE, string = CONDITIONAL with `activation_condition` |
| Fallback | Invalid JSON or LLM exception → single VISIBLE terminal CandidateNode (goal as description, score=1.0) |
| Score clamping | Scores clamped to [0.0, 1.0] regardless of LLM output |
| Dependencies | `LLMGateway` port only (Clean Architecture compliant, no infrastructure imports in constructor) |
| LLM params | `temperature=0.3`, `max_tokens=2048` (deterministic, sufficient for plan generation) |

### Files Changed

| File | Change |
|------|--------|
| `infrastructure/fractal/__init__.py` | NEW: package marker |
| `infrastructure/fractal/llm_planner.py` | NEW: LLMPlanner(PlannerPort) + _extract_json() |
| `tests/unit/infrastructure/test_llm_planner.py` | NEW: 22 tests (6 categories) |

### Test count after TD-100

**2,258 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-101: Gate ① Plan Evaluator + Aggregator

**Date**: 2026-03-25
**Status**: Accepted
**Sprint**: 15.3
**Trigger**: Sprint 15.1 defined `PlanEvaluatorPort`; Sprint 15.3 implements the multi-LLM plan evaluation gate with domain-level score aggregation.

### Problem

The fractal engine needs Gate ① — an evaluation checkpoint that assesses generated plans before execution. Multiple LLMs should independently score a plan on completeness, feasibility, and safety, with aggregated consensus determining approval or rejection.

### Decision

Implement in two layers following Clean Architecture:

**Domain layer** — `PlanEvalAggregator` (pure aggregation, no I/O):

| Design Choice | Detail |
|---------------|--------|
| Aggregation | Weighted arithmetic mean per axis across N evaluations |
| Axis weights | Configurable `{"completeness": w, "feasibility": w, "safety": w}`, default equal |
| Decision threshold | `overall_score >= min_score` → APPROVED, else REJECTED (AD-4: default 0.5) |
| Feedback | Merged from all evaluators with model labels: `[ollama] ...; [claude] ...` |
| Empty input | Returns REJECTED with "No evaluations provided" |

**Infrastructure layer** — `LLMPlanEvaluator(PlanEvaluatorPort)`:

| Design Choice | Detail |
|---------------|--------|
| Multi-model | `asyncio.gather` parallel evaluation across configured model list |
| Default model | Empty models list → single evaluation with `model=None` (Ollama $0 via LOCAL_FIRST) |
| Prompt structure | KV-cache friendly: stable system prefix (eval axes + JSON schema) + dynamic user message (goal + formatted plan nodes + conditional fallbacks) |
| JSON extraction | Reuses `_extract_json()` from `llm_planner.py` + additional `re.search(r"\{.*}")` for JSON objects |
| Score clamping | All scores clamped to [0.0, 1.0] |
| Fallback | JSON parse failure or LLM exception → conservative scores (0.5, 0.5, 1.0) |
| Partial failure | If 1 of N models fails, surviving evaluations + fallback still aggregated |
| LLM params | `temperature=0.2` (more deterministic than planner), `max_tokens=1024` |
| Cost strategy | AD-3: Ollama first ($0), cloud models optional |

### Files Changed

| File | Change |
|------|--------|
| `domain/services/plan_eval_aggregator.py` | NEW: PlanEvalAggregator + _weighted_mean + _merge_feedback |
| `infrastructure/fractal/llm_plan_evaluator.py` | NEW: LLMPlanEvaluator(PlanEvaluatorPort) |
| `tests/unit/domain/test_plan_eval_aggregator.py` | NEW: 18 tests (6 categories) |
| `tests/unit/infrastructure/test_llm_plan_evaluator.py` | NEW: 16 tests (6 categories) |

### Test count after TD-101

**2,292 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-102: Gate ② Result Evaluator + Decision Maker

**Date**: 2026-03-25
**Status**: Accepted
**Sprint**: 15.4
**Trigger**: Sprint 15.1 defined `ResultEvaluatorPort`; Sprint 15.4 implements the post-execution quality gate with score-to-decision conversion.

### Problem

The fractal engine needs Gate ② — an evaluation checkpoint that assesses execution results after each node completes. It must score the result on accuracy, validity, and goal_alignment, then decide: OK (advance), RETRY (re-execute), or REPLAN (revise plan). Thresholds must be configurable per AD-4.

### Decision

Implement in two layers following Clean Architecture:

**Domain layer** — `ResultEvalDecisionMaker` (pure score-to-decision, no I/O):

| Design Choice | Detail |
|---------------|--------|
| `decide()` | Raw ResultEvaluation → weighted overall_score → OK/RETRY/REPLAN |
| `aggregate()` | N evaluations → arithmetic mean per axis → `decide()` |
| Thresholds | OK ≥ `ok_threshold` (0.7), RETRY ≥ `retry_threshold` (0.4), REPLAN < `retry_threshold` — per AD-4 |
| Axis weights | Configurable `{"accuracy": w, "validity": w, "goal_alignment": w}`, default equal |
| Round-before-compare | `round(overall, 4)` before threshold comparison to avoid floating-point boundary errors |
| Feedback | Merged from all evaluators with `[eval-N]` labels |
| Empty input | Returns REPLAN with "No evaluations provided" |

**Infrastructure layer** — `LLMResultEvaluator(ResultEvaluatorPort)`:

| Design Choice | Detail |
|---------------|--------|
| Single-model | Uses cheapest available model (Ollama preferred, AD-3). No multi-model parallelism needed (Gate ② runs per-node, cost-sensitive) |
| Prompt structure | KV-cache friendly: stable system prefix (eval axes + JSON schema) + dynamic user message (goal + node description + result preview) |
| Result truncation | Execution results truncated to 2000 chars in prompt to prevent context overflow |
| JSON extraction | Dedicated `_extract_json_object()` — handles think tags, markdown blocks, surrounding text |
| Score clamping | All scores clamped to [0.0, 1.0] |
| Fallback | JSON parse failure or LLM exception → conservative scores (0.5, 0.5, 0.5) → DecisionMaker applies thresholds |
| LLM params | `temperature=0.2`, `max_tokens=1024` |
| Decision delegation | Raw scores passed to `ResultEvalDecisionMaker.decide()` — separation of parsing from decision logic |
| Cost strategy | AD-3: Ollama first ($0), configurable `model` parameter for cloud override |

### Key Difference from Gate ①

| Aspect | Gate ① (Plan Evaluator) | Gate ② (Result Evaluator) |
|--------|-------------------------|---------------------------|
| When | Before execution | After execution |
| Input | Execution plan + goal | Execution result + node + goal |
| Axes | completeness, feasibility, safety | accuracy, validity, goal_alignment |
| Decision | APPROVED / REJECTED | OK / RETRY / REPLAN |
| Multi-model | Yes (parallel, consensus) | No (single cheapest model per node) |
| Aggregation | `PlanEvalAggregator` (separate class) | `ResultEvalDecisionMaker.aggregate()` (same class) |

### Files Changed

| File | Change |
|------|--------|
| `domain/services/result_eval_decision_maker.py` | NEW: ResultEvalDecisionMaker + _score_to_decision + _weighted_mean + _simple_mean + _merge_feedback |
| `domain/services/__init__.py` | MODIFIED: Added ResultEvalDecisionMaker export |
| `infrastructure/fractal/llm_result_evaluator.py` | NEW: LLMResultEvaluator(ResultEvaluatorPort) + _extract_json_object + _clamp |
| `tests/unit/domain/test_result_eval_decision_maker.py` | NEW: 31 tests (7 categories) |
| `tests/unit/infrastructure/test_llm_result_evaluator.py` | NEW: 26 tests (6 categories) |

### Test count after TD-102

**2,349 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-103: FractalTaskEngine Core — Recursive Execution Engine (Sprint 15.5)

**Date**: 2026-03-25
**Status**: Accepted
**Sprint**: 15.5

### Context

Sprint 15.1-15.4 built all components: domain model (TD-099), LLM Planner (TD-100), Gate ① Plan Evaluator (TD-101), Gate ② Result Evaluator (TD-102). Sprint 15.5 integrates everything into the FractalTaskEngine — the recursive execution engine.

### Decision

**WRAP strategy**: FractalTaskEngine wraps the existing LangGraphTaskEngine (884 lines of proven code) instead of replacing it.

```
FractalTaskEngine (NEW: recursion + eval gates + candidate space)
    │
    └── Terminal node execution → LangGraphTaskEngine (EXISTING: engine routing + ReAct + artifacts)
```

**Config-based selection**: `execution_engine: "langgraph" | "fractal"`. Default remains `langgraph` for zero impact on existing behavior.

### Key Design Decisions

1. **NodeExecutor bridge**: Converts PlanNode ↔ SubTask/TaskEntity for inner engine delegation. Handles artifact chaining between nodes.
2. **_PlanFailureError propagation**: Clean exception-based failure propagation across recursion levels. `_execute_with_eval` raises when should_propagate=True; `_execute_plan` catches and tries fallbacks.
3. **Fallback activation at plan level**: When a node fails with REPLAN, `_execute_plan` activates CONDITIONAL candidates matching "failure:{node_description}". The fallback replaces the failed node.
4. **Budget enforcement**: `NestingDepthController.check_budget()` forces non-terminal nodes to terminal when budget is nearly exhausted, preventing unbounded recursion cost.
5. **Plan retry loop**: `_generate_approved_plan` retries up to `max_plan_attempts` when Gate ① rejects, passing rejection feedback to the Planner for revision.

### Execution Flow

```
execute(task)
  → _generate_approved_plan(goal, level=0)
    → Planner → Gate ① → approved plan
  → _execute_plan(plan, goal, level=0)
    → For each visible node:
      → inject_artifacts (chain from previous nodes)
      → check_budget (force terminal if exhausted)
      → _execute_with_eval(node, goal, level)
        → should_terminate? → NodeExecutor.execute_terminal (→ LangGraphTaskEngine)
        → expandable?       → _execute_expandable (recursive decompose + execute)
        → Gate ② evaluate result
          → OK: advance
          → RETRY: re-execute (up to max_retries)
          → REPLAN: raise _PlanFailureError
      → on _PlanFailureError: activate conditional fallbacks or mark failed
  → Convert completed PlanNodes → SubTasks → TaskEntity
```

### Gate ① ↔ Gate ② Interaction

| Scenario | Gate ① | Gate ② | Engine Action |
|----------|--------|--------|---------------|
| Good plan, good result | APPROVED | OK | Advance to next node |
| Good plan, bad result | APPROVED | RETRY | Re-execute node (up to max_retries) |
| Good plan, wrong approach | APPROVED | REPLAN | Propagate failure, try fallbacks |
| Bad plan | REJECTED | — | Re-plan with feedback (up to max_plan_attempts) |

### Config Settings Added

```python
execution_engine: str = "langgraph"        # "langgraph" | "fractal"
fractal_max_depth: int = 3                 # max recursion levels
fractal_candidates_per_node: int = 3       # candidates per planning step
fractal_plan_eval_models: str = ""         # comma-separated model list for Gate ①
fractal_plan_eval_min_score: float = 0.5   # minimum score for plan approval
fractal_result_eval_ok_threshold: float = 0.7
fractal_result_eval_retry_threshold: float = 0.4
fractal_max_retries: int = 3              # per-node retry limit
fractal_max_plan_attempts: int = 2        # plan generation attempts
```

### Files Changed

| File | Change |
|------|--------|
| `infrastructure/fractal/node_executor.py` | NEW: NodeExecutor (PlanNode ↔ SubTask bridge, artifact chaining, terminal execution) |
| `infrastructure/fractal/fractal_engine.py` | NEW: FractalTaskEngine(TaskEngine) — recursive execution with dual gates |
| `shared/config.py` | MODIFIED: Added 9 fractal engine settings |
| `interface/api/container.py` | MODIFIED: Conditional wiring (langgraph vs fractal), _create_task_engine() |
| `tests/unit/infrastructure/test_node_executor.py` | NEW: 14 tests |
| `tests/unit/infrastructure/test_fractal_engine.py` | NEW: 20 tests |
| `tests/unit/infrastructure/test_mcp_server.py` | MODIFIED: Added fractal settings to _FakeSettings |

### Test count after TD-103

**2,383 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-104: Sprint 15.6 — Container Wiring Tests + Bug Fix

**Date**: 2026-03-25
**Status**: Accepted
**Sprint**: 15.6

### Decision

Add comprehensive container wiring tests for the fractal engine selection path in `AppContainer._create_task_engine()`. Also fix a parameter name mismatch bug discovered during testing.

### Bug Found

`container.py` passed `eval_models=` to `LLMPlanEvaluator.__init__()`, but the actual parameter name is `models=`. This would have caused a `TypeError` at runtime when `execution_engine="fractal"` was configured. The bug was latent because the default is `langgraph` and the fractal path was never exercised in production.

### Fix

Changed `eval_models=` to `models=` in `_create_task_engine()` (1-line fix in `interface/api/container.py`).

### Test Coverage

19 tests in 4 categories:

| Category | Count | What it verifies |
|----------|-------|-----------------|
| Default Engine Selection | 3 | langgraph default, explicit langgraph, unknown fallback |
| Fractal Engine Selection | 5 | FractalTaskEngine returned, wraps LangGraph, planner/evaluators injected |
| Config Propagation | 9 | All 9 fractal config values correctly passed through |
| Engine Routing Wiring | 2 | route_to_engine wired to inner engine in both modes |

### Files Changed

| File | Change |
|------|--------|
| `interface/api/container.py` | MODIFIED: Fixed `eval_models` → `models` parameter name |
| `tests/unit/interface/test_fractal_container_wiring.py` | NEW: 19 tests |

### Test count after TD-104

**2,402 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-105: Sprint 15.7 — Learning Foundation (Error Patterns + Successful Paths)

**Date**: 2026-03-25
**Status**: Accepted
**Sprint**: 15.7

### Decision

Add minimal viable learning to the fractal engine — record error patterns from failed nodes and successful execution paths from completed plans. In-memory storage for MVP; production persistence deferred.

### Architecture

```
FractalTaskEngine.execute()
  → _record_learning(goal, completed_nodes)
    → FractalLearner.extract_error_patterns() → save to repo
    → FractalLearner.extract_successful_path() → save to repo
```

Clean Architecture:
- **Domain entities**: `ErrorPattern`, `SuccessfulPath` (Pydantic strict, framework-free)
- **Domain port**: `FractalLearningRepository` (ABC)
- **Domain service**: `FractalLearner` (pure functions, no I/O)
- **Infrastructure**: `InMemoryFractalLearningRepository` (auto-merge duplicates)

### Key Design Choices

| Choice | Rationale |
|--------|-----------|
| Optional `learning_repo` param (None default) | Backward-compatible; existing callers unaffected |
| Fire-and-forget `_record_learning()` | Wrapped in try/except, never blocks task execution |
| Auto-merge in repository | Same goal+node+error → increment count, not duplicate entry |
| `_extract_goal_fragment()` | First sentence or 80 chars for matchable goal key |
| In-memory only (MVP) | Full GraphRAG deferred per AD-6 |

### Future Use

Error patterns will be injected into Planner context to avoid known-bad strategies. Successful paths will serve as reference templates. This wiring is deferred to post-stability.

### Files Changed

| File | Change |
|------|--------|
| `domain/entities/fractal_learning.py` | NEW: ErrorPattern, SuccessfulPath entities |
| `domain/ports/fractal_learning_repository.py` | NEW: FractalLearningRepository ABC |
| `domain/services/fractal_learner.py` | NEW: FractalLearner extraction logic |
| `infrastructure/fractal/in_memory_learning_repo.py` | NEW: InMemoryFractalLearningRepository |
| `infrastructure/fractal/fractal_engine.py` | MODIFIED: +learning_repo param, +_record_learning() hook |
| `domain/entities/__init__.py` | MODIFIED: +ErrorPattern, +SuccessfulPath exports |
| `domain/ports/__init__.py` | MODIFIED: +FractalLearningRepository export |
| `domain/services/__init__.py` | MODIFIED: +FractalLearner export |
| `tests/unit/domain/test_fractal_learner.py` | NEW: 23 tests |
| `tests/unit/infrastructure/test_fractal_learning_repo.py` | NEW: 9 tests |

### Test count after TD-105

**2,434 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-106: Wire learning_repo into AppContainer

**Date**: 2026-03-25
**Status**: Accepted
**Sprint**: 15.8

### Decision

Wire `InMemoryFractalLearningRepository` into `AppContainer._create_task_engine()` so that fractal mode automatically records error patterns and successful paths after every task execution.

### Rationale

TD-105 added the learning foundation (`ErrorPattern`, `SuccessfulPath`, `FractalLearner`, `InMemoryFractalLearningRepository`) and `FractalTaskEngine` accepted an optional `learning_repo` parameter. However, `container.py` was not passing it — the parameter defaulted to `None`, meaning no learning was recorded in practice.

### Change

| File | Change |
|------|--------|
| `interface/api/container.py` | Create `InMemoryFractalLearningRepository()` and pass as `learning_repo=` to `FractalTaskEngine` |
| `tests/unit/interface/test_fractal_container_wiring.py` | +2 tests (`TestLearningRepoWiring`) |

### Test count after TD-106

**2,436 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-107: Eliminate double-planning in FractalTaskEngine.decompose()

**Date**: 2026-03-26
**Status**: Accepted
**Sprint**: 16.1

### Decision

Change `FractalTaskEngine.decompose()` to return a lightweight placeholder subtask instead of running the full Planner + Gate ① pipeline. Real planning happens in `execute()`.

### Rationale

`FractalTaskEngine.execute()` re-plans from `task.goal` (by design — "recursive planning is the fractal engine's power"). So `decompose()` running Planner + Gate ① was wasteful: its output was discarded during `execute()`, doubling LLM cost per task.

### Change

| File | Change |
|------|--------|
| `infrastructure/fractal/fractal_engine.py` | `decompose()` returns `[SubTask(description=goal)]` — no LLM calls |
| `tests/unit/infrastructure/test_fractal_engine.py` | 4 old decompose tests replaced with 3 new placeholder tests |

### Test count after TD-107

**2,435 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-108: Non-blocking task execution with asyncio.create_task()

**Date**: 2026-03-26
**Status**: Accepted
**Sprint**: 16.1

### Decision

Replace `background_tasks.add_task()` with `asyncio.create_task()` for task execution dispatch in the tasks API route.

### Rationale

During fractal engine execution (5-7 sequential LLM calls, ~60s total), `background_tasks.add_task()` blocked the uvicorn event loop. Health and task GET endpoints were unresponsive for the entire duration. `asyncio.create_task()` schedules the coroutine concurrently, keeping the server responsive.

### Verified

- Live E2E: health endpoint returns `{"status":"ok"}` during fractal execution
- Planner → Gate ① (score=0.73) → Execute (ReactExecutor+shell_exec) → Gate ② → Learning

### Change

| File | Change |
|------|--------|
| `interface/api/routes/tasks.py` | `asyncio.create_task(_safe_execute())` replaces `background_tasks.add_task()` |

### Test count after TD-108

**2,435 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-109: Fractal Learning Persistence — InMemory → PostgreSQL

**Date**: 2026-03-26
**Status**: Accepted
**Sprint**: 16.2

### Decision

Persist fractal learning data (ErrorPattern, SuccessfulPath) to PostgreSQL instead of in-memory storage, so learning survives server restarts.

### Rationale

InMemoryFractalLearningRepository loses all accumulated learning data on restart. For the "gets smarter with every task" vision to work, patterns and paths must be durable. PostgreSQL is already the project's persistence backend with session_factory available.

### Design

| Aspect | Choice | Reason |
|--------|--------|--------|
| Tables | 2 (`fractal_error_patterns`, `fractal_successful_paths`) | Different column structures per entity |
| Dedup | SELECT → UPDATE/INSERT | ORM-only, no raw SQL. Existing pattern (pg_cost_repository) |
| Substring search | `func.strpos()` | PG-native. Matches domain `matches()` semantics |
| ID | UUID PK (separate from domain 8-char ID) | Existing convention |
| InMemory | Kept | Fallback for `use_postgres=False` + test use |

### Change

| File | Change |
|------|--------|
| `infrastructure/persistence/models.py` | +`FractalErrorPatternModel`, `FractalSuccessfulPathModel` |
| `migrations/versions/003_add_fractal_learning_tables.py` | Alembic migration: 2 tables + unique constraints + desc indexes |
| `infrastructure/persistence/pg_fractal_learning_repository.py` | New: PG implementation of FractalLearningRepository |
| `interface/api/container.py` | Auto-switch: `use_postgres=True` → PgFractalLearningRepository |
| `tests/unit/infrastructure/test_pg_fractal_learning_repo.py` | 11 new tests |
| `tests/unit/interface/test_fractal_container_wiring.py` | +1 PG wiring test |

### Test count after TD-109

**2,447 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-110: Fractal Learning → Planner Integration (Closed-Loop Learning)

**Date**: 2026-03-26
**Status**: Accepted
**Sprint**: 16.3

### Decision

Inject historical learning data into LLMPlanner prompts so the planner avoids known-bad strategies and reuses proven approaches.

### Rationale

Sprint 16.2 persisted learning data but the planner never consumed it — the learning loop was open. Closing it means the system genuinely improves with every task execution.

### Design

| Aspect | Choice | Reason |
|--------|--------|--------|
| Injection point | User message (not system prompt) | KV-cache stability (Manus principle 1) |
| Port ABC | Added `find_error_patterns_by_goal()` | At planning time, node descriptions are unknown; goal-only search needed |
| Constructor | Optional `learning_repo: ... | None = None` | Backward compatible; existing tests unaffected |
| Limits | Max 5 error patterns, 3 successful paths | Prevent context bloat |
| Resilience | try/except around repo queries | DB failure → planner still works (no learning, not crash) |

### Prompt format

```
Known failure patterns (AVOID these approaches):
  - "Setup project" failed with: timeout exceeded (seen 5x)

Proven successful approaches (PREFER these):
  - [Design schema -> Implement endpoints -> Test] (cost: $0.0500) (used 3x)

<goal text>
```

### Change

| File | Change |
|------|--------|
| `domain/ports/fractal_learning_repository.py` | +`find_error_patterns_by_goal()` abstract method |
| `infrastructure/fractal/in_memory_learning_repo.py` | Implement goal-only search |
| `infrastructure/persistence/pg_fractal_learning_repository.py` | PG goal-only search (strpos) |
| `infrastructure/fractal/llm_planner.py` | +`learning_repo` param, `_build_learning_context()`, user message injection |
| `interface/api/container.py` | Pass learning_repo to LLMPlanner |
| `tests/unit/infrastructure/test_llm_planner_learning.py` | 13 new tests |
| `tests/unit/infrastructure/test_fractal_learning_repo.py` | +2 find_by_goal tests |
| `tests/unit/interface/test_fractal_container_wiring.py` | +1 planner wiring test |

### Test count after TD-110

**2,463 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-111: InMemory → PostgreSQL Persistence for ExecutionRecord, AgentAffinity, SharedTaskState

**Date**: 2026-03-26
**Status**: Accepted
**Sprint**: 17.1

### Decision

Migrate all remaining InMemory repositories to PostgreSQL: ExecutionRecordRepository, AgentAffinityRepository, SharedTaskStateRepository.

### Rationale

Sprint 16.2 established the PG migration pattern for FractalLearningRepository. Three other repositories still used InMemory implementations, losing all data on server restart. This blocks production readiness.

### Design

| Repository | ORM Model | Key Design | Dedup Strategy |
|-----------|-----------|------------|----------------|
| ExecutionRecord | `ExecutionRecordModel` | Indexes on created_at DESC, task_type, engine_used. `get_stats()` uses SQL GROUP BY + aggregate functions | Append-only (no dedup needed) |
| AgentAffinity | `AgentAffinityScoreModel` | UNIQUE(engine, topic). All float scores in columns | SELECT→UPDATE/INSERT on (engine, topic) |
| SharedTaskState | `SharedTaskStateModel` | task_id as PK. decisions/agent_history as JSONB arrays, blockers as JSONB | SELECT→UPDATE/INSERT on task_id |

### SharedTaskState JSONB design

`decisions` and `agent_history` contain rich nested objects (Decision, AgentAction). Stored as JSONB arrays using `model_dump(mode="json")` for serialisation and `model_validate(strict=False)` for deserialisation — strict=False allows string→Enum coercion from JSON.

### Change

| File | Change |
|------|--------|
| `infrastructure/persistence/models.py` | +3 ORM models: ExecutionRecordModel, AgentAffinityScoreModel, SharedTaskStateModel |
| `migrations/versions/004_add_execution_affinity_state_tables.py` | 3 new tables + indexes |
| `infrastructure/persistence/pg_execution_record_repository.py` | NEW — PgExecutionRecordRepository |
| `infrastructure/persistence/pg_agent_affinity_repository.py` | NEW — PgAgentAffinityRepository |
| `infrastructure/persistence/pg_shared_task_state_repository.py` | NEW — PgSharedTaskStateRepository |
| `interface/api/container.py` | 3× use_postgres conditional DI wiring |
| `tests/unit/infrastructure/test_pg_execution_record_repo.py` | +16 tests |
| `tests/unit/infrastructure/test_pg_agent_affinity_repo.py` | +13 tests |
| `tests/unit/infrastructure/test_pg_shared_task_state_repo.py` | +13 tests |

---

## TD-112: N-gram Overlap Matching for Learning Pattern Retrieval

**Date**: 2026-03-26
**Status**: Accepted
**Sprint**: 17.2

### Decision

Replace substring-only goal matching in FractalLearningRepository with character n-gram overlap matching.

### Rationale

Round 11 Live E2E verification revealed that the original `goal_fragment in goal` substring matching fails when goals are rephrased or when CJK text structure differs (e.g. "素数判定関数をPythonで作成して" does not substring-match "素数判定を高速化する関数をPythonで実装して"). This prevented the learning closed-loop from functioning in realistic scenarios.

### Design

Character 4-gram overlap with threshold ≥ 30%:
1. Generate all 4-character substrings from both fragment and goal
2. Calculate `|intersection| / |fragment_ngrams|`
3. Match if ratio ≥ 0.3 (configurable)
4. Fast path: exact substring still matches immediately

Works for both Latin and CJK text without requiring word segmentation or external NLP libraries.

### Change

| File | Change |
|------|--------|
| `domain/entities/fractal_learning.py` | +`matches_goal()` on ErrorPattern and SuccessfulPath, +`_ngram_set()`, +`_goal_overlap()` |
| `infrastructure/fractal/in_memory_learning_repo.py` | Use `matches_goal()` instead of substring |
| `infrastructure/persistence/pg_fractal_learning_repository.py` | Fetch-all + Python n-gram filter (dataset is small) |
| `infrastructure/fractal/llm_planner.py` | Add learning injection logging |
| `tests/unit/domain/test_fractal_learner.py` | +13 tests (CJK, English, edge cases) |

### Live E2E Verification (Round 11)

| Step | Result |
|------|--------|
| Task A: "素数判定関数をPythonで作成して" | `No learning data found` → executed → `Learning recorded: 3 error patterns` |
| Task B: "素数判定を高速化する関数をPythonで実装して" | **`Learning data found: 3 error patterns`** → AVOID patterns injected into planner |
| Closed-loop confirmed | Task B's planner received Task A's learning data via n-gram matching |

### Test count after TD-112

**2,518 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-113: MCP Integration Hardening — Public Properties + Container Encapsulation Fix

**Date**: 2026-03-26
**Status**: Accepted
**Sprint**: 18.1

### Problem

MCP integration (Sprint 12.4) was functionally complete but had:
1. Container accessing `ReactExecutor._mcp_client` (private attribute) directly — encapsulation violation
2. No dedicated tests for `register_mcp_tools()` schema conversion logic
3. No tests for container `_connect_mcp_servers()` startup flow
4. No observability for tool availability at startup

### Decision

1. Add public properties to ReactExecutor: `mcp_client`, `mcp_tool_count`, `laee_tool_count`
2. Fix container to use public `mcp_client` property instead of private `_mcp_client`
3. Add startup log: "Tool availability: N LAEE + M MCP = T total"
4. Add 20 comprehensive tests covering schema conversion, tool tracking, and container startup

### Changes

| File | Change |
|------|--------|
| `infrastructure/task_graph/react_executor.py` | +`mcp_client` property, +`mcp_tool_count` property, +`laee_tool_count` property |
| `interface/api/container.py` | `_mcp_client` → `mcp_client` (3 occurrences), +tool count logging |
| `tests/unit/infrastructure/test_mcp_react_integration.py` | +20 tests (8 schema, 5 properties, 7 container startup) |

### Test count after TD-113

**2,538 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-114: A2A Protocol Domain Model (Phase 14.1)

**Date**: 2026-03-26
**Status**: Accepted
**Sprint**: 18.2

### Problem

Morphic-Agent manages 6 agent engines (Claude Code, Gemini CLI, Codex CLI, OpenHands, ADK, Ollama) but has no formal protocol for inter-agent communication. The UCL foundation (SharedTaskState, AgentAffinityScore, etc.) enables shared cognition, but agents cannot send structured messages to each other — they can only be orchestrated top-down by the meta-orchestrator.

A2A (Agent-to-Agent) protocol enables:
1. Direct request/response between engines (e.g., Claude asks Gemini to review)
2. Broadcast messages to all participants
3. Conversation lifecycle management (open → resolved/timeout/error)
4. Capability-based + affinity-based routing

### Decision

Implement A2A as a pure domain model layer (Phase 14.1), building on the existing UCL entities:

**Value Objects** (`domain/value_objects/a2a.py`):
- `A2AMessageType`: REQUEST, RESPONSE, BROADCAST, ACK, ERROR (5 members)
- `A2AAction`: SOLVE, REVIEW, SYNTHESIZE, DELEGATE, CRITIQUE, INFORM (6 members)
- `A2AConversationStatus`: OPEN, RESOLVED, TIMEOUT, ERROR (4 members)

**Entities** (`domain/entities/a2a.py`):
- `A2AMessage`: Immutable message with sender, optional receiver (None=broadcast), action, payload, artifacts, reply_to chain
- `A2AConversation`: Mutable conversation with participant tracking, message history, TTL, status transitions
- `AgentDescriptor`: Agent identity with capabilities list, heartbeat, case-insensitive capability matching

**Ports** (ABCs):
- `A2AMessageBroker`: send(), receive(), poll_replies() — async message passing
- `AgentRegistryPort`: register/deregister/lookup/list agents — discovery service

**Domain Services**:
- `A2ARouter`: Pure capability + affinity routing. Maps action→required capability, filters by exclude, ranks by AgentAffinityScore, falls back to first available
- `A2AConversationManager`: Conversation lifecycle — create, request/response factory, TTL expiry check, pending participant tracking

### Key Design Choices

1. **Reuse UCL's AgentAffinityScore** for routing — no new scoring model needed
2. **Pydantic strict=True** on all entities with field validators
3. **Action→Capability mapping** in A2ARouter (e.g., SOLVE→"code", REVIEW→"review")
4. **Fallback-first**: If no capability match, pick first available agent rather than fail
5. **TTL-based expiry**: Conversations have configurable ttl_seconds (default 300s)
6. **Broadcast support**: receiver=None signals broadcast to all participants

### Changes

| File | Change |
|------|--------|
| `domain/value_objects/a2a.py` | +3 enums (A2AMessageType, A2AAction, A2AConversationStatus) |
| `domain/entities/a2a.py` | +3 entities (A2AMessage, A2AConversation, AgentDescriptor) |
| `domain/ports/a2a_broker.py` | +A2AMessageBroker ABC |
| `domain/ports/agent_registry.py` | +AgentRegistryPort ABC |
| `domain/services/a2a_router.py` | +A2ARouter (pure routing service) |
| `domain/services/a2a_conversation_manager.py` | +A2AConversationManager (lifecycle service) |
| `domain/value_objects/__init__.py` | +3 exports |
| `domain/entities/__init__.py` | +3 exports |
| `domain/ports/__init__.py` | +2 exports |
| `tests/unit/domain/test_a2a.py` | +38 tests (3 VO, 7 message, 10 conversation, 3 descriptor, 7 router, 8 manager) |

### Test count after TD-114

**2,576 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-115: A2A Infrastructure — InMemory Broker and Agent Registry (Phase 14.2)

**Date**: 2026-03-26
**Status**: Accepted
**Sprint**: 18.3

### Problem

Sprint 18.2 defined A2A ports (A2AMessageBroker, AgentRegistryPort) as abstract interfaces. Infrastructure implementations are needed for testing and local development.

### Decision

Implement in-memory versions following the established InMemory* pattern:

**InMemoryA2ABroker** (`infrastructure/a2a/in_memory_broker.py`):
- Per-receiver asyncio.Queue for directed messages
- Broadcast delivers to all known inboxes
- Messages indexed by conversation_id for poll_replies
- asyncio.Event per conversation for efficient waiting
- FIFO ordering guaranteed by asyncio.Queue

**InMemoryAgentRegistry** (`infrastructure/a2a/in_memory_agent_registry.py`):
- Dict keyed on agent_id for O(1) lookup
- register() upserts, deregister() is no-op for unknowns
- list_by_capability uses case-insensitive matching

### Changes

| File | Change |
|------|--------|
| `infrastructure/a2a/__init__.py` | New package |
| `infrastructure/a2a/in_memory_broker.py` | +InMemoryA2ABroker |
| `infrastructure/a2a/in_memory_agent_registry.py` | +InMemoryAgentRegistry |
| `tests/unit/infrastructure/test_a2a_infrastructure.py` | +22 tests (10 broker, 12 registry) |

### Test count after TD-115

**2,598 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-116: A2A Use Cases + Container DI (Phase 14.3)

**Date**: 2026-03-26
**Status**: Accepted
**Sprint**: 18.4

### Problem

A2A domain model (TD-114) and infrastructure (TD-115) exist but have no application-layer use cases or DI wiring in the container.

### Decision

**SendA2AMessageUseCase** (`application/use_cases/send_a2a_message.py`):
- `execute()`: Send a REQUEST message with optional auto-routing via A2ARouter + AgentRegistryPort
- `reply()`: Send a RESPONSE message to a specific request
- Returns `SendResult` dataclass with message_id, conversation_id, receiver, routed flag

**ManageA2AConversationUseCase** (`application/use_cases/manage_a2a_conversation.py`):
- `create()`: Create a new conversation with participants and TTL
- `check_expired()`: Check TTL and auto-mark TIMEOUT
- `check_complete()`: Check if all participants responded and auto-resolve
- `collect_replies()`: Poll broker for new replies, deduplicate, add to conversation
- `summarize()`: Return ConversationSummary dataclass

**Container DI**: InMemoryA2ABroker + InMemoryAgentRegistry wired in AppContainer, use cases composed.

### Changes

| File | Change |
|------|--------|
| `application/use_cases/send_a2a_message.py` | +SendA2AMessageUseCase |
| `application/use_cases/manage_a2a_conversation.py` | +ManageA2AConversationUseCase |
| `interface/api/container.py` | +A2A DI wiring (broker, registry, 2 use cases) |
| `tests/unit/application/test_a2a_use_cases.py` | +17 tests (6 send, 11 manage) |

### Test count after TD-116

**2,615 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-117: A2A REST API Routes (Phase 14.4)

**Date**: 2026-03-26
**Status**: Accepted
**Sprint**: 18.5

### Problem

A2A domain model (TD-114), infrastructure (TD-115), and use cases (TD-116) exist but have no HTTP API endpoints for external consumers.

### Decision

**9 REST endpoints** under `/api/a2a/` prefix:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/a2a/conversations` | POST | Create conversation with participants + TTL |
| `/api/a2a/conversations/{id}` | GET | Get conversation state, summary, messages |
| `/api/a2a/conversations/{id}/check` | POST | Check expired/complete, auto-resolve |
| `/api/a2a/conversations/{id}/collect` | POST | Collect pending replies from broker |
| `/api/a2a/conversations/{id}/messages` | POST | Send message (auto-route if no receiver) |
| `/api/a2a/conversations/{id}/reply` | POST | Reply to specific message |
| `/api/a2a/agents` | GET | List registered agents |
| `/api/a2a/agents` | POST | Register agent with capabilities |
| `/api/a2a/agents/{id}` | DELETE | Deregister agent |

**Key design choices:**
- Conversation tracking via `container.a2a_conversations` dict (in-memory, consistent with InMemoryA2ABroker)
- Enum parsing with `_parse_engine()` / `_parse_action()` helpers → 400 on invalid values
- `ConversationResponse.from_conversation()` combines entity + summary for rich response
- `SendResultResponse.from_result()` converts domain SendResult to API response
- Follows established route patterns: `_container(request)`, HTTPException for errors, 201/204 status codes

### Changes

| File | Change |
|------|--------|
| `interface/api/routes/a2a.py` | +9 endpoints (246 lines) |
| `interface/api/schemas.py` | +13 A2A schemas with from_* conversion |
| `interface/api/main.py` | +a2a_router import and include |
| `interface/api/container.py` | +a2a_conversations tracking dict |
| `tests/unit/interface/test_a2a_api.py` | +27 tests (10 conversation, 11 message, 6 registry) |

### Test count after TD-117

**2,642 unit tests + 50 integration, 0 failures, lint clean.**

---

## TD-118: A2A Integration Tests (Phase 14.5)

**Date**: 2026-03-26
**Status**: Accepted
**Sprint**: 18.6

### Problem

A2A Protocol has unit tests per layer but no cross-layer integration tests verifying the full pipeline.

### Decision

10 integration tests using real InMemory implementations (no mocks):

1. **Full conversation lifecycle**: create → send → reply → check complete → summarize
2. **Auto-routing**: registry capability matching routes to correct agent
3. **Broker delivery**: messages sent via use case receivable via broker.receive()
4. **Reply collection**: external responses collected via broker polling
5. **TTL expiration**: conversation auto-marks TIMEOUT after TTL
6. **Multi-party**: 3 agents with multiple request/response pairs
7. **Parallel conversations**: independent conversations don't interfere
8. **Registry lifecycle**: register → list → lookup → deregister
9. **Artifact preservation**: artifacts survive full send → reply pipeline
10. **API E2E**: full flow through FastAPI TestClient routes

### Changes

| File | Change |
|------|--------|
| `tests/integration/test_a2a_protocol.py` | +10 integration tests (528 lines) |

### Test count after TD-118

**2,642 unit tests + 60 integration, 0 failures, lint clean.**

---

## TD-119: MCP Live E2E Verification (Round 12) — mcp-server-fetch

**Date**: 2026-03-27
**Status**: Accepted
**Sprint**: 19.1

### Problem

MCP integration was implemented (Sprint 12.4) and hardened (Sprint 18.1, TD-113) with 66+ unit tests, but never verified against a real MCP server process. All prior tests used mocks — no live subprocess, no real stdio transport, no actual HTTP fetch.

### Decision

Live E2E integration tests with real `mcp-server-fetch` (via `uvx mcp-server-fetch`):

1. **Connection lifecycle**: MCPClient connects via stdio transport, server appears in connected_servers
2. **Tool discovery**: list_tools returns fetch tool with valid schema
3. **Tool execution**: call_tool fetches https://example.com, returns "Example Domain" content
4. **MCPToolAdapter**: wraps MCP tool as callable with `mcp_fetch_{tool}` naming
5. **discover_and_register**: batch connects and creates adapters
6. **ReactExecutor registration**: MCP tools added to schema list, tracked in mcp_tool_names
7. **ReactExecutor routing**: tool calls routed to MCPClient (not LAEE LocalExecutor)
8. **Disconnect cleanup**: server removed from connected_servers after disconnect
9. **Schema format**: registered schemas follow OpenAI function-calling format
10. **Full startup flow**: mirrors container._connect_mcp_servers() with LAEE+MCP tool counts

### Results

All 10 tests passed. Round 12 Live E2E confirmed:
- `mcp-server-fetch` starts as stdio subprocess in ~0.5s
- Tool `fetch` registered with input schema `{url: string}`
- https://example.com fetched, "Example Domain" content verified
- ReactExecutor correctly routes MCP tool calls to MCPClient, not LAEE
- Total test time: 4.73s

### Changes

| File | Change |
|------|--------|
| `tests/integration/test_mcp_live.py` | +10 integration tests (new file, MCP Live E2E) |

### Test count after TD-119

**2,642 unit tests + 70 integration, 0 failures, lint clean.**

---

## TD-120: A2A CLI Commands (Sprint 19.2)

**Date**: 2026-03-27
**Status**: COMPLETE

### Problem

A2A protocol had API routes (TD-117) but no terminal interface. Users needed CLI access to create conversations, send messages, manage agents, and monitor A2A state.

### Solution

9 CLI subcommands under `morphic a2a`:
- `create` — Create new conversation with participant engines and TTL
- `list` — List all active conversations
- `show` — Show conversation detail with messages and summary
- `send` — Send A2A message with auto-routing support
- `reply` — Reply to a specific message
- `check` — Check conversation expiry/completion status
- `collect` — Poll for new replies
- `agents` — List registered agents
- `register` — Register an agent with engine type and capabilities

4 Rich formatters added: conversation table, conversation detail, message table, agent table.

### Changes

| File | Change |
|------|--------|
| `interface/cli/commands/a2a.py` | +265 lines — 9 CLI commands (new file) |
| `interface/cli/formatters.py` | +91 lines — 4 A2A formatters |
| `interface/cli/main.py` | +6 lines — a2a_app registration |
| `tests/unit/interface/test_a2a_cli.py` | +339 lines — 21 unit tests (new file) |

### Test count after TD-120

**2,663 unit tests + 70 integration, 0 failures, lint clean.**

---

## TD-121: Evolution Pipeline Integration Tests (Sprint 20.1)

**Date:** 2026-03-27
**Status:** COMPLETE
**Category:** Testing / Self-Evolution

### Context

The Level 1→2→3 self-evolution pipeline had unit tests but no integration test validating the full end-to-end flow: execution record creation → stats aggregation → failure pattern extraction → strategy update → tool gap detection.

### Solution

15 integration tests using real InMemory repositories (no mocks):
- Execution record lifecycle and stats aggregation
- Failure pattern extraction and recovery rule creation
- Model/engine preference updates from historical data
- JSONL strategy store round-trip persistence
- Full Level 2 strategic update pipeline
- Level 3 systemic evolution with tool gap detection
- Fractal learning integration
- Edge cases: empty history, filtered stats, appended rules

### Changes

| File | Change |
|------|--------|
| `tests/integration/test_evolution_pipeline.py` | +623 lines — 15 integration tests (new file) |

### Test count after TD-121

**2,663 unit tests + 85 integration, 0 failures, lint clean.**

---

## TD-122: Marketplace Live Integration Tests + MCP Registry v0.1 Update (Sprint 20.2)

**Date:** 2026-03-27
**Status:** COMPLETE
**Category:** Infrastructure / Marketplace

### Context

The MCP Registry API changed from `/api/servers` to `/v0.1/servers` with a new nested response format `{"servers": [{"server": {...}, "_meta": {...}}]}`. All marketplace tests were SKIPPING because the reachability check hit the old path.

### Solution

1. Updated `MCPRegistryClient` API path to `/v0.1/servers`
2. Updated response parser for v0.1 nested format (extracting `entry["server"]`)
3. Updated `_parse_item` for new fields: `repository.url`, `remotes[0].type`
4. Created 14 integration tests: 5 live (real MCP Registry with `@_skip_no_network`), 9 offline

### Changes

| File | Change |
|------|--------|
| `infrastructure/marketplace/mcp_registry_client.py` | Updated API path + response parser for v0.1 |
| `tests/integration/test_marketplace_live.py` | +267 lines — 14 integration tests (new file) |

### Test count after TD-122

**2,663 unit tests + 99 integration, 0 failures, lint clean.**

---

## TD-123: Prompt Template Evolution (Sprint 20.3)

**Date:** 2026-03-27
**Status:** COMPLETE
**Category:** Domain / Application — Self-Evolution

### Context

The Self-Evolution Engine (Level 2) needed prompt template versioning with performance tracking. Templates should be versioned, outcomes recorded, best-performing versions selected, and improvements suggested based on regression detection, failure rate analysis, and cost comparison.

### Solution

Full Clean Architecture implementation:
- **Domain entity**: `PromptTemplate` (Pydantic strict mode) — versioned with success_count, failure_count, total_cost_usd; computed properties: sample_count, success_rate, avg_cost_usd; method: record_outcome()
- **Domain port**: `PromptTemplateRepository` (5 abstract methods)
- **Infrastructure**: `InMemoryPromptTemplateRepository` (dict-backed, keyed by id)
- **Application**: `EvolvePromptsUseCase` — create_version (auto-increment), record_outcome, get_best_template (success_rate → cost tiebreak with min_samples qualification), suggest_improvements (3 detectors: regression >10%, failure <50%, cost >1.5x), run_evolution (full analysis)

### Changes

| File | Change |
|------|--------|
| `domain/entities/prompt_template.py` | +57 lines — PromptTemplate entity (new file) |
| `domain/ports/prompt_template_repository.py` | +38 lines — Repository port (new file) |
| `infrastructure/evolution/in_memory_prompt_template_repo.py` | +40 lines — InMemory impl (new file) |
| `application/use_cases/evolve_prompts.py` | +201 lines — Use case (new file) |
| `tests/unit/domain/test_prompt_template.py` | +138 lines — 20 entity tests (new file) |
| `tests/unit/application/test_evolve_prompts.py` | +389 lines — 31 use case/repo tests (new file) |

### Test count after TD-123

**2,714 unit tests + 99 integration, 0 failures, lint clean.**

---

## TD-124: Competitive Analysis + Plan Approval Execution Fix (Sprint 21.1)

**Date:** 2026-03-27
**Status:** COMPLETE
**Category:** Interface / Docs — Bug Fix + Competitive Analysis

### Context

Live execution testing of Morphic-Agent revealed that `POST /api/plans/{id}/approve` does not trigger task execution when Celery is disabled (the default dev mode). The approved task stays in "pending" state forever. This is the #1 blocker for first-time user experience.

Simultaneously, a comprehensive competitive analysis against 8 major frameworks (OpenClaw 338K⭐, Manus/Meta $2B, Devin, Windsurf, OpenHands 65K⭐, Claude Code, Gemini CLI 99K⭐, Codex CLI 68K⭐) was conducted via live execution + web research.

### Solution

1. **BUG-001 Fix**: Added `asyncio.create_task(_safe_execute(c, task.id))` fallback in `approve_plan` when Celery is disabled — matching the existing pattern in `tasks.py`'s `_create_and_execute()`.
2. **Competitive Analysis**: Created `docs/COMPETITIVE_ANALYSIS.md` documenting:
   - Live execution results (what works, what doesn't)
   - 8 competitor feature matrices
   - Morphic-Agent unique advantages (5 features no competitor has)
   - Critical gaps and bugs found
   - Priority action roadmap

### Changes

| File | Change |
|------|--------|
| `interface/api/routes/plans.py` | +12 lines — asyncio import, `_safe_execute()`, fallback in `approve_plan` |
| `tests/unit/interface/test_plans_route.py` | +210 lines — 12 tests for plan routes including BUG-001 regression test (new file) |
| `docs/COMPETITIVE_ANALYSIS.md` | +350 lines — Full competitive analysis report (new file) |

### Key Findings

- **Morphic-Agent has 5 features no competitor has**: meta-orchestration (6 engines), UCL, A2A, self-evolution, Fractal Recursive Engine
- **3 critical bugs found**: Plan approval execution, engine fallback opacity, execution record gaps
- **OpenClaw security**: 12-20% malicious skills on ClawHub — cautionary tale for our marketplace
- **Market opportunity**: Multi-AI context fragmentation is unsolved; UCL + Context Adapters is unique

### Test count after TD-124

**2,726 unit tests + 99 integration, 0 failures, lint clean.**

---

## TD-125: Fix AsyncMock RuntimeWarnings in PG Repository Tests (Sprint 22.1)

**Date:** 2026-03-28
**Status:** COMPLETE
**Category:** Tests — Mock Quality Improvement

### Context

8 `RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited` warnings were emitted during PG repository unit tests. Root cause: `session = AsyncMock()` makes all attributes (including `session.add`) return AsyncMock coroutines, but SQLAlchemy's `AsyncSession.add()` is synchronous.

### Solution

Added `session.add = MagicMock()` in `_mock_session_factory()` across 5 test files. This ensures `session.add()` calls in repository code don't create unawaited coroutines.

### Changes

| File | Change |
|------|--------|
| `tests/unit/infrastructure/test_pg_repositories.py` | `session.add = MagicMock()` |
| `tests/unit/infrastructure/test_pg_shared_task_state_repo.py` | `session.add = MagicMock()` |
| `tests/unit/infrastructure/test_pg_execution_record_repo.py` | `session.add = MagicMock()` |
| `tests/unit/infrastructure/test_pg_agent_affinity_repo.py` | `session.add = MagicMock()` |
| `tests/unit/infrastructure/test_pg_fractal_learning_repo.py` | `session.add = MagicMock()` |

### Test count after TD-125

**2,726 unit tests + 99 integration, 0 failures, 0 AsyncMock warnings, lint clean.**

---

## TD-126: Token-Overlap Jaccard Dedup for Paraphrase Detection (Sprint 22.2)

**Date:** 2026-03-28
**Status:** COMPLETE
**Category:** Infrastructure — Insight Extraction Enhancement

### Context

Exact-match dedup achieves 0% on paraphrase detection. When no `EmbeddingPort` is available (the fallback path), paraphrased facts like "Decided to use PostgreSQL" vs "PostgreSQL was chosen" are treated as unique.

### Solution

Added `_token_dedup()` to `InsightExtractor` — word-level Jaccard similarity with punctuation-free tokenization (`re.findall(r"[a-z0-9]+")`) as a lightweight second pass after exact-match dedup. No embedding required.

- **Dedup pipeline**: `raw → exact_dedup → token_dedup` (without embedding) or `raw → semantic_dedup` (with embedding)
- **New config**: `token_dedup_threshold` (default 0.6)
- **Benchmark**: Updated `_merge_and_dedup` to use token overlap for cross-engine scoring

### Changes

| File | Change |
|------|--------|
| `infrastructure/cognitive/insight_extractor.py` | +47 lines — `_tokenize()`, `_token_dedup()`, `jaccard_similarity()` |
| `shared/config.py` | +1 line — `token_dedup_threshold` |
| `interface/api/container.py` | +1 line — pass threshold to InsightExtractor |
| `benchmarks/dedup_accuracy.py` | +17 lines — token-aware `_merge_and_dedup` |
| `tests/unit/infrastructure/test_insight_extractor_semantic_dedup.py` | +130 lines — 11 new tests |
| `tests/unit/infrastructure/test_mcp_server.py` | +1 line — `_FakeSettings.token_dedup_threshold` |
| `tests/unit/interface/test_fractal_container_wiring.py` | +1 line — `_FakeSettings.token_dedup_threshold` |

### Test count after TD-126

**2,737 unit tests + 99 integration, 0 failures, lint clean.**

---

## TD-127: Explicit Skip Markers for Ollama-Dependent E2E Tests (Sprint 22.3)

**Date:** 2026-03-28
**Status:** COMPLETE
**Category:** Tests — Skip Marker Improvement

### Context

`test_e2e_pipeline.py` and `test_live_smoke.py` use `pytest.skip()` inside async fixtures but have no explicit module-level skip markers. When Ollama is not installed, tests are skipped without clear indication in collection phase.

### Solution

Added module-level `pytestmark` with `pytest.mark.skipif(not _HAS_OLLAMA)` and custom `pytest.mark.ollama` marker. Registered `ollama` marker in `pyproject.toml`. Tests can now be filtered with `pytest -m ollama` and show clear skip reason at collection time.

### Changes

| File | Change |
|------|--------|
| `tests/integration/test_e2e_pipeline.py` | +8 lines — `_HAS_OLLAMA`, `pytestmark` |
| `tests/integration/test_live_smoke.py` | +6 lines — `_HAS_OLLAMA`, `pytestmark`, import cleanup |
| `pyproject.toml` | +3 lines — `markers` config |

### Test count after TD-127

**2,737 unit tests + 99 integration, 0 failures, lint clean.**

---

## TD-128: BUG-002/003 Fix + `morphic serve` + `morphic doctor` (Sprint 23.1)

**Date:** 2026-03-28
**Status:** COMPLETE
**Category:** Bug Fix + CLI Enhancement

### Context

**BUG-002**: Engine execution costs (Claude Code, Gemini, Codex, Ollama drivers) were calculated in `AgentEngineResult.cost_usd` and flowed through `ExecutionRecord`, but never reached `CostRecord`. Daily/monthly cost totals, budget checks, and cost analytics were blind to engine usage.

**BUG-003**: When an engine failed and the system fell back to another, the caller had no visibility into which engines were tried, why they failed, or why a specific engine was selected.

**CLI**: No one-command server startup or diagnostic tool existed.

### Solution

**BUG-002 Fix — Engine Cost Recording:**
- Added `CostRecord.from_engine_result()` factory method with `engine_type: str | None` field
- Added `CostTracker.record_engine_result()` method
- Wired `cost_tracker` into `RouteToEngineUseCase` via constructor + container DI
- Engine costs now included in `get_daily_total()`, `get_monthly_total()`, `check_budget()`

**BUG-003 Fix — Fallback Transparency:**
- Created `FallbackAttempt` frozen VO: `engine`, `attempted`, `skip_reason`, `error`, `duration_seconds`
- Extended `AgentEngineResult` with `fallback_reason`, `engines_tried`, `fallback_attempts`
- Every engine attempt recorded as FallbackAttempt
- Added `FallbackAttemptResponse` schema + extended `EngineRunResponse` in API

**CLI Commands:**
- `morphic serve start`: one-command server startup with diagnostic banner
- `morphic doctor check`: comprehensive health diagnostics

### Changes

| File | Change |
|------|--------|
| `domain/value_objects/fallback_attempt.py` | **NEW** — FallbackAttempt frozen VO |
| `domain/entities/cost.py` | +18 lines — `engine_type` field, `from_engine_result()` |
| `domain/ports/agent_engine.py` | +5 lines — 3 fallback fields |
| `application/use_cases/route_to_engine.py` | +92 lines — fallback tracking, cost recording |
| `infrastructure/llm/cost_tracker.py` | +32 lines — `record_engine_result()` |
| `interface/api/schemas.py` | +23 lines — FallbackAttemptResponse |
| `interface/cli/commands/doctor.py` | **NEW** — `morphic doctor check` |
| `interface/cli/commands/serve.py` | **NEW** — `morphic serve start` |

### Test count after TD-128

**2,785 unit tests + 134 integration, 0 failures, lint clean.**

---

## TD-129: OpenHands Docker Diagnostics + E2E Test Scaffold (Sprint 24.1)

**Date:** 2026-03-29
**Status:** COMPLETE
**Category:** Testing / Observability

### Context

OpenHands E2E verification was listed as next step but had no diagnostic tooling or test scaffold. Docker availability and image state were invisible to `morphic doctor`.

### Solution

- Added Docker daemon + OpenHands image checks to `morphic doctor check`
- Created `tests/integration/test_openhands_e2e.py` with 14 tests (4 Docker infra, 4 driver construction, 6 live E2E)
- Progressive skip logic: no Docker → skip all; no image → skip live; no API → skip execution

### Changes

| File | Change |
|------|--------|
| `interface/cli/commands/doctor.py` | +40 lines — `_check_docker()`, `_check_openhands()` |
| `tests/integration/test_openhands_e2e.py` | **NEW** — 14 integration tests |
| `tests/unit/interface/test_doctor_cli.py` | +10 tests — Docker/OpenHands CLI checks |

### Test count after TD-129

**2,795 unit tests + 148 integration, 0 failures, lint clean.**

---

## TD-130: SQLite Persistence Fallback (Sprint 24.2)

**Date:** 2026-03-29
**Status:** COMPLETE
**Category:** Infrastructure / Portability

### Context

`morphic serve` required PostgreSQL for persistence. For local development and quick demos, a zero-config SQLite backend was needed. PG-specific types (UUID, JSONB) in ORM models prevented direct reuse.

### Solution

- Created `GUID` TypeDecorator: UUID on PG, CHAR(36) on SQLite with automatic conversion
- Created `PortableJSON`: JSONB on PG, JSON on SQLite via `with_variant()`
- Replaced all PG-specific types in 12 ORM models with portable types
- PG repositories work unchanged on SQLite — no code duplication
- Added `use_sqlite` / `sqlite_url` settings, SQLite repo factory in AppContainer

### Changes

| File | Change |
|------|--------|
| `infrastructure/persistence/portable_types.py` | **NEW** — GUID TypeDecorator + PortableJSON |
| `infrastructure/persistence/models.py` | 12 models: UUID→GUID, JSONB→PortableJSON |
| `shared/config.py` | +2 lines — `use_sqlite`, `sqlite_url` |
| `interface/api/container.py` | +30 lines — `_create_sqlite_repos()` |
| `pyproject.toml` | +1 dep — `aiosqlite>=0.20` |
| `tests/unit/infrastructure/test_sqlite_persistence.py` | **NEW** — 14 tests |

### Test count after TD-130

**2,809 unit tests + 148 integration, 0 failures, lint clean.**

---

## TD-131: CLI Gap-Fill — Conflicts + Strategies (Sprint 24.3)

**Date:** 2026-03-29
**Status:** COMPLETE
**Category:** CLI Enhancement

### Context

Gap analysis revealed that `ConflictResolver` (pure domain service) and `StrategyStore` (JSONL persistence) were fully implemented but had no CLI exposure. Users couldn't inspect cross-engine conflicts or learned strategies from the command line.

### Solution

**`morphic cognitive conflicts`:**
- Fetches memories from L1-L3 layers via MemoryRepository
- Converts MemoryEntry → ExtractedInsight (reverse type mapping + metadata extraction)
- Runs `ConflictResolver.detect_conflicts()` for detection, or `.resolve_all()` with `--resolve`
- Displays conflict pairs in Rich table with engine, overlap score, and winner

**`morphic evolution strategies`:**
- Reads from StrategyStore (JSONL files): model prefs, engine prefs, recovery rules
- Optional `--type model|engine|recovery` filter
- Three dedicated Rich tables for each strategy type

### Changes

| File | Change |
|------|--------|
| `interface/cli/commands/cognitive.py` | +55 lines — `conflicts` subcommand |
| `interface/cli/commands/evolution.py` | +35 lines — `strategies` subcommand |
| `interface/cli/formatters.py` | +95 lines — 5 new formatter functions |
| `tests/unit/interface/test_cognitive_cli.py` | +8 tests — conflicts CLI |
| `tests/unit/interface/test_evolution_cli.py` | +8 tests — strategies CLI |

### Test count after TD-131

**2,825 unit tests + 148 integration, 0 failures, lint clean.**

---

## TD-132: Memory Layer CLI — `morphic memory list/search/show/stats/delete` (Sprint 25.1)

**Date**: 2026-03-29
**Status**: Accepted
**Sprint**: 25.1

### Problem

MemoryRepository port (5 methods) and two implementations (InMemory + PG) were fully complete, but the memory layer had no CLI exposure. Users couldn't list, search, inspect, or delete memory entries from the command line. This was the highest-priority CLI gap remaining.

### Solution

5 subcommands under `morphic memory`:

| Command | Description | Repo Method |
|---------|-------------|-------------|
| `memory list` | List entries, filter by `--type`, `--limit` | `list_by_type()` × 4 types |
| `memory search <query>` | Keyword/semantic search | `search()` |
| `memory show <id>` | Detailed single entry view | `get_by_id()` |
| `memory stats` | Type counts, access totals, max importance | `list_by_type()` × 4 |
| `memory delete <id>` | Remove entry by ID (with existence check) | `get_by_id()` + `delete()` |

3 new Rich formatters: `print_memory_table`, `print_memory_detail`, `print_memory_stats`.

### Changes

| File | Change |
|------|--------|
| `interface/cli/commands/memory.py` | New — 5 subcommands |
| `interface/cli/formatters.py` | +75 lines — 3 memory formatters + MEMORY_TYPE_STYLES |
| `interface/cli/main.py` | +2 lines — memory_app import + registration |
| `tests/unit/interface/test_memory_cli.py` | New — 18 tests (5 list + 3 search + 2 show + 2 stats + 2 delete + 4 formatter) |

### Test count after TD-132

**2,843 unit tests + 148 integration, 0 failures, lint clean.**

---

## TD-133: Fallback Strategy Inspection CLI — `morphic fallback history/failures/stats` (Sprint 25.2)

**Date**: 2026-03-29
**Status**: Accepted
**Sprint**: 25.2

### Problem

FallbackAttempt VO (TD-128) tracked engine routing transparency, but users couldn't inspect execution history, failure patterns, or engine routing distribution from the CLI. ExecutionRecordRepository (PG + InMemory) had full data but no CLI frontend.

### Solution

3 subcommands under `morphic fallback`:

| Command | Description | Repo Method |
|---------|-------------|-------------|
| `fallback history` | Recent executions with engine/model/cost/status | `list_recent()` or `list_by_task_type()` |
| `fallback failures` | Failed executions, `--since` date filter | `list_failures()` |
| `fallback stats` | Aggregated success rates, engine/model distribution | `get_stats()` |

2 new Rich formatters: `print_execution_history_table`, `print_execution_stats`.

### Changes

| File | Change |
|------|--------|
| `interface/cli/commands/fallback.py` | New — 3 subcommands |
| `interface/cli/formatters.py` | +65 lines — 2 execution formatters |
| `interface/cli/main.py` | +5 lines — fallback_app import + registration |
| `tests/unit/interface/test_fallback_cli.py` | New — 17 tests (5 history + 4 failures + 4 stats + 4 formatter) |

### Test count after TD-133

**2,860 unit tests + 148 integration, 0 failures, lint clean.**

---

## TD-134: Learning Repository CLI — `morphic learning list/search/stats` (Sprint 25.3)

**Date**: 2026-03-29
**Status**: Accepted
**Sprint**: 25.3

### Problem

Fractal engine learning data (ErrorPattern, SuccessfulPath) was persisted (PG + InMemory) and used by the LLMPlanner at runtime, but users had no way to inspect what the system had learned. No CLI to browse error patterns, successful paths, or learning statistics.

### Solution

3 subcommands under `morphic learning`:

| Command | Description | Repo Method |
|---------|-------------|-------------|
| `learning list` | List error patterns and/or successful paths. `--kind errors\|successes\|all` | `list_error_patterns()` + `list_successful_paths()` |
| `learning search <goal>` | Search by goal (n-gram matching) | `find_error_patterns_by_goal()` + `find_successful_paths()` |
| `learning stats` | Counts, top errors, avg path cost | `list_error_patterns()` + `list_successful_paths()` |

3 new Rich formatters: `print_error_pattern_table`, `print_successful_path_table`, `print_learning_stats`.

Container change: `learning_repo` exposed as `AppContainer.learning_repo` (was local variable in `_create_task_engine`). InMemory fallback created for non-fractal mode so CLI always has access.

### Changes

| File | Change |
|------|--------|
| `interface/cli/commands/learning.py` | New — 3 subcommands |
| `interface/cli/formatters.py` | +90 lines — 3 learning formatters |
| `interface/cli/main.py` | +5 lines — learning_app import + registration |
| `interface/api/container.py` | +8 lines — expose learning_repo, InMemory fallback |
| `tests/unit/interface/test_learning_cli.py` | New — 17 tests (5 list + 3 search + 3 stats + 6 formatter) |

### Test count after TD-134

**2,877 unit tests + 148 integration, 0 failures, lint clean.**

---

## TD-135: Context Export CLI — `morphic context export/export-all/platforms` (Sprint 25.4)

**Date**: 2026-03-29
**Status**: Accepted
**Sprint**: 25.4

### Problem

ContextBridge infrastructure was complete (TD-118) with 4 platform formatters (claude_code, chatgpt, cursor, gemini) and wired into AppContainer, but had no CLI exposure. Users could only access context export via the REST API (`GET /api/memory/export`). This blocked the core use case of quickly exporting Morphic-Agent context into other AI tools from the terminal.

### Solution

3 subcommands under `morphic context`:

| Command | Description | Bridge Method |
|---------|-------------|---------------|
| `context export <platform>` | Export for one platform. `--query`, `--max-tokens`, `--output` flags | `export()` |
| `context export-all` | Export for all 4 platforms with summary table | `export_all()` |
| `context platforms` | List supported platforms with format descriptions | N/A (reads `SUPPORTED_PLATFORMS`) |

2 new Rich formatters: `print_export_result`, `print_export_results_table`.

`--output` flag writes content directly to file instead of stdout, enabling `morphic context export claude_code -o CONTEXT.md`.

### Changes

| File | Change |
|------|--------|
| `interface/cli/commands/context.py` | New — 3 subcommands |
| `interface/cli/formatters.py` | +30 lines — 2 context export formatters |
| `interface/cli/main.py` | +5 lines — context_app import + registration |
| `tests/unit/interface/test_context_cli.py` | New — 15 tests (6 export + 4 export-all + 2 platforms + 3 formatter) |

### Test count after TD-135

**2,892 unit tests + 148 integration, 0 failures, lint clean.**

---

## TD-136: Conflict Resolver API Route — `POST /api/cognitive/conflicts` (Sprint 25.5)

**Date**: 2026-03-29
**Status**: Accepted
**Sprint**: 25.5

### Problem

ConflictResolver domain service (TD-055) and CLI command `morphic cognitive conflicts` (TD-131) were complete, but the REST API had no endpoint for conflict detection. API consumers (frontend, external integrations) couldn't detect or resolve cross-engine insight contradictions programmatically.

### Solution

1 new endpoint on the existing cognitive router:

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/cognitive/conflicts` | Detect and optionally resolve conflicts between L1-L3 memory insights |

Request body: `DetectConflictsRequest` with `limit` (default 100) and `resolve` (default false).

Response: `ConflictListResponse` with `conflicts[]`, `count`, `insights_analyzed`, and optional `survivors` count (when resolve=true).

Reuses the same memory→insight conversion pattern from the CLI command (TD-131): fetch L2_SEMANTIC, L3_FACTS, L1_ACTIVE memories → convert to ExtractedInsight → run ConflictResolver.

### Changes

| File | Change |
|------|--------|
| `interface/api/routes/cognitive.py` | +55 lines — `POST /api/cognitive/conflicts` endpoint |
| `interface/api/schemas.py` | +18 lines — `DetectConflictsRequest`, `ConflictPairResponse`, `ConflictListResponse` |
| `tests/unit/interface/test_cognitive_api.py` | +85 lines — 5 tests (empty, detected, resolve, same-engine, default body) |

### Test count after TD-136

**2,897 unit tests + 148 integration, 0 failures, lint clean.**

---

## TD-137: Pytest Warnings Elimination (Sprint 26.1)

**Date**: 2026-03-30
**Status**: ✅ Complete

### Problem

316 deprecation warnings from `@pytest.mark.asyncio()` (empty parens) across 18 test files, 2 warnings from sync functions inheriting module-level `pytestmark = pytest.mark.asyncio`, and 1 RuntimeWarning from unawaited `_safe_execute` coroutine in plan route tests.

### Decision

1. **Remove empty parens**: `@pytest.mark.asyncio()` → `@pytest.mark.asyncio` (316 occurrences, 18 files)
2. **Per-class pytestmark**: In `test_sqlite_persistence.py`, replaced module-level `pytestmark` with per-class `@pytest.mark.asyncio` decorators so sync `TestSQLiteConfig` tests no longer inherit the async mark
3. **Fix coroutine leak**: In `test_plans_route.py`, patched `asyncio.create_task` with `coro.close()` side effect to prevent orphaned coroutines, and used `.side_effect` assignment on existing mocks instead of full mock replacement

### Changes

| File | Change |
|------|--------|
| 18 test files | `@pytest.mark.asyncio()` → `@pytest.mark.asyncio` (316 replacements) |
| `tests/unit/infrastructure/test_sqlite_persistence.py` | Module-level pytestmark → per-class decorators |
| `tests/unit/interface/test_plans_route.py` | Patched create_task with coro.close(), .side_effect instead of mock reassignment |
| `docs/CONTINUATION.md` | Compressed 643 → 199 lines (69% reduction) |

### Test count after TD-137

**2,897 unit tests + 148 integration, 0 failures, 0 warnings, lint clean.**

---

## TD-138: Frontend UI Expansion — Engine Status + Cost Dashboard + Tasks List (Sprint 27.1)

**Date**: 2026-03-30
**Status**: ✅ Complete

### Problem

Frontend UI was at ~60% completion. Missing dedicated pages for Engine Status, Cost Dashboard, and Tasks List. Navigation only linked to 5 of 10+ available pages.

### Decision

Add three new pages and expand API client + navigation:

1. **`/engines`**: Engine Status Dashboard — grid of 6 engines with availability status, capabilities (Sandbox/Parallel/MCP), context window size, cost/hr. Includes "Run Task" form with engine selector and auto-routing.
2. **`/cost`**: Cost Dashboard — summary cards (daily/monthly/local%/remaining), budget progress bar, model distribution chart, and paginated cost log table with LOCAL/API badges.
3. **`/tasks`**: Tasks List — filterable by status (all/pending/running/success/failed), stats cards, delete with confirmation. Standalone from dashboard's inline task list.
4. **Nav update**: Added Tasks, Engines, Cost links to header navigation (8 nav items total).
5. **API client**: Added types and fetch functions for `/api/engines`, `/api/cost/logs`, `/api/memory/search`, `/api/memory/export`.

### Changes

| File | Change |
|------|--------|
| `ui/app/engines/page.tsx` | New — 6-engine status grid + run-task form |
| `ui/app/cost/page.tsx` | New — budget bar + model distribution + log table |
| `ui/app/tasks/page.tsx` | New — filterable task list with stats |
| `ui/app/layout.tsx` | Added Tasks, Engines, Cost nav links |
| `ui/lib/api.ts` | Added Engine, CostLog, Memory API types + functions |

### Build

Next.js production build: 12 routes, 0 TypeScript errors.

---

## TD-139: Frontend Memory + A2A Pages (Sprint 27.2)

**Date**: 2026-03-31
**Status**: ✅ Complete

### Problem

Backend APIs for Memory (search + context export) and A2A Protocol (conversations, messages, agent registry) were fully implemented, but had no dedicated frontend UI. API client also lacked A2A type definitions and fetch functions.

### Decision

Add two new pages and expand API client + navigation:

1. **`/memory`**: Semantic Memory page — search form with results display, context export with platform selector (Claude Code/ChatGPT/Cursor/Gemini), copy-to-clipboard, token estimate display. Info banner explaining L1-L4 hierarchy.
2. **`/a2a`**: A2A Protocol page — tabbed UI (Conversations / Agent Registry). Conversations: create with participant picker, message timeline with sender→receiver arrows, action badges, artifact previews, inline send-message form. Agent Registry: grid of registered agents with status, capabilities, last-seen; register/deregister forms.
3. **API client**: Added 11 A2A functions (createConversation, getConversation, checkConversation, collectReplies, sendA2AMessage, replyA2AMessage, listAgents, registerAgent, deregisterAgent) + 8 type definitions.
4. **Nav update**: Added Memory and A2A links to header navigation (10 nav items total).

### Changes

| File | Change |
|------|--------|
| `ui/app/memory/page.tsx` | New — semantic search + context export with platform selector |
| `ui/app/a2a/page.tsx` | New — conversations + agent registry with tabbed UI |
| `ui/app/layout.tsx` | Added Memory, A2A nav links (10 items) |
| `ui/lib/api.ts` | Added A2A types + 11 fetch functions |

### Build

Next.js production build: 14 routes, 0 TypeScript errors.
Backend: 2,897 unit tests, 0 failures, 0 warnings.

---

## TD-140: Dashboard Redesign + Plans List Page (Sprint 27.3)

**Date**: 2026-04-02
**Status**: ✅ Complete

### Problem

Dashboard was minimal (goal input + task list + sidebar). No quick overview stats, no engine status visibility, no activity feed. Plans had a detail page (`/plans/[id]`) but no list page for browsing all plans.

### Decision

1. **Dashboard redesign**: Added QuickStats row (5 metrics: Tasks/Success Rate/Running/Engines/Local%), EngineWidget in sidebar (compact engine status with online/offline indicators), ActivityFeed (recent 8 tasks with status icons and cost).
2. **`/plans` list page**: Filterable by status (all/proposed/approved/executed/rejected), plan cards with step previews, cost display with FREE badge, link to detail view.
3. **Nav update**: Added Plans link (11 nav items total).

### Changes

| File | Change |
|------|--------|
| `ui/app/page.tsx` | Redesigned — QuickStats + EngineWidget + ActivityFeed + 4 parallel API calls |
| `ui/app/plans/page.tsx` | New — filterable plan list with card grid |
| `ui/app/layout.tsx` | Added Plans nav link |

### Build

Next.js production build: 15 routes, 0 TypeScript errors.

---

## TD-141: Chrome Extension — Context Bridge (Sprint 28.1)

**Date**: 2026-04-02
**Status**: ✅ Complete

### Decision

Build a Chrome Extension (Manifest v3) that connects to the Morphic-Agent backend for one-click context export to AI platforms. Extension communicates with `/api/memory/export` and `/api/health` endpoints.

### Key Design Choices

| Choice | Rationale |
|---|---|
| Manifest v3 (Service Worker) | Chrome deprecating Manifest v2 |
| `chrome.storage.local` for settings | Persists API URL + platform selection across sessions |
| CORS `chrome-extension://` origin | Required for fetch from extension popup |
| Keyboard shortcut `Ctrl+Shift+M` | Quick access without clicking extension icon |
| 15s health check interval | Balance between responsiveness and network cost |
| Dark theme matching app | Consistent design system across all surfaces |

### Changes

| File | Change |
|------|--------|
| `ui/extension/manifest.json` | New — Manifest v3, permissions, host_permissions |
| `ui/extension/popup.html` | New — Dark theme popup with platform selector |
| `ui/extension/popup.js` | New — API communication, clipboard, storage |
| `ui/extension/popup.css` | New — Dark theme styles |
| `ui/extension/background.js` | New — Service worker stub |
| `interface/api/main.py` | Updated CORS to allow chrome-extension:// origins |

---

## TD-142: OpenHands Driver API Update + E2E Verification (Sprint 28.2)

**Date**: 2026-04-02
**Status**: ✅ Complete

### Problem

OpenHands API changed in the latest image (2025-10-10):
- Old: `POST /api/v1/app-conversations` with `{task, model}` in body
- New: `POST /api/settings` (required first) → `POST /api/conversations` with `{}`
- Poll endpoint changed from `/api/v1/app-conversations/{id}` to `/api/conversations/{id}`
- Settings require lowercase field names: `llm_model`, `llm_api_key`, `agent`

### Decision

Update `OpenHandsDriver` to use the new API flow:
1. `_ensure_settings(model)` — POST model/key to `/api/settings` before conversation creation
2. Create conversation at `/api/conversations` with empty body
3. Fallback to legacy `/api/v1/app-conversations` if new endpoint returns 404/405
4. Poll at `/api/conversations/{id}` instead of legacy path
5. Settings only submitted when `api_key` is provided (skip for no-key drivers)

### Verification (Round 14)

- Docker container (image 2025-10-10) with `-v /var/run/docker.sock:/var/run/docker.sock`
- ✅ API reachable, settings POST succeeds
- ✅ Conversation creation with `initial_user_msg` succeeds
- ✅ Runtime sandbox image built (11.7GB) and started successfully
- ✅ Agent loop started, CodeActAgent loaded with 11 tools
- ❌ LLM call: `claude-sonnet-4-6` → old litellm sends `temperature`+`top_p` together (invalid)
- ❌ LLM call: `gpt-4o` → OpenAI quota exceeded
- Root cause: OpenHands image (2025-10-10) bundles old litellm incompatible with Claude 4.x parameter constraints
- 25 unit tests pass (+ 3 new), 2,900 total unit tests pass, 0 failures

### Changes

| File | Change |
|------|--------|
| `infrastructure/agent_cli/openhands_driver.py` | `_ensure_settings()`, `initial_user_msg`, status `.lower()`, IDLE/STOPPED handling |
| `tests/unit/infrastructure/test_openhands_driver.py` | Settings flow + 3 new tests (settings skip, ensure_settings, idle status) |
| `tests/integration/test_openhands_e2e.py` | API key injection, expanded skip patterns |

---

## TD-143: Production Hardening — Docker + Compose + Nginx (Sprint 28.3)

**Date**: 2026-04-02
**Status**: ✅ Complete

### Decision

Add production deployment infrastructure: multi-stage Dockerfiles, docker-compose.prod.yml, nginx reverse proxy.

### Key Design Choices

| Choice | Rationale |
|---|---|
| Multi-stage Dockerfile (Python) | uv for deps in builder, slim runtime image, non-root `morphic` user |
| 3-stage Dockerfile (Next.js) | deps → build → runner with standalone output, minimal image |
| nginx reverse proxy | Route `/` → ui, `/api/` → api, `/ws/` → api (WebSocket upgrade) |
| Health checks on all services | Docker restart policy + orchestrator visibility |
| pgvector image | Vector similarity search for semantic memory |
| `.dockerignore` | Exclude .env, caches, docs from build context |

### Changes

| File | Change |
|------|--------|
| `Dockerfile` | New — Python API multi-stage build |
| `ui/Dockerfile` | New — Next.js 3-stage build |
| `docker-compose.prod.yml` | New — 6 services (nginx, api, ui, pg, redis, neo4j) |
| `nginx.conf` | New — Reverse proxy with WebSocket + gzip |
| `.dockerignore` | New — Build context exclusions |
| `ui/next.config.ts` | Added `output: "standalone"` |
| `.env.example` | Updated with all production variables |

### Build Verification

- ✅ `docker compose -f docker-compose.prod.yml config` — valid
- ✅ `docker compose -f docker-compose.prod.yml build api` — success (CLAUDE.md included for pyproject.toml readme)
- ✅ `docker compose -f docker-compose.prod.yml build ui` — success (standalone output)

---

## TD-144 — README, LICENSE, Makefile + Version Alignment

**Date**: 2026-04-02
**Sprint**: 29.1
**Status**: ✅ Done

### Decision
Add standard open-source project files and align version strings from `0.4.0-alpha` to `0.5.0-alpha`.

### What Changed
| File | Change |
|------|--------|
| `README.md` | New — public-facing overview, quickstart, dev commands |
| `LICENSE` | New — MIT (as declared in pyproject.toml) |
| `Makefile` | New — test, lint, serve, docker shortcuts |
| `pyproject.toml` | Version `0.4.0-alpha` → `0.5.0-alpha` |
| `interface/api/main.py` | FastAPI version `0.4.0-alpha` → `0.5.0-alpha` |
| `tests/unit/test_version_consistency.py` | New — 3 tests for version alignment |

---

## TD-145 — GitHub Actions CI Pipeline

**Date**: 2026-04-02
**Sprint**: 29.2
**Status**: ✅ Done

### Decision
Add CI/CD pipeline for automated quality gates on push/PR.

### What Changed
| File | Change |
|------|--------|
| `.github/workflows/ci.yml` | New — 4 jobs: lint, unit tests, UI build, Docker build |

### Jobs
- `lint`: `ruff check .`
- `unit-tests`: `pytest tests/unit/ -v`
- `ui-build`: `npm ci && npm run build`
- `docker-build`: Build API + UI Docker images

---

## TD-146 — Settings API Route + Frontend Settings Page

**Date**: 2026-04-02
**Sprint**: 29.3
**Status**: ✅ Done

### Decision
Add a read-only Settings API and UI page for runtime configuration visibility and system health monitoring.

### What Changed
| File | Change |
|------|--------|
| `interface/api/routes/settings.py` | New — `GET /api/settings` (config, keys redacted), `GET /api/settings/health` |
| `interface/api/main.py` | Register settings_router |
| `ui/app/settings/page.tsx` | New — health, config, budget, engines, API keys, features |
| `ui/app/layout.tsx` | Added Settings nav link |
| `ui/lib/api.ts` | Added `getSettings()`, `getHealth()` + types |
| `tests/unit/interface/test_settings_api.py` | New — 12 tests |

---

## TD-147 — Route Unit Test Coverage Hardening

**Date**: 2026-04-02
**Sprint**: 29.4
**Status**: ✅ Done

### Decision
Add dedicated unit tests for previously untested API route modules (cost, memory, models).

### What Changed
| File | Change |
|------|--------|
| `tests/unit/interface/test_cost_route.py` | New — 5 tests (summary shape, budget calc, logs) |
| `tests/unit/interface/test_memory_route.py` | New — 6 tests (search, empty, export with params) |
| `tests/unit/interface/test_models_route.py` | New — 12 tests (list, status, pull, switch, info, 404) |

### Test Count
- +23 new route tests
- Total: 2,943 unit + 148 integration = 3,091

---

## TD-148 — .env Validation Script

**Date**: 2026-04-02
**Sprint**: 29.5
**Status**: ✅ Done

### Decision
Add a validation script to catch configuration errors early. Validates `.env` against `.env.example` with type checking.

### What Changed
| File | Change |
|------|--------|
| `scripts/validate_env.py` | New — missing key detection, boolean/number type validation, URL format check |
| `tests/unit/test_validate_env.py` | New — 5 tests |

### Capabilities
- Missing key detection (vs `.env.example`)
- Boolean value validation (true/false/1/0)
- Numeric value validation
- URL format sanity check

---

## TD-149 — PostgreSQL Auto-Init with pgvector Extension

**Date**: 2026-04-02
**Sprint**: 30.1
**Status**: ✅ Done

### Problem
Fresh `docker compose up` with `USE_POSTGRES=true` failed because:
1. Docker disk space exhaustion caused PG crash loop (`No space left on device`)
2. After volume cleanup and recreation, `CREATE EXTENSION vector` was missing — `VECTOR(384)` column type in `memories` table caused `UndefinedObjectError`

### Decision
Auto-enable pgvector extension on fresh PostgreSQL initialization via Docker init script.

### What Changed
| File | Change |
|------|--------|
| `scripts/init_pg.sql` | New — `CREATE EXTENSION IF NOT EXISTS vector` |
| `docker-compose.yml` | Mount init script to `/docker-entrypoint-initdb.d/` |

### Why
PostgreSQL's `docker-entrypoint-initdb.d/` runs SQL files only on first volume initialization. This ensures pgvector is always available without manual intervention.

### Verification
- `docker compose down -v && docker compose up -d postgres` → healthy
- `USE_POSTGRES=true make serve` → all 11 tables created, `/api/health` returns OK
- All 6 engines, cost tracking, memory (VECTOR column) working

---

## TD-150 — Chrome Extension README Documentation

**Date**: 2026-04-02
**Sprint**: 31.1
**Status**: ✅ Done

### Decision
Document Chrome Extension installation and usage in README.md. Extension was already fully implemented (Manifest v3, popup.js 316 lines, popup.css 412 lines, background.js 70 lines, 3 icon PNGs).

---

## TD-151 — Task Graph Visualizer Enhancement

**Date**: 2026-04-02
**Sprint**: 31.2
**Status**: ✅ Done

### Decision
Enhance TaskGraph.tsx with click-to-select detail panel, cost badges per node, engine labels, and improved edge styling.

### What Changed
| File | Change |
|------|--------|
| `ui/components/TaskGraph.tsx` | Added SubTaskPanel slide-out, click-to-select, cost/engine badges, glow highlight |

### Features Added
- Click subtask node → slide-out detail panel (status, cost, model, engine, tool calls, code, output, result, error)
- Cost badge (`$0.0000`) on each node
- Engine used label on nodes
- Box-shadow glow on selected node
- Edge `strokeWidth: 2` for success, `1` for pending
- `onPaneClick` to deselect

---

## TD-152 — Codex CLI Engine Routing E2E

**Date**: 2026-04-02
**Sprint**: 31.3
**Status**: ✅ Done

### Decision
Live E2E verification of Codex CLI (gpt-5-codex) as execution engine via `POST /api/engines/run` with `"engine": "codex_cli"`.

### Verification (Live E2E Round 15)
- `POST /api/engines/run` with `{"task": "Write a Python factorial function", "engine": "codex_cli", "task_type": "code_generation"}`
- Engine: `codex_cli` — correctly routed (no fallback needed)
- Codex CLI autonomously: explored codebase (pwd, ls, rg) → wrote code → created file → verified
- Duration: 42.6s, input tokens: 142K (107K cached), success: true
- `engines_tried: ["codex_cli", "claude_code", "ollama"]` — first engine succeeded

---

## TD-153 — OpenHands Sandbox E2E Verification

**Date**: 2026-04-02
**Sprint**: 31.4
**Status**: ✅ Done

### Decision
Live E2E verification of OpenHands sandbox execution via REST API with Gemini 2.5 Flash.

### Verification (Live E2E Round 16)
1. Started `ghcr.io/all-hands-ai/openhands:latest` on port 3001 with Docker socket mount
2. Configured settings: `gemini/gemini-2.5-flash` + `CodeActAgent`
3. Created conversation: `POST /api/conversations` → `conversation_id` returned
4. Agent autonomously: created file → cat to verify → python3 execution → finish
5. Output: `is_prime()` function with correct results (True, False, True, False)

### Issues Found
| Issue | Cause | Workaround |
|-------|-------|------------|
| Claude model fails | OpenHands v0.59 sends `temperature` + `top_p` simultaneously (Anthropic API rejects) | Use Gemini or newer OpenHands image |
| OpenAI quota error | Insufficient balance on account | Use Gemini or Claude (after OH upgrade) |
| Events API returns 0 | Different pagination per conversation context | Use `?limit=100` parameter |

### Full Pipeline Verified
- ✅ OpenHands server start + API health
- ✅ Settings configuration (LLM model, API key, agent type)
- ✅ Conversation creation + sandbox runtime spin-up
- ✅ CodeActAgent: file create → shell commands → Python execution
- ✅ Finish event with correct output

---

## TD-154 — Version Bump to v0.5.1

**Date**: 2026-04-02
**Sprint**: 31.5
**Status**: ✅ Done

### Decision
Bump version from 0.5.0-alpha to 0.5.1 across all source files. All 65 sprints (TD-001 to TD-154) complete. 6/6 engines live E2E verified across 16 rounds.

### Files Updated
| File | Change |
|------|--------|
| `pyproject.toml` | version "0.5.0-alpha" → "0.5.1" |
| `interface/api/main.py` | FastAPI version → "0.5.1" |
| `interface/api/routes/settings.py` | Settings version → "0.5.1" |
| `interface/cli/commands/serve.py` | CLI banner → "v0.5.1" |
| `CLAUDE.md` | Build date + version → "2026-04-02 / 0.5.1" |
| `tests/unit/interface/test_settings_api.py` | Assertion → "0.5.1" |
| `tests/unit/test_version_consistency.py` | EXPECTED_VERSION → "0.5.1" |

---

## TD-155 — Auto-route Intelligence: Per-subtask Engine Classification

**Date**: 2026-04-02
**Sprint**: 32.1
**Status**: ✅ Done

### Problem
When `preferred_model` is null (most cases), `LangGraphTaskEngine._execute_batch()` skips engine routing entirely. All subtasks fall through to ReactExecutor/direct LLM → LiteLLMGateway defaults to Ollama/qwen3:8b. The intelligent `AgentEngineRouter.select()` is never called for individual subtasks.

### Root Cause
Lines 343-344 in `engine.py`:
```python
engine_type = _resolve_engine_type(subtask.preferred_model)  # None → None
use_engine_route = ... and engine_type is not None  # → False → skip routing
```

### Solution
Add `SubtaskTypeClassifier` — a pure domain service that infers `TaskType` from subtask description using `TopicExtractor` + `TaskComplexityClassifier`. When `preferred_model` is null, classify the subtask and call `AgentEngineRouter.select()` to determine the optimal engine. Route to that engine via `RouteToEngineUseCase.execute()` with fallback chain.

### TaskType Mapping
| Topic | TaskType | Primary Engine |
|-------|----------|----------------|
| backend, frontend, database, testing | CODE_GENERATION | Codex CLI |
| ml, security, refactoring | COMPLEX_REASONING | Claude Code |
| data | LONG_CONTEXT | Gemini CLI |
| documentation, devops | FILE_OPERATION | Ollama (FREE) |
| general | SIMPLE_QA | Ollama (FREE) |
| (complexity=COMPLEX override) | COMPLEX_REASONING | Claude Code |
| (requires_tools override) | COMPLEX_REASONING | Claude Code |

### Files Changed
| File | Change |
|------|--------|
| `domain/services/subtask_type_classifier.py` | NEW: topic+complexity → TaskType |
| `infrastructure/task_graph/engine.py` | Auto-route logic in _execute_batch |
| `interface/api/container.py` | Inject task_budget into engine |
| `tests/unit/domain/test_subtask_type_classifier.py` | NEW: classification tests |
| `tests/unit/infrastructure/test_langgraph_engine.py` | Auto-route integration tests |

---

## TD-159 — Fix Parallel Decomposition + Quality Gate + DB Persistence

**Date**: 2026-04-03
**Sprint**: 33.1
**Status**: ✅ Done

### Problem
1. LLM returns `deps=[]` for parallel subtasks, but `_apply_artifact_flow()` overrides with linear chain artifacts, destroying parallel structure.
2. Ollama produces unusable single-word subtask descriptions ("取得", "解析") that break execution.
3. `PgTaskRepository` only serializes 8 of 16 SubTask fields — `engine_used`, `complexity`, `react_iterations`, `tool_calls_count`, `tools_used`, `data_sources`, `code`, `execution_output` all lost on DB round-trip.

### Solution
1. Add `llm_decomposed` keyword to `_apply_artifact_flow()` — when True, skips linear chain inference to preserve LLM's parallel deps.
2. Quality gate: if any subtask description < 8 chars, fall back to `_template_decompose()` which provides well-structured parallel subtasks.
3. Extract `_subtask_to_dict()` / `_dict_to_subtask()` helpers for complete 16-field serialization.

### Files Changed
| File | Change |
|------|--------|
| `infrastructure/task_graph/intent_analyzer.py` | `llm_decomposed` flag, quality gate, `_template_decompose()` |
| `infrastructure/persistence/pg_task_repository.py` | Full 16-field SubTask serialization |
| `tests/unit/infrastructure/test_intent_analyzer.py` | Updated for new parallel behavior + quality gate tests |
| `tests/unit/infrastructure/test_intent_analyzer_artifacts.py` | 4 tests updated for parallel preservation |

---

## TD-160 — Real-time UI with Lucide React Icons

**Date**: 2026-04-03
**Sprint**: 33.2
**Status**: ✅ Done

### Problem
1. All UI status indicators use CSS dots (`rounded-full bg-success`) or Unicode characters (`⏳✓✗↻`) — inconsistent and visually poor.
2. Status transitions are invisible: user sees only start (pending) and end (success) with no live feedback during execution.

### Solution
Replace all CSS dots and Unicode icons across the entire UI with Lucide React icons. Add animated transitions for running state (spin, pulse, glow shadows). Components updated:

### Files Changed
| File | Change |
|------|--------|
| `ui/components/TaskDetail.tsx` | Full rewrite: Lucide icons, AnimatedNumber, RunningPulse, status glow |
| `ui/components/TaskList.tsx` | Lucide StatusIcon replacing Unicode |
| `ui/components/TaskGraph.tsx` | Lucide NodeStatusIcon, Code2, Zap, running glow in graph nodes |
| `ui/components/NavBar.tsx` | NEW: Lucide nav icons (12 items), active state highlighting |
| `ui/components/CodeBlock.tsx` | Copy/Check/Code2 icons for copy button and language label |
| `ui/components/ExecutionResult.tsx` | CheckCircle2/XCircle/Terminal replacing CSS dot |
| `ui/components/ModelStatus.tsx` | CheckCircle2/XCircle replacing CSS dot for Ollama status |
| `ui/components/GoalInput.tsx` | CheckCircle2/XCircle for engine availability indicators |
| `ui/app/tasks/page.tsx` | Lucide StatusIcon replacing Unicode STATUS_ICON map + CSS Spinner |
| `ui/app/a2a/page.tsx` | CheckCircle2/XCircle/Network for agent online status |
| `ui/app/layout.tsx` | Import NavBar component |

---

## TD-161 — SSE Real-time Streaming + Activity Timeline

**Date**: 2026-04-04
**Sprint**: 33.3
**Status**: ✅ Done

### Problem
Users only see task start (pending) and end (success) states. No visibility into intermediate subtask execution. WebSocket polls DB every 1 second, but the engine only writes to DB twice (RUNNING at start, final state at end), so no intermediate updates are visible.

### Root Cause
`LangGraphTaskEngine._execute_batch()` updates `subtask.status` in-memory only. No DB writes or event emissions occur during execution. WebSocket polls DB, but finds no changes until the task is fully complete.

### Solution
1. **TaskEventBus** (`shared/event_bus.py`): In-memory asyncio.Queue-based pub/sub. Engine publishes events; SSE endpoint subscribes and streams to browser.
2. **Engine events**: Emit `task_started`, `subtask_started`, `subtask_completed`, `task_completed` during execution.
3. **Intermediate DB persistence**: Write task state after each subtask status change, so WebSocket fallback and page-refresh also see updates.
4. **SSE endpoint** (`/api/tasks/{task_id}/stream`): Server-Sent Events with heartbeat, auto-close on task completion.
5. **useTaskStream hook**: React hook connecting to SSE, progressively updating task state.
6. **ActivityTimeline component**: Deep Research-style step-by-step timeline with icons, animations, result previews.
7. **TaskGraph console fix**: Replaced mixed `border` shorthand + `borderLeftWidth`/`borderLeftColor` with individual border properties.

### Event Flow
```
Engine._execute_batch()
  → subtask.status = RUNNING
  → event_bus.publish("subtask_started", ...)
  → task_repo.update(task)  ← intermediate DB write
  → [execute subtask via engine/react/llm]
  → event_bus.publish("subtask_completed", ...)
  → task_repo.update(task)  ← intermediate DB write
  ↓
SSE Endpoint (task_stream.py)
  → event_bus.subscribe(task_id)
  → yield SSE events to browser
  ↓
useTaskStream hook
  → EventSource → setTask() → React re-render
```

### Files Changed
| File | Change |
|------|--------|
| `shared/event_bus.py` | NEW: TaskEventBus (asyncio.Queue pub/sub) |
| `infrastructure/task_graph/engine.py` | Event emission + intermediate DB writes + _emit/_persist helpers |
| `application/use_cases/execute_task.py` | Wire event_bus + task_repo to engine |
| `interface/api/container.py` | TaskEventBus singleton in DI |
| `interface/api/routes/task_stream.py` | NEW: SSE endpoint |
| `interface/api/main.py` | Register SSE route |
| `ui/lib/useTaskStream.ts` | NEW: SSE React hook |
| `ui/components/ActivityTimeline.tsx` | NEW: Deep Research-style timeline |
| `ui/app/tasks/[id]/page.tsx` | Rewritten to use SSE hook + timeline |
| `ui/components/TaskGraph.tsx` | Fix border shorthand console error |

---

## TD-162 — TaskGraph Live Node Animations

**Date**: 2026-04-04
**Sprint**: 34.1–34.2
**Status**: ✅ Done

### Problem
TaskGraph nodes appear all at once when the page loads or when SSE updates arrive. No visual indication of which nodes are new or which changed status. Running nodes lack visual feedback beyond a static shadow.

### Solution
Three CSS keyframe animations + React state tracking for differential rendering:

1. **morphic-node-enter** (0.5s, cubic-bezier): Scale(0.85)+translateX(-12px) → scale(1.02) → scale(1). Plays once on first appearance.
2. **morphic-node-pulse** (2s, infinite): Box-shadow breathing glow (info blue) on running nodes.
3. **morphic-status-flash** (0.6s): Brightness flash when node transitions status (e.g. pending→running→success).
4. **Stagger delay**: Multiple new nodes animate in cascade (80ms increments) instead of all at once.
5. **Edge transitions**: CSS transition on stroke/strokeWidth for smooth color changes on status updates.
6. **Goal node**: ReactFlow `className` prop for enter animation.

### Implementation
- `useRef<Set<string>>` tracks previously seen node IDs → diff detection for `isNew` flag
- `useRef<Map<string, string>>` tracks previous status → diff detection for `prevStatus`
- `useEffect` updates refs after each render (runs after paint, so useMemo reads stale refs correctly)
- Animation classes applied conditionally in SubTaskNode via filtered class list

### Files Changed
| File | Change |
|------|--------|
| `ui/app/globals.css` | 4 keyframe animations + 3 utility classes |
| `ui/components/TaskGraph.tsx` | prevNodeIds/prevStatusMap refs, isNew/enterDelay/prevStatus flags, goal className |

### Live Verification
SSE end-to-end test: `POST /api/tasks` → `GET /api/tasks/{id}/stream` → received snapshot → subtask_completed → task_completed → final snapshot. All events with correct timestamps, status transitions, and cost data.

---

## TD-163 — Living Fractal: Reflection-Driven Dynamic Node Spawning

**Date**: 2026-04-04
**Sprint**: 35
**Status**: ✅ Done

### Problem
FractalTaskEngine had recursive decomposition (non-terminal nodes expand into sub-plans) but no mechanism to assess whether the *overall goal* was fully addressed after all visible nodes completed. If the initial plan missed an aspect, there was no way to discover and fill that gap dynamically.

### Solution
**Reflection cycle**: After the dynamic execution queue empties, a `ReflectionEvaluator` asks an LLM "Is the goal satisfied given the completed work?" If not, it suggests new subtask descriptions. These are spawned as new `PlanNode` objects (with `spawned_by_reflection=True`), appended to the execution queue, and processed normally — making the task graph self-expanding ("living fractal").

Key design decisions:
1. **Queue-based execution**: Changed from static `for node in plan.visible_nodes` to `deque`-based queue. Reflection appends new nodes to the same queue — no special execution path needed.
2. **Safety guards**: `max_reflection_rounds` (default 2), `max_total_nodes` (default 20), budget check, nesting level 0 only. Guards are checked *before* calling the LLM to save cost.
3. **Graceful degradation**: If the reflection evaluator raises, execution continues without spawning (non-fatal). LLM failure returns `is_satisfied=True` with low confidence as fallback.
4. **SSE event propagation**: Three new event types — `reflection_started`, `node_spawned`, `reflection_complete` — enable real-time UI updates.
5. **KV-cache friendly prompts**: Stable system prompt prefix for the LLM reflection evaluator. Dynamic content (completed node summaries) appended at the end.
6. **Incremental SubTask management**: SubTasks created immediately from the approved plan (not post-execution), enabling real-time UI updates via SSE.

### Architecture
```
execute() → _generate_approved_plan() → initial visible_nodes → deque
         ↓
while pending:
  node = pending.popleft()
  _execute_with_eval(node)  # Gate 2
  ↓
  if queue empty:
    _maybe_reflect(plan, goal, completed)
      → guards check → ReflectionEvaluator.reflect()
      → if unsatisfied → _create_reflection_nodes() → append to pending
      → loop continues
```

### Files Changed
| File | Change |
|------|--------|
| `domain/entities/reflection.py` | NEW: `ReflectionResult` entity with `spawn_count` property |
| `domain/ports/reflection_evaluator.py` | NEW: `ReflectionEvaluatorPort` ABC |
| `domain/entities/fractal_engine.py` | `spawned_by_reflection` on PlanNode, `reflection_rounds` on ExecutionPlan |
| `domain/services/nesting_depth_controller.py` | `check_reflection_allowed()` static method |
| `shared/config.py` | `fractal_max_reflection_rounds`, `fractal_max_total_nodes` settings |
| `infrastructure/fractal/llm_reflection_evaluator.py` | NEW: LLM-powered reflection evaluator |
| `infrastructure/fractal/fractal_engine.py` | Queue-based execution, `_maybe_reflect()`, `_create_reflection_nodes()`, SSE integration |
| `interface/api/container.py` | DI wiring for reflection evaluator |
| `ui/lib/useTaskStream.ts` | SSE handlers for `node_spawned`, `reflection_started`, `reflection_complete` |
| `ui/components/ActivityTimeline.tsx` | UI rendering for 3 new event types |
| `tests/unit/domain/test_reflection.py` | NEW: 10 tests for entity + guards |
| `tests/unit/infrastructure/test_fractal_reflection.py` | NEW: 14 tests for reflection cycle + LLM evaluator |

### Test Coverage
- 3002 unit tests passing (from 2984, +18 new)
- 0 failures, 0 warnings, lint clean

---

## TD-164 — SSE Inactivity Timeout Fix + Dashboard Auto-Navigate

**Date**: 2026-04-05
**Sprint**: 35.1
**Status**: ✅ Done

### Problem
SSE reflection events (`reflection_started`, `node_spawned`, `reflection_complete`) were emitted correctly server-side but never reached the browser during live fractal execution. Two root causes:

1. **SSE stream timeout**: `MAX_STREAM_DURATION = 600` (10 min) used an `elapsed` counter that accumulated heartbeat timeouts but was never reset when real events arrived. For long fractal executions (30+ min), heartbeat time accumulated past 600s and the stream closed before reflection events were emitted.
2. **Dashboard UX gap**: After task creation, the dashboard stayed on the main page using WebSocket (`connectTaskWs`) for limited status polling, while the rich SSE-powered task detail page (with ActivityTimeline, TaskGraph animations, and reflection event rendering) was only accessible by manual navigation.

### Solution
1. **True inactivity timeout**: Reset `elapsed = 0.0` when a real event arrives. The timer now measures *inactivity* (no events for N seconds) rather than cumulative idle time. Raised `MAX_STREAM_DURATION` from 600 to 3600 (1 hour).
2. **Auto-navigate to task detail**: After task creation in execute mode, `router.push(/tasks/{id})` instead of staying on dashboard with WebSocket. This gives immediate access to the SSE stream with reflection events, live graph animations, and activity timeline.

### Files Changed
| File | Change |
|------|--------|
| `interface/api/routes/task_stream.py` | `elapsed` reset on event, `MAX_STREAM_DURATION` 600→3600, docstring updated with reflection event types |
| `ui/app/page.tsx` | Task creation auto-navigates to `/tasks/{id}`, removed unused `connectTaskWs` import |

### Verified
- 3002 unit tests passing, lint clean
- UI build successful

---

## TD-165 — Reflection Badge: Visual Distinction for Spawned Nodes

**Date**: 2026-04-05
**Sprint**: 35.2
**Status**: ✅ Done

### Problem
Reflection-spawned subtasks were visually indistinguishable from initial plan nodes. During live SSE streaming, `node_spawned` events carried `spawned_by: "reflection"` metadata, but this wasn't persisted on the SubTask entity or exposed via the API. After page refresh, the information was lost.

### Solution
Full vertical slice through all 4 layers:

1. **Domain**: Added `spawned_by_reflection: bool = False` and `reflection_round: int | None = None` to `SubTask` entity
2. **Infrastructure**: `NodeExecutor.to_subtask()` carries over `spawned_by_reflection` from `PlanNode`. `FractalEngine` sets `reflection_round` when creating reflection SubTasks. PG serialization updated.
3. **API**: `SubTaskResponse` schema includes both fields. Persisted through page refreshes.
4. **UI**: Amber "R1"/"R2" badge on reflection nodes in TaskGraph (graph view) and TaskDetail (list view). SubTaskPanel shows "Spawned by reflection (round N)" info line.

### Files Changed (9 files, 4 layers)
| File | Layer | Change |
|------|-------|--------|
| `domain/entities/task.py` | Domain | `spawned_by_reflection`, `reflection_round` fields |
| `infrastructure/fractal/node_executor.py` | Infra | Carry `spawned_by_reflection` to SubTask |
| `infrastructure/fractal/fractal_engine.py` | Infra | Set `reflection_round` on spawned SubTasks |
| `infrastructure/persistence/pg_task_repository.py` | Infra | Serialize/deserialize new fields |
| `interface/api/schemas.py` | API | `SubTaskResponse` fields + `from_subtask()` |
| `ui/lib/api.ts` | UI | TypeScript type update |
| `ui/lib/useTaskStream.ts` | UI | Set flags on `node_spawned` SSE event |
| `ui/components/TaskGraph.tsx` | UI | Amber "R1" badge + Sparkles icon in panel |
| `ui/components/TaskDetail.tsx` | UI | "REFLECT R1" badge in subtask list |

### Verified
- 3002 unit tests passing, lint clean
- UI build successful

---

## TD-166: Fractal Engine — Subtask Status Persistence + Complexity Classification

**Date**: 2026-04-05
**Sprint**: 35.3
**Status**: Done

### Problem
Two critical issues in FractalTaskEngine execution:

1. **Stuck "pending" status in REST API**: When the fractal engine started executing a subtask, the `SubTask.status` was only updated to RUNNING inside the inner LangGraphTaskEngine's synthetic task. The outer task's SubTask (persisted in DB) remained PENDING until execution completed. REST API consumers saw all subtasks as "pending" for the entire duration.

2. **Infinite ReAct tool loop**: NodeExecutor created subtasks without setting `complexity`, which defaulted to `None`. LangGraphTaskEngine then defaulted `None` complexity to `MEDIUM`, routing ALL fractal subtasks through the ReAct executor with 39 LAEE tools. The qwen3:8b model entered an infinite loop calling `shell_exec` repeatedly (6+ iterations, ~45s each) instead of producing a final answer. Simple tasks like "What is 2+2?" ran indefinitely.

### Root Cause Analysis
- **Issue 1**: `_sync_subtask()` and `_persist_intermediate()` in `_execute_plan()` were only called AFTER `_execute_with_eval()` returned. No intermediate status update occurred.
- **Issue 2**: The execution path selection in LangGraphTaskEngine (line 500): `use_react = self._react is not None and (complexity != TaskComplexity.SIMPLE or ...)`. With `complexity=None → MEDIUM`, the condition was always True.

### Solution
1. **Status persistence**: Set `SubTask.status = RUNNING` and call `_persist_intermediate()` BEFORE `_execute_with_eval()`. Both SSE subscribers and REST API now see real-time status.
2. **Complexity classification**: `NodeExecutor._build_task()` now classifies the subtask description using `TaskComplexityClassifier.classify()`. Simple subtask descriptions (e.g., "Calculate") are correctly classified as SIMPLE, routing them through the direct LLM path instead of ReAct.

### Performance Impact
- Before: "What is 2+2?" → infinite loop (never completes)
- After: "What is 2+2?" → 4.5 minutes (planning 80s + 3 subtasks ~30s each + reflection 50s)
- Each subtask now completes in ~24-32s via direct LLM instead of 6+ minutes looping

### Files Changed (2 files)
| File | Change |
|------|--------|
| `infrastructure/fractal/fractal_engine.py` | Set SubTask RUNNING + persist before execution |
| `infrastructure/fractal/node_executor.py` | Add TaskComplexityClassifier to _build_task() |

### Verified
- 3002 unit tests passing
- Live E2E: task "What is 2+2?" completes successfully with status=success
- All 3 subtasks show "running" during execution, "success" after
- Reflection evaluator confirms goal satisfaction

---

## TD-167: SIMPLE Task Fractal Bypass — LLM Intent Analysis

**Date:** 2026-04-05
**Sprint:** 36
**Status:** Done
**Category:** Performance / Architecture

### Problem
In fractal mode, ALL tasks (including "What is 2+2?") went through the full pipeline:
1. Planner LLM call (~30-45s) → generate candidate nodes
2. PlanEvaluator LLM call (~30-45s) → Gate 1 evaluation
3. Node execution (~30s each × 3 nodes)
4. ResultEvaluator (~30s per node)
5. ReflectionEvaluator (~30s)

Total: ~4.5 minutes for trivial tasks. This is 9x slower than necessary.

### Root Cause
FractalTaskEngine.execute() always called _generate_approved_plan() regardless of goal complexity. No early-exit for goals that don't benefit from fractal decomposition.

### Solution: Pure LLM Intent Analysis

**All classification through LLM** (~15-30s)
- Every goal goes through LLM intent analysis — no rule-based shortcuts
- The model understands nuance that regex cannot (e.g., "fix the bug" is MEDIUM)
- Focused classification prompt: "Is this SIMPLE, MEDIUM, or COMPLEX?"
- Conservative: uncertain → MEDIUM → proceeds with fractal planning
- Handles qwen3:8b `<think>` tags and markdown code blocks
- LLM failure → default to fractal (safe fallback)

**Bypass path**: FractalTaskEngine.execute() → _execute_bypass()
- Creates single SubTask with complexity=SIMPLE
- Wires inner engine (LangGraph) for SSE events + persistence
- LangGraph takes the direct-LLM fast path (no ReAct, no tools)
- Unwires inner engine after execution

### Files
- `infrastructure/fractal/bypass_classifier.py` — NEW (FractalBypassClassifier)
- `infrastructure/fractal/fractal_engine.py` — bypass check + _execute_bypass()
- `interface/api/container.py` — wire bypass classifier into FractalTaskEngine

### Performance Impact
- SIMPLE tasks: ~4.5min → ~45-60s (4-6x faster)
- MEDIUM/COMPLEX tasks: +15-30s for classification call (negligible vs planning time)
- LLM classification adds ~15-30s but saves 3-4 minutes for SIMPLE goals

### Tests
- 18 new tests: LLM classification (13), engine integration (5)
- All 3,020 unit tests passing

## TD-168: Gate 2 Skip for Successful Terminal Nodes

**Date:** 2026-04-05
**Sprint:** 36.1
**Status:** Done
**Category:** Performance

### Problem
Every terminal node execution was followed by a Gate 2 LLM evaluation call
(~30s via Ollama). For terminal nodes where the inner engine (LangGraph)
already returned SUCCESS with a result, this re-evaluation is redundant —
the inner engine already validated the output.

### Solution: Opt-in Gate 2 Skip
Added `skip_gate2_for_terminal_success` constructor parameter to
FractalTaskEngine (default: `False` for safety, `True` in production).

When enabled, the Gate 2 result evaluator LLM call is skipped if ALL of:
1. The node is terminal (`should_term=True`)
2. The node status is `SubTaskStatus.SUCCESS`
3. The node has a non-empty result

Gate 2 still runs for:
- Failed terminal nodes (need RETRY/REPLAN decisions)
- Terminal nodes with empty results (suspicious success)
- Non-terminal (expandable) nodes (recursive quality check)

### Files
- `infrastructure/fractal/fractal_engine.py` — gate 2 skip condition
- `interface/api/container.py` — enabled in production
- `tests/unit/infrastructure/test_fractal_engine.py` — 4 new tests

### Performance Impact
- ~30s saved per successful terminal node in fractal execution
- Typical 3-node plan: 90s savings (3 × 30s Gate 2 calls eliminated)
- No quality regression: inner engine (LangGraph) already validates results

### Tests
- 4 new tests: skip on success, no skip on failure, no skip on empty result,
  no skip on non-terminal
- All 3,024 unit tests passing

## TD-169: Parallel Node Execution via asyncio.gather

**Date:** 2026-04-05
**Sprint:** 37
**Status:** Done
**Category:** Performance

### Problem
Fractal plans with multiple nodes (typically 3) execute sequentially:
Node A (~30s) → Node B (~30s) → Node C (~30s) = ~90s total.
These nodes are often independent and could run simultaneously.

### Solution: Opt-in Parallel Execution
Added `parallel_node_execution` constructor parameter to FractalTaskEngine
(default: `False`, `True` in production).

When enabled, all pending nodes are drained into a batch and executed via
`asyncio.gather`. Each node runs `_execute_node_safe()` which wraps
`_execute_with_eval()` and captures `_PlanFailureError` as a return value
instead of raising, so one node's failure doesn't abort the batch.

When disabled (default), the sequential path preserves:
- **Artifact chaining**: Earlier nodes' outputs injected into later nodes
- **Budget accumulation**: Cost tracked between each node execution
- **Fallback ordering**: `continue` skips failed node when fallback activates

### Design Decisions
1. **Opt-in, not default**: Implicit node ordering (planner output order) may
   encode artifact dependencies. Parallel mode breaks this.
2. **Batch draining**: All pending nodes form a single batch per iteration.
   Reflection-spawned nodes go to the next batch.
3. **Fallback handling**: `_try_fallback()` async method replaces the sync
   `_handle_node_failure()`. Fallbacks execute sequentially after gather.
4. **Single node optimization**: When batch has 1 node, direct await (no
   gather overhead).

### Files
- `infrastructure/fractal/fractal_engine.py` — parallel/sequential dual path
- `interface/api/container.py` — enabled in production
- `tests/unit/infrastructure/test_fractal_engine.py` — 4 new tests

### Performance Impact
- 3-node plan: ~90s → ~30s (3x speedup)
- Single node: no change
- Sequential fallback: no change

### Tests
- 4 new tests: parallel multi-node, single node with parallel, mixed
  success/failure, sequential order preservation
- All 3,028 unit tests passing

## TD-170: Auto-Refresh Dashboard, Cost, Engines Pages

**Date:** 2026-04-05
**Sprint:** 37.1
**Status:** Done
**Category:** UX

### Problem
Dashboard, Cost, and Engines pages only fetched data once on mount. When tasks
were running in the background, these pages showed stale data until manual
refresh. Only the Tasks List page had auto-refresh.

### Solution: useAutoRefresh Hook
Created `ui/lib/useAutoRefresh.ts` — a shared hook that polls at 3s intervals
when `active` is true (any task running or pending).

Applied to 3 pages:
- **Dashboard** (`ui/app/page.tsx`) — stats, engines, activity feed update live
- **Cost** (`ui/app/cost/page.tsx`) — budget, logs refresh during execution
- **Engines** (`ui/app/engines/page.tsx`) — availability status updates

### Files
- `ui/lib/useAutoRefresh.ts` — NEW shared hook
- `ui/app/page.tsx` — added auto-refresh
- `ui/app/cost/page.tsx` — added auto-refresh + listTasks for active detection
- `ui/app/engines/page.tsx` — added auto-refresh + listTasks for active detection

### Tests
- Next.js build passes (16 pages generated)
- All 3,028 unit tests passing

---

## TD-171: Skip Reflection for Single-Node Successful Plans

**Date:** 2026-04-05
**Sprint:** 37.2
**Status:** Done
**Category:** Performance

### Problem
FractalTaskEngine's `_maybe_reflect()` invokes an LLM call (~30s) even for trivial
plans with a single node that already succeeded. For simple "2+2"-class tasks that
bypass fractal planning (TD-167), the plan often has just 1 node. The reflection
call adds latency with no value — there are no failed nodes to reassess, no
multi-node interactions to reconsider.

### Solution: Opt-in Reflection Skip
Added `skip_reflection_for_single_success: bool = False` constructor parameter to
`FractalTaskEngine`. When enabled, `_maybe_reflect()` returns `[]` immediately if:
1. Exactly 1 completed node
2. That node has `SubTaskStatus.SUCCESS`
3. It's the first reflection round (`plan.reflection_rounds == 0`)

This saves one full LLM call (~30s) per single-node plan execution.

### Files
| File | Change |
|------|--------|
| `infrastructure/fractal/fractal_engine.py` | +19 lines — skip condition in `_maybe_reflect()` |
| `interface/api/container.py` | +1 line — enable flag in production |
| `tests/unit/infrastructure/test_fractal_engine.py` | +3 tests in `TestReflectionSkip` |

### Tests
- 3,031 unit tests passing, 0 failures, lint clean

---

## TD-172: Live E2E Round 18 — Performance Optimization Validation

**Date:** 2026-04-05
**Sprint:** 38
**Status:** Done
**Category:** Verification

### Objective
Validate 4 performance optimizations (TD-167, TD-168, TD-169, TD-171) in live E2E.

### Results

| Task | Classification | Subtasks | Engine | Cost | Time | Optimizations Fired |
|------|---------------|----------|--------|------|------|---------------------|
| "What is 2 + 2?" | SIMPLE | 1 | ollama | $0.00 | <5s | TD-167 bypass, TD-168 gate2 skip, TD-171 reflection skip |
| "List three advantages of Python for web development" | SIMPLE | 1 | ollama | $0.00 | <10s | TD-167 bypass, TD-168 gate2 skip, TD-171 reflection skip |

### Key Findings
- **SIMPLE bypass (TD-167)**: Both tasks correctly classified as SIMPLE, single-node direct execution
- **Gate 2 skip (TD-168)**: Successful terminal nodes skip result evaluation LLM call
- **Reflection skip (TD-171)**: Single-node successful plans skip reflection LLM call
- **Parallel node execution (TD-169)**: Not triggered (1-node plans), covered by unit tests
- **End-to-end latency**: <5-10s for SIMPLE tasks (previous: ~4.5 minutes)
- **Total cost**: $0.00 (Ollama local execution)

### Test count after TD-172
3,031 unit tests + 148 integration, 0 failures, lint clean.

---

## TD-173: Planner Candidate Caching for Repeat Goals

**Date:** 2026-04-05
**Sprint:** 38.1
**Status:** Done
**Category:** Performance

### Problem
When the same goal is submitted multiple times (retries, benchmarking, testing),
`_generate_approved_plan` calls `planner.generate_candidates()` each time — an LLM
call costing ~15-30s. The planner output for identical goals at the same nesting
level is deterministic enough to cache.

### Solution: In-Memory Planner Cache
Added `cache_planner_candidates: bool = False` constructor parameter. When enabled:
- Cache key: `f"{goal}::{nesting_level}"`
- Only caches on first attempt (no feedback from Gate 1 rejection)
- Deep-copies candidates on both store and retrieve to prevent mutation leakage
- In-memory dict (session-scoped, no persistence)

### Files
| File | Change |
|------|--------|
| `infrastructure/fractal/fractal_engine.py` | +import copy, +cache dict, +cache logic in `_generate_approved_plan` |
| `interface/api/container.py` | +1 line — enable flag in production |
| `tests/unit/infrastructure/test_fractal_engine.py` | +4 tests in `TestPlannerCache` |

### Tests
- 3,035 unit tests passing, 0 failures, lint clean

---

## TD-174: Fractal Child Node Visibility + Final Answer Display

**Date:** 2026-04-05
**Sprint:** 38.2
**Status:** Done
**Category:** UX / Architecture

### Problem
Three UX gaps observed during live E2E fractal execution:

1. **React Flow graph static** — fractal decomposition creates child nodes via
   `_execute_expandable`, but they weren't added to `task.subtasks` or broadcast
   via SSE. The graph showed only the initial plan nodes.
2. **No Final Answer** — completed tasks concatenated all subtask results. No
   dedicated `final_answer` field for a consolidated response.
3. **No progress_pct from API** — computed only client-side in useTaskStream.

### Solution

**A. Fractal child node visibility:**
- `_execute_expandable()` now adds child plan nodes to `task.subtasks` with
  `dependencies=[parent_node.id]` before executing the sub-plan
- Emits `node_spawned` SSE events with `spawned_by="expansion"` and `parent_id`
- `useTaskStream.ts` reads `parent_id` from event to set `dependencies`
- React Flow graph dynamically grows as fractal tree expands

**B. Final Answer:**
- Added `final_answer: str | None` to `TaskEntity`, `TaskModel`, `TaskResponse`
- Fractal engine sets `final_answer` from successful node results on completion
- Bypass path sets `final_answer` from the single successful subtask
- `PgTaskRepository` persists/restores `final_answer`
- DB migration: `ALTER TABLE tasks ADD COLUMN final_answer TEXT`
- TaskDetail UI shows prominent green-bordered "Final Answer" section

**C. Progress percentage:**
- `TaskResponse.from_task()` computes `progress_pct` server-side

### Files
| File | Change |
|------|--------|
| `domain/entities/task.py` | +`final_answer` field |
| `infrastructure/fractal/fractal_engine.py` | +child node exposure, +final_answer |
| `infrastructure/persistence/models.py` | +`final_answer` column |
| `infrastructure/persistence/pg_task_repository.py` | +final_answer in to_model/to_entity/update |
| `interface/api/schemas.py` | +`progress_pct`, +`final_answer` |
| `ui/components/TaskDetail.tsx` | Redesigned Final Output → Final Answer |
| `ui/lib/useTaskStream.ts` | +`parent_id` → dependencies for node_spawned |

### Tests
- 3,035 unit tests passing, 0 failures, lint clean

---

## TD-175: Fractal Concurrency Throttle — Semaphore + Delay + Per-Task Overrides

**Date:** 2026-04-06
**Sprint:** 39.1
**Status:** Done
**Category:** Performance / API

### Problem
Complex fractal tasks spawn many parallel LLM calls simultaneously via
`asyncio.gather`, causing CPU spikes. Users reported high CPU load during
deep fractal execution. No mechanism existed to control concurrency or
smooth out CPU load.

### Solution

**A. Semaphore-based concurrency limit (`max_concurrent_nodes`):**
- `asyncio.Semaphore` wraps `_execute_with_eval()` inside `_execute_node_safe()`
- Default `3` (set in `shared/config.py`), `0` = unlimited
- Throttle delay placed INSIDE semaphore context so the next node waits
- Per-execution state: semaphore created in `execute()`, cleaned up in `finally`

**B. Throttle delay (`throttle_delay_ms`):**
- `asyncio.sleep(delay / 1000)` after each node completes
- Inside semaphore context for parallel mode → delays stack properly
- Default `0` (no delay). Use 50-500ms to smooth CPU spikes

**C. Per-task overrides via API:**
- `CreateTaskRequest` adds optional `fractal_max_depth`, `fractal_max_concurrent_nodes`,
  `fractal_throttle_delay_ms` fields
- `FractalTaskEngine.set_execution_overrides()` stores pending overrides
- `_apply_execution_overrides()` consumes them at start of `execute()`, sets
  per-execution semaphore, delay, and depth
- Overrides are consumed (not leaked to next task)

**D. Dynamic depth override:**
- `_execute_with_eval()` uses `self._exec_max_depth` instead of `self._max_depth`
- Per-task `max_depth=1` forces all nodes terminal → flat decomposition only

### Impact table

| Setting | Max Nodes | Concurrent | CPU Load |
|---------|-----------|------------|----------|
| Default (depth=3, conc=3) | 20 | 3 | **Medium** |
| depth=2, conc=2 | 12 | 2 | Low |
| depth=1, conc=1 | 3 | 1 | **Minimal** |

### Files
| File | Change |
|------|--------|
| `shared/config.py` | +`fractal_max_concurrent_nodes`, +`fractal_throttle_delay_ms` |
| `infrastructure/fractal/fractal_engine.py` | +semaphore, +delay, +overrides, +_exec_max_depth |
| `interface/api/schemas.py` | +3 optional fields on CreateTaskRequest |
| `interface/api/routes/tasks.py` | +override collection, threading through execution chain |
| `interface/api/container.py` | +wiring from settings |

### Tests
- 6 new tests in `TestConcurrencyThrottle`: semaphore limit, unlimited, delay timing,
  per-task overrides, consumption, depth override
- 3,041 unit tests passing, 0 failures, lint clean

---

## TD-176: Goal Grounding — Planner Entity Preservation

**Date**: 2026-04-12
**Status**: Accepted
**Sprint**: 39.2

### Problem
Fractal Planner abstracts away specific entities when decomposing goals.
"氷川神社の歴史を調べスライドにして" → "Search for information" loses the topic.
The inner engine then calls `web_search(query="検索キーワード")` — searching
for the concept "search keyword" rather than the actual entity.

### Decision
Three prompt-level changes (zero logic changes):

A. **Planner system prompt**: Added entity-preservation rules with BAD/GOOD examples.
   Node descriptions MUST preserve specific entities, proper nouns, and search terms.
B. **NodeExecutor._build_task**: Changed goal format from `[Subtask of: {goal}]`
   to `[Original goal: {goal}] Current step: {node.description}` — the full goal
   remains visible to the inner engine.
C. **TOOL_USAGE_INSTRUCTION**: Added explicit prohibition of generic search terms
   and file-creation mandate when task requires FILE output.

### Files
| File | Change |
|------|--------|
| `infrastructure/fractal/llm_planner.py` | +6 lines in _SYSTEM_PROMPT |
| `infrastructure/fractal/node_executor.py` | goal format in _build_task |
| `infrastructure/task_graph/engine.py` | +7 lines in TOOL_USAGE_INSTRUCTION |

### Tests
10 new tests in `test_goal_grounding.py`

---

## TD-177: Output-Aware Evaluation — Gate ② Extension

**Date**: 2026-04-12
**Status**: Accepted
**Sprint**: 39.2

### Problem
Gate ② evaluates text quality only. A task that requires file creation
("create slides") scores 86% SUCCESS when only descriptive text is generated
without any actual file being created.

### Decision
A. **OutputRequirement VO**: `TEXT | FILE_ARTIFACT | CODE_ARTIFACT | DATA_ARTIFACT`
B. **OutputRequirementClassifier**: LLM-based classification of goal output type
   (no regex — per user's feedback_no_rulebased constraint).
C. **Gate ② prompt extension**: When `output_requirement` is FILE/CODE/DATA,
   user message includes specific evaluation criteria (e.g. "was fs_write called?").
D. **PlanNode propagation**: FractalTaskEngine classifies the top-level goal and
   propagates `output_requirement` to terminal visible nodes before execution.

### Files
| File | Change |
|------|--------|
| `domain/value_objects/output_requirement.py` | **NEW** — 4-value enum |
| `domain/services/output_requirement_classifier.py` | **NEW** — LLM classifier |
| `domain/entities/fractal_engine.py` | +output_requirement field on PlanNode |
| `infrastructure/fractal/llm_result_evaluator.py` | output-aware _build_messages |
| `infrastructure/fractal/fractal_engine.py` | classify + propagate in execute() |
| `interface/api/container.py` | wire OutputRequirementClassifier |

### Tests
23 new tests: 15 in `test_output_requirement.py`, 8 in `test_output_aware_evaluation.py`

---

## TD-178: Skill Acquisition Loop — Discover → Install → Retry

**Date**: 2026-04-12
**Status**: Accepted
**Sprint**: 39.2

### Problem
`_safe_suggest_tools()` was fire-and-forget: discovered tools were logged but
never installed or retried. A task needing `python-pptx` would discover it
in the registry, log the suggestion, and terminate as FAILED.

### Decision
Replaced fire-and-forget with a closed loop:
1. On failure, `_try_acquire_skills()` calls `DiscoverToolsUseCase`
2. Filters to safe candidates only (>= COMMUNITY safety tier)
3. Installs best candidate via `InstallToolUseCase`
4. If installed successfully AND `max_skill_retries > 0`, re-executes task once

Safety constraints:
- Maximum 1 retry (prevents infinite loops)
- Only COMMUNITY or VERIFIED tools installed automatically
- All failures handled gracefully (exception → return False)

### Files
| File | Change |
|------|--------|
| `application/use_cases/execute_task.py` | +_try_acquire_skills, retry loop |
| `interface/api/container.py` | wire install_tool into ExecuteTaskUseCase |
| `infrastructure/local_execution/tools/__init__.py` | +register_tool() |

### Tests
9 new tests in `test_skill_acquisition.py`

---

## TD-179: Artifact Pipeline — File Tracking + API/UI Surface

**Date**: 2026-04-12
**Status**: Accepted
**Sprint**: 39.2

### Problem
Files created by `fs_write` during execution were invisible. No tracking,
no display in API response, no UI indication.

### Decision
A. **AuditLog.get_produced_files()**: Extracts file paths from successful
   `fs_write` entries in the JSONL audit log. Supports `since` filter and dedup.
B. **TaskEntity.artifact_paths**: New `list[str]` field for produced file paths.
C. **TaskResponse.artifact_paths**: Surfaced in API response JSON.

### Files
| File | Change |
|------|--------|
| `infrastructure/local_execution/audit_log.py` | +get_produced_files() |
| `domain/entities/task.py` | +artifact_paths field |
| `interface/api/schemas.py` | +artifact_paths in TaskResponse |

### Tests
13 new tests in `test_artifact_pipeline.py`

---

## TD-180: Zombie Task Prevention — Repetitive Loop Detection + Status Guarantees

**Date**: 2026-04-13
**Status**: Accepted
**Sprint**: 39.3

### Problem
A task ("氷川神社の歴史を調べ、スライドにして") ran for 14+ hours stuck in "running"
status. Root cause analysis revealed three design defects:

1. **Repetitive tool loop**: LLM called `system_notify` with identical args 170+ times.
   ReAct's `max_iterations=10` stopped the loop eventually, but wasted 9/10 iterations
   on a single repeated notification.
2. **Unconditional SUCCESS**: `LangGraphTaskEngine` marked subtasks as `SUCCESS`
   regardless of `terminated_reason` — even when ReAct hit `max_iterations`.
3. **Missing catch-all**: `FractalTaskEngine._execute_node_safe` only caught
   `_PlanFailureError`. Any other exception left the node in `RUNNING` forever.

### Decision
A. **Repetitive tool-call detection** in `ReactExecutor`: Track last tool+args
   signature. If the same signature repeats 3 times consecutively, terminate with
   `terminated_reason="repetitive_tool_loop"`. Multi-tool steps reset the counter.
B. **Failed on incomplete execution**: `LangGraphTaskEngine` now checks
   `terminated_reason`. If `"max_iterations"` or `"repetitive_tool_loop"`, subtask
   status is set to `FAILED` instead of `SUCCESS`.
C. **Catch-all exception handler**: `_execute_node_safe` now catches `Exception`
   (not just `_PlanFailureError`) and marks the node `FAILED` with error message.
D. **New Literal value**: `ReactTrace.terminated_reason` extended with
   `"repetitive_tool_loop"`.

### Files
| File | Change |
|------|--------|
| `domain/entities/react_trace.py` | +`"repetitive_tool_loop"` Literal |
| `infrastructure/task_graph/react_executor.py` | +repetitive loop detection |
| `infrastructure/task_graph/engine.py` | +max_iterations/loop → FAILED |
| `infrastructure/fractal/fractal_engine.py` | +catch-all in _execute_node_safe |

### Tests
8 new tests: 3 in `test_react_executor.py` (loop detection), 5 in
`test_zombie_task_prevention.py` (status guarantees). 3 existing tests updated
to use varying args (avoid false positive loop detection).

---

## TD-181: Hard Time-Based Timeout + Live E2E Round 19 Results

**Date**: 2026-04-13
**Status**: Accepted
**Sprint**: 39.4

### Problem
Round 19 E2E test ("氷川神社の歴史を調べ、スライドにして") exposed that TD-180's
cooperative zombie prevention (repetitive loop detection, catch-all handler) is
**insufficient** because:

1. **No time-based timeout**: `_execute_plan` while-loop and `_execute_with_eval`
   retry-loop rely on iteration/cost limits but have no wall-clock limit. With
   max_depth=3 × max_retries=3 × reflection_rounds=2, worst-case execution
   can exceed 300s.
2. **Cooperative checks unreachable**: The `_is_timed_out()` check at the top of
   `while pending:` is never reached when execution is blocked inside
   `_node_executor.execute_terminal()` → inner_engine.execute() → LLM call.
3. **Bypass over-classification**: "スライドにして" (create slides) was classified
   as SIMPLE by bypass classifier, returning text-only answer without file output.

### Round 19 E2E Results (FAIL — 1/7 checkpoints)

| # | Check | Result | Detail |
|---|-------|--------|--------|
| 1 | Goal Grounding | PARTIAL | No web_search; browser_navigate to wrong URL |
| 2 | Output classification | UNTESTED | Bypassed or stuck before Gate ② |
| 3 | Gate ② enforcement | UNTESTED | Same |
| 4 | File generation | FAIL | 78-byte fake PPTX (text content) |
| 5 | Zombie prevention | FAIL | 300s+ timeout, all subtasks RUNNING |
| 6 | Artifact tracking | FAIL | artifact_paths empty |
| 7 | Time & cost | FAIL | >300s |

Audit log from first run: 16 tool calls — `fs_write` (fake PPTX), `browser_navigate`
(Playwright missing), `browser_pdf` (failed), `system_notify` ×12 (spam across subtasks).

### Decision
A. **`asyncio.wait_for` hard timeout**: Wrap `_execute_plan()` call in
   `asyncio.wait_for(timeout=max_execution_seconds)`. This provides a true async
   cancellation that works even when inner engine hangs on LLM calls.
B. **Cooperative timeout checks retained**: `_is_timed_out()` in `_execute_plan`
   while-loop and `_execute_with_eval` retry-loop for graceful shutdown when
   control passes through those points.
C. **Remaining RUNNING cleanup**: After timeout or normal completion, iterate
   `task.subtasks` and mark any still-RUNNING/PENDING as FAILED.
D. **New config**: `fractal_max_execution_seconds` (default 180s) in settings.
E. **Reflection blocked after timeout**: `_maybe_reflect` returns [] immediately
   if `_is_timed_out()`.

### Architectural issues identified (not fixed in this TD)
- **Bypass classifier too aggressive**: "スライドにして" classified as SIMPLE.
  Needs output-requirement awareness in bypass decision.
- **No agent engine delegation**: Content creation tasks (slides, infographics)
  should route to Claude Code / Gemini CLI, not local LAEE tools + qwen3:8b.
- **Playwright not installed**: All browser_* tools fail silently.

### Files
| File | Change |
|------|--------|
| `infrastructure/fractal/fractal_engine.py` | +`asyncio.wait_for` timeout, +`_is_timed_out()`, +RUNNING cleanup |
| `shared/config.py` | +`fractal_max_execution_seconds` |
| `interface/api/container.py` | Wire new param |
| `tests/unit/infrastructure/test_fractal_engine.py` | +4 timeout tests |
| `tests/unit/interface/test_fractal_container_wiring.py` | +fake setting |

### Tests
4 new tests in `TestExecutionTimeout`: `_is_timed_out` true/false, timeout marks
task FAILED, disabled timeout (0). Total: 3114 pass, 0 fail.


---

## TD-182: StrategyRepository Port — Application-to-Infrastructure Decoupling

**Date**: 2026-04-22
**Status**: Accepted
**Sprint**: 83 (post-v0.5.2 SDD pilot)
**Spec**: [`specs/strategy-store-port/`](../specs/strategy-store-port/)

### Problem
`application/use_cases/update_strategy.py` imported the concrete
`infrastructure.evolution.StrategyStore` directly, violating constitution
principle 2 (Clean Architecture: application depends only on domain).

Discovered during the constitution-check audit that followed the CLAUDE.md
restructure. Single rg hit, but the rule is non-negotiable.

### Decision
Extract `StrategyRepository` ABC in `domain/ports/`, mirroring the existing
7-method surface of `StrategyStore` 1:1 (sync; matches the file-based impl):

- `load_recovery_rules / save_recovery_rules / append_recovery_rule`
- `load_model_preferences / save_model_preferences`
- `load_engine_preferences / save_engine_preferences`

`StrategyStore` inherits the ABC; `UpdateStrategyUseCase.__init__` widens its
`strategy_store` parameter to `StrategyRepository`. Caller kwarg name preserved
to avoid touching DI sites in `interface/api/container.py`.

### Why sync (not async)
The concrete `StrategyStore` is sync (JSONL read/write). Forcing async at the
port would either (a) require all callers to `await` for no I/O benefit, or
(b) wrap sync calls in `run_in_executor` — both are noise. Future async impls
(if any) can be introduced via a separate `AsyncStrategyRepository` ABC.

### Test strategy
Parametrised contract test (`tests/unit/domain/test_strategy_repository_contract.py`)
runs 8 behavioural cases against both `InMemoryStrategyRepository` (test fake)
and `StrategyStore` (file-backed) — proves Liskov substitutability.
`UpdateStrategyUseCase` unit tests now use the in-memory fake (faster, hermetic).

### SDD process
First feature shipped via the new spec→plan→tasks workflow. spec.md (215L,
12 FRs, 5 clarifications resolved), plan.md (316L, layer map + 5-commit series),
tasks.md (24 atomic tasks, ~145min serial). Constitution-check: PASS.

### Files
| File | Change |
|------|--------|
| `domain/ports/strategy_repository.py` | NEW (39 lines) |
| `domain/ports/__init__.py` | re-export |
| `infrastructure/evolution/strategy_store.py` | inherit ABC |
| `application/use_cases/update_strategy.py` | widen ctor type |
| `tests/unit/domain/test_strategy_repository_contract.py` | NEW (16 tests) |
| `tests/unit/application/_fakes/in_memory_strategy_repository.py` | NEW |
| `tests/unit/application/test_update_strategy.py` | swap concrete → fake |
| `tests/unit/infrastructure/test_strategy_store.py` | +isinstance assertion |

### Tests
3,131 unit pass, 15 integration (evolution_pipeline) pass, ruff clean on
touched files. 0 regressions.

### Out of scope
Two `TYPE_CHECKING`-only imports remain (`manage_ollama.py`, `route_to_engine.py`).
No runtime dep but architecturally still owed; addressed in separate sprints.


---

## TD-183: OllamaManagerPort — Application-to-Infrastructure Decoupling

**Date**: 2026-04-23
**Status**: Accepted
**Sprint**: 84 (port-extraction follow-up #1)

### Problem
`application/use_cases/manage_ollama.py` had a TYPE_CHECKING-only import of
`infrastructure.llm.OllamaManager`. No runtime dep, but architecturally a
constitution principle 2 violation — the application layer named a concrete
infra class in its type signature.

### Decision
Extract `OllamaManagerPort` ABC in `domain/ports/` with the 6 async methods
that `ManageOllamaUseCase` actually calls:

- `is_running / list_models / pull_model / delete_model / model_info / get_running_models`

Pure-function helper `OllamaManager.get_recommended_model` (RAM-based
recommendation) excluded — callers import it directly from the impl when they
need it.

`OllamaManager` now inherits the ABC. `ManageOllamaUseCase.__init__` widened
to accept `OllamaManagerPort`. Existing `AsyncMock`-based tests upgraded to
`AsyncMock(spec=OllamaManagerPort)` so the port is enforced at mock setup.

### Why exclude `ensure_model`
Concrete impl exposes `ensure_model = list + pull` for caller convenience. Not
in the UseCase surface, so kept out of the ABC. Future callers can either use
the concrete impl or compose `list_models + pull_model` themselves.

### Files
| File | Change |
|------|--------|
| `domain/ports/ollama_manager.py` | NEW (32 lines) |
| `domain/ports/__init__.py` | re-export |
| `infrastructure/llm/ollama_manager.py` | inherit ABC |
| `application/use_cases/manage_ollama.py` | widen ctor type, drop TYPE_CHECKING import |
| `tests/unit/application/_fakes/in_memory_ollama_manager.py` | NEW |
| `tests/unit/domain/test_ollama_manager_port_contract.py` | NEW (10 tests) |
| `tests/unit/application/test_manage_ollama.py` | AsyncMock(spec=Port) |
| `tests/unit/infrastructure/test_ollama_manager.py` | +isinstance assertion |

### Tests
3,142 unit pass (+11 new), touched files ruff clean. Zero regressions.


---

## TD-184: EngineCostRecorderPort — Last application→infrastructure import eliminated

**Date**: 2026-04-23
**Status**: Accepted
**Sprint**: 84 (port-extraction follow-up #2)

### Problem
`application/use_cases/route_to_engine.py` had a TYPE_CHECKING-only import of
`infrastructure.llm.CostTracker` for the `cost_tracker` parameter type. Same
shape as TD-183: no runtime dep, but principle 2 violation in the type
signature.

### Decision
Extract a **narrow** port `EngineCostRecorderPort` in `domain/ports/` with a
single async method:

```python
async def record_engine_result(self, result: AgentEngineResult) -> None
```

Why narrow rather than mirroring `CostTracker`'s 6-method surface: the only
caller in the application layer is `RouteToEngineUseCase._record_engine_cost`,
which uses exactly this one method. Aggregation/query helpers (`get_daily_total`,
`get_monthly_total`, `get_local_usage_rate`, `check_budget`, `record`) stay on
the concrete `CostTracker`. If a future application-layer caller needs reads,
add a separate read-side port — don't fatten this one.

`CostTracker` inherits the ABC; `RouteToEngineUseCase.__init__` widened.

### Net result
**`from infrastructure` import count in `application/`: 0**

Two TYPE_CHECKING imports eliminated across TD-183 + TD-184. The application
layer is now fully decoupled from infrastructure at every type signature.

### Files
| File | Change |
|------|--------|
| `domain/ports/engine_cost_recorder.py` | NEW (22 lines) |
| `domain/ports/__init__.py` | re-export |
| `infrastructure/llm/cost_tracker.py` | inherit ABC |
| `application/use_cases/route_to_engine.py` | widen ctor, drop TYPE_CHECKING import |
| `tests/unit/application/_fakes/in_memory_engine_cost_recorder.py` | NEW |
| `tests/unit/domain/test_engine_cost_recorder_port_contract.py` | NEW (3 tests) |
| `tests/unit/infrastructure/test_cost_tracker.py` | +isinstance assertion |

### Tests
3,146 unit pass (+4 new this ADR), zero regressions.


---

## TD-185: Pre-existing ruff debt cleanup

**Date**: 2026-04-23
**Status**: Accepted
**Sprint**: 84 (port-extraction follow-up #3 / housekeeping)

### Problem
The full `ruff check .` reported 10 pre-existing errors that surfaced during
the TD-182…TD-184 work. All in test files, none blocking, but the
constitution requires the lint gate to be green for new work.

### Errors fixed
- `tests/unit/application/test_skill_acquisition.py`
  - F401: unused `unittest.mock.patch` import → removed
  - F841 ×7: `result = await uc.execute(...)` where `result` is never used
    → renamed to `_result` (ruff dummy-variable convention). Two call sites
    that *do* read `result.status` kept the original name.
- `tests/unit/infrastructure/test_artifact_pipeline.py`
  - F401: unused `tempfile` import → removed
  - I001: import block ordering → `ruff check --fix` (safe fix)

### Net result
`ruff check .` exit 0, full unit suite 3,146/3,146 pass. The lint gate is
green again — TD-186+ can land without inheriting noise.

### Rationale for `_result` over deletion
Some sites have the comment `# Should not raise` — the assignment documents
that the call is being made *for its side effect of not raising*, not for the
return value. `_result = ` keeps that intent visible to readers; bare
`await uc.execute(...)` would lose it.


---

## TD-186: Domain layer purity audit + numpy carve-out

**Date**: 2026-04-23
**Status**: Accepted (constitution amendment)
**Sprint**: 84 (port-extraction follow-up #4 / governance)

### Problem
Constitution principle 2 reads "domain has zero framework deps (stdlib +
Pydantic only)". A repo-wide audit found exactly one external import in
`domain/`: `numpy` in `domain/services/semantic_fingerprint.py` (LSH +
cosine similarity, no I/O, no state).

Strict reading would force a port; pragmatic reading recognizes numpy as
a pure-math primitive in the same category as `math` / `datetime`.

### Decision
Constitution amendment: explicitly allow `numpy` (and document the
process for future additions). Pure-math libs are now an enumerated
allow-list, not an open category.

### Changes
- `.specify/memory/constitution.md` principle 2: append "+ pure-math libs",
  list `numpy` explicitly, add explicit ban on `from infrastructure/...` in
  `domain/` including TYPE_CHECKING.
- `.claude/rules/clean-architecture.md`: same wording + extended
  verification recipe (3 greps, all expected to return empty).

### Audit baseline (2026-04-23)
| Check | Result |
|---|---|
| `from infrastructure` in `domain/` | 0 hits |
| `from application` in `domain/` | 0 hits |
| `from interface` in `domain/` | 0 hits |
| `from infrastructure` in `application/` | 0 hits (since TD-184) |
| External libs in `domain/` | `pydantic`, `numpy` only |

The architecture is **provably** clean from the dependency-rule angle.
Future PRs can re-run the 3 greps as a 5-second gate.

### Why not port `numpy` behind an ABC
Pure mathematical operations have no semantic boundary worth abstracting.
A `VectorOpsPort` would be a dumb pass-through with one caller; the cost
is real (extra layer to read), the benefit is zero (no second impl will
ever exist that doesn't reduce to BLAS underneath).


---

## TD-187: Test-code port-borrowing policy

**Date**: 2026-04-23
**Status**: Accepted (test-policy clarification)
**Sprint**: 84 (port-extraction follow-up #5 / governance)

### Problem
TD-186 left the 3-grep dependency audit clean for production code:

| Check | Result |
|---|---|
| `from infrastructure` in `domain/` | 0 hits |
| `from infrastructure` in `application/` | 0 hits |

But a follow-up grep on `tests/unit/application/` found **8 files** that
still import from `infrastructure/`:

```
tests/unit/application/test_update_strategy.py        → InMemoryExecutionRecordRepository
tests/unit/application/test_interactive_plan.py       → InMemoryPlan/TaskRepository
tests/unit/application/test_systemic_evolution.py     → InMemoryExecutionRecordRepository
tests/unit/application/test_a2a_use_cases.py          → InMemoryAgentRegistry, InMemoryA2ABroker
tests/unit/application/test_background_planner.py     → InMemoryTaskRepository
tests/unit/application/test_evolve_prompts.py         → InMemoryPromptTemplateRepo
tests/unit/application/test_analyze_execution.py      → InMemoryExecutionRecordRepository
```

Question: are these constitution principle 2 violations that need fakes
moved to `tests/unit/application/_fakes/`?

### Decision
**No. This is an accepted pattern.** Document the rule explicitly so the
audit grep doesn't get re-flagged in future reviews.

**Policy**: Test code MAY import port-compliant `InMemory*` adapters from
`infrastructure/` and inject them into use cases via port-typed
constructor parameters. The dependency rule applies to **production
source flow** (`application/use_cases/*.py`, `domain/**/*.py`), not to
test wiring code.

### Rationale

1. **The adapters are production code, not test fixtures.** Every
   `InMemory*` adapter listed above is the **default DI backend** in
   `interface/api/container.py` for local-dev mode (no PG / Redis
   required). Each one inherits from a port ABC and ships in the
   distribution.

2. **The use case never sees the concrete type.** `UpdateStrategyUseCase`
   takes `StrategyRepository` (the ABC); the test injects an InMemory
   impl, exactly as the production DI container would inject `StrategyStore`.
   Replacing the InMemory adapter with a hand-rolled `tests/_fakes/`
   class would be **duplication**, not isolation.

3. **The constitution targets dependency direction, not import location.**
   Principle 2 says "Dependencies flow inward". The production import
   graph already does. Tests are the assembly root for `application/` —
   they wire concrete impls to abstract ports, just like
   `interface/api/container.py` does for the running server.

4. **The TD-182 SDD pilot used a `_fakes/` directory.** That's still
   appropriate when the InMemory impl is owned by tests (e.g.
   `InMemoryStrategyRepository` exists only because the production
   `StrategyStore` is filesystem-backed and unsuitable for unit tests).
   When a production InMemory adapter already exists and is port-
   compliant, prefer reuse.

### Decision matrix (when to write a `_fakes/` impl vs. borrow from `infrastructure/`)

| Situation | Choice |
|---|---|
| Production InMemory adapter exists and is port-compliant | **Borrow** from `infrastructure/` |
| Production adapter is filesystem/network-backed only | **Write** in `tests/unit/<layer>/_fakes/` |
| Test needs to assert on internal state (e.g. `fake.records`) | **Write** a fake — production adapters shouldn't expose internals |
| Multiple use cases share the same fake | Either is fine; prefer `infrastructure/` if the fake is also useful at runtime |

### Constitution amendment
Append to principle 2 (`.specify/memory/constitution.md`):

> Test code MAY import port-compliant `InMemory*` adapters from
> `infrastructure/` for DI wiring (see TD-187). The dependency rule
> targets production source flow, not test assembly.

### Updated audit recipe (`.claude/rules/clean-architecture.md`)

```bash
# Production-source check (must return empty)
rg -l "from infrastructure" application/ --glob '!tests/**'

# Test-code is exempt — InMemory port adapters may be borrowed
rg -l "from infrastructure" tests/unit/application/  # informational only
```

### Net effect
The 5-second gate (3 production greps) remains the contract. The
test-code import is reclassified from "audit finding" to "documented
DI wiring pattern". Zero file moves, zero test changes.
