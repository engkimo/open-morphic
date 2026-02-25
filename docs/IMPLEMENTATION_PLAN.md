# Morphic-Agent Implementation Plan

> Master implementation plan — 7 phases, 14 weeks
> Phase 1 has sprint-level detail. Phases 2-7 have week-level plans.

---

## Design Principles (All Phases)

```
1. Prove $0 operation first (LOCAL_FIRST)
2. Default independent tasks to parallel (DEFAULT TO PARALLEL)
3. Embed Context Engineering (Manus 5 principles) from Phase 1
4. Guarantee behavior with E2E tests at each phase end
5. "If you declare it, execute it" — no stubs without follow-through
6. OSS-First: use established libraries, custom code only for domain logic
7. CLI + API: both are first-class interfaces calling the same use cases
```

---

## Dependency Graph

```
[Infrastructure]
  PostgreSQL+pgvector, Redis, Neo4j, Docker Compose
       │
       ▼
[LLM Layer]  ←── Phase 1 top priority
  Ollama Manager → LiteLLM Router → Cost Tracker
       │
       ▼
[Task Graph Engine]  ←── Phase 1 core
  LangGraph DAG → Scheduler → Parallel Execution
       │
       ├──────────────────────┐
       ▼                      ▼
[Context Engineering]    [Semantic Memory]
  KV-Cache Optimizer      mem0 + pgvector
  Tool State Machine      Neo4j Knowledge Graph
  todo.md Manager         Context Zipper (simple)
  Observation Diversifier
       │                      │
       └──────────┬───────────┘
                  ▼
[API + CLI Layer]  FastAPI + WebSocket + typer
                  │
                  ▼
[UI Layer]   Next.js 15 + Shadcn/ui
                  │
                  ▼
         *** Phase 1 Complete ***
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼
[Phase 2]    [Phase 3]   [Phase 4]
Parallel &   Memory &    Agent CLI
Planning     Context     Orchestration
+ CLI v1
       │          │          │
       └──────────┼──────────┘
                  ▼
       ┌──────────┼──────────┐
       ▼          ▼          ▼
[Phase 5]    [Phase 6]   [Phase 7]
Marketplace  Evolution   A2A & Scale
```

---

## Phase 1: Foundation (Week 1-2)

> **Goal**: Complete a minimal agent loop that runs at $0 with Ollama
> **Deliverable**: User inputs a goal → DAG generated → Ollama executes → results displayed + cost $0

### Sprint 1.1: Infrastructure (Day 1-2)

**Goal**: All infrastructure starts with `docker compose up -d`, DB schema complete

#### Files to Create

```
pyproject.toml                          # uv project definition
docker-compose.yml                      # PostgreSQL+pgvector, Redis, Neo4j
.env.example                            # Environment variable template
alembic.ini                             # DB migration config
domain/                                 # Clean Architecture Layer 1
infrastructure/persistence/database.py  # SQLAlchemy async engine + pgvector
infrastructure/persistence/models.py    # ORM models
shared/config.py                        # pydantic-settings config
migrations/env.py                       # Alembic async environment
```

#### Docker Compose Services

```yaml
services:
  postgres:
    image: pgvector/pgvector:pg16        # pgvector extension pre-installed
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    # Queue only. No persistence needed (Phase 1)

  neo4j:
    image: neo4j:5-community
    ports: ["7474:7474", "7687:7687"]    # Browser + Bolt
    volumes: [neo4jdata:/data]
```

#### DB Schema (PostgreSQL)

```sql
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    goal TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    parent_id UUID REFERENCES tasks(id),
    depth INT DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE task_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES tasks(id) NOT NULL,
    model_used VARCHAR(100) NOT NULL,
    prompt_tokens INT,
    completion_tokens INT,
    cost_usd DECIMAL(10,6) DEFAULT 0,
    latency_ms INT,
    result TEXT,
    error TEXT,
    cache_hit BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    embedding vector(1536),               -- pgvector
    memory_type VARCHAR(20) NOT NULL,
    access_count INT DEFAULT 1,
    importance_score FLOAT DEFAULT 0.5,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    last_accessed TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX ON memories
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE TABLE cost_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model VARCHAR(100) NOT NULL,
    prompt_tokens INT DEFAULT 0,
    completion_tokens INT DEFAULT 0,
    cost_usd DECIMAL(10,6) DEFAULT 0,
    cached_tokens INT DEFAULT 0,
    is_local BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

#### Neo4j Schema (L3 Knowledge Graph)

```cypher
CREATE CONSTRAINT entity_name IF NOT EXISTS
  FOR (e:Entity) REQUIRE e.name IS UNIQUE;
-- Phase 1 uses dynamic labels for flexibility
```

#### Completion Criteria

- [ ] `docker compose up -d` starts all 3 services
- [ ] `alembic upgrade head` creates schema successfully
- [ ] pgvector `vector` type insert + search test passes
- [ ] Neo4j Cypher query node create + search test passes
- [ ] `shared/config.py` loads `.env` + pydantic validation

---

### Sprint 1.2: LLM Layer (Day 3-4)

**Goal**: Local inference with Ollama at $0, cost tracking functional

#### Files to Create

```
infrastructure/llm/__init__.py
infrastructure/llm/router.py              # MultiLLMRouter (LiteLLM integration)
infrastructure/llm/ollama_manager.py       # OllamaManager
infrastructure/llm/cost_tracker.py         # CostTracker (callback-based)
tests/unit/infrastructure/test_llm_router.py
tests/unit/infrastructure/test_ollama_manager.py
```

#### OllamaManager Spec

```python
class OllamaManager:
    """Ollama lifecycle management"""
    base_url: str = "http://127.0.0.1:11434"

    async def is_running(self) -> bool:
        """Health check via GET /api/tags"""

    async def list_models(self) -> list[str]:
        """List installed models"""

    async def pull_model(self, model: str) -> None:
        """Pull model via POST /api/pull"""

    async def ensure_model(self, model: str) -> bool:
        """Pull if missing, return True if available"""

    def get_recommended_model(self, ram_gb: int) -> str:
        """Recommend model based on machine specs
        8GB  → qwen3:8b
        16GB → qwen3:8b (default)
        32GB → qwen3-coder:30b
        GPU  → llama3.3:70b
        """
```

#### MultiLLMRouter Spec

```python
class MultiLLMRouter:
    MODEL_TIERS = {
        "free":   ["ollama/qwen3:8b", "ollama/deepseek-r1:8b", ...],
        "low":    ["claude-haiku-4-5-20251001", "gemini/gemini-2.0-flash"],
        "medium": ["claude-sonnet-4-6", "gpt-4o-mini", ...],
        "high":   ["claude-opus-4-6", "gpt-4o"],
    }

    async def route(self, task_type: str, budget_remaining: float) -> str:
        """Select optimal model from task type + remaining budget
        1. LOCAL_FIRST: prefer free tier if Ollama is running
        2. Budget check: force free tier if budget exhausted
        3. Task type → tier → first available model
        """

    async def call(self, model: str, messages: list, **kwargs) -> LLMResponse:
        """LiteLLM completion() wrapper
        cache={"type": "disk"} for disk caching
        Swap api_base for Ollama
        """
```

#### CostTracker Spec

```python
class CostTracker:
    """Real-time cost tracking via LiteLLM success_callback"""

    async def on_success(self, kwargs, response, start_time, end_time):
        """LiteLLM callback: record cost of every LLM call to DB"""

    async def get_daily_total(self) -> float:
    async def get_monthly_total(self) -> float:
    async def get_local_usage_rate(self) -> float:
    def check_budget(self, budget_usd: float) -> bool:
    async def get_savings_from_local(self) -> float:
```

#### Completion Criteria

- [ ] Ollama inference with `qwen3:8b` → response received
- [ ] LiteLLM → Ollama call → recorded in `cost_logs` (cost=0)
- [ ] With API key: Claude Haiku call → recorded in `cost_logs` (cost>0)
- [ ] `get_local_usage_rate()` returns accurate ratio
- [ ] Router forces free tier when budget exhausted

---

### Sprint 1.3: Task Graph Engine (Day 5-7)

**Goal**: Goal input → LLM decomposition → DAG generation → execution → result

#### Files to Create

```
application/use_cases/execute_task.py      # ExecuteTaskUseCase
application/use_cases/create_task.py       # CreateTaskUseCase
infrastructure/task_graph/__init__.py
infrastructure/task_graph/engine.py        # TaskGraphEngine (LangGraph)
infrastructure/task_graph/scheduler.py     # TaskScheduler (parallel execution)
infrastructure/task_graph/intent_analyzer.py # IntentAnalyzer (goal → subtask decomposition)
tests/unit/application/test_execute_task.py
```

#### AgentState Model

```python
class AgentState(TypedDict):
    goal: str                              # User's original goal
    tasks: list[TaskNode]                  # Subtask list
    current_task_index: int                # Currently executing task
    history: Annotated[list[dict], add]    # Append-only execution history
    context: str                           # Compressed context
    status: str                            # Overall status
    cost_so_far: float                     # Cumulative cost
```

#### TaskGraphEngine Spec

```python
class TaskGraphEngine:
    def build_graph(self) -> StateGraph:
        """Build LangGraph StateGraph"""
        graph = StateGraph(AgentState)
        graph.add_node("analyze_intent",   self.analyze_intent)
        graph.add_node("plan_tasks",       self.plan_tasks)
        graph.add_node("execute_task",     self.execute_task)
        graph.add_node("observe_result",   self.observe_result)
        graph.add_node("handle_failure",   self.handle_failure)
        graph.add_node("complete",         self.complete)

        graph.set_entry_point("analyze_intent")
        graph.add_edge("analyze_intent", "plan_tasks")
        graph.add_edge("plan_tasks", "execute_task")

        graph.add_conditional_edges(
            "execute_task",
            self.route_after_execution,
            {"success": "observe_result", "failure": "handle_failure"}
        )

        graph.add_conditional_edges(
            "observe_result",
            self.has_next_task,
            {"continue": "execute_task", "done": "complete"}
        )

        graph.add_conditional_edges(
            "handle_failure",
            self.failure_strategy,
            {"retry": "execute_task", "fallback": "execute_task", "abort": "complete"}
        )

        graph.add_edge("complete", END)
        return graph.compile()

    async def run(self, goal: str) -> AgentState:
        """Accept a goal, execute full DAG, return final state"""
```

#### Completion Criteria

- [ ] "Implement fibonacci in Python" → subtask decomposition → execution → result
- [ ] Failure fallback: Ollama fails → retry with different model
- [ ] Parallel execution: 2 independent subtasks run simultaneously, faster than sequential
- [ ] All tasks recorded in `tasks` table
- [ ] Execution details recorded in `task_executions`

---

### Sprint 1.3b: Local Autonomous Execution Engine — LAEE (Day 8-9)

**Goal**: Foundation for agent to directly operate user's local PC

#### Files to Create

```
infrastructure/local_execution/__init__.py
infrastructure/local_execution/executor.py       # LocalExecutor implementation
infrastructure/local_execution/audit_log.py      # Append-only JSONL audit log
infrastructure/local_execution/undo_manager.py   # Reversible operation undo
infrastructure/local_execution/tools/__init__.py
infrastructure/local_execution/tools/shell_tools.py   # shell_exec/background/stream/pipe
infrastructure/local_execution/tools/fs_tools.py      # fs_read/write/edit/delete/move/glob/watch/tree
infrastructure/local_execution/tools/system_tools.py  # process/resource/clipboard/notify/screenshot
infrastructure/local_execution/tools/dev_tools.py     # git/docker/pkg_install/env_setup
tests/unit/infrastructure/test_local_execution.py
```

Note: Domain logic (RiskAssessor, ApprovalEngine) is already implemented in `domain/services/`.
LAEE tools are thin wrappers around OSS/stdlib:
- Shell → `subprocess` (stdlib)
- File → `pathlib` (stdlib)
- Browser → `playwright` (OSS)
- Process → `psutil` (OSS)
- Scheduling → `apscheduler` (OSS)
- File watching → `watchdog` (OSS)

#### Completion Criteria

- [ ] `shell_exec("echo hello")` → returns "hello"
- [ ] `fs_write` + `fs_read` round-trip test
- [ ] `fs_delete(recursive=True)` requires confirmation in `confirm-destructive` mode
- [ ] `full-auto` mode executes all operations without confirmation
- [ ] `confirm-all` mode requires confirmation for everything except SAFE
- [ ] All operations logged to `.morphic/audit_log.jsonl`
- [ ] `undo_last()` reverts a `fs_write` operation
- [ ] Commands containing `sudo` auto-classified as CRITICAL

---

### Sprint 1.4: Context Engineering (Day 10-11)

**Goal**: Foundation of Manus 5 principles. KV-Cache optimization + tool masking + todo.md

#### Files to Create

```
infrastructure/context_engineering/__init__.py
infrastructure/context_engineering/kv_cache_optimizer.py
infrastructure/context_engineering/tool_state_machine.py
infrastructure/context_engineering/todo_manager.py
infrastructure/context_engineering/observation_diversifier.py
infrastructure/context_engineering/file_context.py
tests/unit/infrastructure/test_context_engineering.py
```

#### Module Specs

**kv_cache_optimizer.py — Principle 1: KV-Cache as design center**

```python
class KVCacheOptimizer:
    STABLE_PREFIX: str  # Immutable system prompt prefix

    def build_system_prompt(self, dynamic_context: dict) -> str:
        """Stable prefix + dynamic section (at end)
        Never change the prefix → maximize KV-Cache hits"""

    def serialize_context(self, context: dict) -> str:
        """Deterministic serialization with JSON sort_keys=True"""

    def append_to_history(self, history: list, new_entry: dict) -> list:
        """Append-only. Never edit past entries"""
```

**tool_state_machine.py — Principle 2: Mask tools, don't remove**

```python
class ToolStateMachine:
    ALL_TOOLS: list[ToolDef]  # All tool definitions (immutable)

    def get_allowed_tools(self, state: AgentState) -> list[ToolDef]:
        """Return tools usable in current state.
        Tool definitions always stay in prompt."""

    def mask(self, tool_name: str, reason: str) -> None:
    def unmask(self, tool_name: str) -> None:
```

**todo_manager.py — Principle 4: Steer attention with todo.md**

```python
class TodoManager:
    TODO_PATH = "todo.md"
    async def read(self) -> str:        # Read at iteration start
    async def update(self, tasks) -> None:  # Update at iteration end
    def format_for_context(self, todo_content: str) -> str:
        """Emphasize [IN PROGRESS] tasks for LLM attention"""
```

**observation_diversifier.py — Principle 5: Maintain observation diversity**

```python
class ObservationDiversifier:
    TEMPLATES = [
        "Result: {result}\nStatus: {status}",
        "Observation #{n}: {result} [{status}]",
        "Completed: {result} | State: {status}",
    ]
    def serialize(self, obs: dict, n: int) -> str:
        """Template rotation to prevent similar-observation drift"""
```

#### Completion Criteria

- [ ] System prompt first 128 tokens are always identical (cache validation)
- [ ] Tool definition count does not change during execution
- [ ] todo.md auto-updated before/after task execution
- [ ] 3 consecutive similar observations all serialized with different formats

---

### Sprint 1.5: Semantic Memory (Day 12-13)

**Goal**: L1-L4 memory hierarchy foundation. mem0 + pgvector + Neo4j integration

#### Files to Create

```
infrastructure/memory/__init__.py
infrastructure/memory/memory_hierarchy.py    # L1-L4 unified management
infrastructure/memory/knowledge_graph.py     # Neo4j L3 wrapper
infrastructure/memory/context_zipper.py      # Simplified compression
tests/integration/test_memory.py
```

#### MemoryHierarchy Spec

```python
class MemoryHierarchy:
    """CPU cache hierarchy design — same philosophy"""

    # L1: Active Context (in-memory, ~2000 tokens)
    # L2: Semantic Cache (mem0 + pgvector)
    # L3: Structured Facts (Neo4j)
    # L4: Cold Storage (PostgreSQL memories table)

    async def add(self, content: str, role: str = "user") -> None:
        """Distribute new utterance to each layer asynchronously"""

    async def retrieve(self, query: str, max_tokens: int = 500) -> str:
        """Hierarchical search: L1 → L2 → L3 → L4
        Trim by priority within max_tokens budget"""
```

#### Completion Criteria

- [ ] add() → retrieve() returns relevant memories
- [ ] mem0 stores vectors in pgvector (verified)
- [ ] Neo4j stores entities/relations, searchable via Cypher
- [ ] ContextZipper compresses 5000-token history → 500 tokens

---

### Sprint 1.6: API + UI (Day 14-15)

**Goal**: FastAPI backend + Next.js minimal UI

#### Backend Files

```
interface/api/__init__.py
interface/api/main.py                       # FastAPI app factory
interface/api/deps.py                       # Dependency injection (DB session, router, etc.)
interface/api/routes/__init__.py
interface/api/routes/tasks.py               # POST/GET /api/tasks
interface/api/routes/models.py              # GET /api/models
interface/api/routes/cost.py                # GET /api/cost
interface/api/routes/memory.py              # GET /api/memory/search
interface/api/websocket.py                  # WebSocket /ws/tasks/{id}
```

#### API Endpoints

```
POST   /api/tasks              Create task (accept goal, generate DAG, start execution)
GET    /api/tasks              List tasks (status filter support)
GET    /api/tasks/{id}         Task detail (includes subtasks + execution logs)
DELETE /api/tasks/{id}         Cancel task

GET    /api/models             Available models list (Ollama + API)
GET    /api/models/status      Ollama health check

GET    /api/cost               Cost summary (daily/monthly/local rate)
GET    /api/cost/logs          Cost log list

GET    /api/memory/search?q=   Semantic memory search

WS     /ws/tasks/{id}          Real-time task execution progress
```

#### Frontend Files

```
ui/                                     # npx create-next-app@latest
ui/app/layout.tsx                       # Dark theme root layout
ui/app/page.tsx                         # Dashboard (task list + cost)
ui/app/tasks/[id]/page.tsx              # Task detail page
ui/components/TaskList.tsx
ui/components/TaskDetail.tsx
ui/components/CostMeter.tsx
ui/components/ModelStatus.tsx
ui/components/GoalInput.tsx
ui/lib/api.ts                           # API client
ui/lib/theme.ts                         # morphicAgentTheme
```

#### UI Phase 1 Scope

```
┌─────────────────────────────────────────────────┐
│ Morphic-Agent                          [Models] │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌─ Goal Input ──────────────────────────────┐  │
│  │ [Text area: enter your goal]    [Execute] │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  ┌─ Active Tasks ─────────────────────────────┐ │
│  │ ● "Implement fibonacci"  [Running] qwen3   │ │
│  │   ├ ✓ Algorithm design                     │ │
│  │   ├ ⚡ Code implementation [Running]       │ │
│  │   └ ○ Test creation [Pending]              │ │
│  └────────────────────────────────────────────┘ │
│                                                 │
│  ┌─ Cost ──────────────┐  ┌─ Model Status ──┐  │
│  │ Today:    $0.00     │  │ Ollama: ● ON    │  │
│  │ Local:    100%      │  │ qwen3:8b ✓      │  │
│  │ Budget:   ████░ 95% │  │ API Keys: 0     │  │
│  └─────────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────┘
```

#### Completion Criteria

- [ ] `POST /api/tasks` sends goal → task execution starts
- [ ] WebSocket receives real-time progress
- [ ] Next.js UI displays task list + details
- [ ] Cost meter displayed ($0 / Local 100%)

---

### Sprint 1.7: Integration & E2E Test (Day 16)

**Goal**: Full component integration test. Validate $0 path.

#### Test Scenarios

```
E2E Test 1: $0 Full Local Path
  Input:  "Implement fibonacci in Python"
  Flow:   Intent Analysis (Ollama) → DAG → Execution (Ollama) → Result
  Assert: cost_usd == 0, task.status == "success", result contains "fibonacci"

E2E Test 2: Failure Recovery
  Input:  Intentionally failing task
  Flow:   Execute → Fail → Fallback → Success
  Assert: task_executions has retry record, final status == "success"

E2E Test 3: Parallel Execution
  Input:  "Execute A and B simultaneously"
  Flow:   2 independent subtasks via asyncio.gather
  Assert: Start times nearly identical (diff < 1 second)

E2E Test 4: Memory Persistence
  Input:  Execute task → ask related question in new session
  Flow:   add() → retrieve() returns previous context
  Assert: retrieved_context contains task result info

E2E Test 5: LAEE Local Execution
  Input:  "Create test directory and generate 3 Python files"
  Flow:   fs_write × 3 (parallel) → fs_tree → verify
  Assert: Files actually created, audit_log.jsonl has records

E2E Test 6: LAEE Approval Mode Test
  Input:  confirm-destructive mode + fs_delete(recursive=True)
  Flow:   Risk assessment → CRITICAL → user confirmation request
  Assert: Not executed without user confirmation

E2E Test 7: LAEE Undo Test
  Input:  fs_write("test.txt") → undo_last()
  Flow:   Create file → undo → delete file
  Assert: test.txt does not exist
```

#### Completion Criteria

- [ ] E2E Tests 1-7 all pass
- [ ] `docker compose up -d` → `uv run pytest` all tests pass
- [ ] UI task execution → result display flow works end-to-end

---

## Phase 1 Deliverable Summary

```
Files: ~60 (LAEE +15)
Python packages:
  langgraph, litellm, sqlalchemy[asyncio], asyncpg, pgvector,
  neo4j, mem0ai, fastapi, uvicorn, pydantic-settings,
  celery[redis], instructor, alembic, httpx, pytest, pytest-asyncio,
  playwright, watchdog, apscheduler, psutil  # LAEE
  typer, rich  # CLI (Phase 2, but added to deps early)

Next.js packages:
  next, react, tailwindcss, shadcn-ui (initial), recharts

Docker Compose services:
  PostgreSQL 16 + pgvector, Redis 7, Neo4j 5

Verification:
  User inputs goal → DAG generated → Ollama executes → results displayed
  Cost: $0 (full local execution)
```

---

## Phase 2: Parallel & Planning + CLI v1 (Week 3-4)

> **Goal**: Full parallel execution + Interactive Planning + CLI foundation

### Week 3: Parallel Execution & Interactive Planning

| # | Item | File | Depends |
|---|---|---|---|
| 2.1 | ParallelExecutionEngine full impl | `infrastructure/task_graph/parallel.py` | Phase 1 DAG |
| 2.2 | Celery worker integration | `infrastructure/task_graph/celery_worker.py` | Redis |
| 2.3 | Interactive Planning System | `application/use_cases/interactive_plan.py` | DAG + LLM Router |
| 2.4 | Cost estimation engine | `application/use_cases/cost_estimator.py` | Cost Tracker |

**Interactive Planning Flow:**
```
1. User inputs goal
2. LLM decomposes into subtasks + proposes models
3. Cost estimate calculated
4. Plan + estimate presented in UI/CLI
5. User [approve / edit / reject]
6. Execution starts after approval
```

### Week 4: Background Planner, Graph Viz & CLI

| # | Item | File | Depends |
|---|---|---|---|
| 2.5 | Background Planner (Windsurf-style) | `application/use_cases/background_planner.py` | Planning |
| 2.6 | Tool State Machine enhancement | `infrastructure/context_engineering/tool_state_machine.py` | Phase 1 |
| 2.7 | React Flow task graph UI | `ui/components/TaskGraph.tsx` | React Flow |
| 2.8 | Planning View UI | `ui/components/PlanningView.tsx` | Phase 1 UI |
| 2.9 | **CLI foundation (typer + rich)** | `interface/cli/main.py` | Use cases |
| 2.10 | **CLI task commands** | `interface/cli/commands/task.py` | CLI foundation |
| 2.11 | **CLI model/cost commands** | `interface/cli/commands/model.py, cost.py` | CLI foundation |
| 2.12 | LAEE Browser Tools (Playwright) | `infrastructure/local_execution/tools/browser_tools.py` | LAEE |
| 2.13 | LAEE GUI Tools (macOS) | `infrastructure/local_execution/tools/gui_tools.py` | LAEE |
| 2.14 | LAEE Cron Tools (APScheduler) | `infrastructure/local_execution/tools/cron_tools.py` | LAEE |

**Phase 2 Completion Criteria:**
- [ ] 3 independent tasks execute in parallel, 3x+ faster than sequential
- [ ] Interactive Planning: plan presented → user approves → execution starts
- [ ] React Flow visualizes DAG in real-time
- [ ] Background Planner continuously improves plan during execution
- [ ] `morphic task create "..."` creates and executes task from CLI
- [ ] `morphic cost summary` displays cost breakdown in terminal

---

## Phase 3: Context Bridge & Semantic Memory (Week 5-6)

> **Goal**: Elevate memory and context to research-grade + cross-platform support

### Week 5: Full Semantic Memory

| # | Item | File |
|---|---|---|
| 3.1 | SemanticFingerprint (LSH) | `infrastructure/memory/semantic_fingerprint.py` |
| 3.2 | ContextZipper full version | `infrastructure/memory/context_zipper.py` |
| 3.3 | ForgettingCurve | `infrastructure/memory/forgetting_curve.py` |
| 3.4 | DeltaEncoder | `infrastructure/memory/delta_encoder.py` |
| 3.5 | HierarchicalSummarizer | `infrastructure/memory/hierarchical_summary.py` |

### Week 6: Context Bridge & MCP

| # | Item | File |
|---|---|---|
| 3.6 | Cross-Platform Context Bridge | `infrastructure/memory/context_bridge.py` |
| 3.7 | MCP Server implementation | `infrastructure/mcp/server.py` |
| 3.8 | MCP Client implementation | `infrastructure/mcp/client.py` |
| 3.9 | Chrome Extension | `integrations/browser_extension/` |
| 3.10 | L1→L4 integration test | `tests/integration/test_memory_hierarchy.py` |

**Phase 3 Completion Criteria:**
- [ ] 10,000 tokens → 500 tokens compression (information retention > 90%)
- [ ] LSH retrieves semantically similar memories in near-O(1) time
- [ ] MCP Server enables other tools to access Morphic-Agent memory
- [ ] Forgetting curve auto-promotes low-importance memories to L3, removes from L2

---

## Phase 4: Agent CLI Orchestration (Week 7-8)

> **Goal**: Meta-orchestrator managing 4 Agent CLIs

### Week 7: Common Interface + OpenHands & Claude Code

| # | Item | File |
|---|---|---|
| 4.1 | AgentEngine Protocol | `infrastructure/agent_orchestration/agent_engine_protocol.py` |
| 4.2 | OpenHands Driver | `infrastructure/agent_orchestration/openhands_driver.py` |
| 4.3 | Claude Code SDK Driver | `infrastructure/agent_orchestration/claude_code_driver.py` |
| 4.4 | AgentCLIRouter foundation | `application/use_cases/agent_routing.py` |

### Week 8: Gemini & Codex + Router completion

| # | Item | File |
|---|---|---|
| 4.5 | Gemini CLI + ADK Driver | `infrastructure/agent_orchestration/gemini_adk_driver.py` |
| 4.6 | Codex CLI Driver | `infrastructure/agent_orchestration/codex_cli_driver.py` |
| 4.7 | AgentCLIRouter routing complete | (extend 4.4) |
| 4.8 | Knowledge file management | `infrastructure/agent_orchestration/knowledge_files.py` |

**Phase 4 Completion Criteria:**
- [ ] Same task executed on OpenHands / Claude Code / Gemini / Codex, results compared
- [ ] AgentCLIRouter auto-selects optimal engine based on task characteristics
- [ ] Availability check + fallback for each engine

---

## Phase 5: Marketplace & Tools (Week 9-10)

> **Goal**: Autonomous tool discovery, installation, and sharing

| # | Item | File |
|---|---|---|
| 5.1 | Auto Tool Discoverer | `infrastructure/marketplace/auto_discoverer.py` |
| 5.2 | MCP Registry search | `infrastructure/marketplace/mcp_search.py` |
| 5.3 | Tool Installer | `infrastructure/marketplace/tool_installer.py` |
| 5.4 | Ollama Model Manager | `infrastructure/marketplace/ollama_installer.py` |
| 5.5 | Tool Safety Scorer | `infrastructure/marketplace/safety_scorer.py` |
| 5.6 | Marketplace UI | `ui/app/marketplace/page.tsx` |

**Phase 5 Completion Criteria:**
- [ ] Auto-search and suggest tools on task failure
- [ ] 1-click install from MCP Registry
- [ ] Ollama model UI management (pull/delete/switch)
- [ ] Tool safety score displayed

---

## Phase 6: Self-Evolution (Week 11-12)

> **Goal**: Autonomous improvement from execution data

| # | Item | File |
|---|---|---|
| 6.1 | Execution Analyzer | `application/use_cases/execution_analysis.py` |
| 6.2 | Tactical Recovery (Level 1) | `domain/services/tactical_recovery.py` |
| 6.3 | Strategy Updater (Level 2) | `application/use_cases/strategy_update.py` |
| 6.4 | Systemic Evolver (Level 3) | `application/use_cases/systemic_evolution.py` |
| 6.5 | Evolution Dashboard | `ui/app/evolution/page.tsx` |

**Phase 6 Completion Criteria:**
- [ ] Failure pattern analysis → auto-improve prompt templates
- [ ] Model selection accuracy improves +10% over 2 weeks
- [ ] Agent CLI engine selection auto-optimized
- [ ] Evolution reports viewable in UI

---

## Phase 7: A2A & Scale (Week 13-14)

> **Goal**: Multi-agent coordination + benchmarks

| # | Item | File |
|---|---|---|
| 7.1 | A2A Protocol implementation | `infrastructure/a2a/protocol.py` |
| 7.2 | Agent Coordinator | `infrastructure/a2a/coordinator.py` |
| 7.3 | Multi-Agent Parallel | `infrastructure/a2a/parallel.py` |
| 7.4 | Benchmark Suite | `benchmarks/` |
| 7.5 | vs Manus / Devin / OpenHands comparison | `benchmarks/results/` |

**Phase 7 Completion Criteria:**
- [ ] 3 agents coordinate via A2A to complete a task
- [ ] SWE-bench lite score measured
- [ ] Benchmark results dashboard

---

## Risk Management

| Risk | Impact | Probability | Mitigation |
|---|---|---|---|
| LangGraph breaking changes | High | Low | Thin wrapper isolates API |
| Ollama model quality insufficient | Medium | Medium | Auto-fallback to API by task type |
| Neo4j Community limitations | Low | Low | No issue at Phase 1 scale |
| Agent CLI (OpenHands etc.) API changes | Medium | Medium | AgentEngine Protocol abstraction |
| Phase 1 exceeds 2 weeks | High | Medium | Minimize UI scope, prioritize API + CLI |
| mem0 pgvector compatibility | Low | Low | Can fallback to direct pgvector usage |

---

## Critical Path

```
Sprint 1.1 (Infra)
    → Sprint 1.2 (LLM Layer) ← TOP PRIORITY. Delays here cascade
        → Sprint 1.3 (Task Graph) ← Core. All of Phase 2-7 depends on this
            → Sprint 1.3b (LAEE) ← Partially parallelizable with 1.3
            → Sprint 1.4 (Context Eng.) ← Partially parallelizable with 1.3
            → Sprint 1.5 (Memory) ← Partially parallelizable with 1.3
                → Sprint 1.6 (API + UI) ← Requires 1.3-1.5 completion
                    → Sprint 1.7 (E2E Test)
```

**Bottleneck**: Sprint 1.2 (LLM Layer) and Sprint 1.3 (Task Graph Engine) are most critical. Allocate maximum time here.

---

## Success Metrics by Phase

| Phase | Metric | Target |
|---|---|---|
| 1 | Task completion at $0 | Yes |
| 1 | Ollama inference latency | < 10s |
| 2 | Parallel execution speedup | 3x+ |
| 2 | Interactive Planning approval rate | > 80% |
| 2 | CLI commands functional | task, model, cost |
| 3 | Memory compression ratio | 98% (10K→500 tokens) |
| 3 | Context restoration accuracy | > 90% |
| 4 | Agent CLI routing accuracy | > 85% |
| 5 | Auto tool discovery success rate | > 60% |
| 6 | Monthly improvement rate | +15% |
| 7 | SWE-bench lite score | TBD |
