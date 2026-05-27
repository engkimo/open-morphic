# Tasks — Bypass Classifier Router (TD-196 / B)

> **Plan:** [`plan.md`](plan.md)
> **`[P]` = parallelizable** (no deps on prior unfinished tasks in the list)
> **TDD:** every production task is preceded by a failing test task (RED → GREEN → REFACTOR)

## Setup

- [ ] T001 — Create feature branch `feature/bypass-classifier-router`
- [ ] T002 — Add scope entry to `docs/CHANGELOG.md` (unreleased section)

## Domain layer — value objects (TDD RED)

- [ ] T010 `[P]` — RED: Write `tests/unit/domain/value_objects/test_bypass_decision.py` covering Pydantic validation, frozen semantics, default `output_requirement = TEXT`, `reason` max-length (200), all 3 `TaskComplexity` values, all 4 `OutputRequirement` values. Expected to fail.
- [ ] T011 `[P]` — RED: Write `tests/unit/domain/value_objects/test_council_events_bypass_classified.py` covering: round-trip JSON, `kind="bypass_classified"` discriminator, payload fields, `goal_hash` regex enforcement (`^[0-9a-f]{16}$`), raw-goal field absence (string-match `"goal"` and `"raw_goal"` NOT in `model_dump()`). Expected to fail.

## Domain layer — value objects (TDD GREEN)

- [ ] T012 — GREEN: Add `domain/value_objects/bypass_decision.py::BypassDecision` frozen Pydantic VO. T010 passes.
- [ ] T013 — GREEN: Extend `domain/value_objects/council_events.py` with `BypassClassified` variant; update `DebateEvent` union. T011 passes. Verify existing council-pilot and goal-classifier tests still pass byte-identically.

## Domain layer — port (TDD RED → GREEN)

- [ ] T020 — RED: Write `tests/unit/domain/ports/test_bypass_classifier_port.py` asserting `BypassClassifierPort` is abstract, requires `async def classify(goal: str) -> BypassDecision`, and rejects empty / whitespace goal with `ValueError`. Expected to fail.
- [ ] T021 — GREEN: Add `domain/ports/bypass_classifier.py::BypassClassifierPort` ABC. T020 passes.

## Test fakes (port-compliant InMemory adapter, per TD-187)

- [ ] T030 `[P]` — Add `tests/unit/application/_fakes/in_memory_bypass_classifier.py` — `InMemoryBypassClassifier(BypassClassifierPort)` with configurable response queue, raise-on-call mode, and recorded-call list for assertions.

## Infrastructure — shared prompts + parser (TDD RED → GREEN)

- [ ] T040 — RED: Write `tests/unit/infrastructure/fractal/test_bypass_prompts.py` covering `parse_bypass` golden cases:
  - SIMPLE + text → `BypassDecision(bypass=True, complexity=SIMPLE, output_requirement=TEXT)`
  - SIMPLE + file → `BypassDecision(bypass=False, complexity=SIMPLE, output_requirement=FILE_ARTIFACT)` (TD-192 gate)
  - SIMPLE + code / data → bypass=False, complexity=SIMPLE
  - MEDIUM → bypass=False, complexity=MEDIUM
  - COMPLEX → bypass=False, complexity=COMPLEX
  - `<think>...</think>` block stripping (qwen3)
  - ```json fenced output
  - malformed JSON → safe fallback (`bypass=False, complexity=MEDIUM, reason="Unparseable..."`)
  - missing keys → safe defaults
  Expected to fail.
- [ ] T041 — GREEN: Add `infrastructure/fractal/_bypass_prompts.py` with `SYSTEM_PROMPT` constant (byte-identical to current `_CLASSIFY_SYSTEM` in `bypass_classifier.py:28-62`), `_REQUIREMENT_VALUE_MAP`, `parse_bypass(raw: str) -> BypassDecision`. T040 passes.

## Infrastructure — prompt stability (NFR-2)

- [ ] T042 `[P]` — Write `tests/unit/infrastructure/fractal/test_prompt_stability.py` — AST walker: open `infrastructure/fractal/_bypass_prompts.py`, find the `SYSTEM_PROMPT = ...` assignment, assert the RHS is `ast.Constant` of type `str` (no f-string, no concat, no `.format()`, no call). Fails on any non-literal RHS.

## Infrastructure — LLM classifier (remote, TDD RED → GREEN)

- [ ] T050 — RED: Write `tests/unit/infrastructure/fractal/test_llm_bypass_classifier.py` using a fake `LLMGateway`. Cover: happy path, parse error path, cost recording, latency recording, model id passed to gateway equals Haiku 4.5, `temperature=0.1`, `max_tokens=256`. Expected to fail.
- [ ] T051 — GREEN: Implement `infrastructure/fractal/llm_bypass_classifier.py::LLMBypassClassifier(BypassClassifierPort)` using existing `LLMGateway`. Re-uses `parse_bypass` from `_bypass_prompts`. T050 passes.

## Infrastructure — Local classifier (Ollama, TDD RED → GREEN)

- [ ] T060 `[P]` — RED: Write `tests/unit/infrastructure/fractal/test_local_bypass_classifier.py` using a fake `OllamaManagerPort`. Cover: happy path, parse error path, cost is always 0.0, latency recorded, model id is qwen3:8b. Expected to fail.
- [ ] T061 — GREEN: Implement `infrastructure/fractal/local_bypass_classifier.py::LocalBypassClassifier(BypassClassifierPort)` using existing `OllamaManagerPort`. T060 passes.

## Infrastructure — NoOp classifier (disabled mode, TDD RED → GREEN)

- [ ] T070 `[P]` — RED: Write `tests/unit/infrastructure/fractal/test_noop_bypass_classifier.py` asserting it always returns `BypassDecision(bypass=False, complexity=MEDIUM, output_requirement=TEXT, reason="bypass disabled")` regardless of input, makes no LLM call, latency 0, cost 0.
- [ ] T071 — GREEN: Implement `infrastructure/fractal/noop_bypass_classifier.py::NoOpBypassClassifier(BypassClassifierPort)`. T070 passes.

## Infrastructure — observability wrapper (TDD RED → GREEN)

- [ ] T080 — RED: Write `tests/unit/infrastructure/observability/test_bypass_observer.py` using a fake wrapped port + fake `EventBusPort` + fake `BypassMetrics`. Cover:
  - delegates `classify()` to the wrapped port and returns the same result
  - emits exactly one `BypassClassified` event per call
  - event has correct `goal_hash = sha256(goal)[:16]` (16-hex regex match)
  - raw goal NEVER appears in event payload (string-match assertion against `event.model_dump_json()`)
  - increments `classifications_total{decision,complexity}` correctly
  - records latency histogram
  - event-bus publish failure does NOT break classification (caller still gets a decision)
  - wrapped-port failure DOES propagate (errors are surfaced, not swallowed)
  Expected to fail.
- [ ] T081 — GREEN: Implement `infrastructure/observability/bypass_observing_event_bus.py::BypassObservingEventBus(BypassClassifierPort)` decorator. T080 passes.

## Infrastructure — metrics (TDD RED → GREEN)

- [ ] T090 `[P]` — RED: Write `tests/unit/infrastructure/metrics/test_bypass_metrics.py` covering counter labels `(decision, complexity)` cardinality (2 × 3 = 6) and `classifier_latency_ms` histogram buckets. Expected to fail.
- [ ] T091 — GREEN: Implement `infrastructure/metrics/bypass_metrics.py::BypassMetrics` with Prometheus counters + histogram. T090 passes.

## FractalEngine refactor (TDD RED → GREEN)

- [ ] T100 — RED: Write `tests/unit/infrastructure/fractal/test_fractal_engine_port_wiring.py` using `InMemoryBypassClassifier` (T030). Assert: `FractalEngine.__init__` accepts a `BypassClassifierPort | None`; engine calls `classify()` exactly once per top-level goal; uses returned `BypassDecision` verbatim (no transformation); when classifier is `None`, no call is made and behaviour matches `FractalEngine` pre-TD-167. Expected to fail.
- [ ] T101 — GREEN: Modify `infrastructure/fractal/fractal_engine.py` lines 67 / 114 — change parameter type from `FractalBypassClassifier | None` to `BypassClassifierPort | None`; update internal call from `should_bypass()` to `classify()`. T100 passes. Verify `tests/integration/test_round19_regression.py` still passes byte-identically.

## Settings + DI wiring

- [ ] T110 — Add fields to `shared/config/settings.py`:
  - `bypass_classifier_mode: Literal["remote", "local", "disabled", "auto"] = "auto"`
  - `bypass_classifier_timeout_ms: int = 2000`
  Add unit test in `tests/unit/shared/config/test_settings.py` for env-var parsing (`MORPHIC_BYPASS_CLASSIFIER`).
- [ ] T111 — Wire DI in `interface/api/container.py` per AD-6:
  - Read `bypass_classifier_mode` and `auto`-detect logic (API key → remote, else Ollama up → local, else `NoOpBypassClassifier`).
  - Construct active adapter, wrap in `BypassObservingEventBus`, inject into `FractalEngine` factory.
  - Add unit test in `tests/unit/interface/api/test_container_bypass_wiring.py` covering all 4 branches (`auto` × 3 detect cases + explicit `disabled`).

## Migration cleanup

- [ ] T120 — Delete `infrastructure/fractal/bypass_classifier.py` (old class). Confirm no remaining imports via `rg "FractalBypassClassifier"`. If any test still imports it, port the test to use `LLMBypassClassifier` + `InMemoryBypassClassifier`.

## Integration tests (require live services; skipped if env missing)

- [ ] T130 — `tests/integration/test_bypass_classifier_local_live.py` — real Ollama qwen3:8b, 3 goals: `"What is 2+2?"` (expect bypass=True, complexity=SIMPLE, output=TEXT), `"氷川神社の歴史についてPPTXスライドを作成"` (expect bypass=False, output=FILE), `"Refactor the auth system to use OAuth2"` (expect bypass=False, complexity=COMPLEX). Skipped if Ollama unreachable. Cost $0.
- [ ] T131 `[P]` — `tests/integration/test_bypass_classifier_remote_live.py` — real Anthropic Haiku 4.5, same 3 goals + same expectations. Skipped if `ANTHROPIC_API_KEY` not set. Cost ≤ $0.0009.

## Regression bar (NFR-1 / NFR-7)

- [ ] T140 — Run `uv run --extra dev pytest tests/integration/test_round19_regression.py -v` with `MORPHIC_BYPASS_CLASSIFIER` unset (auto-detect). Expect 6/6 PASS, byte-identical decision outcomes vs `main` HEAD baseline.
- [ ] T141 — Run same regression with `MORPHIC_BYPASS_CLASSIFIER=disabled`. Expect all 6 goals to take the fractal path (no bypass), test suite still passes.

## Docs

- [ ] T150 `[P]` — Add ADR entry in `docs/TECH_DECISIONS.md` (next TD number after TD-195; expected TD-196). Title: "Bypass Classifier Router — port + adapter split for fractal bypass decisions".
- [ ] T151 `[P]` — Update `docs/ENV_VARS.md` with `MORPHIC_BYPASS_CLASSIFIER`, `MORPHIC_BYPASS_CLASSIFIER_TIMEOUT_MS`.
- [ ] T152 `[P]` — Update `docs/CONTINUATION.md` handoff state.

## Verification

- [ ] T160 — `uv run --extra dev pytest tests/unit/ -v` passes (0 regressions across the 3,169+ existing tests; expect +15 new tests).
- [ ] T161 — `uv run --extra dev pytest tests/integration/test_bypass_classifier_local_live.py -v` passes (or skips cleanly if Ollama unreachable).
- [ ] T162 — `uv run --extra dev pytest tests/integration/test_bypass_classifier_remote_live.py -v` passes (or skips cleanly if no API key).
- [ ] T163 — `uv run --extra dev ruff check .` clean.
- [ ] T164 — Constitution + spec compliance verification:
  - `rg -l "from (sqlalchemy|fastapi|litellm|redis|mem0|celery|httpx|infrastructure|application|interface)" domain/ports/bypass_classifier.py domain/value_objects/bypass_decision.py` returns nothing.
  - `rg -l "from infrastructure.fractal" application/ domain/` returns nothing.
  - `rg "FractalBypassClassifier"` returns nothing (old class fully removed).
  - String-match assertion: raw integration-test goals never appear in captured `BypassClassified` event payloads of T130/T131.
  - All spec.md "Constitution Compliance" checkboxes ticked.
- [ ] T165 — Regression guard: with `MORPHIC_BYPASS_CLASSIFIER=disabled`, all bypass-related unit tests skip cleanly AND `test_round19_regression.py` passes (T141 already covers this; final gate-check here).

## Ship

- [ ] T170 — Self-review via `/morphic-pr-reviewer` subagent.
- [ ] T171 — Create PR with `spec.md` + `plan.md` + T140 / T141 regression evidence linked in description.
- [ ] T172 — Update `docs/CHANGELOG.md` with shipped entry.
- [ ] T173 — Close feature branch after merge.

---

## Parallel execution groups

```text
T010, T011                                # Domain VO tests — independent files
T012, T013                                # Domain VO impls — after T010/T011
T020 → T021                               # Port test → port impl
T030                                      # Test fake — after T021 (needs port ABC)
T040 → T041                               # Parser test → parser impl
T042                                      # Prompt-stability AST test — after T041
T050 → T051                               # Remote classifier test → impl (needs T041)
T060 → T061                               # Local classifier test → impl (parallel with T050/T051)
T070 → T071                               # NoOp classifier test → impl (fully independent)
T080 → T081                               # Observer test → impl (needs T021 + T013)
T090 → T091                               # Metrics test → impl (fully independent)
T100 → T101                               # FractalEngine wiring test → refactor (needs T021 + T030)
T110, T111                                # Settings + DI wiring (T111 needs T051 + T061 + T071 + T081 + T101)
T120                                      # Delete old class — after T111
T130, T131                                # Integration tests — parallel; after T111
T140, T141                                # Regression bar — after T101 + T111
T150, T151, T152                          # Docs — fully parallel; after T111
T160, T161, T162, T163, T164, T165        # Verification gates — can run in parallel
T170 → T171 → T172 → T173                 # Ship sequence — strict order
```
