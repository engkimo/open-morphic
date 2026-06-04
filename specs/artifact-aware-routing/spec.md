# Feature Specification — Artifact-Aware Engine Routing (TD-197)

> **Branch:** `feature/artifact-aware-routing`
> **Status:** draft
> **Owner:** RYo
> **Created:** 2026-06-02

## Problem Statement

When a goal produces a file/code/data artifact (e.g. "日本の氷川神社の
歴史を調べ、スライドにして"), the artifact-producing subtasks are routed
to **Ollama qwen3:8b**, which cannot reliably create files and degenerates
into repetitive tool loops. The result: the task burns the fractal hard
timeout (180s) without producing the slide, and is marked failed.

Root cause (confirmed live, 2026-06-02 run):

1. The **bypass classifier already derives `output_requirement` via LLM**
   (`file` for the slide goal) — but that signal is **discarded at
   node-execution routing time**.
2. Node→engine selection uses the **regex `SubtaskTypeClassifier`**
   (`domain/services/subtask_type_classifier.py`). Verified routing of the
   actual decomposed nodes:
   - `"Search for '氷川神社 歴史' …"` → `web_search` → **gemini_cli** ✓
   - `"Create a PPTX slide file …"` → `simple_qa` → **ollama** ✗
   - `"Generate a PPTX slide file …"` → `simple_qa` → **ollama** ✗
   The keyword heuristic has no rule for "create/generate a file", so
   artifact nodes fall through to `simple_qa → OLLAMA`.
3. `PlanNode.output_requirement` exists and `FractalTaskEngine` even sets
   it (`fractal_engine.py:318-322`), but:
   - it blanket-inherits the **goal-level** requirement onto every
     terminal node (so a `text` search subnode is wrongly tagged `file`),
   - it is only set for **level-0** nodes (deeper recursion + reflection
     spawns are unset),
   - `SubTask` has **no `output_requirement` field**, so
     `NodeExecutor.to_subtask` drops the signal entirely, and the
     LangGraph routing never sees it.

This violates RYo's standing preference: routing relies on a **regex
heuristic** where an **LLM signal is already available** but unused.

## Goals

- **G-1:** Route artifact-producing subtasks to a **capable agent engine**
  (file → OpenHands/Claude Code; code → Codex; data → Gemini) instead of
  Ollama, using the **LLM-derived `output_requirement`** rather than the
  regex keyword classifier.
- **G-2:** Make `output_requirement` a **per-subtask** signal that survives
  the PlanNode → SubTask conversion and reaches the LangGraph routing
  decision (both fractal-inner and standalone LangGraph modes).
- **G-3:** Classify each node's `output_requirement` from its **own
  description** (LLM), not by blanket goal inheritance — so a `text` search
  subnode stays on Ollama while only the `file`-producing node escalates.
- **G-4:** Preserve $0 default for genuinely TEXT/SIMPLE subtasks
  (no regression of the bypass / direct-LLM fast path).

## Non-Goals

- **N-1:** Do NOT change the bypass classifier decision semantics
  (TD-167/192/196 are correct). This feature consumes its output, it does
  not alter it.
- **N-2:** Do NOT remove `SubtaskTypeClassifier` — it remains the fallback
  for TEXT subtasks where engine choice is by task-type (web_search →
  gemini etc.). Artifact detection moves to the LLM signal; task-type
  routing for TEXT stays.
- **N-3:** Do NOT tune the fractal hard timeout / recursion depth here.
  Over-planning latency is a separate concern (see Open Questions OQ-3).
- **N-4:** Do NOT add new agent engines or new artifact types.

## User Stories

### US-1: As a user, when I ask for a slide/report/file, the file-producing step runs on an engine that can actually create files.

**Acceptance Criteria:**
- [ ] A subtask whose `output_requirement == FILE_ARTIFACT` routes to a
      file-capable engine (OpenHands or Claude Code), never Ollama.
- [ ] The live "氷川神社スライド" goal produces a real file artifact (path
      recorded on the subtask) within the time budget.

### US-2: As a developer, the LLM output-requirement signal flows end-to-end from classification to engine selection.

**Acceptance Criteria:**
- [ ] `SubTask.output_requirement: OutputRequirement | None` exists.
- [ ] `NodeExecutor.to_subtask` copies `node.output_requirement`.
- [ ] LangGraph `_execute_batch` consults `subtask.output_requirement`
      BEFORE the regex `SubtaskTypeClassifier`.

### US-3: As a cost-conscious operator, TEXT subtasks still run free on Ollama.

**Acceptance Criteria:**
- [ ] `output_requirement == TEXT` (or `None`) preserves the current
      routing (SubtaskTypeClassifier → ollama for simple_qa).
- [ ] No new cloud calls are introduced for pure-text goals beyond the
      per-node requirement classification (which may itself run on Ollama /
      Haiku per config).

## Functional Requirements

- **FR-1:** Add `output_requirement: OutputRequirement | None = None` to
  `domain/entities/task.py::SubTask` (strict Pydantic, additive, default
  None for backward compatibility).
- **FR-2:** `NodeExecutor.to_subtask` propagates `node.output_requirement`
  → `subtask.output_requirement`.
- **FR-3:** Add an output-aware selection to `AgentEngineRouter`:
  `select_for_output(output_requirement, budget, task_type) -> AgentEngineType`
  with mapping:
  - `FILE_ARTIFACT` → `OPENHANDS` (Docker sandbox, real FS) with fallback
    `CLAUDE_CODE`
  - `CODE_ARTIFACT` → `CODEX_CLI` (fallback `CLAUDE_CODE`)
  - `DATA_ARTIFACT` → `GEMINI_CLI` (web/data, grounding)
  - `TEXT` / `None` → delegate to existing `select(task_type, budget)`
  - `budget <= 0` still forces `OLLAMA` (LOCAL_FIRST guard preserved).
- **FR-4:** In `infrastructure/task_graph/engine.py::_execute_batch`, when
  `subtask.output_requirement` is an artifact type, derive `engine_type`
  via `select_for_output(...)` instead of the regex `SubtaskTypeClassifier`
  path. TEXT/None falls through to the current logic unchanged.
- **FR-5:** Replace blanket goal-inheritance with **per-node** requirement
  classification: `FractalTaskEngine` classifies each terminal node's
  `output_requirement` from the node description via the existing
  `OutputRequirementClassifier` (LLM). The goal-level requirement is used
  only as a prior / fallback when per-node classification is unavailable.
- **FR-6:** Persist `output_requirement` on the subtask record and surface
  it in the task-detail API/UI (observability — why a node went to a
  cloud engine).

## Non-Functional Requirements

- **NFR-1 (No new regex heuristic):** Artifact→engine routing must key off
  the LLM `OutputRequirement` enum, not new keyword patterns.
- **NFR-2 (Backward compatibility):** With `output_requirement = None`
  (all existing tests / non-fractal callers), routing behaviour is
  byte-identical to today.
- **NFR-3 (LOCAL_FIRST):** `budget <= 0` still pins every engine choice to
  Ollama. Artifact escalation only happens when budget > 0.
- **NFR-4 (Cost):** Per-node requirement classification adds ≤ 1 LLM call
  per terminal node; it MUST be routeable to Ollama ($0) or Haiku per
  existing gateway config, and cached where the planner already caches.
- **NFR-5 (Clean Architecture):** New routing logic lives in
  `domain/services/agent_engine_router.py` (pure). `SubTask` field is
  domain. No framework imports added to `domain/`.
- **NFR-6 (Fallback safety):** If the chosen capable engine is unavailable
  at runtime, the existing `RouteToEngineUseCase` fallback chain applies
  (capable → … → Ollama), and the DEGRADED check (TD-156) still fires.

## Success Metrics

| Metric | Target |
|---|---|
| Slide goal: file-producing node routes to OpenHands/Claude Code | 100% (not Ollama) |
| Live "氷川神社スライド" goal produces a real file artifact | PASS |
| TEXT/SIMPLE goal still routes to Ollama, $0 | PASS (no regression) |
| New regex patterns added for artifact routing | 0 |
| Unit tests added (router, SubTask field, to_subtask, engine wiring) | ≥ 12 |
| Framework imports in `domain/` new/changed files | 0 |
| Existing test regressions | 0 |

## Open Questions

- [ ] **OQ-1:** FILE_ARTIFACT default engine — OpenHands (Docker sandbox,
      heavier) vs Claude Code (lighter, also writes files)? Initial answer:
      OpenHands primary, Claude Code fallback — matches the project's
      "delegate content creation to agent engines" + sandbox isolation.
- [ ] **OQ-2:** Per-node requirement classification cost — classify every
      terminal node, or only when the goal-level requirement is an
      artifact (skip when goal is pure TEXT)? Initial answer: skip when
      goal-level requirement is TEXT (most nodes inherit TEXT → no extra
      calls for pure-Q&A goals).
- [ ] **OQ-3:** Fractal over-planning latency (the 180s timeout exhaustion)
      is out of scope here but blocks the live PASS. Track as a follow-up
      (planner-on-Haiku and/or depth cap). Note in plan as a risk.

## Constitution Compliance

- [x] `domain/` stays framework-free (new SubTask field + router method are
      stdlib + Pydantic only; `OutputRequirementClassifier` already depends
      only on the `LLMGateway` port)
- [x] No new rule-based heuristic — routing uses the LLM `OutputRequirement`
      signal (NFR-1, satisfies the no-regex preference)
- [ ] LAEE risk classification declared (N/A — routing only; the engine the
      task lands on governs its own LAEE actions)
- [x] Unit + integration test strategy defined (see Success Metrics + plan)

---

*Next: generate `plan.md` via `/prp-plan`.*
