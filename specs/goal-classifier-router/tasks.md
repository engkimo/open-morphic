# Tasks — Goal Classifier Router (Planner Model Selection)

> **Plan:** [`plan.md`](plan.md)
> **`[P]` = parallelizable** (no deps on prior unfinished tasks in the list)
> **TDD:** every production task is preceded by a failing test task (RED → GREEN → REFACTOR)

## Setup

- [x] T001 — Create feature branch `feature/goal-classifier-router`
- [x] T002 — Add scope entry to `docs/CHANGELOG.md` (unreleased section)

## Domain layer — value objects (TDD RED)

- [x] T010 `[P]` — RED: Write `tests/unit/domain/value_objects/test_planner_model.py` covering enum members, string equality, and `to_gateway_id()` for both members. Expected to fail.
- [x] T011 `[P]` — RED: Write `tests/unit/domain/value_objects/test_goal_classification.py` covering Pydantic validation, `reason` max length (200), `confidence` bounds (0.0–1.0), non-negative latency / cost. Expected to fail.
- [x] T012 `[P]` — RED: Write `tests/unit/domain/value_objects/test_council_events_goal_classified.py` covering the new `GoalClassified` discriminated-union variant: round-trip JSON, `kind="goal_classified"` discriminator, payload fields. Expected to fail.

## Domain layer — value objects (TDD GREEN)

- [x] T013 — GREEN: Add `domain/value_objects/planner_model.py::PlannerModel` (StrEnum + `to_gateway_id`). T010 passes.
- [x] T014 — GREEN: Add `domain/value_objects/goal_classification.py::GoalClassification` Pydantic VO. T011 passes.
- [x] T015 — GREEN: Extend `domain/value_objects/council_events.py` with `GoalClassified` variant; update `DebateEvent` union. T012 passes. Verify existing council-pilot tests still pass byte-identically.

## Domain layer — port (TDD RED → GREEN)

- [x] T020 — RED: Write `tests/unit/domain/ports/test_goal_classifier_port.py` asserting `GoalClassifierPort` is abstract, requires `classify(goal: str) -> GoalClassification`, and rejects empty / whitespace goal with `ValueError`. Expected to fail.
- [x] T021 — GREEN: Add `domain/ports/goal_classifier.py::GoalClassifierPort` ABC. T020 passes.

## Test fakes (port-compliant InMemory adapter, per TD-187)

- [x] T030 `[P]` — Add `tests/unit/application/_fakes/in_memory_goal_classifier.py` — `InMemoryGoalClassifier(GoalClassifierPort)` with configurable response queue, raise-on-call mode, and recorded-call list for assertions.

## Domain service — router (TDD RED)

- [x] T040 — RED: Write `tests/unit/domain/services/test_planner_model_router.py` covering ALL of:
  - router-disabled returns `(default_model, None)` and does NOT call classifier
  - router-enabled + Haiku high-confidence (≥ 0.7) → routes Haiku, event emitted
  - router-enabled + Haiku low-confidence (< 0.7) → routes Sonnet, reason `"low_confidence: ..."`, category `low_confidence`
  - router-enabled + classifier raises → routes Sonnet, reason `"classifier_failed: ..."`, category `classifier_failed`
  - router-enabled + classifier timeout > `classifier_timeout_ms` → routes Sonnet, category `classifier_failed`
  - reason-category normalization covers all 6 AD-3 buckets
  - event emission failure does NOT abort routing
  - `goal_hash` is `sha256(goal)[:16]`; raw goal NEVER appears in the published event (string-match assertion)
  Expected to fail.

## Domain service — router (TDD GREEN)

- [x] T041 — GREEN: Add `domain/services/planner_model_router.py::PlannerModelRouter` with confidence gating (AD-2), reason-category normalization (AD-3), `asyncio.wait_for` timeout, and best-effort event emission. T040 passes.

## Infrastructure — shared prompts + parser (TDD RED → GREEN)

- [x] T050 — RED: Write `tests/unit/infrastructure/routing/test_prompts_parser.py` covering: clean JSON, JSON with `<think>` block (qwen3), JSON inside ```json fences, malformed JSON → `ClassificationParseError`, invalid `model` enum → `ClassificationParseError`, out-of-range confidence → `ClassificationParseError`. Expected to fail.
- [x] T051 — GREEN: Add `infrastructure/routing/_prompts.py` with `SYSTEM_PROMPT` constant (KV-cache stable; identical bytes for remote + local), `parse_classification(raw: str) -> GoalClassification`, and `ClassificationParseError`. T050 passes.

## Infrastructure — LLM classifier (remote, TDD RED → GREEN)

- [x] T060 — RED: Write `tests/unit/infrastructure/routing/test_llm_goal_classifier.py` using a fake `LLMGateway`. Cover: happy path (Haiku returns valid JSON), parse error path, cost recording, latency recording, model id passed to gateway equals Haiku 4.5. Expected to fail.
- [x] T061 — GREEN: Implement `infrastructure/routing/llm_goal_classifier.py::LLMGoalClassifier(GoalClassifierPort)` using existing `LLMGateway`. T060 passes.

## Infrastructure — Local classifier (Ollama, TDD RED → GREEN)

- [x] T070 `[P]` — RED: Write `tests/unit/infrastructure/routing/test_local_goal_classifier.py` using a fake `OllamaManagerPort`. Cover: happy path, parse error path, cost is always 0.0, latency recorded, model id is qwen3:8b. Expected to fail.
- [x] T071 — GREEN: Implement `infrastructure/routing/local_goal_classifier.py::LocalGoalClassifier(GoalClassifierPort)` using existing `OllamaManagerPort`. T070 passes.

## Infrastructure — planner integration (TDD RED → GREEN)

- [x] T080 — RED: Write `tests/unit/infrastructure/fractal/test_llm_planner_router_integration.py` using a fake `PlannerModelRouter` and fake `LLMGateway`. Cover: planner consults router with the goal, passes resolved gateway model id to `LLMGateway.complete`, and the stable system prompt (TD-190) is byte-identical regardless of chosen model. Expected to fail.
- [x] T081 — GREEN: Modify `infrastructure/fractal/llm_planner.py` to accept an injected `PlannerModelRouter` and consult it per call. Preserve TD-190 stable system prefix. T080 passes. Verify existing `tests/unit/infrastructure/fractal/test_llm_planner.py` still passes when `router_mode="disabled"`.

## Settings + DI wiring

- [x] T090 — Add fields to `shared/config/settings.py`:
  - `planner_router_mode: Literal["disabled", "enabled"] = "disabled"`
  - `planner_router_haiku_confidence_threshold: float = 0.7`
  - `planner_router_classifier_timeout_ms: int = 1500`
  Add unit test in `tests/unit/shared/config/test_settings.py` for env-var parsing (`MORPHIC_PLANNER_ROUTER`).
- [x] T091 — Wire DI in `interface/api/container.py`:
  - Read `planner_router_mode` and budget signal.
  - Construct active `GoalClassifierPort` (Local if LOCAL_FIRST + budget ≤ 0, else Remote).
  - Construct `PlannerModelRouter` and inject into `LLMPlanner` factory.
  - Add unit test in `tests/unit/interface/api/test_container_router_wiring.py` covering both branches and the `disabled` short-circuit.

## Observability

- [x] T100 `[P]` — Add Prometheus counters/histograms per FR-12 in `infrastructure/metrics/` (or wherever existing planner metrics live). Add a unit test asserting label cardinality matches the 6 AD-3 buckets.
- [x] T101 `[P]` — Add structured-logging fields (`goal_hash`, `chosen_model`, `reason_category`, `classifier_latency_ms`, `classifier_cost_usd`) on the planner-call log line. Verify no raw goal string is logged.

## Integration tests (require live services; skipped if env missing)

- [x] T110 — `tests/integration/test_goal_classifier_local_live.py` — real Ollama qwen3:8b, 3 goals: `"Build REST API in Python"` (expect HAIKU), `"東京から京都への新幹線の最安ルートを調査"` (expect SONNET), `"Generate a Python script that sorts a CSV file by the 'date' column"` (expect SONNET). Skipped if Ollama unreachable. Cost $0.
- [x] T111 `[P]` — `tests/integration/test_goal_classifier_remote_live.py` — real Anthropic Haiku 4.5, same 3 goals + same expectations. Skipped if `ANTHROPIC_API_KEY` not set. Cost ≤ $0.0015.

## Benchmark / A/B re-run

- [x] T120 — Extend `benchmarks/planner_quality_ab.py` with `--router` mode per AD-4: run router on the 10-goal benchmark, record per-goal `chosen_model`, run planner+judge with the router-chosen model (3 trials), compute (a) router-gated mean vs Sonnet baseline, (b) captured-saving ratio. Add `--dump` JSON output.
- [x] T121 — Run `uv run --extra dev python -m benchmarks.planner_quality_ab --router --dump /tmp/planner_ab_router_$(date +%Y_%m_%d).json` live. Acceptance: `entity_preserved` Δ ≥ −5pt and `plan_eval` Δ ≥ −0.030 vs Sonnet baseline; captured-saving ≥ 30%. Record results into a new memory file `memory/planner_router_ab_<date>.md`.

## Docs

- [x] T130 `[P]` — Add ADR entry in `docs/TECH_DECISIONS.md` (next TD number after TD-194; expected TD-195). Title: "Goal Classifier Router for Planner Model Selection".
- [x] T131 `[P]` — Update `docs/ENV_VARS.md` with `MORPHIC_PLANNER_ROUTER`, `MORPHIC_PLANNER_ROUTER_HAIKU_CONFIDENCE_THRESHOLD`, `MORPHIC_PLANNER_ROUTER_CLASSIFIER_TIMEOUT_MS`.
- [x] T132 `[P]` — Update `docs/CONTINUATION.md` handoff state with the router status and the T121 benchmark outcome.

## Verification

- [x] T140 — `uv run --extra dev pytest tests/unit/ -v` passes (0 regressions across the 3,169+ existing tests).
- [x] T141 — `uv run --extra dev pytest tests/integration/test_goal_classifier_local_live.py -v` passes (or skips cleanly if Ollama unreachable).
- [x] T142 — `uv run --extra dev pytest tests/integration/test_goal_classifier_remote_live.py -v` passes (or skips cleanly if no API key).
- [x] T143 — `uv run --extra dev ruff check .` clean.
- [x] T144 — Constitution + spec compliance verification:
  - `rg -l "from (sqlalchemy|fastapi|litellm|redis|mem0|celery|httpx|infrastructure|application|interface)" domain/ports/goal_classifier.py domain/value_objects/planner_model.py domain/value_objects/goal_classification.py domain/services/planner_model_router.py` returns nothing.
  - `rg -l "from infrastructure.routing" application/` returns nothing.
  - String-match assertion: raw benchmark goals never appear in the captured event payloads of T110/T111.
  - All spec.md "Constitution Compliance" checkboxes ticked.
- [x] T145 — Regression guard: with `MORPHIC_PLANNER_ROUTER=disabled`, `tests/unit/infrastructure/fractal/test_llm_planner.py` test count and pass count match `main` HEAD byte-identically (NFR-8).

## Ship

- [x] T150 — Self-review via `/morphic-pr-reviewer` subagent.
- [x] T151 — Create PR with `spec.md` + `plan.md` + T121 benchmark result memo linked in description.
- [x] T152 — Update `docs/CHANGELOG.md` with shipped entry.
- [x] T153 — Tag memory file `memory/planner_router_ab_<date>.md` as authoritative for future routing decisions.
- [x] T154 — Close feature branch after merge.

---

## Parallel execution groups

```text
T010, T011, T012                  # Domain VO tests — independent files
T013, T014, T015                  # Domain VO impls — after T010-T012
T020 → T021                       # Port test → port impl
T030                              # Test fake — after T021 (needs port ABC)
T040 → T041                       # Router test → router impl (needs T021 + T030)
T050 → T051                       # Parser test → parser impl
T060 → T061                       # Remote classifier test → impl
T070 → T071                       # Local classifier test → impl (parallel with T060/T061)
T080 → T081                       # Planner integration test → impl (needs T041 + T051)
T090, T091                        # Settings + DI wiring (T091 needs T061 + T071 + T081)
T100, T101                        # Observability — parallel; after T041
T110, T111                        # Integration tests — parallel; after T091
T120 → T121                       # Benchmark extension → live A/B run
T130, T131, T132                  # Docs — fully parallel; after T091
T140, T141, T142, T143, T144, T145 # Verification gates — can run in parallel
T150 → T151 → T152 → T153 → T154  # Ship sequence — strict order
```
