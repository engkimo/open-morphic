# Implementation Plan — Artifact-Aware Engine Routing (TD-197)

> **Spec:** [`spec.md`](spec.md)
> **Status:** draft
> **Estimated effort:** ~1 day (mostly wiring; the classifier + node field + router
> mapping already exist or are small additions)

## Architecture Decisions

### AD-1 — Carry `output_requirement` on `SubTask` (domain), not via side-channel

The signal already lives on `PlanNode` but is lost at `to_subtask`. Add a
nullable field to `SubTask` so it survives into the LangGraph routing
decision. Nullable default keeps every existing caller/test valid (NFR-2).

### AD-2 — Output-aware selection is a pure domain method on `AgentEngineRouter`

`AgentEngineRouter` is already the single source of routing truth (pure,
static, fully tested). Add `select_for_output(output_requirement, *, budget,
task_type)`:

```
budget <= 0                  → OLLAMA            (LOCAL_FIRST guard, AD wins first)
FILE_ARTIFACT                → OPENHANDS         (fallback chain → CLAUDE_CODE → OLLAMA)
CODE_ARTIFACT                → CODEX_CLI         (fallback → CLAUDE_CODE → OLLAMA)
DATA_ARTIFACT                → GEMINI_CLI        (fallback → CLAUDE_CODE → OLLAMA)
TEXT / None                  → select(task_type, budget)   (existing behaviour)
```

No new regex (NFR-1). The mapping is an enum→engine dict, mirroring the
existing `_PRIMARY_ENGINE_MAP`. Fallback chains reuse `_FALLBACK_CHAIN`.

### AD-3 — Consume the signal in `engine.py::_execute_batch` BEFORE the regex path

Current order: `_resolve_engine_type(preferred_model)` → regex auto-route.
New order:

```
1. preferred_model        → _resolve_engine_type        (explicit, unchanged)
2. subtask.output_requirement is artifact → select_for_output(...)   (NEW)
3. else regex auto-route via SubtaskTypeClassifier       (TEXT fallback, unchanged)
```

Only step 2 is added. TEXT/None subtasks are byte-identical to today.

### AD-4 — Per-node requirement via the existing LLM `OutputRequirementClassifier`

Replace the blanket goal-inheritance loop (`fractal_engine.py:318-322`) with
per-terminal-node classification using `OutputRequirementClassifier.classify
(node.description)`. To bound cost (NFR-4 / OQ-2): **only classify when the
goal-level requirement is an artifact** (`goal_output_req != TEXT`); pure-TEXT
goals skip per-node classification entirely (every node inherits TEXT → no
extra LLM calls, no behaviour change for Q&A goals).

The classifier is injected into `FractalTaskEngine` as an optional port-typed
dependency (`OutputRequirementClassifier | None`); when None (unit tests),
the engine falls back to goal-level inheritance (current behaviour).

### AD-5 — Deeper-level + reflection nodes also get classified

Move the per-node classification into the path that materialises terminal
nodes (so level-1/2 and reflection-spawned terminals are covered), not just
the level-0 `visible_nodes` loop. Concretely: classify at
`NodeExecutor`-prep time inside the reflection/expansion cycle, gated by the
same "goal is artifact" flag.

## Data Model

```python
# domain/entities/task.py
class SubTask(BaseModel):
    model_config = ConfigDict(strict=True)
    ...
    preferred_model: str | None = None
    output_requirement: OutputRequirement | None = None   # NEW (additive)
```

```python
# domain/services/agent_engine_router.py  (additive)
_OUTPUT_TO_ENGINE: dict[OutputRequirement, AgentEngineType] = {
    OutputRequirement.FILE_ARTIFACT: AgentEngineType.OPENHANDS,
    OutputRequirement.CODE_ARTIFACT: AgentEngineType.CODEX_CLI,
    OutputRequirement.DATA_ARTIFACT: AgentEngineType.GEMINI_CLI,
}
```

## Contracts

### Router contract

```python
@staticmethod
def select_for_output(
    output_requirement: OutputRequirement | None,
    *,
    budget: float = 0.0,
    task_type: TaskType = TaskType.SIMPLE_QA,
) -> AgentEngineType:
    """Artifact requirement → capable engine. budget<=0 → OLLAMA.
    TEXT/None → delegate to select(task_type, budget)."""
```

`select_with_fallbacks` gains a sibling or is reused via the existing
`_FALLBACK_CHAIN[preferred]` so `RouteToEngineUseCase` keeps its chain
semantics (capable → … → OLLAMA) unchanged.

### Engine wiring contract (engine.py)

```python
engine_type = _resolve_engine_type(subtask.preferred_model)
if engine_type is None and self._route_to_engine is not None:
    req = subtask.output_requirement
    if req is not None and req != OutputRequirement.TEXT:
        engine_type = AgentEngineRouter.select_for_output(
            req, budget=self._task_budget,
            task_type=SubtaskTypeClassifier.infer(subtask.description),
        )
        if engine_type == AgentEngineType.OLLAMA:   # budget<=0 guard
            engine_type = None
    else:
        # existing regex auto-route (unchanged)
        ...
```

## LLM / Engine Routing

- Per-node requirement classifier model: existing gateway routing
  (LOCAL_FIRST → Ollama $0, or Haiku if configured). No new model pinning.
- Artifact engines: FILE→OpenHands, CODE→Codex, DATA→Gemini; all already
  wired in `container._wire_agent_drivers` and confirmed `available=True`
  at server start (2026-06-02 log).

## LAEE touchpoints

N/A for the routing logic. The destination engine (e.g. OpenHands writing a
.pptx) governs its own LAEE actions under the existing approval model.

## Test Strategy

### Unit (DB-free, no live LLM)

- `tests/unit/domain/test_entities.py` — `SubTask.output_requirement`
  defaults None, accepts enum, strict-validates.
- `tests/unit/domain/test_agent_engine_router.py` — `select_for_output`:
  FILE→OPENHANDS, CODE→CODEX, DATA→GEMINI, TEXT→delegates to `select`,
  None→delegates, budget<=0→OLLAMA for every requirement.
- `tests/unit/infrastructure/test_fractal_node_executor.py` —
  `to_subtask` copies `output_requirement` (incl. None).
- `tests/unit/infrastructure/test_task_graph_engine.py` — `_execute_batch`
  routes a FILE subtask to the capable engine (fake `route_to_engine`
  records `preferred_engine`); a TEXT subtask preserves the regex path.
- `tests/unit/infrastructure/test_fractal_engine.py` — per-node
  classification fires only when goal requirement is an artifact; falls
  back to goal-inheritance when classifier is None.

### Integration (live, skip if services down)

- `tests/integration/test_artifact_routing_live.py` — real Ollama for
  classification; assert the "氷川神社スライド" file node selects
  OpenHands/Claude Code (mock the driver execution to keep it $0/fast;
  assert the *selection*, not the full slide build).
- Manual/live E2E (separate, real cost): full slide goal → file produced.

### Regression

- `tests/integration/test_round19_regression.py` — unchanged, must pass
  (bypass semantics untouched).
- Full `tests/unit/` — 0 regressions (`output_requirement=None` path).

## Migration Plan

No DB migration required for routing. (Optional later: persist
`output_requirement` on `cost_logs`/subtask records for observability —
FR-6; deferred if it needs schema change.)

**Code order (each revertable):**
1. Add `SubTask.output_requirement` field + tests.
2. `AgentEngineRouter.select_for_output` + tests.
3. `NodeExecutor.to_subtask` propagation + test.
4. `engine.py::_execute_batch` artifact branch + test.
5. `FractalTaskEngine` per-node classification (inject classifier) + test.
6. Container DI: inject `OutputRequirementClassifier` into FractalTaskEngine.
7. Live integration + manual E2E.

## Risks & Mitigations

| Risk | Sev | Mitigation |
|---|---|---|
| Over-planning latency still exhausts 180s before file node runs (OQ-3) | high | Out of scope but blocks live PASS. Mitigate during E2E by raising fractal hard timeout temporarily / capping depth; file a follow-up TD for planner-on-Haiku. |
| Per-node LLM classification adds latency/cost | med | Gate on "goal is artifact" (skip for TEXT goals); route classifier to Ollama $0; reuse planner cache. |
| Capable engine unavailable at runtime → falls to Ollama anyway | med | Existing `RouteToEngineUseCase` fallback + TD-156 DEGRADED check already handle this; surfaced via fallback_reason. |
| Wrong artifact engine (e.g. data goal needs FS not web) | low | Mapping is a small enum dict; adjust per live findings without touching call sites. |
| Behaviour drift for existing TEXT tasks | high | `output_requirement=None` path is unchanged; covered by full unit regression + Round 19. |

## Rollout

- No feature flag needed (additive, None-default is a no-op). Optional
  `MORPHIC_ARTIFACT_ROUTING=on|off` if a kill-switch is desired — initial
  answer: not needed, the None-default IS the off-state for legacy callers.
- Validate: unit suite green → live selection test → manual slide E2E.

---

*Next: generate `tasks.md` via `/prp-implement` after this plan is approved.*
