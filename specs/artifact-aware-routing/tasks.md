# Tasks — Artifact-Aware Engine Routing (TD-197)

> **Plan:** [`plan.md`](plan.md)
> **`[P]` = parallelizable** · **TDD:** RED before GREEN

## Setup

- [ ] T001 — Create branch `feature/artifact-aware-routing`
- [ ] T002 — Add unreleased entry to `docs/CHANGELOG.md`

## Domain — SubTask field (TDD)

- [ ] T010 — RED: `tests/unit/domain/test_entities.py` — assert
  `SubTask.output_requirement` defaults `None`, accepts each
  `OutputRequirement`, strict-rejects bad type.
- [ ] T011 — GREEN: add `output_requirement: OutputRequirement | None = None`
  to `domain/entities/task.py::SubTask`. T010 passes.

## Domain — Router output-aware selection (TDD)

- [ ] T020 `[P]` — RED: `tests/unit/domain/test_agent_engine_router.py` —
  `select_for_output`: FILE→OPENHANDS, CODE→CODEX_CLI, DATA→GEMINI_CLI,
  TEXT→equals `select(task_type,budget)`, None→delegates,
  budget<=0→OLLAMA for every requirement.
- [ ] T021 — GREEN: add `_OUTPUT_TO_ENGINE` map + `select_for_output(...)`
  to `domain/services/agent_engine_router.py`. T020 passes.

## Infrastructure — node→subtask propagation (TDD)

- [ ] T030 `[P]` — RED: `tests/unit/infrastructure/test_fractal_node_executor.py`
  — `to_subtask` copies `node.output_requirement` (FILE and None cases).
- [ ] T031 — GREEN: `NodeExecutor.to_subtask` sets
  `output_requirement=node.output_requirement`. T030 passes.

## Infrastructure — engine routing branch (TDD)

- [ ] T040 — RED: `tests/unit/infrastructure/test_task_graph_engine.py` —
  with a fake `route_to_engine` recording `preferred_engine`: a SubTask
  with `output_requirement=FILE_ARTIFACT` (budget>0) selects OpenHands;
  a `TEXT`/`None` SubTask keeps the regex path (no artifact escalation);
  budget<=0 forces neither (Ollama / ReAct path).
- [ ] T041 — GREEN: add the artifact branch in
  `infrastructure/task_graph/engine.py::_execute_batch` per plan AD-3.
  T040 passes; existing engine tests unchanged.

## Infrastructure — per-node requirement classification (TDD)

- [ ] T050 — RED: `tests/unit/infrastructure/test_fractal_engine.py` —
  inject a fake `OutputRequirementClassifier`: when goal requirement is
  FILE, each terminal node is classified individually (search node→TEXT,
  slide node→FILE); when goal requirement is TEXT, classifier is NOT
  called (nodes inherit TEXT); when classifier is None, goal-inheritance
  fallback (current behaviour) applies.
- [ ] T051 — GREEN: replace `fractal_engine.py:318-322` blanket loop with
  gated per-node classification (plan AD-4/AD-5). Add optional
  `output_classifier: OutputRequirementClassifier | None` ctor param.
  T050 passes.

## Interface — DI wiring

- [ ] T060 — Wire `OutputRequirementClassifier(llm=self.llm)` into the
  `FractalTaskEngine` construction in `interface/api/container.py`. Add
  wiring assertion in `tests/unit/interface/api/test_container*.py`.

## Observability (FR-6, no schema change)

- [ ] T070 `[P]` — Surface `output_requirement` + chosen `engine_used` on
  the task-detail API response (`interface/api/schemas.py` subtask DTO) and
  the UI subtask row. Log one INFO line per artifact escalation
  (`artifact_route node=… requirement=… → engine=…`).

## Integration / Live

- [ ] T080 — `tests/integration/test_artifact_routing_live.py` — real
  Ollama classification; assert the slide node *selects* a file-capable
  engine (driver execution mocked → $0/fast). Skip if Ollama down.
- [ ] T081 — Manual live E2E (real cost): full "氷川神社スライド" goal →
  confirm a real file artifact is produced. Document timeout/depth setting
  used (links to OQ-3 follow-up).

## Regression / Verification

- [ ] T090 — `uv run --extra dev pytest tests/unit/ -v` — 0 regressions,
  ≥12 new tests.
- [ ] T091 — `tests/integration/test_round19_regression.py` passes
  (bypass semantics untouched).
- [ ] T092 — `uv run --extra dev ruff check .` clean.
- [ ] T093 — Constitution check: `rg "from (sqlalchemy|fastapi|litellm|infrastructure|application|interface)" domain/entities/task.py domain/services/agent_engine_router.py` returns nothing; no new regex patterns added for artifact routing (diff review).

## Docs / Ship

- [ ] T100 `[P]` — ADR `docs/TECH_DECISIONS.md` TD-197.
- [ ] T101 `[P]` — Update `docs/CONTINUATION.md`.
- [ ] T102 — Self-review via `/morphic-pr-reviewer`.
- [ ] T103 — PR with spec/plan + T080/T081 evidence; `docs/CHANGELOG.md`
  shipped entry; close branch after merge.

---

## Parallel groups

```text
T010→T011         SubTask field
T020→T021         Router (parallel with T010)
T030→T031         to_subtask (parallel; needs T011 for field)
T040→T041         engine branch (needs T011+T021)
T050→T051         per-node classify (needs T031)
T060              DI (needs T051)
T070              observability (needs T011)
T080,T081         live (needs T041+T060)
T090..T093        verification
T100,T101         docs
```
