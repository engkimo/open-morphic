# Feature Specification — Council Pilot (2-Engine Debate Spike)

> **Branch:** `feature/council-pilot`
> **Status:** draft
> **Owner:** Ryousuke (ryosuke.ohori@ulusage.com)
> **Created:** 2026-05-12

## Problem Statement

Engine selection in Morphic-Agent today is a **deterministic dictionary lookup**, not a deliberation. The two relevant lookup tables are `_PRIMARY_ENGINE_MAP` (TaskType → AgentEngineType) and `_FALLBACK_CHAIN` (engine → ordered fallbacks) in `domain/services/agent_engine_router.py` (lines 19-58); they are consumed by `RouteToEngineUseCase._build_chain()` in `application/use_cases/route_to_engine.py` (lines 267-309) and by the goal-level auto-route at `interface/api/routes/tasks.py` line 138. The product north star (see `project_vision_living_graph.md`, constraint #2 "engine/model selection is a deliberation, not a lookup") explicitly treats this dict-based path as a *bootstrap* that the eventual multi-agent council should replace. The `Decision` data shape already exists in `domain/entities/cognitive.py` line 19, but nothing in the codebase ever *generates* a Decision via inter-engine debate during execution. This spike turns the council from data model into a live mechanism for exactly two engines, behind a feature flag, so the existing path remains the default. Without this spike the UX vision (`project_vision_live_debate_ux.md`, "minimum 2-engine debate spike that emits Decision events to a domain event bus") cannot be unblocked — the renderer has no event stream to render.

## Goals

- Make engine selection *deliberation-capable* for one wiring point: introduce a `CouncilDebatePort` that takes a subtask + 2 candidate engines and returns a `Decision` whose `rationale` records both engines' arguments and the resolution. Measurable: a unit test feeds a fake debate port into `RouteToEngineUseCase` and asserts the resulting chain is governed by the returned `Decision`, not by `_PRIMARY_ENGINE_MAP`.
- Establish the **domain event vocabulary** the future UX layer will subscribe to: `DebateStarted`, `ArgumentSubmitted`, `DecisionResolved`. Measurable: an InMemory recording adapter for the new `EventBus` port captures all three event types in order during a debate, with no infrastructure dependency.
- Ship the spike behind a feature flag (`MORPHIC_COUNCIL_DEBATE=false` by default) so the deterministic lookup path remains the canonical production path until evidence justifies promotion. Measurable: with the flag unset, `tests/unit/application/test_route_to_engine.py` continues to pass byte-identically (zero behavior change).
- Hold the budget: one real-LLM live integration test, total spike-induced LLM cost ≤ $0.10 across one full CI run.

## Non-Goals

- **No UI / SSE / WebSocket wiring** in this spike. The renderer (per `project_vision_live_debate_ux.md`) is a separate sprint that *consumes* the events emitted here. Order of operations is enforced: events first, transport second, render third.
- **No more than 2 engines in the debate.** The vision is a 6-engine council; this spike picks the cheapest already-wired pair and proves the mechanism. Generalization to N engines is a follow-up spec.
- **No replacement of `AGENT_ROUTING_MAP` or `_PRIMARY_ENGINE_MAP`.** The dict-based path stays as the default branch behind the feature flag and as the ultimate fallback when the debate fails.
- **No council "memory" across subtasks.** Each debate is independent; reusing prior debates' Decisions to skip future debates is a follow-up.
- **No cost optimization of the debate itself.** A debate doubles or triples the planner LLM calls for the wired entry point; that overhead is acceptable for the spike and will be tuned later.
- **No LAEE integration.** The debate produces a `Decision`; it does not produce an action that LAEE governs. Risk classification is therefore N/A.
- **No subscriber implementations of `EventBus`.** Only the port + an in-memory recording adapter for tests. Wiring the bus to `task_stream.py` is the next sprint's job.
- **No promotion of the spike to canonical path.** Even if the debate works perfectly in the live test, the flag stays default-off until a follow-up spec evaluates cost / latency / decision-quality on a representative corpus.

## User Stories

### As the developer wiring the next sprint (UI / SSE renderer), I want a stable domain event vocabulary emitted during debate, so that I can build the renderer against a real event stream rather than a mock.

**Acceptance Criteria:**
- [ ] Given the council pilot enabled in tests, when a debate runs over a subtask with two candidate engines, then exactly one `DebateStarted`, two `ArgumentSubmitted`, and one `DecisionResolved` events are observed on the `EventBus`, in that order.
- [ ] Given the same debate, when the recording adapter is inspected, then each `ArgumentSubmitted` event names the engine, the capability claim, the cost claim, the risk claim, and the recommended approach.
- [ ] Given the same debate, when the `DecisionResolved` event is inspected, then it carries a domain `Decision` whose `agent_engine` is one of the two candidates and whose `rationale` cites both arguments.

### As a non-engineer end-user (per vision constraint #1, primary persona), I want the system to *defend* its engine choice rather than silently dispatch, so that when a result disappoints me I can read why this engine was picked.

**Acceptance Criteria:**
- [ ] Given a task executed with the council pilot enabled, when I retrieve the task's `SharedTaskState.decisions` after completion, then it contains at least one `Decision` whose `rationale` is non-empty and references both candidate engines (string contains both engine names).
- [ ] Given the same task with the council pilot **disabled** (default), when I retrieve `SharedTaskState.decisions`, then no debate-originated `Decision` is present (regression guard for the deterministic path).

### As a PR reviewer, I want to confirm the spike does not violate Clean Architecture, so that the council infrastructure does not pollute the domain layer.

**Acceptance Criteria:**
- [ ] Given the new port files in `domain/ports/`, when grepped for framework imports (`sqlalchemy|fastapi|litellm|redis|mem0|celery|httpx`), then nothing is returned.
- [ ] Given the new use case in `application/`, when grepped for `from infrastructure`, then nothing is returned.
- [ ] Given `domain/entities/cognitive.py`, when diffed against `main`, then `Decision` is **unchanged** (the spike consumes the existing entity; it does not modify it).

## Functional Requirements

- **FR-1:** The system shall introduce `domain/ports/council_debate.py::CouncilDebatePort` — an `abc.ABC` with one abstract method `async def debate(subtask: SubtaskBrief, candidates: list[AgentEngineType]) -> Decision`. The port shall require `len(candidates) == 2` for this spike (validated at the boundary, raising `ValueError` otherwise).
- **FR-2:** The system shall introduce `domain/ports/event_bus.py::EventBusPort` — an `abc.ABC` exposing `async def publish(event: DebateEvent) -> None`. No subscribe / consume API in this spike (publish-only is sufficient for the recording adapter).
- **FR-3:** The system shall introduce a `domain/entities/council.py` module containing: `Argument` (engine + capability_claim + cost_claim + risk_claim + recommended_approach), `SubtaskBrief` (id + description + task_type), and a `DebateEvent` discriminated union with three variants: `DebateStarted`, `ArgumentSubmitted`, `DecisionResolved`.
- **FR-4:** The system shall reuse the **existing** `domain/entities/cognitive.py::Decision` unmodified. The spike does not extend, alter, or version this entity.
- **FR-5:** The system shall introduce `application/use_cases/run_council_debate.py::RunCouncilDebateUseCase` that orchestrates: emit `DebateStarted` → invoke `CouncilDebatePort.debate()` → emit one `ArgumentSubmitted` per argument received → emit `DecisionResolved` carrying the resolved `Decision`. The use case shall depend only on the two new ports and the existing `EventBusPort`.
- **FR-6:** The system shall introduce `infrastructure/council/two_engine_debate.py::TwoEngineDebate(CouncilDebatePort)` — a concrete adapter that, for each of the two candidate engines, issues exactly one LLM call (via the existing `LLMGateway` port) prompting the engine to produce an `Argument` for the subtask, then issues one resolver LLM call to reduce the two arguments into a `Decision`.
- **FR-7:** The system shall introduce `infrastructure/events/in_memory_event_bus.py::InMemoryEventBus(EventBusPort)` — a recording adapter that stores published events in an in-memory list. This adapter is the **only** subscriber implementation in this spike. (Test-only consumption is allowed via the port.)
- **FR-8:** The system shall wire the council into exactly one production entry point: `RouteToEngineUseCase._build_chain()` in `application/use_cases/route_to_engine.py`. When the feature flag is on AND no `preferred_engine` was passed by the caller AND the affinity-aware path returned no boost (top score < threshold), the use case shall consult `CouncilDebatePort` with the top-2 engines from the existing `select_with_fallbacks` chain, and shall use the resolved `Decision.agent_engine` as the new chain head; the rest of the original chain is retained as fallback (deduped, with OLLAMA last per existing semantics).
- **FR-9:** The system shall expose the feature flag as `MORPHIC_COUNCIL_DEBATE` (env var, default `false`) wired through `shared/config/Settings` and read once at container construction in `interface/api/container.py`. Toggling the flag shall require no code change and no service restart beyond what existing flags require.
- **FR-10:** The system shall, when the council path is taken, append the resolved `Decision` to the task's `SharedTaskState.decisions` via the existing `SharedTaskStateRepository.add_decision` mechanism (or equivalent), so the audit trail shows the deliberation outcome.
- **FR-11:** The system shall, when the council path fails (debate raises, resolver returns malformed output, or LLM gateway times out), fall back to the deterministic `select_with_fallbacks` chain unchanged and emit no `DecisionResolved` event. A `DebateAbandoned` event variant **may** be emitted; this is recommended but not required for the spike.
- **FR-12:** The system shall pick the **cheapest already-wired engine pair** for the live integration test. Selection rule: the pair shall consist of two engines whose corresponding `AgentEnginePort` driver is registered in the default DI container AND whose typical per-call cost (per existing CostTracker telemetry) is at the bottom two of the registered set. At the time of writing, this is expected to be `OLLAMA` + `GEMINI_CLI` (Gemini 2.5 Flash); the plan shall confirm this against current driver registration.

## Non-Functional Requirements

- **NFR-1 (Latency):** A debate shall complete within a budget of **15 seconds** wall-clock for the wired pair (3× the typical single planner-LLM call latency observed in Round 18, ~5s). The `RunCouncilDebateUseCase` shall enforce this with a hard timeout; on timeout, FR-11 fallback applies.
- **NFR-2 (Observability):** Every debate shall emit at minimum one `DebateStarted` and one `DecisionResolved` (or one `DebateAbandoned`). Argument count emitted shall equal the candidate count. The recording adapter shall preserve event order. Structured logging shall include a debate_id (UUID) on every event for correlation.
- **NFR-3 (Cost):** Per-debate cost shall be ≤ **$0.02** when the wired pair is `OLLAMA` + `GEMINI_CLI` (Gemini 2.5 Flash, ~$0.01/call × 2 args + 1 resolver call). Total spike-induced LLM cost across one CI run shall be ≤ **$0.10**.
- **NFR-4 (LOCAL_FIRST):** The wired pair shall include `OLLAMA`. The resolver LLM call shall route through the existing `LLMGateway` whose LOCAL_FIRST policy already prefers Ollama when budget ≤ 0. With budget = 0, the entire debate shall be free ($0).
- **NFR-5 (Clean Architecture):** `domain/ports/council_debate.py`, `domain/ports/event_bus.py`, and `domain/entities/council.py` shall import only stdlib + Pydantic + `domain/*`. Verifiable: `rg -l "from (sqlalchemy|fastapi|litellm|redis|mem0|celery|httpx|infrastructure|application|interface)" domain/ports/council_debate.py domain/ports/event_bus.py domain/entities/council.py` returns nothing.
- **NFR-6 (TDD):** Every production-code task shall be preceded by a failing test task. The use case unit test shall use fake implementations of `CouncilDebatePort` and `EventBusPort`; no LLM call from any unit test.
- **NFR-7 (Backward compatibility):** With the feature flag disabled, the existing test suite shall pass byte-identically. Verifiable: `tests/unit/application/test_route_to_engine.py` test count and pass count match `main` HEAD.
- **NFR-8 (KV-cache safety):** The debate prompts (per-engine argument prompt + resolver prompt) shall follow the stable-prefix rule: the system message is byte-identical across calls; per-debate values (subtask description, candidate names) live in the user message. No timestamps or debate_ids in the system prompt.

## Success Metrics

| Metric | Target |
|---|---|
| Production source files importing `from infrastructure.council.*` outside `interface/` | 0 |
| Framework imports (`sqlalchemy|fastapi|litellm|...`) in new domain files | 0 |
| Unit tests added for the new port + use case | ≥ 8 |
| Integration tests with real LLMs added | exactly 1 |
| Live-test debate cost (Ollama + Gemini Flash, 1 subtask) | ≤ $0.02 |
| Total spike-induced LLM cost across 1 CI run | ≤ $0.10 |
| Behavioral regression in existing tests with flag off | 0 failures |
| `Decision.rationale` non-empty in live test | 100% (1/1) |
| Wall-clock per debate (live test, ≤ 2 engines) | ≤ 15s |
| `DecisionResolved` events captured by recording adapter (live test) | exactly 1 |
| Modifications to `domain/entities/cognitive.py::Decision` | 0 lines |

## Resolved Questions (2026-05-12)

- [x] **Resolver mechanism (LLM-judge vs. weighted-vote):** RESOLVED — **LLM-judge**. Plan §Architecture Decisions justifies this. Short version: weighted-vote requires hand-tuned weights that bake in exactly the deterministic-table assumption this spike is trying to replace; LLM-judge is the honest "deliberation" path the vision specifies, and the cost (one extra LLM call per debate) fits inside NFR-3.
- [x] **Engine pair for the live integration test:** RESOLVED — `OLLAMA` (qwen3:8b) + `GEMINI_CLI` (Gemini 2.5 Flash). Both already wired (per `MEMORY.md` "API Key Status"); together they are the cheapest registered pair. Plan task T-INT-01 verifies registration at integration-test time.
- [x] **Should `DebateAbandoned` be required (FR-11):** RESOLVED — **recommended but not required** for the spike. Logging is sufficient for failure observability today; the event variant is reserved in the `DebateEvent` union shape so the renderer can subscribe to it later without a domain entity bump.
- [x] **Where the feature flag lives:** RESOLVED — `shared/config/Settings.council_debate_enabled: bool = False`, env var `MORPHIC_COUNCIL_DEBATE`. Read once at `interface/api/container.py` construction. Checked at the entry point in `RouteToEngineUseCase._build_chain` (the use case takes a `council_enabled: bool` constructor arg, not a Settings reference, to keep `application/` framework-free).
- [x] **Reuse `Decision` vs. introduce `CouncilDecision`:** RESOLVED — **reuse `Decision`**. The existing entity already carries `agent_engine`, `confidence`, `rationale`, `description`. Adding a parallel entity would fragment the cognitive model. The debate-specific context (the two `Argument`s) lives in the `DecisionResolved` event payload, not on `Decision` itself, so the entity stays unchanged.

## Open Questions

- [ ] None blocking start of `plan.md`. (All ambiguities above were resolved at spec-time per spec-writer policy "make a reasonable default decision and proceed.")

## Constitution Compliance

- [x] **`domain/` has zero framework deps** — new files in `domain/ports/` and `domain/entities/council.py` use only `abc`, `enum`, Pydantic, and `domain/*` imports (NFR-5).
- [x] **KV-cache safe (stable prefix, append-only)** — debate prompts use stable system prefix; per-debate values in user message; no system-prompt mutation across calls; no past-event mutation in the bus (NFR-8).
- [x] **LAEE risk classification declared** — N/A. The debate produces a `Decision` (a deliberation artifact); it does not produce a LAEE-governed action. Risk = N/A documented here so reviewers do not expect a LAEE section in the plan.
- [x] **Unit + integration test strategy defined** — unit tests with fakes (≥ 8 tests, NFR-6); exactly one live integration test with Ollama + Gemini Flash (NFR-3). See plan §Test Strategy.
- [x] **Ollama path included (LOCAL_FIRST)** — wired engine pair includes OLLAMA (FR-12); resolver routes through `LLMGateway` whose default is Ollama when budget ≤ 0 (NFR-4).

---

*Next: generate `plan.md` via `/prp-plan` after this spec is approved.*
