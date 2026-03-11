# Morphic-Agent Architecture

> Clean Architecture (4-layer) + TDD + Pydantic Strict Mode + OSS-First
>
> **Phase 1 Foundation: COMPLETE** (2026-02-25) — 7/7 sprints done
> **Phase 2 Parallel & Planning + CLI: COMPLETE** (2026-02-26) — All 6 sprints (2-A through 2-F) + CLI v1
> **Phase 3 Semantic Memory & Context Bridge: COMPLETE** (2026-02-26) — Week 5: SemanticFingerprint LSH → ContextZipper v2 → ForgettingCurve → DeltaEncoder → HierarchicalSummarizer | Week 6: Context Bridge → MCP Server → MCP Client → L1-L4 Integration — 725 tests (699 unit + 26 integration)
> **Phase 4 Agent CLI Orchestration: COMPLETE** — Sprint 4.1–4.6 done (domain foundation + 6 drivers + RouteToEngine use case + API/CLI + knowledge file injection) — 898 unit tests + 30 integration
> **Phase 5 Marketplace & Tools: COMPLETE** — Sprint 5.1–5.6 done (safety scorer + MCP registry + tool installer + auto discoverer + Ollama manager + marketplace UI) — 988 unit tests + 37 integration
> **Phase 6 Self-Evolution: COMPLETE** — Sprint 6.1–6.5 done (execution recorder + tactical recovery + strategy learning + systemic evolution + evolution dashboard) — 1162 unit tests + 37 integration
> **Phase 7 UCL: Sprint 7.1 COMPLETE** (2026-03-10) — UCL domain foundation (Decision, AgentAction, SharedTaskState, AgentAffinityScore, CognitiveMemoryType, 2 ports, AgentAffinityScorer service) — 1230 unit tests + 37 integration
> **Phase 7 UCL: Sprint 7.2 COMPLETE** (2026-03-10) — ContextAdapterPort + InMemorySharedTaskStateRepo + 6 context adapters (Claude Code, Gemini, Codex, Ollama, OpenHands, ADK) — 1350 unit tests + 37 integration
> **Phase 7 UCL: Sprint 7.3 COMPLETE** (2026-03-11) — Insight Extraction Pipeline (MemoryClassifier + ConflictResolver + InsightExtractor + ExtractInsightsUseCase + ExecuteTask integration + container wiring) — 1438 unit tests + 37 integration
> **Phase 7 UCL: Sprint 7.4 COMPLETE** (2026-03-11) — Affinity-Aware Routing + Task Handoff (AgentAffinityRepository port + TopicExtractor + select_with_affinity() + InMemory/JSONL affinity stores + RouteToEngine with affinity/adapter/action recording + HandoffTaskUseCase + container wiring) — 1528 unit tests + 37 integration
> **Phase 7 UCL: Sprint 7.5 COMPLETE** (2026-03-11) — UCL API + CLI + UI (cognitive API routes + CLI commands + Next.js cognitive page + 30 new tests) — 1558 unit tests + 37 integration
> **Sprint 5.7 COMPLETE** (2026-03-12) — Model management test coverage (15 tests) + auto-discovery trigger on task failure (8 tests) — Phase 5 fully complete — 1592 unit tests + 50 integration
> **Sprint 8.1 COMPLETE** (2026-03-12) — Self-Evolution Loop Closure: ExecuteTaskUseCase now auto-records ExecutionRecords after every task execution, feeding Phase 6's AnalyzeExecution/UpdateStrategy/SystemicEvolution pipeline — 1599 unit tests + 50 integration

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
│  ├── memory/         mem0, vector DB adapters                │
│  └── marketplace/    MCP registry client, tool installer     │
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
│  │ POST /api/tasks  ─────┼──┼── morphic task create ──────┤ │
│  │ GET  /api/cost   ─────┼──┼── morphic cost summary ─────┤ │
│  │ GET  /api/models ─────┼──┼── morphic model list ───────┤ │
│  │ GET  /api/engines ────┼──┼── morphic engine list ──────┤ │
│  │ POST /api/engines/run ┼──┼── morphic engine run  ──────┤ │
│  │ GET  /api/marketplace ┼──┼── morphic marketplace ──────┤ │
│  └───────────────────────┘  └───────────────────────────┘ │
│              │                          │                  │
│              └──────────┬───────────────┘                  │
│                         ▼                                  │
│              application/use_cases/                        │
│              ├── create_task.py                            │
│              ├── route_to_engine.py                        │
│              └── ...                                       │
└─────────────────────────────────────────────────────────┘
```

### CLI Architecture (Phase 2 + 5 + 6)

```
interface/cli/
├── main.py            # typer.Typer() app, entry point: `morphic`
├── commands/
│   ├── task.py        # morphic task {create|list|show|cancel}
│   ├── model.py       # morphic model {list|status|pull|delete|switch|info} (Sprint 5.5)
│   ├── cost.py        # morphic cost {summary|budget}
│   ├── plan.py        # morphic plan {create|list|show|approve|reject}
│   ├── mcp.py         # morphic mcp server
│   ├── engine.py      # morphic engine {list|run} (Sprint 4.3)
│   ├── marketplace.py # morphic marketplace {search|install|list|suggest|uninstall} (Sprint 5.3)
│   └── evolution.py   # morphic evolution {stats|failures|update|report} (Sprint 6.5)
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
| `domain/services/agent_engine_router.py` | Two-tier routing: task characteristics → execution engine selection, pure static (Sprint 4.1) |
| `domain/services/tool_safety_scorer.py` | Multi-signal safety scoring: publisher trust + transport + popularity + metadata (Sprint 5.1) |
| `domain/services/failure_analyzer.py` | Regex error pattern → MCP search query mapping, pure static (Sprint 5.4) |
| `domain/services/memory_classifier.py` | Regex-based text → CognitiveMemoryType classification, pure static (Sprint 7.3) |
| `domain/services/conflict_resolver.py` | Jaccard+negation contradiction detection, confidence-weighted resolution, pure static (Sprint 7.3) |
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
│   │   ├── plan.py                 # PlanStep, ExecutionPlan (strict)
│   │   ├── tool_candidate.py       # ToolCandidate — MCP tool metadata (strict, Sprint 5.1)
│   │   ├── execution_record.py    # ExecutionRecord — single execution outcome (strict, Sprint 6.1)
│   │   └── strategy.py            # RecoveryRule, ModelPreference, EnginePreference (strict, Sprint 6.3)
│   ├── value_objects/
│   │   ├── status.py               # TaskStatus, SubTaskStatus, ObservationStatus, MemoryType, PlanStatus
│   │   ├── risk_level.py           # RiskLevel (5-tier IntEnum)
│   │   ├── approval_mode.py        # ApprovalMode (3-tier)
│   │   ├── model_tier.py           # ModelTier, TaskType (+LONG_RUNNING_DEV, +WORKFLOW_PIPELINE)
│   │   ├── agent_engine.py         # AgentEngineType (6 engines, Sprint 4.1)
│   │   ├── tool_safety.py          # SafetyTier (4-tier IntEnum: UNSAFE→VERIFIED, Sprint 5.1)
│   │   └── evolution.py            # EvolutionLevel (TACTICAL, STRATEGIC, SYSTEMIC, Sprint 6.1)
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
│   │   ├── mcp_client.py           # MCPClientPort ABC (Sprint 3.8)
│   │   ├── agent_engine.py         # AgentEnginePort ABC + Result + Capabilities (Sprint 4.1)
│   │   ├── tool_registry.py        # ToolRegistryPort ABC + ToolSearchResult (Sprint 5.2)
│   │   ├── tool_installer.py       # ToolInstallerPort ABC + InstallResult (Sprint 5.3)
│   │   ├── execution_record_repository.py # ExecutionRecordRepository ABC + ExecutionStats (Sprint 6.1)
│   │   ├── shared_task_state_repository.py # SharedTaskStateRepository ABC (Sprint 7.1)
│   │   ├── insight_extractor.py    # InsightExtractorPort ABC + ExtractedInsight (Sprint 7.1)
│   │   └── context_adapter.py      # ContextAdapterPort ABC + AdapterInsight (Sprint 7.2)
│   └── services/
│       ├── risk_assessor.py        # 40+ tool risk mapping + escalation
│       ├── approval_engine.py      # 3-mode × 5-risk approval matrix
│       ├── semantic_fingerprint.py # LSH hash + cosine similarity (Sprint 3.1)
│       ├── forgetting_curve.py    # Ebbinghaus retention scoring R=e^(-t/S) (Sprint 3.3)
│       ├── delta_encoder.py      # hash_changes, reconstruct, create_delta, compute_diff (Sprint 3.4)
│       ├── hierarchical_summarizer.py # estimate_tokens, split_sentences, extract_summary, build_hierarchy, select_level (Sprint 3.5)
│       ├── agent_engine_router.py # select, get_fallback_chain, select_with_fallbacks — pure static (Sprint 4.1)
│       ├── tool_safety_scorer.py  # score() — publisher trust + transport + popularity + metadata (Sprint 5.1)
│       ├── failure_analyzer.py    # extract_queries() — regex error→search query mapping (Sprint 5.4)
│       ├── tactical_recovery.py   # find_alternative, create_rule, rank_rules — pure static (Sprint 6.2)
│       ├── memory_classifier.py   # classify(), classify_with_confidence() — regex→CognitiveMemoryType (Sprint 7.3)
│       └── conflict_resolver.py   # detect_conflicts(), resolve(), resolve_all() — Jaccard+negation (Sprint 7.3)
│
├── application/                     # Layer 3: Use Cases
│   ├── use_cases/
│   │   ├── create_task.py          # CreateTaskUseCase (decompose + persist)
│   │   ├── execute_task.py         # ExecuteTaskUseCase (run DAG + persist + insight extraction hook)
│   │   ├── cost_estimator.py       # CostEstimator (per-model token pricing)
│   │   ├── interactive_plan.py     # InteractivePlanUseCase (create/approve/reject)
│   │   ├── background_planner.py   # BackgroundPlannerUseCase (advisory monitoring)
│   │   ├── route_to_engine.py      # RouteToEngineUseCase (engine selection + fallback execution, Sprint 4.3)
│   │   ├── install_tool.py         # InstallToolUseCase (search + score + install, Sprint 5.3)
│   │   ├── discover_tools.py       # DiscoverToolsUseCase (failure → suggest tools, Sprint 5.4)
│   │   ├── manage_ollama.py        # ManageOllamaUseCase (status/pull/delete/switch, Sprint 5.5)
│   │   ├── analyze_execution.py   # AnalyzeExecutionUseCase (record + stats + failure patterns, Sprint 6.1)
│   │   ├── update_strategy.py     # UpdateStrategyUseCase (model/engine prefs + recovery rules, Sprint 6.3)
│   │   ├── systemic_evolution.py  # SystemicEvolutionUseCase (tool gap detection + evolution report, Sprint 6.4)
│   │   └── extract_insights.py   # ExtractInsightsUseCase (extract → resolve → store → update state, Sprint 7.3)
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
│   │   ├── pg_plan_repository.py    # PgPlanRepository (ExecutionPlan ↔ PlanModel)
│   │   ├── in_memory_execution_record.py # InMemoryExecutionRecordRepository (Sprint 6.1)
│   │   └── shared_task_state_repo.py # InMemorySharedTaskStateRepository (Sprint 7.2)
│   ├── llm/                         # Sprint 1.2 + 5.5: LLM Layer
│   │   ├── ollama_manager.py        # Ollama lifecycle (health, pull, delete, info, running, Sprint 5.5)
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
│   ├── mcp/                         # Sprint 3.7–3.8: Model Context Protocol
│   │   ├── server.py                # create_mcp_server() — FastMCP, 6 tools + 2 resources
│   │   └── client.py               # MCPClient, MCPToolAdapter, discover_and_register
│   └── agent_cli/                   # Sprint 4.1–4.6: Agent CLI Orchestration
│       ├── __init__.py              # Re-exports all 6 drivers
│       ├── _subprocess_base.py      # CLIResult + SubprocessMixin (shared by CLI drivers)
│       ├── ollama_driver.py         # OllamaEngineDriver (wraps LiteLLMGateway, $0)
│       ├── claude_code_driver.py    # ClaudeCodeDriver (claude -p, 200K ctx)
│       ├── codex_cli_driver.py      # CodexCLIDriver (codex exec, sandbox+MCP)
│       ├── gemini_cli_driver.py     # GeminiCLIDriver (gemini -p, 2M ctx)
│       ├── openhands_driver.py      # OpenHandsDriver (httpx REST, Docker sandbox)
│       ├── adk_driver.py            # ADKDriver (Google ADK Python SDK, 2M ctx, Sprint 4.5)
│       └── knowledge_loader.py      # KnowledgeFileLoader (engine→file mapping, Sprint 4.6)
│   ├── cognitive/                   # Sprint 7.2-7.3: UCL Context Adapters + Insight Extraction
│   │   ├── __init__.py              # Re-exports InsightExtractor (Sprint 7.3)
│   │   ├── insight_extractor.py     # InsightExtractorPort impl — adapters + dedup + reclassify (Sprint 7.3)
│   │   └── adapters/
│   │       ├── __init__.py          # Re-exports all 6 adapters
│   │       ├── _base.py             # Shared helpers (format, truncate, regex patterns)
│   │       ├── claude_code.py       # ClaudeCodeContextAdapter (CLAUDE.md format, 200K ctx)
│   │       ├── gemini.py            # GeminiContextAdapter (XML blocks, 2M ctx)
│   │       ├── codex.py             # CodexContextAdapter (AGENTS.md format)
│   │       ├── ollama.py            # OllamaContextAdapter (ultra-compact, small window)
│   │       ├── openhands.py         # OpenHandsContextAdapter (REST task context)
│   │       └── adk.py               # ADKContextAdapter (workflow-context XML)
│   ├── marketplace/                 # Sprint 5.2–5.3: Marketplace
│   │   ├── __init__.py              # Re-exports MCPRegistryClient, MCPToolInstaller
│   │   ├── mcp_registry_client.py   # MCPRegistryClient(ToolRegistryPort) — httpx, auto-score (Sprint 5.2)
│   │   └── tool_installer.py        # MCPToolInstaller(ToolInstallerPort) — npm/pip subprocess (Sprint 5.3)
│   └── evolution/                   # Sprint 6.3: Self-Evolution Engine
│       ├── __init__.py              # Re-exports StrategyStore
│       └── strategy_store.py        # StrategyStore — JSONL persistence (recovery rules + preferences)
│
├── interface/                       # Layer 4: Entry Points
│   ├── api/                         # Sprint 1.6: FastAPI + WebSocket
│   │   ├── main.py                  # create_app() factory + lifespan + CORS
│   │   ├── container.py             # AppContainer DI (Settings → repos → use cases)
│   │   ├── schemas.py               # 50+ Pydantic request/response models (+UCL cognitive schemas, Sprint 7.5)
│   │   ├── websocket.py             # /ws/tasks/{id} (poll + delta-only sends + recommendations)
│   │   └── routes/
│   │       ├── tasks.py             # POST, GET, GET/{id}, DELETE /api/tasks (+ Celery dispatch)
│   │       ├── plans.py             # POST, GET, approve, reject /api/plans
│   │       ├── models.py            # GET /api/models/status, POST /pull, DELETE /{name}, POST /switch, GET /running (Sprint 5.5)
│   │       ├── cost.py              # GET /api/cost, GET /api/cost/logs
│   │       ├── memory.py            # GET /api/memory/search?q= + GET /api/memory/export?platform=
│   │       ├── engines.py           # GET /api/engines, GET /api/engines/{type}, POST /api/engines/run (Sprint 4.3)
│   │       ├── marketplace.py       # GET /search, POST /install, GET /installed, POST /suggest, DELETE /{name} (Sprint 5.3)
│   │       ├── evolution.py        # GET /stats, GET /failures, GET /preferences, POST /update, POST /evolve (Sprint 6.1)
│   │       ├── cognitive.py       # GET/DELETE /state, GET /affinity, POST /handoff, POST /insights/extract (Sprint 7.5)
│   │       └── benchmarks.py     # POST /api/benchmarks/{run|continuity|dedup} (Sprint 7.6)
│   └── cli/                         # Sprint 2.9-2.11: typer + rich
│       ├── main.py                  # typer app, _get_container() lazy singleton, _run() async bridge
│       ├── formatters.py            # Rich tables, trees, status styles, safety badge (all output isolated here)
│       └── commands/
│           ├── task.py              # morphic task {create|list|show|cancel}
│           ├── model.py             # morphic model {list|status|pull|delete|switch|info} (Sprint 5.5)
│           ├── cost.py              # morphic cost {summary|budget}
│           ├── plan.py              # morphic plan {create|list|show|approve|reject}
│           ├── mcp.py               # morphic mcp server (stdio/streamable-http)
│           ├── engine.py            # morphic engine {list|run} (Sprint 4.3)
│           ├── marketplace.py       # morphic marketplace {search|install|list|suggest|uninstall} (Sprint 5.3)
│           ├── evolution.py        # morphic evolution {stats|failures|update|report} (Sprint 6.1)
│           ├── cognitive.py       # morphic cognitive {state|delete|affinity|handoff|insights} (Sprint 7.5)
│           └── benchmark.py      # morphic benchmark {run|continuity|dedup} (Sprint 7.6)
│
├── shared/
│   └── config.py                    # pydantic-settings (all env vars + marketplace + evolution settings)
│
├── ui/                              # Sprint 1.6 + 2-F + 5.6: Next.js 15 (bun, Tailwind CSS 4, @xyflow/react)
│   ├── lib/
│   │   ├── theme.ts                 # morphicAgentTheme design tokens
│   │   └── api.ts                   # Typed fetch wrappers + WebSocket + Plan/Marketplace/Model/Evolution/Cognitive/Benchmark API
│   ├── app/
│   │   ├── layout.tsx               # Dark theme root layout (Geist font, nav: Marketplace/Models/Evolution/Cognitive/Benchmarks)
│   │   ├── globals.css              # CSS variables matching design spec
│   │   ├── page.tsx                 # Dashboard (Execute/Plan toggle + GoalInput + TaskList)
│   │   ├── tasks/[id]/page.tsx      # Task detail + TaskGraph with live WebSocket
│   │   ├── plans/[id]/page.tsx      # Plan review page (approve/reject)
│   │   ├── marketplace/             # Sprint 5.6: MCP tool marketplace
│   │   │   ├── page.tsx             # Search/browse tools + installed tab
│   │   │   └── components/
│   │   │       ├── SearchBar.tsx    # Debounced search input (400ms)
│   │   │       ├── ToolCard.tsx     # Tool result card (SafetyBadge + InstallButton)
│   │   │       ├── SafetyBadge.tsx  # Color-coded safety tier indicator (4 tiers)
│   │   │       └── InstallButton.tsx # Install/uninstall with confirm dialog
│   │   ├── models/                  # Sprint 5.6: Ollama model management
│   │   │   └── page.tsx             # Pull/delete/switch models + running status
│   │   ├── evolution/               # Sprint 6.5: Evolution dashboard
│   │   │   └── page.tsx             # Stats, failure patterns, preferences, evolution trigger
│   │   ├── cognitive/               # Sprint 7.5: UCL cognitive dashboard
│   │   │   ├── page.tsx             # Shared states + affinity scores (tab UI)
│   │   │   └── components/
│   │   │       ├── StateCard.tsx    # State card (task_id, last_agent, counts)
│   │   │       ├── StateDetail.tsx  # Full state detail (decisions, artifacts, blockers, history)
│   │   │       └── AffinityTable.tsx # Affinity scores table (engine, topic, score)
│   │   └── benchmarks/              # Sprint 7.6: Benchmark dashboard
│   │       └── page.tsx             # Run benchmarks, view continuity + dedup results
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
│       │   ├── test_hierarchical_summarizer.py # 27 tests (tokens, sentences, extract, hierarchy, select, depth, Sprint 3.5)
│       │   ├── test_agent_engine_router.py    # 36 tests (select, fallback, with_fallbacks, engine type, task type, Sprint 4.1)
│       │   ├── test_agent_engine_port.py      # 10 tests (result, capabilities, ABC, backward compat, Sprint 4.1)
│       │   ├── test_tool_candidate.py         # 8 tests (strict validation, defaults, fields, Sprint 5.1)
│       │   ├── test_tool_safety_scorer.py     # 14 tests (trusted publisher, suspicious, tier mapping, Sprint 5.1)
│       │   ├── test_failure_analyzer.py       # 12 tests (error patterns, query extraction, limits, Sprint 5.4)
│       │   ├── test_evolution_vo.py           # EvolutionLevel enum validation (Sprint 6.1)
│       │   ├── test_execution_record.py       # ExecutionRecord strict validation (Sprint 6.1)
│       │   ├── test_strategy_entities.py      # RecoveryRule, ModelPreference, EnginePreference (Sprint 6.3)
│       │   ├── test_tactical_recovery.py      # find_alternative, create_rule, rank (Sprint 6.2)
│       │   ├── test_memory_classifier.py     # 30 tests (classify + classify_with_confidence, Sprint 7.3)
│       │   └── test_conflict_resolver.py     # 25 tests (detect, resolve, resolve_all + helpers, Sprint 7.3)
│       ├── application/
│       │   ├── test_create_task.py      # 5 tests (decompose, save, status, deps)
│       │   ├── test_execute_task.py     # 11 tests (success, fallback, failed, cost + insight extraction, Sprint 7.3)
│       │   ├── test_route_to_engine.py  # 27 tests (list/get/execute happy/fallback/chain + context injection, Sprint 4.3+4.6)
│       │   ├── test_install_tool.py     # 9 tests (search, install, install_by_name, uninstall, list, Sprint 5.3)
│       │   ├── test_discover_tools.py   # 9 tests (suggest, dedup, sort, max_results, context, Sprint 5.4)
│       │   ├── test_manage_ollama.py    # 10 tests (status, pull, delete, switch, info, Sprint 5.5)
│       │   ├── test_analyze_execution.py # AnalyzeExecution (record, stats, failure patterns, Sprint 6.1)
│       │   ├── test_update_strategy.py   # UpdateStrategy (prefs, rules, full update, Sprint 6.3)
│       │   ├── test_systemic_evolution.py # SystemicEvolution (gaps, tools, report, Sprint 6.4)
│       │   └── test_extract_insights.py # 15 tests (extract, store, conflict resolve, task state update, Sprint 7.3)
│       ├── infrastructure/
│       │   ├── test_ollama_manager.py   # 20 tests (health, list, ensure, recommend + delete, info, running, Sprint 5.5)
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
│       │   ├── test_mcp_client.py      # 21 tests (port, connect, tools, resources, adapter, discover, Sprint 3.8)
│       │   ├── test_adk_driver.py     # 17 tests (construct, available, run_task, capabilities, Sprint 4.5)
│       │   ├── test_knowledge_loader.py # 13 tests (construction, load, format, missing files, Sprint 4.6)
│       │   ├── test_mcp_registry_client.py # 14 tests (search, parse, error handling, Sprint 5.2)
│       │   ├── test_tool_installer.py  # 11 tests (install, safety gate, uninstall, tracking, Sprint 5.3)
│       │   ├── test_execution_record_repo.py # InMemoryExecutionRecordRepository CRUD (Sprint 6.1)
│       │   ├── test_strategy_store.py  # StrategyStore JSONL I/O (Sprint 6.3)
│       │   ├── test_shared_task_state_repo.py # 16 tests (CRUD, list_active, append, Sprint 7.2)
│       │   ├── test_context_adapters.py # 104 tests (6 adapters × inject/extract, Sprint 7.2)
│       │   └── test_insight_extractor.py # 13 tests (extract, dedup, reclassify, tags, Sprint 7.3)
│       └── interface/
│           ├── test_api.py              # 22 tests (CRUD, WebSocket, CORS, models, cost, memory)
│           ├── test_api_e2e.py          # 12 tests (HTTP round-trip: POST→execute→GET→verify)
│           ├── test_cli.py              # 20 tests (3 foundation + 9 task + 5 model + 3 cost)
│           ├── test_engine_api.py       # 12 tests (list/get/run engines, validation, Sprint 4.3)
│           ├── test_engine_cli.py       # 8 tests (engine list/run, flags, validation, Sprint 4.3)
│           ├── test_marketplace_api.py  # 10 tests (search, install, list, uninstall, validation, Sprint 5.3)
│           ├── test_marketplace_cli.py  # 6 tests (search, install, list, suggest, uninstall, Sprint 5.3)
│           ├── test_evolution_api.py    # Evolution API endpoints (stats, failures, update, evolve, Sprint 6.1)
│           ├── test_evolution_cli.py    # Evolution CLI commands (stats, failures, update, report, Sprint 6.1)
│           ├── test_cognitive_api.py   # 19 tests (state CRUD, affinity, handoff, insights, Sprint 7.5)
│           ├── test_cognitive_cli.py   # 11 tests (state, affinity, insights CLI commands, Sprint 7.5)
│           ├── test_benchmark_api.py  # 7 tests (run/continuity/dedup endpoints, field validation, Sprint 7.6)
│           └── test_benchmark_cli.py  # 4 tests (run/continuity/dedup/help CLI commands, Sprint 7.6)
│   └── integration/
│       ├── test_live_smoke.py           # 10 tests (real Ollama + real filesystem)
│       ├── test_cloud_llm.py            # 11 tests (Anthropic + OpenAI + Gemini + cost + routing)
│       ├── test_e2e_pipeline.py         # 5 tests (Goal → Decompose → DAG → Result)
│       ├── test_memory_hierarchy_full.py # 16 tests (L1-L4 full lifecycle, compression interplay, edge cases, cross-component, Sprint 3.10)
│       ├── test_agent_engines.py        # 37 tests (6 engines live + routing + fallback + availability, Sprint 4.4-4.5)
│       └── test_ucl_cross_engine.py    # 13 tests (handoff pipeline + adapter fidelity + insight roundtrip + affinity + conflict + benchmarks, Sprint 7.6)
│
├── benchmarks/                      # Sprint 7.6: Context continuity + dedup accuracy benchmarks
│   ├── __init__.py
│   ├── context_continuity.py       # AdapterScore, ContinuityResult, run_benchmark() — target >85%
│   ├── dedup_accuracy.py           # DedupScore, DedupResult, run_benchmark() — target >50%
│   └── runner.py                   # BenchmarkSuiteResult, run_all() — unified benchmark runner
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
| `TaskType` | `str, Enum` | simple_qa, code_generation, ..., long_running_dev, workflow_pipeline |
| `AgentEngineType` | `str, Enum` | openhands, claude_code, gemini_cli, codex_cli, adk, ollama |
| `SafetyTier` | `IntEnum` | UNSAFE(0), EXPERIMENTAL(1), COMMUNITY(2), VERIFIED(3) |
| `EvolutionLevel` | `str, Enum` | tactical, strategic, systemic |

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
├── mcp_client.py           # MCP client connections (Sprint 3.8)
├── agent_engine.py         # Agent execution engine interface (Sprint 4.1)
├── tool_registry.py        # MCP tool registry search (Sprint 5.2)
├── tool_installer.py       # Tool install/uninstall (Sprint 5.3)
├── execution_record_repository.py # Execution record CRUD + stats (Sprint 6.1)
├── shared_task_state_repository.py # Shared task state CRUD + list_active (Sprint 7.1)
├── insight_extractor.py    # Insight extraction from agent output (Sprint 7.1)
└── context_adapter.py      # Bidirectional UCL ↔ engine context translation (Sprint 7.2)
```

### 4. Services are Pure Functions

Domain services (`risk_assessor.py`, `approval_engine.py`, `semantic_fingerprint.py`, `forgetting_curve.py`, `delta_encoder.py`, `hierarchical_summarizer.py`, `agent_engine_router.py`, `tool_safety_scorer.py`, `failure_analyzer.py`, `tactical_recovery.py`) have:
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
| **Unit/Domain** | `tests/unit/domain/` | None | ~0.03s | Entities, value objects, services, LSH fingerprint, forgetting curve, delta encoder, hierarchical summarizer, agent engine router, tool safety scorer, failure analyzer, tactical recovery |
| **Unit/Application** | `tests/unit/application/` | Mocked ports | Fast | Use case orchestration, cost estimator, planning, engine routing, tool install, tool discovery, Ollama management, analyze execution, update strategy, systemic evolution |
| **Unit/Infra** | `tests/unit/infrastructure/` | Mocked ports | ~1.2s | LLM gateway, cost, task graph, LAEE, memory, PG repos, Celery, browser/gui/cron, semantic search, forgetting curve, delta encoder, hierarchical summarizer, context bridge, MCP server/client, ADK driver, knowledge loader, MCP registry, tool installer, execution record repo, strategy store |
| **Unit/Interface** | `tests/unit/interface/` | Mock container | ~1.4s | API, WebSocket, CORS, CLI commands, plan endpoints, engine endpoints, marketplace endpoints, evolution endpoints |
| **Integration** | `tests/integration/` | Ollama running | ~18s (37 tests) | Real LLM inference, real filesystem, L1-L4 memory hierarchy, agent engine live tests |
| **E2E** | `tests/e2e/` | Full stack | Slowest | API/CLI → Use Case → DB round-trips |

### TDD Process

```
1. Red:      Write test that fails
2. Green:    Write minimum code to pass
3. Refactor: Clean up while tests protect

Current: 1162 unit tests + 37 integration tests = 1199 total, 100% pass (~5s)
Lint: ruff check 0 errors, ruff format 245 files clean
Default model: qwen3-coder:30b (thinking mode disabled via extra_body)
Cloud providers verified: Anthropic (Haiku/Sonnet), OpenAI (o4-mini/o3), Gemini (3-flash/3-pro)
```

### Phase 3 Verification (2026-02-26)

```
✓ Unit tests:       699 passed (3.51s)
✓ Integration tests: 16 passed (0.22s) — L1-L4 full lifecycle
✓ Lint:             ruff check 0 errors, ruff format 169 files clean
✓ FastAPI app:      21 routes (incl. GET /api/memory/export)
✓ AppContainer DI:  MemoryHierarchy, ContextZipper, DeltaEncoderManager,
                    ForgettingCurveManager, ContextBridge, MCPClient — all wired
✓ MCP Server:       6 tools + 1 resource + 1 template registered
✓ CLI:              morphic {task,plan,model,cost,mcp} — 5 subcommands
✓ Context Bridge:   4 platforms output verified (claude_code, chatgpt, cursor, gemini)
```

### Phase 4 Verification — Sprint 4.1–4.3 (2026-03-02)

```
✓ Unit tests:       864 passed (6.49s)
✓ Lint:             ruff check 0 errors, ruff format 192 files clean
✓ Domain:           AgentEngineType (6), AgentEnginePort ABC, AgentEngineRouter (pure static)
✓ Drivers:          5 implementations (Ollama, ClaudeCode, Codex, Gemini, OpenHands)
✓ Use case:         RouteToEngineUseCase — list/get/execute with fallback chain
✓ API:              GET /api/engines, GET /api/engines/{type}, POST /api/engines/run
✓ CLI:              morphic engine {list, run} — 6 subcommands total
✓ AppContainer DI:  agent_drivers dict + RouteToEngineUseCase wired
✓ New tests:        43 (23 use case + 12 API + 8 CLI)
```

### Phase 4 Verification — Sprint 4.4 Integration Tests (2026-03-03)

```
✓ Unit tests:       864 passed (3.89s), 0 regressions
✓ Integration tests: 30 total (18 passed, 12 skipped, 0 failed)
✓ Lint:             ruff check 0 errors, ruff format 193 files clean
✓ Test classes:     9 classes covering all 5 engines + routing + fallback
✓ Availability:     is_available() verified for all 5 engines
✓ Disabled drivers: ClaudeCode/Codex disabled=False → proper failure result
✓ Skip pattern:     Graceful skip on env/auth issues (nested session, 401)
✓ Cross-engine:     Same task comparison table with success/duration/cost
✓ Routing:          budget=0→OLLAMA, SIMPLE_QA→OLLAMA, COMPLEX→fallback chain
✓ Fallback:         LONG_RUNNING_DEV→OpenHands or fallback if unavailable

Completion Criteria:
  1. ✓ Same task across multiple engines with result comparison
  2. ✓ Task-type-based automatic engine selection (5 routing tests)
  3. ✓ Availability check + fallback in live environment (fallback chain)
```

### Phase 4 Verification — Sprint 4.5-4.6 (2026-03-05)

```
✓ Unit tests:       898 passed (3.53s), 0 regressions
✓ Lint:             ruff check 0 errors, ruff format 197 files clean

Sprint 4.5 — ADK Driver:
  ✓ ADKDriver:        google-adk optional dep with try-import guard (_ADK_AVAILABLE)
  ✓ LlmAgent→Runner:  run_async wrapper with InMemorySessionService
  ✓ Capabilities:     2M tokens, parallel=True, mcp=True, streaming=True, $0/hr
  ✓ Container wired:  AgentEngineType.ADK → ADKDriver in AppContainer
  ✓ Config:           adk_enabled, adk_default_model settings
  ✓ Integration:      TestADKEngineLive (3 tests) + availability detection
  ✓ New tests:        17 unit (4 classes: construct, available, run_task, capabilities)

Sprint 4.6 — Knowledge File Management:
  ✓ KnowledgeFileLoader:  engine→file mapping (CLAUDE.md, AGENTS.md, llms-full.txt)
  ✓ Context injection:     RouteToEngineUseCase.execute(context=...) prepends to task
  ✓ API:                   EngineRunRequest.context field → POST /api/engines/run
  ✓ CLI:                   --context / -c flag on morphic engine run
  ✓ Backward compatible:   No ABC changes, no driver signature changes
  ✓ New tests:             13 knowledge loader + 4 context injection = 17

Phase 4 COMPLETE: 6 drivers, router, use case, API/CLI, knowledge injection
  Total new tests: 34 (Sprint 4.5: 17 unit + Sprint 4.6: 17 unit)
```

### Phase 5 Verification — Sprint 5.1–5.6 (2026-03-05)

```
✓ Unit tests:       988 passed (4.90s), 0 regressions
✓ Lint:             ruff check 0 errors, ruff format 221 files clean

Sprint 5.1 — Tool Safety Scorer:
  ✓ SafetyTier:          IntEnum (UNSAFE=0, EXPERIMENTAL=1, COMMUNITY=2, VERIFIED=3)
  ✓ ToolCandidate:       Pydantic entity (strict=True, validate_assignment=True)
  ✓ ToolSafetyScorer:    score() — publisher trust (0.40) + transport (0.25) + popularity (0.15) + metadata (0.20)
  ✓ Suspicious patterns: Forced UNSAFE for shell_exec, eval, rm -rf patterns
  ✓ New tests:           22 (8 entity + 14 scorer)

Sprint 5.2 — MCP Registry Search:
  ✓ ToolRegistryPort:    ABC + ToolSearchResult dataclass
  ✓ MCPRegistryClient:   httpx GET registry.modelcontextprotocol.io, auto-score results
  ✓ Error handling:      Returns empty ToolSearchResult on HTTP failure (never raises)
  ✓ Response parsing:    Handles both list and dict formats
  ✓ New tests:           14

Sprint 5.3 — Tool Installer + Use Case + API/CLI:
  ✓ ToolInstallerPort:   ABC + InstallResult dataclass
  ✓ MCPToolInstaller:    Safety gate (refuses UNSAFE), subprocess npm/pip, in-memory tracking
  ✓ InstallToolUseCase:  search + score + install coordination
  ✓ API endpoints:       GET /search, POST /install, GET /installed, DELETE /{name}
  ✓ CLI commands:        morphic marketplace {search|install|list|uninstall}
  ✓ Config:              marketplace_enabled, marketplace_auto_install, marketplace_safety_threshold, mcp_registry_url
  ✓ New tests:           36 (11 installer + 9 use case + 10 API + 6 CLI)

Sprint 5.4 — Auto Tool Discoverer:
  ✓ FailureAnalyzer:     Regex error pattern → search query mapping (pure domain)
  ✓ DiscoverToolsUseCase: suggest_for_failure() — top-3 queries, dedup, sort by score
  ✓ API:                 POST /api/marketplace/suggest
  ✓ CLI:                 morphic marketplace suggest
  ✓ New tests:           21 (12 analyzer + 9 use case)

Sprint 5.5 — Ollama Model Manager Extended:
  ✓ OllamaManager:       +delete_model(), +model_info(), +get_running_models()
  ✓ ManageOllamaUseCase: status/pull/delete/info/switch_default
  ✓ API:                 POST /pull, DELETE /{name}, POST /switch, GET /running, GET /{name}/info
  ✓ CLI:                 morphic model {delete|switch|info}
  ✓ New tests:           16 (6 manager + 10 use case)

Sprint 5.6 — Marketplace UI (Next.js):
  ✓ SearchBar:           Debounced search input (400ms)
  ✓ ToolCard:            Search result card (SafetyBadge + InstallButton)
  ✓ SafetyBadge:         Color-coded safety tier (4 tiers)
  ✓ InstallButton:       Install/uninstall with confirm dialog
  ✓ Marketplace page:    Search + browse + installed tab
  ✓ Models page:         Pull/delete/switch + running status display
  ✓ Navigation:          Header links to Marketplace + Models

Sprint 5.7a — Model Management Test Coverage:
  ✓ _MockContainer:    +manage_ollama mock in test_api.py and test_cli.py
  ✓ API tests (9):     pull/delete/switch/info success+failure, running models
  ✓ CLI tests (6):     delete/switch/info success+failure

Sprint 5.7b — Auto-Discovery Trigger on Task Failure:
  ✓ ExecuteTaskUseCase: +discover_tools optional param, +_safe_suggest_tools()
  ✓ Fire-and-forget:   Triggered on FAILED/FALLBACK, never blocks execution
  ✓ Container wiring:  discover_tools=self.discover_tools (1 line)
  ✓ New tests (8):     suggests on failure, not on success, on fallback,
                        failure doesn't block, None safe, combined errors,
                        passes task goal, skipped when no errors

Phase 5 COMPLETE: Safety scoring, MCP registry, tool installer, auto discoverer, Ollama manager, marketplace UI, model mgmt tests, auto-discovery trigger
  Total new tests: ~113 (Sprint 5.1: 22 + 5.2: 14 + 5.3: 36 + 5.4: 21 + 5.5: 16 + 5.7: 23)
  New API endpoints: 8, New CLI commands: 8, New settings: 4
```

### Phase 6 Verification — Sprint 6.1–6.5 (2026-03-05)

```
✓ Unit tests:       1162 passed (4.82s), 0 failures (MCP server tests fixed)
✓ Lint:             ruff check 0 errors, ruff format 245 files clean

Sprint 6.1 — Execution Recorder + Domain Foundation:
  ✓ ExecutionRecord:   Pydantic entity (strict=True) — task_type, engine, model, success, cost, cache_hit_rate, user_rating
  ✓ EvolutionLevel:    str Enum (tactical, strategic, systemic)
  ✓ ExecutionRecordRepository: ABC + ExecutionStats dataclass (success_rate, avg_cost, total_count)
  ✓ InMemoryExecutionRecordRepository: List-backed CRUD + filtering + stats aggregation
  ✓ AnalyzeExecutionUseCase: record() + get_stats() + get_failure_patterns() + get_model_distribution()

Sprint 6.2 — Tactical Recovery (Level 1):
  ✓ TacticalRecovery:  Pure domain service — find_alternative(), create_rule_from_recovery(), rank_rules()
  ✓ Pattern matching:  Regex-based error→alternative tool mapping
  ✓ RecoveryRule:      error_pattern + alternative_tool + success_rate + sample_size

Sprint 6.3 — Strategy Updater (Level 2):
  ✓ Strategy entities: RecoveryRule, ModelPreference, EnginePreference (all strict Pydantic)
  ✓ StrategyStore:     JSONL persistence (recovery_rules.jsonl, model_preferences.jsonl, engine_preferences.jsonl)
  ✓ UpdateStrategyUseCase: update_model_preferences() + update_engine_preferences() + update_recovery_rules() + run_full_update()
  ✓ Min samples filter: Configurable (default 10) to avoid overfitting

Sprint 6.4 — Systemic Evolver (Level 3):
  ✓ SystemicEvolutionUseCase: identify_tool_gaps() + suggest_tools_for_gaps() + run_evolution()
  ✓ Composes:         AnalyzeExecution + UpdateStrategy + DiscoverTools (Phase 5)
  ✓ EvolutionReport:  level + strategy_update + tool_gaps_found + tools_suggested + summary

Sprint 6.5 — Evolution Interface (API + CLI + UI):
  ✓ API endpoints:    GET /stats, GET /failures, GET /preferences, POST /update, POST /evolve
  ✓ CLI commands:     morphic evolution {stats|failures|update|report}
  ✓ UI page:          Evolution dashboard scaffold (stats, failures, preferences)
  ✓ AppContainer DI:  execution_record_repo + strategy_store + 3 use cases wired
  ✓ Config:           evolution_enabled, evolution_strategy_dir, evolution_min_samples

Phase 6 COMPLETE: 3-tier self-evolution (tactical recovery + strategy learning + systemic evolution)
  Total new tests: ~174 (domain + application + infrastructure + interface)
  New API endpoints: 5, New CLI commands: 4, New settings: 4
  Also fixed: 19 pre-existing test_mcp_server.py failures (_FakeSettings updated)
```

### Phase 7 Verification — Sprint 7.1 (2026-03-10)

```
✓ Unit tests:       1230 passed (6.18s), 0 failures
✓ New tests:        68 (cognitive domain)
✓ Lint:             ruff check 0 errors, ruff format 251 files clean

Sprint 7.1 — UCL Domain Foundation:
  ✓ CognitiveMemoryType:         str Enum (episodic, semantic, procedural, working)
  ✓ Decision:                    Pydantic entity — description, rationale, agent_engine, confidence [0,1]
  ✓ AgentAction:                 Pydantic entity — agent_engine, action_type (str), cost_usd, duration
  ✓ SharedTaskState:             Pydantic entity — task_id, decisions[], artifacts{}, blockers[], agent_history[]
                                 Methods: add_decision, add_action, add_artifact, add/remove_blocker
                                 Properties: last_agent, total_cost_usd
  ✓ AgentAffinityScore:          Pydantic entity — engine, topic, familiarity/recency/success/cost [0,1]
  ✓ SharedTaskStateRepository:   ABC port (7 methods: save, get, list_active, update_decisions/artifacts, append_action, delete)
  ✓ InsightExtractorPort:        ABC port + ExtractedInsight dataclass
  ✓ AgentAffinityScorer:         Pure static service — score()/rank()/select_best() with 4-factor weighting
```

### Phase 7 Verification — Sprint 7.3 (2026-03-11)

```
✓ Unit tests:       1438 passed (4.40s), 0 failures
✓ New tests:        88 (30 domain + 15 application + 13 infrastructure + 5 execute_task extension + 25 domain)
✓ Lint:             ruff check 0 errors, ruff format 272 files clean

Sprint 7.3 — Insight Extraction Pipeline:
  ✓ MemoryClassifier:             Pure static service — classify()/classify_with_confidence()
                                  4 regex patterns (PROCEDURAL > SEMANTIC > WORKING > EPISODIC priority)
                                  Confidence: min(0.3 + hits * 0.2, 0.9)
  ✓ ConflictResolver:             Pure static service — detect_conflicts()/resolve()/resolve_all()
                                  3 criteria: different engine + Jaccard overlap ≥ 0.4 + negation contrast
                                  Resolution: higher confidence wins, tie → first (stable)
                                  ConflictPair dataclass for conflict audit trail
  ✓ InsightExtractor:             InsightExtractorPort impl — adapter lookup + dedup + reclassification
                                  Dedup: normalised content (strip+lowercase)
                                  Low confidence (<0.5) → MemoryClassifier override
  ✓ ExtractInsightsUseCase:       Full pipeline: extract → ConflictResolver.resolve_all → MemoryEntry storage → SharedTaskState update
                                  CognitiveMemoryType → MemoryType mapping:
                                    EPISODIC/PROCEDURAL → L2_SEMANTIC, SEMANTIC → L3_FACTS, WORKING → L1_ACTIVE
                                  "decision" tag → state.add_decision(), "artifact"/"file" tag → state.add_artifact()
  ✓ ExecuteTaskUseCase:           +extract_insights optional param, _safe_extract_insights hook (try/except, never blocks)
                                  Gathers subtask results + errors into combined output
  ✓ AppContainer wiring:          6 context adapters → InsightExtractor → ExtractInsightsUseCase → ExecuteTaskUseCase
                                  SharedTaskStateRepository (in-memory) added to container
```

### Phase 7 Verification — Sprint 7.4 (2026-03-11)

```
✓ Unit tests:       1528 passed (5.0s), 0 failures
✓ New tests:        90 (6 port + 17 domain + 18 infra + 16 route_to_engine + 23 handoff + 10 router)
✓ Lint:             ruff check 0 errors, ruff format 280 files clean

Sprint 7.4 — Affinity-Aware Routing + Task Handoff:
  ✓ AgentAffinityRepository:      New ABC port — 5 methods (get, get_by_topic, get_by_engine, upsert, list_all)
                                  Separate from SharedTaskStateRepository (engine×topic keyed)
  ✓ TopicExtractor:               Pure static service — keyword-based topic extraction
                                  10 topics (frontend/backend/database/devops/testing/security/ml/data/docs/refactoring)
                                  Falls back to "general" if no match
  ✓ select_with_affinity():       New AgentEngineRouter method — affinity-aware reranking
                                  Base chain + AgentAffinityScorer.rank() + boost_threshold gate
                                  OLLAMA always last, budget=0 → [OLLAMA], dedup preserved
  ✓ InMemoryAffinityRepository:   Dict keyed by (engine, topic) tuple
  ✓ JSONLAffinityStore:           JSONL file persistence (lazy-load + full-overwrite on upsert)
  ✓ RouteToEngineUseCase:         Extended with affinity-aware routing + adapter context injection +
                                  post-success affinity updates + action recording to SharedTaskState
                                  All new params optional (None) → full backward compatibility
  ✓ HandoffTaskUseCase:           Cross-agent handoff: load state → record handoff action → add decision →
                                  merge artifacts → adapter inject → execute via RouteToEngine →
                                  record received_handoff → optional insight extraction → persist
  ✓ AppContainer wiring:          InMemoryAffinityRepo + RouteToEngine(adapters, affinity, state) +
                                  HandoffTaskUseCase(route_to_engine, state, adapters, insights)
  ✓ Settings:                     +affinity_min_samples (3) + affinity_boost_threshold (0.6)
```

### Phase 7 Verification — Sprint 7.5 (2026-03-11)

```
✓ Unit tests:       1558 passed (5.31s), 0 failures
✓ New tests:        30 (19 API + 11 CLI)
✓ Lint:             ruff check 0 errors, ruff format clean

Sprint 7.5 — UCL API + CLI + UI:
  ✓ API schemas:          DecisionResponse, AgentActionResponse, SharedTaskStateResponse (with from_state()),
                          SharedTaskStateListResponse, AffinityScoreResponse (with from_affinity()),
                          AffinityListResponse, HandoffRequestSchema, HandoffResponseSchema (with from_result()),
                          InsightResponse (with from_insight()), InsightListResponse, InsightExtractRequest
  ✓ API routes:           GET /api/cognitive/state (list), GET /api/cognitive/state/{task_id},
                          DELETE /api/cognitive/state/{task_id}, GET /api/cognitive/affinity (?topic, ?engine),
                          POST /api/cognitive/handoff, POST /api/cognitive/insights/extract
  ✓ CLI commands:         morphic cognitive {state|delete|affinity|handoff|insights}
                          state: list all or show by task_id arg
                          affinity: --topic/-t, --engine/-e filters
                          handoff: --task-id, --source, --reason, --target, --budget
                          insights: --task-id, --engine, --output
  ✓ CLI formatters:       print_shared_state() (rich Tree), print_state_list_table() (rich Table),
                          print_affinity_table() (rich Table, color-coded scores)
  ✓ UI page:              /cognitive — tab UI (Shared States + Affinity Scores)
                          StateCard (task_id, last_agent, counts, cost)
                          StateDetail (decisions, artifacts, blockers, agent history)
                          AffinityTable (engine, topic, score, success rate, samples)
  ✓ API client:           getCognitiveStates(), getCognitiveState(), deleteCognitiveState(),
                          getAffinityScores() — TypeScript types + fetch wrappers
  ✓ Navigation:           Header link to Cognitive, version bumped to v0.5.0-alpha
  ✓ Tests:                19 API tests (state CRUD, affinity filter, handoff valid/invalid, insights)
                          11 CLI tests (state list/show, delete, affinity filter, insights invalid)
                          Patch target: interface.cli.commands.cognitive._get_container
```

### Phase 7 Verification — Sprint 7.6 (2026-03-11)

```
✓ Unit tests:       1569 passed (6.02s), 0 failures
✓ Integration tests: 13 new (50 total), 0 failures
✓ New unit tests:   11 (7 API + 4 CLI)
✓ Lint:             ruff check 0 errors, ruff format clean

Sprint 7.6 — Integration Testing + Benchmarks:
  ✓ Cross-engine integration tests:
      TestFullHandoffPipeline       3 tests (state preservation, insight extraction, chained A→B→C)
      TestContextAdapterFidelity    3 tests (nonempty context, extract insights, roundtrip key info)
      TestInsightExtractionRoundTrip 2 tests (stored in memory, updates task state)
      TestAffinityLearning          2 tests (updates after execution, builds with multiple runs)
      TestConflictResolution        1 test (conflicting insights resolved by confidence)
      TestContextContinuityBenchmark 2 tests (continuity >85%, dedup >50%)
  ✓ Context continuity benchmark:   97.2% overall (target >85%)
      AdapterScore dataclass (engine, decisions/artifacts/blockers injected/found, context_length)
      ContinuityResult (adapter_scores, overall_score property)
      _build_reference_state() — 5 decisions, 4 artifacts, 3 blockers, 3 agent actions
  ✓ Memory dedup benchmark:         57.1% overall (target >50%)
      DedupScore (scenario, engine_a/b, raw counts, deduped_count, dedup_rate)
      DedupResult (scores, overall_accuracy property)
      3 scenarios: overlapping_facts, unique_outputs, case_variation
  ✓ Benchmark runner:               BenchmarkSuiteResult, async run_all()
  ✓ Benchmark API:                  POST /api/benchmarks/{run|continuity|dedup}
      BenchmarkResultResponse schema (overall_score, context_continuity, dedup_accuracy, errors, timestamp)
  ✓ Benchmark CLI:                  morphic benchmark {run|continuity|dedup}
      Rich table output with color-coded scores
  ✓ Benchmark UI:                   /benchmarks page (ScoreBar, adapter table, dedup table)
  ✓ API client:                     runBenchmarks(), runContinuityBenchmark(), runDedupBenchmark()
  ✓ Item 4 (A2A protocol):          Skipped — UCL already provides cross-engine communication

PHASE 7 COMPLETE — All 6 sprints done, all completion criteria met.
```

---

## Unified Cognitive Layer (UCL) — Phase 7 Architecture

> **Key Insight**: Individual AI agents are cognitive islands. The real power isn't a better model — it's shared cognition across all agents. UCL is the "connective tissue" that makes Morphic-Agent more than the sum of its parts.

### Why UCL > Simple A2A

| Approach | What it shares | What it doesn't |
|---|---|---|
| A2A Protocol | Task requests | Memory, decisions, context, artifacts |
| MCP | Tool access | Reasoning, context, task state |
| **UCL** | **Memory + Tasks + Decisions + Artifacts + Context** | — |

### UCL Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   Unified Cognitive Layer (UCL)                  │
│                                                                 │
│  ┌────────────────────┐        ┌────────────────────┐          │
│  │  Shared Task State  │        │  Shared Memory      │          │
│  │  goals, subtasks,   │        │  (4-type hierarchy) │          │
│  │  decisions, artifacts│        │  episodic, semantic, │          │
│  │  blockers, history  │        │  procedural, working│          │
│  └────────────────────┘        └────────────────────┘          │
│                                                                 │
│  ┌────────────────────┐        ┌────────────────────┐          │
│  │  Context Adapters   │        │  Insight Extractor  │          │
│  │  (bidirectional,    │        │  (post-execution,   │          │
│  │   per-engine)       │        │   auto-store)       │          │
│  └────────────────────┘        └────────────────────┘          │
│                                                                 │
│  ┌────────────────────┐        ┌────────────────────┐          │
│  │  Agent Affinity     │        │  Conflict Resolver  │          │
│  │  (context-fit)      │        │  (confidence-weight)│          │
│  └────────────────────┘        └────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
         ↕              ↕              ↕              ↕
   Claude Code     Gemini CLI     Codex CLI      Ollama ...
```

### New Domain Components (Phase 7)

**Entities** (`domain/entities/cognitive.py`):
- `Decision` — rationale, agent_engine, confidence, timestamp
- `AgentAction` — action_type, summary, cost_usd
- `SharedTaskState` — task_id, decisions, artifacts, blockers, agent_history
- `AgentAffinityScore` — engine, topic, familiarity, recency, success_rate

**Value Objects** (`domain/value_objects/cognitive.py`):
- `CognitiveMemoryType` — EPISODIC, SEMANTIC, PROCEDURAL, WORKING

**Ports** (new ABCs):
- `SharedTaskStateRepository` — CRUD for shared task state
- `InsightExtractorPort` — extract structured insights from agent output
- `ContextAdapterPort` — bidirectional context translation per engine
- `AgentAffinityRepository` — engine×topic affinity score persistence (Sprint 7.4)

**Domain Services** (new):
- `AgentAffinityScorer` — context-fit scoring (familiarity×0.4 + recency×0.25 + success×0.2 + cost×0.15)
- `ConflictResolver` — confidence-weighted contradiction resolution
- `MemoryClassifier` — auto-classify into 4 memory types
- `TopicExtractor` — keyword-based topic classification for affinity lookup (Sprint 7.4)

**Use Cases** (new/modified):
- `ExtractInsightsUseCase` — post-execution: extract → conflict check → store → update task state
- `HandoffTaskUseCase` — Agent A state capture → context prepare → Agent B delegation (Sprint 7.4)
- `RouteToEngineUseCase` — extended with affinity routing + adapter injection + action recording (Sprint 7.4)

**Infrastructure** (new):
- `InMemoryAgentAffinityRepository` — in-memory affinity store (Sprint 7.4)
- `JSONLAffinityStore` — JSONL persistence for affinity scores (Sprint 7.4)

### Context Adapter Pattern

Each engine speaks a different "context language". Adapters are OS device drivers for AI:

```
UCL Unified Memory ─── ContextAdapter ─── Engine-specific format
                         │
                    ┌────┴────┐
                    │ inject  │  UCL → engine (pre-execution)
                    │ extract │  engine → UCL (post-execution)
                    └─────────┘
```

| Engine | inject() format | extract() targets |
|---|---|---|
| Claude Code | CLAUDE.md + compressed memory | Decisions, code changes, reasoning |
| Codex CLI | AGENTS.md + task context | Code output, test results |
| Gemini CLI | Full context (2M window) | Research findings, analysis |
| ADK | Workflow state | Pipeline outputs, errors |
| OpenHands | REST task + sandbox state | Artifacts, test results |
| Ollama | ContextZipper compressed | Draft outputs |

### Builds on Phase 3 Foundations

| Existing (Phase 3) | UCL Role |
|---|---|
| SemanticFingerprint (LSH) | Dedup across agents (same concept = same hash) |
| ContextZipper | Per-engine compression (token budget varies) |
| ContextBridge | Evolves into Context Adapters |
| ForgettingCurve | UCL memory lifecycle management |
| DeltaEncoder | Shared state change tracking |
| HierarchicalSummarizer | Multi-level views for different context windows |
| L1-L4 Memory Hierarchy | 4 memory types map to existing layers |
