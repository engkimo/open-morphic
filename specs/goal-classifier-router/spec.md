# Feature Specification — Goal Classifier Router (Planner Model Selection)

> **Branch:** `feature/goal-classifier-router`
> **Status:** draft
> **Owner:** Ryousuke (ryosuke.ohori@ulusage.com)
> **Created:** 2026-05-19

## Problem Statement

The 2026-05-19 live A/B between Sonnet 4.6 and Haiku 4.5 as the `LLMPlanner` model
(see `memory/haiku_planner_ab_2026_05_19.md`) confirmed a real cost win and a real
quality regression at the same time: Haiku 4.5 cuts planner per-call cost by 47.6%
(planner-only ~66.7%) but degrades `entity_preserved` by **−11.4pt** and the
composite `plan_eval` score by **−0.070**. The regression is structural, not noise:
Haiku reliably abstracts away Japanese proper nouns, quoted file/column names, and
specific entities the planner system prompt explicitly forbids dropping, while
Sonnet honors the same constraint. On generic English tasks (e.g. *"Build REST API"*,
*"Implement Dijkstra in Rust"*) both models tie at `entity_preserved = 1.0`.

Today the planner picks one model globally via `infrastructure/fractal/llm_planner.py`
configuration; there is no per-goal routing. As a result the team has only two
options: keep Sonnet everywhere (pay the full bill) or switch to Haiku everywhere
(eat the entity-preservation regression). Neither is acceptable. We need a small,
auditable router that classifies the incoming goal and dispatches **only the safe
subset** to Haiku, leaving everything else on Sonnet. This is the cheapest path to
recover the ~47.6% cost win on the eligible slice of traffic without regressing
quality on the rest.

## Goals

- Introduce a `GoalClassifierPort` whose single responsibility is to map a goal
  string to a `PlannerModel` choice (`SONNET` or `HAIKU`). Measurable: a unit test
  with a fake classifier injected into the planner-selection call site demonstrates
  end-to-end routing without touching the existing planner implementation.
- Land **two production-grade adapters** for the port: a remote LLM adapter
  (`LLMGoalClassifier`) and a local Ollama adapter (`LocalGoalClassifier`,
  qwen3:8b). Both must satisfy `LOCAL_FIRST` (the local adapter is the
  default when budget ≤ 0). Measurable: with budget=0 the router runs at $0/call.
- Ship the router behind a feature flag (`MORPHIC_PLANNER_ROUTER=disabled` by
  default) so the existing Sonnet-everywhere behaviour is byte-identical until the
  flag is flipped. Measurable: with the flag unset, the existing planner unit
  tests pass with identical pass count.
- Make the routing decision **observable**: emit a `goal_classified` event on the
  existing `EventBusPort` with `{ goal_hash, chosen_model, reason, classifier_latency_ms, classifier_cost_usd }`,
  and increment Prometheus counters by `chosen_model`.
- After enablement, demonstrate that **router-gated Haiku is within −5pt of the
  Sonnet baseline on every plan-quality axis** when re-running the A/B harness.
  This is the criterion the previous A/B failed; meeting it is the success bar.

## Non-Goals

- **No new planner.** We are *selecting* between two existing planner models; we are
  not changing the `LLMPlanner` prompt, the candidate-node schema, or the parsing.
- **No multi-model fan-out / ensemble.** Exactly one planner runs per goal. The
  router picks one model; it does not run both and merge.
- **No rule-based pre-filter as the primary mechanism.** Per `feedback_no_rulebased.md`
  the user explicitly prefers pure-LLM classification over regex heuristics. A
  hybrid is enumerated in `plan.md` as an *alternative* with a clear caveat; it is
  not the default and is not in scope unless explicitly approved.
- **No persistence of past classifications.** The router is stateless within this
  spec. Caching identical-goal classifications is a follow-up optimization, not a
  v1 requirement.
- **No expansion of the model set.** Two classes only: `SONNET` and `HAIKU`. Adding
  a third class (e.g. Opus, GPT-4o-mini, Ollama-as-planner) is a follow-up spec.
- **No replacement of the existing planner selection in non-planner LLM call sites.**
  Evaluators, classifiers, reflection, council debate, etc. keep their current
  model wiring. The router governs `LLMPlanner` only.
- **No UI surface.** The decision is observable via events + logs + metrics, not
  via a user-facing screen in this spec.
- **No prompt-tightening experiment.** The A/B memo lists "tighten Haiku prompt
  with a few-shot example" as an alternative path to the same goal. That path is
  parallel work; this spec assumes the prompt stays as-is and the router carries
  the safety load.

## User Stories

### As a developer wiring planner cost reductions, I want a feature-flagged router that picks the planner model per goal, so that I can turn on Haiku for safe goals without giving up Sonnet quality on entity-heavy goals.

**Acceptance Criteria:**
- [ ] Given `MORPHIC_PLANNER_ROUTER=enabled` and the input goal `"Build REST API in Python"`, when the planner selection runs, then the chosen model is `PlannerModel.HAIKU` and a `goal_classified` event is emitted with `chosen_model="haiku"`.
- [ ] Given `MORPHIC_PLANNER_ROUTER=enabled` and the input goal `"東京から京都への新幹線の最安ルートを調査"`, when the planner selection runs, then the chosen model is `PlannerModel.SONNET` and the event's `reason` references entity preservation / non-ASCII / proper-noun risk.
- [ ] Given `MORPHIC_PLANNER_ROUTER=enabled` and the input goal `"Generate a Python script that sorts a CSV file by the 'date' column"`, when the planner selection runs, then the chosen model is `PlannerModel.SONNET` (quoted column name = specific entity).
- [ ] Given `MORPHIC_PLANNER_ROUTER=enabled` and the classifier raises or returns malformed output, when the planner selection runs, then the chosen model is `PlannerModel.SONNET` (safe fallback) and the event's `reason` includes `"classifier_failed"`.
- [ ] Given `MORPHIC_PLANNER_ROUTER=disabled` (default), when the planner selection runs for any goal, then the chosen model equals the prior global default (Sonnet) and no `goal_classified` event is emitted (regression guard).

### As an SRE responsible for cost dashboards, I want every routing decision to emit a structured event + metric, so that I can confirm the router is shedding the expected slice of traffic to Haiku and not silently regressing onto Sonnet.

**Acceptance Criteria:**
- [ ] Given the router is enabled, when N goals are classified in a session, then the `EventBusPort` recording adapter contains exactly N `goal_classified` events in order.
- [ ] Given the router is enabled, when an event is inspected, then it contains `goal_hash` (sha256-truncated, not the raw goal), `chosen_model`, `reason` (≤200 chars), `classifier_latency_ms`, and `classifier_cost_usd`.
- [ ] Given a classifier adapter is used, when latency exceeds NFR-1 budget, then a warning is logged with `goal_hash` and the actual latency; routing still completes (fallback to Sonnet).
- [ ] Given budget = 0 (LOCAL_FIRST), when the router runs, then the active adapter is `LocalGoalClassifier` (Ollama) and `classifier_cost_usd == 0`.

### As a PR reviewer, I want to confirm the router does not violate Clean Architecture, so that classification logic stays inside `domain/` + `infrastructure/` and does not leak into application use cases.

**Acceptance Criteria:**
- [ ] Given the new port file `domain/ports/goal_classifier.py`, when grepped for framework imports (`sqlalchemy|fastapi|litellm|redis|mem0|celery|httpx`), then nothing is returned.
- [ ] Given `application/` after the change, when grepped for `from infrastructure.routing`, then nothing is returned (DI binds the port at `interface/api/container.py`).
- [ ] Given the existing planner unit tests, when run, then no test imports the concrete classifier; all use the in-memory fake from `tests/unit/application/_fakes/`.

## Functional Requirements

- **FR-1:** The system shall introduce `domain/value_objects/planner_model.py::PlannerModel` — a `StrEnum` with exactly two members: `SONNET = "sonnet"` and `HAIKU = "haiku"`. The model identifier strings used by `LLMGateway` shall be resolved by a separate adapter function (`PlannerModel.to_gateway_id()`), so that gateway-specific name churn does not bleed into domain.
- **FR-2:** The system shall introduce `domain/value_objects/goal_classification.py::GoalClassification` — a Pydantic value object carrying `chosen_model: PlannerModel`, `reason: str` (≤200 chars), `confidence: float ∈ [0, 1]`, `classifier_latency_ms: int`, `classifier_cost_usd: float`.
- **FR-3:** The system shall introduce `domain/ports/goal_classifier.py::GoalClassifierPort` — an `abc.ABC` with one abstract method `async def classify(goal: str) -> GoalClassification`. The port shall reject empty / whitespace-only goals by raising `ValueError`.
- **FR-4:** The system shall introduce `domain/value_objects/council_events.py::GoalClassified` — a new variant in the existing `DebateEvent` discriminated union (or a sibling event union if discriminated-union extension is not viable; plan decides). The event payload is `{ debate_id: UUID, goal_hash: str, chosen_model: str, reason: str, classifier_latency_ms: int, classifier_cost_usd: float }`. **The raw goal MUST NOT be in the event**; only its sha256-truncated hash.
- **FR-5:** The system shall introduce `infrastructure/routing/llm_goal_classifier.py::LLMGoalClassifier(GoalClassifierPort)` — a remote-LLM adapter that issues exactly one LLM call via the existing `LLMGateway` port (default model: Haiku 4.5, configurable). System prompt is a stable 2-class classifier instruction; user message contains the goal. Output JSON: `{"model": "haiku"|"sonnet", "reason": "..."}`. Parse errors fall back to `SONNET` and `reason="parse_failed: <truncated>"`.
- **FR-6:** The system shall introduce `infrastructure/routing/local_goal_classifier.py::LocalGoalClassifier(GoalClassifierPort)` — an Ollama adapter using `qwen3:8b` via the existing `OllamaManagerPort`. Same prompt contract as FR-5; cost is recorded as 0.
- **FR-7:** The system shall introduce a domain service `domain/services/planner_model_router.py::PlannerModelRouter` that takes a `GoalClassifierPort` and a settings object (`router_enabled: bool`, `default_model: PlannerModel`) and exposes `async def select_for(goal: str) -> tuple[PlannerModel, GoalClassification | None]`. When `router_enabled is False`, the router returns `(default_model, None)` without calling the classifier. When the classifier raises, the router returns `(PlannerModel.SONNET, GoalClassification(..., reason="classifier_failed: ..."))`.
- **FR-8:** The system shall integrate the router into the planner call site by passing the router into `LLMPlanner.__init__` and consulting `router.select_for(goal)` inside `LLMPlanner.generate_candidates` *before* the LLM call. The chosen `PlannerModel` is then translated via `PlannerModel.to_gateway_id()` and passed to `LLMGateway.complete(model=...)`. The existing stable system prompt is unchanged (TD-190 KV-cache safety preserved).
- **FR-9:** The system shall, after a successful classification, publish a `GoalClassified` event via the injected `EventBusPort`. Failure of the bus publish shall NOT abort the planner call (best-effort observability).
- **FR-10:** The system shall expose the feature flag as `MORPHIC_PLANNER_ROUTER` (env var, default `"disabled"`, accepted values `"disabled"|"enabled"`) wired through `shared/config/Settings.planner_router_mode` and read once at container construction in `interface/api/container.py`. Toggling the flag shall require no code change and no service restart beyond what existing flags require.
- **FR-11:** The system shall, when `LOCAL_FIRST=true` and the configured monthly budget is exhausted (existing `CostTracker` signals), prefer `LocalGoalClassifier` over `LLMGoalClassifier`. The selection happens at container-construction time using existing budget-aware DI patterns; runtime swap is out of scope.
- **FR-12:** The system shall emit Prometheus counters `morphic_goal_classifier_decisions_total{model="haiku|sonnet", reason_category="..."}` and a histogram `morphic_goal_classifier_latency_ms`. Existing metrics infrastructure is reused; no new transport.

## Non-Functional Requirements

- **NFR-1 (Latency):** Classifier wall-clock latency per call shall be **< 300ms p95** for `LLMGoalClassifier` (Haiku 4.5) and **< 800ms p95** for `LocalGoalClassifier` (qwen3:8b on the dev box). The router shall enforce a hard timeout (`asyncio.wait_for`) at **1500ms**; on timeout, fallback to `SONNET` per FR-7.
- **NFR-2 (Cost):** Per-call classifier cost shall be **≤ $0.0005** for the remote adapter and **$0.0000** for the local adapter. Per-task cumulative classifier overhead shall be **≤ 5%** of the planner LLM cost it gates (i.e. it must not eat its own savings).
- **NFR-3 (LOCAL_FIRST):** A working `LocalGoalClassifier(GoalClassifierPort)` adapter on Ollama qwen3:8b is a **release blocker** (per Constitution §1). With budget = 0 the router shall complete classification at $0.
- **NFR-4 (Clean Architecture):** `domain/ports/goal_classifier.py`, `domain/value_objects/planner_model.py`, `domain/value_objects/goal_classification.py`, and `domain/services/planner_model_router.py` shall import only stdlib + Pydantic + `domain/*`. Verifiable: `rg -l "from (sqlalchemy|fastapi|litellm|redis|mem0|celery|httpx|infrastructure|application|interface)" domain/ports/goal_classifier.py domain/value_objects/planner_model.py domain/value_objects/goal_classification.py domain/services/planner_model_router.py` returns nothing.
- **NFR-5 (KV-cache safety):** The classifier prompt shall follow the stable-prefix rule (TD-190): the system message is byte-identical across all calls; the per-call goal lives in the user message. No timestamps, no goal hashes, no per-call IDs in the system prompt.
- **NFR-6 (Privacy):** The raw goal string shall NOT appear in any `EventBusPort` event, Prometheus label, or structured log emitted by the router. Only a sha256-truncated (16-hex-char) `goal_hash` is acceptable for correlation.
- **NFR-7 (TDD):** Every production-code task shall be preceded by a failing test task. Unit tests use a fake `GoalClassifierPort` from `tests/unit/application/_fakes/`; no LLM call from any unit test.
- **NFR-8 (Backward compatibility):** With `MORPHIC_PLANNER_ROUTER=disabled` (the default), the existing planner unit tests shall pass with identical pass count and identical chosen-model byte trace. Verifiable: `tests/unit/infrastructure/fractal/test_llm_planner.py` test count and pass count match `main` HEAD.
- **NFR-9 (A/B success bar):** After enabling the router, re-running `benchmarks/planner_quality_ab.py` in `--router` mode shall yield, on the same 10-goal fixed benchmark with 3 trials per cell, an `entity_preserved` mean **within −5pt of the Sonnet baseline** and a `plan_eval` mean **within −0.030 of the Sonnet baseline**, while still capturing ≥ 30% of the Haiku per-call cost saving on the eligible slice.

## Success Metrics

| Metric | Target |
|---|---|
| Framework imports in new domain files (`sqlalchemy|fastapi|litellm|...`) | 0 |
| `from infrastructure.routing` in `application/` | 0 |
| Unit tests added for port + router + adapters (fake LLM) | ≥ 12 |
| Live integration tests added (real Ollama, $0) | ≥ 1 |
| Live integration tests added (real Anthropic Haiku) | ≥ 1 |
| `MORPHIC_PLANNER_ROUTER=disabled` regression failures | 0 |
| Classifier p95 latency, remote (Haiku 4.5) | < 300ms |
| Classifier p95 latency, local (qwen3:8b) | < 800ms |
| Per-call classifier cost, remote | ≤ $0.0005 |
| Per-call classifier cost, local | $0.0000 |
| Router-gated A/B `entity_preserved` Δ vs Sonnet baseline | ≥ −5pt |
| Router-gated A/B `plan_eval` Δ vs Sonnet baseline | ≥ −0.030 |
| Captured share of Haiku per-call saving on eligible slice | ≥ 30% |
| Raw goal strings appearing in event payloads / metric labels / logs | 0 |

## Open Questions

- [ ] **Eligible-slice definition for NFR-9:** the A/B harness needs an explicit definition of which of the 10 benchmark goals are "eligible for Haiku" so we can compute "share of Haiku saving captured" reproducibly. Proposed default: the router's own decision on each goal *is* the slice definition. Confirm before authoring `tasks.md`.
- [ ] **Confidence threshold for routing to Haiku:** FR-2 introduces a `confidence` field but FR-7 does not use it to gate the decision. Should we require `confidence ≥ 0.7` to route to Haiku, otherwise fall back to Sonnet? Decision deferred to `plan.md`.
- [ ] **Reason taxonomy for Prometheus `reason_category` label:** FR-12 references a categorical label but the values are not enumerated here. Plan to define ~5 buckets (`generic_tech_english`, `non_ascii_entity`, `quoted_specific_entity`, `multilingual`, `classifier_failed`) in `plan.md`.

## Constitution Compliance

- [x] **`domain/` has zero framework deps** — new files in `domain/ports/`, `domain/value_objects/`, and `domain/services/planner_model_router.py` use only `abc`, `enum`, `hashlib`, Pydantic, and `domain/*` imports (NFR-4).
- [x] **KV-cache safe (stable prefix, append-only)** — classifier prompts use a stable byte-identical system message; per-call goal lives only in the user message; no event mutation; planner system prompt (TD-190) is unchanged (NFR-5).
- [x] **LAEE risk classification declared** — N/A. The router selects a planner model; it does not produce a LAEE-governed action. Documented here so reviewers do not expect a LAEE section in the plan.
- [x] **Unit + integration test strategy defined** — unit tests with port fakes (≥ 12 tests, NFR-7); ≥ 1 live integration test on Ollama qwen3:8b ($0); ≥ 1 live integration test on Anthropic Haiku; ≥ 1 router-gated A/B re-run via `benchmarks/planner_quality_ab.py --router`.
- [x] **Ollama path included (LOCAL_FIRST)** — `LocalGoalClassifier(GoalClassifierPort)` on qwen3:8b is a release blocker (NFR-3); LOCAL_FIRST + budget=0 selects it at container-construction time (FR-11).

---

*Next: generate `plan.md` via `/prp-plan` after this spec is approved.*
