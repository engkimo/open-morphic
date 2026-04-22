# Fractal Recursive Engine — Implementation Plan

> Approved: 2026-03-23
> Based on: docs/NEXT_DESIGN.md
> Status: Sprint 15.1-15.5 DONE, 15.6-15.7 PLANNED

---

## Architecture Decision: WRAP, Not Replace

`FractalTaskEngine` wraps the existing `LangGraphTaskEngine` instead of replacing it.

```
FractalTaskEngine (NEW: recursion + eval gates + candidate space)
    │
    └── Terminal node execution → LangGraphTaskEngine (EXISTING: engine routing + ReAct + artifacts)
```

**Rationale:**
- `LangGraphTaskEngine` is 884 lines of proven code (engine routing, ReAct, artifact chaining, discussion, cost tracking)
- Fractal engine operates at a higher abstraction level (recursive planning + evaluation gates + failure propagation)
- Both implement the same `TaskEngine` port → config-based selection
- Default remains `langgraph` (zero impact on existing behavior)

---

## Key Architectural Decisions

| # | Decision | Detail |
|---|----------|--------|
| AD-1 | Engine selection | Config `execution_engine: "langgraph" \| "fractal"`. Default: langgraph |
| AD-2 | Planner | Separate from IntentAnalyzer. Generates `CandidateNode[]` with scores + conditions |
| AD-3 | Gate ① cost | Ollama first ($0) + optional cloud. ~$0-0.01 per evaluation |
| AD-4 | Gate ② thresholds | OK ≥ 0.7 / 0.4 ≤ RETRY < 0.7 / REPLAN < 0.4 (configurable) |
| AD-5 | Max recursion depth | Default 3 levels (configurable via `fractal_max_depth`) |
| AD-6 | Learning | MVP: in-memory error pattern recording. Full GraphRAG deferred to post-stability |

---

## Sprint Plan

### Dependency Graph

```
15.1 (DONE: domain model)
  ├── 15.2 (Planner)    ─┐
  ├── 15.3 (Gate ①)     ─┼── 15.5 (FractalTaskEngine) ── 15.6 (API integration)
  └── 15.4 (Gate ②)     ─┘                             └── 15.7 (Learning)
```

15.2, 15.3, 15.4 are independent of each other. All feed into 15.5.

### Summary Table

| Sprint | Scope | New Files | Modified Files | Tests | Risk | Status |
|--------|-------|-----------|----------------|-------|------|--------|
| 15.1 | Domain model (entities, VOs, ports, services) | 8 + 2 tests | 4 __init__.py | +48 | Low | ✅ DONE (TD-099) |
| 15.2 | LLM Planner (`PlannerPort` impl) | 2 + 1 test | 0 | +15 | Low | ⬜ TODO |
| 15.3 | Gate ① Plan Evaluator + aggregator | 2 + 2 tests | 0 | +34 | Medium | ✅ DONE (TD-101) |
| 15.4 | Gate ② Result Evaluator + decision maker | 2 + 2 tests | 1 | +57 | Low | ✅ DONE (TD-102) |
| 15.5 | FractalTaskEngine core (recursion loop) | 2 + 2 tests | 2 | +34 | **High** | ✅ DONE (TD-103) |
| 15.6 | API integration + config wiring | 0 + 1 test | 3 | +8 | Low | ⬜ TODO |
| 15.7 | Learning foundation (error patterns) | 4 + 2 tests | 1 | +14 | Low | ⬜ TODO |
| **Total** | | **20 + 10 tests** | **10** | **+160** | | |

---

## Sprint Details

### Sprint 15.2 — LLM Planner (TD-100)

**Scope:** Implement `PlannerPort` — LLM-powered candidate node generation.

**Create:**
- `infrastructure/fractal/__init__.py`
- `infrastructure/fractal/llm_planner.py` — `LLMPlanner(PlannerPort)`
  - Uses `LLMGateway.complete()` → structured JSON → `CandidateNode[]`
  - Forward (start→goal) and backward (goal→start) generation
  - Configurable candidate count (default 3)
  - Follows existing `IntentAnalyzer` JSON extraction pattern
- `tests/unit/infrastructure/test_llm_planner.py` — ~15 tests

**Integration:** Depends on `LLMGateway`, `PlannerPort`, `CandidateNode`, `PlanNode`

---

### Sprint 15.3 — Gate ① Plan Evaluator (TD-101)

**Scope:** Multi-LLM plan evaluation with cost optimization.

**Create:**
- `infrastructure/fractal/llm_plan_evaluator.py` — `LLMPlanEvaluator(PlanEvaluatorPort)`
  - Multi-LLM strategy: N models evaluate, aggregated scores
  - Each scores: completeness, feasibility, safety (0.0-1.0)
  - Ollama first (free), cloud optional
- `domain/services/plan_eval_aggregator.py` — pure aggregation logic
  - Weighted average across evaluators
  - Consensus threshold for approval
- `tests/unit/infrastructure/test_llm_plan_evaluator.py` — ~12 tests
- `tests/unit/domain/test_plan_eval_aggregator.py` — ~10 tests

---

### Sprint 15.4 — Gate ② Result Evaluator (TD-102)

**Scope:** Post-execution quality assessment with OK/RETRY/REPLAN decisions.

**Create:**
- `infrastructure/fractal/llm_result_evaluator.py` — `LLMResultEvaluator(ResultEvaluatorPort)`
  - Scores: accuracy, validity, goal_alignment (0.0-1.0)
  - Uses cheapest available model (Ollama preferred)
- `domain/services/result_eval_decision_maker.py` — pure score-to-decision logic
  - OK ≥ 0.7, 0.4 ≤ RETRY < 0.7, REPLAN < 0.4
  - Configurable per-axis weights
- `tests/unit/infrastructure/test_llm_result_evaluator.py` — ~10 tests
- `tests/unit/domain/test_result_eval_decision_maker.py` — ~10 tests

---

### Sprint 15.5 — FractalTaskEngine Core (TD-103) ⚠️ Highest Risk

**Scope:** The recursive execution engine — central integration point.

**Create:**
- `infrastructure/fractal/fractal_engine.py` — `FractalTaskEngine(TaskEngine)`
  - `decompose(goal)`: PlannerPort → Gate ① → visible nodes as SubTask[]
  - `execute(task)`: recursive loop:
    1. `NestingDepthController.should_terminate()`
    2. Terminal → delegate to `LangGraphTaskEngine` (single subtask)
    3. Expandable → spawn sub-engine (recursion)
    4. `ResultEvaluatorPort.evaluate()` (Gate ②)
    5. OK: advance / RETRY: re-execute / REPLAN: `FailurePropagator`
    6. Conditional node activation via `CandidateSpaceManager`
- `infrastructure/fractal/node_executor.py` — `PlanNode` ↔ `SubTask` bridge
- `tests/unit/infrastructure/test_fractal_engine.py` — ~25 tests
- `tests/unit/infrastructure/test_node_executor.py` — ~8 tests

**Modify:**
- `shared/config.py` — add fractal settings
- `interface/api/container.py` — conditional wiring

---

### Sprint 15.6 — API Integration (TD-104)

**Scope:** Wire fractal engine into DI container, add config knobs.

**Modify:**
- `shared/config.py` — `execution_engine`, `fractal_max_depth`, `fractal_candidates_per_node`, `plan_eval_models`, `result_eval_ok_threshold`, `result_eval_retry_threshold`
- `interface/api/container.py` — if fractal: create LLMPlanner + evaluators + FractalTaskEngine wrapping LangGraphTaskEngine
- No API route changes (same TaskEngine port)

**Create:**
- `tests/unit/interface/test_fractal_container_wiring.py` — ~8 tests

---

### Sprint 15.7 — Learning Foundation (TD-105)

**Scope:** Minimal viable learning — record error patterns and successful paths.

**Create:**
- `domain/entities/fractal_learning.py` — `ErrorPattern`, `SuccessfulPath`
- `domain/ports/fractal_learning_repository.py` — persistence port
- `infrastructure/fractal/in_memory_learning_repo.py` — in-memory impl
- `domain/services/fractal_learner.py` — extraction logic
- `tests/unit/domain/test_fractal_learner.py` — ~8 tests
- `tests/unit/infrastructure/test_fractal_learning_repo.py` — ~6 tests

**Modify:**
- `infrastructure/fractal/fractal_engine.py` — wire learning hooks

---

## How It Works End-to-End

```
User: "Build a REST API with auth"
  │
  ▼
FractalTaskEngine.decompose("Build a REST API with auth")
  │
  ├── LLMPlanner.generate_candidates()
  │   → 3 candidates: [Setup project, Implement routes, Add auth]
  │   + 2 conditional: [Add tests (if auth fails), Fallback to basic auth]
  │
  ├── Gate ① LLMPlanEvaluator.evaluate()
  │   → Ollama: completeness=0.8, feasibility=0.9, safety=1.0 → APPROVED
  │
  ▼
FractalTaskEngine.execute(task)
  │
  ├── Node 1: "Setup project" (terminal)
  │   ├── NodeExecutor → LangGraphTaskEngine (single subtask)
  │   │   → Engine routing → Claude Code → result
  │   └── Gate ② ResultEvaluator: accuracy=0.9 → OK ✓
  │
  ├── Node 2: "Implement routes" (expandable, level 1)
  │   ├── FractalTaskEngine.execute() [RECURSIVE, level=1]
  │   │   ├── LLMPlanner → [Define models, Create endpoints, Add middleware]
  │   │   ├── Gate ① → APPROVED
  │   │   ├── Execute each sub-node via LangGraphTaskEngine
  │   │   └── Gate ② each → OK ✓
  │   └── Gate ② (level 0): overall → OK ✓
  │
  ├── Node 3: "Add auth" (expandable, level 1)
  │   ├── FractalTaskEngine.execute() [RECURSIVE, level=1]
  │   │   ├── Execute → Gate ② → RETRY (accuracy=0.5)
  │   │   ├── Re-execute → Gate ② → REPLAN (accuracy=0.3)
  │   │   └── FailurePropagator → propagate to level 0
  │   └── Level 0: activate conditional "Fallback to basic auth"
  │       ├── Execute fallback → Gate ② → OK ✓
  │       └── Continue
  │
  └── Final result returned to user
```

---

## Config Settings Reference

```python
# shared/config.py additions
execution_engine: str = "langgraph"        # "langgraph" | "fractal"
fractal_max_depth: int = 3                 # max recursion levels
fractal_candidates_per_node: int = 3       # candidates generated per planning step
fractal_plan_eval_models: str = ""         # comma-separated model list for Gate ①
fractal_plan_eval_min_score: float = 0.5   # minimum score for plan approval
fractal_result_eval_ok_threshold: float = 0.7
fractal_result_eval_retry_threshold: float = 0.4
fractal_max_retries: int = 3              # per-node retry limit
```
