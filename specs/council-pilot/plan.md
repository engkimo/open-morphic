# Implementation Plan — Council Pilot (2-Engine Debate Spike)

> **Spec:** [`spec.md`](spec.md)
> **Status:** draft
> **Estimated effort:** 2 days (1 day domain + use case + fakes; 0.5 day infra adapter; 0.5 day wiring + live integration test + docs)

## Summary

Introduce a domain-layer abstraction `CouncilDebatePort` that turns engine selection from a deterministic dict lookup into a deliberation between two engines, and a domain-layer event vocabulary (`DebateStarted`, `ArgumentSubmitted`, `DecisionResolved`) emitted via a new publish-only `EventBusPort`. Wire the council into one production entry point — `RouteToEngineUseCase._build_chain()` — behind a default-off feature flag. The wired engine pair is the cheapest already-registered combination (`OLLAMA` + `GEMINI_CLI`). The resolver is an LLM-judge over the two arguments. No UI, no SSE, no subscriber implementations beyond an in-memory recording adapter for tests. The deterministic path remains canonical with the flag off.

## Architecture Decisions

### Why LLM-judge (not weighted-vote) as the resolver

Weighted-vote requires a function `score(engine, subtask) → float` whose weights are hand-tuned. Those weights are precisely the deterministic table this spike is trying to replace; using them as the tiebreaker bakes the bootstrap into the deliberation and silently re-implements `_PRIMARY_ENGINE_MAP` under a new name. The honest rendering of "engine selection is a deliberation, not a lookup" (vision constraint #2) is to let an LLM read the two `Argument`s and judge — exactly what a human deliberator would do in a council meeting. The cost is one additional LLM call per debate (~$0.01 with Gemini 2.5 Flash, $0 with Ollama), which fits inside spec NFR-3 ($0.02/debate). The trade-off — LLM-judge bias — is captured in §Risks and mitigated by NFR-8 (stable prompt prefix) plus FR-12 (Ollama in the candidate pool when budget=0, so the judge has access to the cheapest model's argument and cannot bias toward a specific paid engine on cost grounds).

### Why publish-only `EventBusPort` (no subscribe API in this spike)

The UX vision explicitly orders operations: events first, transport second, render third (`project_vision_live_debate_ux.md` "Tension to watch"). A subscribe API forces a decision about transport (in-process callback? asyncio.Queue? Redis pub/sub?) that this spike has no information to make well. Publish-only means the bus is a write-side commitment whose read side is decided by the next sprint. The recording adapter in `infrastructure/events/in_memory_event_bus.py` exposes a `events: list[DebateEvent]` attribute for **test** consumption (FR-7); production consumers wait for the next sprint.

### Why wire into `RouteToEngineUseCase._build_chain()` (not into `interface/api/routes/tasks.py:138`)

The route handler at `tasks.py:138` is the *goal-level* auto-route for the whole task. The council vision is a *per-subtask* deliberation (constraint #2: "the engines themselves argue capability/cost/risk for the specific subtask"). Wiring at the goal level would force a debate over a vague top-level goal, which is exactly the case where deterministic routing already does fine. The right place is the *subtask* path, which today flows through `RouteToEngineUseCase._build_chain()`. By inserting the debate after the affinity-aware path returns no boost, the spike preserves the affinity learning path (which already encodes telemetry-driven preferences, satisfying constraint #3) and only deliberates when the deterministic path has nothing better to offer.

### Why the use case takes `council_enabled: bool` (not `Settings`)

`application/` is framework-free (constitution #2). Reading `shared/config/Settings` from a use case would either pull `pydantic-settings` into application or force a runtime dict in. The clean shape is: container reads the flag once at construction, passes a `bool` to the use case constructor. This matches the existing pattern (`affinity_min_samples`, `affinity_boost_threshold` on `RouteToEngineUseCase`).

### Ports added / changed

- **NEW:** `domain/ports/council_debate.py` — `CouncilDebatePort(ABC)` with one async method `debate(subtask, candidates) -> Decision`. Imports allowed: `abc`, `domain.entities.cognitive` (`Decision`), `domain.entities.council` (`SubtaskBrief`), `domain.value_objects.agent_engine` (`AgentEngineType`).
- **NEW:** `domain/ports/event_bus.py` — `EventBusPort(ABC)` with one async method `publish(event) -> None`. Imports allowed: `abc`, `domain.entities.council` (`DebateEvent`).
- **CHANGED:** `domain/ports/__init__.py` — re-export both new ports alphabetically.

### Entities added / changed

- **NEW:** `domain/entities/council.py` containing:
  - `Argument` (Pydantic BaseModel): `engine: AgentEngineType`, `capability_claim: str`, `cost_claim: str`, `risk_claim: str`, `recommended_approach: str`.
  - `SubtaskBrief` (Pydantic BaseModel): `id: str`, `description: str`, `task_type: TaskType`.
  - `DebateEvent` discriminated union (Pydantic): `DebateStarted` (debate_id, subtask, candidates, started_at), `ArgumentSubmitted` (debate_id, argument, submitted_at), `DecisionResolved` (debate_id, decision, arguments, resolved_at). Optional `DebateAbandoned` (debate_id, reason, abandoned_at) for FR-11; recommended.
- **UNCHANGED:** `domain/entities/cognitive.py::Decision` — reused as-is (FR-4, success metric: 0 lines modified).

### Infrastructure impls

- **NEW:** `infrastructure/council/__init__.py` (empty package marker).
- **NEW:** `infrastructure/council/two_engine_debate.py` — `TwoEngineDebate(CouncilDebatePort)`. Constructor takes `LLMGateway` and a resolver model name (default: `gemini/gemini-2.5-flash`; Ollama-fallback handled by gateway). For each candidate engine, issues one LLM call with a stable system prompt asking the engine (identified by name in the user message) to produce an `Argument` JSON object. Then issues one resolver LLM call passing both `Argument`s and asking for a `Decision` JSON object. Robust JSON parsing with FR-11 abandonment on malformed output.
- **NEW:** `infrastructure/events/__init__.py` (empty package marker).
- **NEW:** `infrastructure/events/in_memory_event_bus.py` — `InMemoryEventBus(EventBusPort)`. ~25 LOC: `self._events: list[DebateEvent] = []`, `async def publish(event)` appends, `events` property returns a copy.
- **CHANGED:** `infrastructure/llm/litellm_gateway.py` — **no change**. The two engine arguments and the resolver call all go through the existing `LLMGateway` port; no new gateway capability needed.

### Use cases added

- **NEW:** `application/use_cases/run_council_debate.py` — `RunCouncilDebateUseCase`. Constructor:
  - `debate_port: CouncilDebatePort`
  - `event_bus: EventBusPort`
  - `timeout_seconds: float = 15.0` (NFR-1)
  Method: `async def execute(subtask: SubtaskBrief, candidates: list[AgentEngineType]) -> Decision | None`. Returns `None` if the debate aborted (FR-11) so the caller can fall back to the deterministic chain. Internally: emit `DebateStarted` → call `debate_port.debate()` under `asyncio.wait_for(timeout=timeout_seconds)` → if it returned an `Argument` for each candidate (the port's contract guarantees this via the resolver call), emit one `ArgumentSubmitted` per — but wait, the port returns a `Decision`, not the arguments. Resolution: the port's `debate()` method shall return a tuple `(Decision, list[Argument])` so the use case can emit `ArgumentSubmitted` events. (Alternative: port emits events itself, but that pulls `EventBusPort` into infrastructure-side adapter responsibilities; cleaner to have application orchestrate emission.) The use case finally emits `DecisionResolved` carrying both pieces. On timeout / exception → emit `DebateAbandoned` and return `None`.

### Use cases changed

- **CHANGED:** `application/use_cases/route_to_engine.py::RouteToEngineUseCase`
  - Constructor adds three optional kwargs: `run_council_debate: RunCouncilDebateUseCase | None = None`, `council_enabled: bool = False`, `task_state_repo` already exists (used to append the resulting `Decision` to `SharedTaskState.decisions` per FR-10).
  - `_build_chain()` is extended: after the affinity-aware branch (lines 292-302) returns its chain, if (a) `council_enabled`, (b) `preferred_engine is None`, (c) the affinity branch did not produce a boost (no affinities or top score < threshold), and (d) the chain has ≥ 2 candidates excluding OLLAMA-as-final-fallback, then call `run_council_debate.execute(brief, top_2)`. If the returned `Decision` is non-None, rebuild the chain with `Decision.agent_engine` at the head, original chain deduped after, OLLAMA last. If `None`, use the original chain unchanged.
  - The `Decision` (when non-None) is appended to `SharedTaskState.decisions` via the existing `task_state_repo.add_decision` path (FR-10). If `task_id` is None (test path), skip.

### Interface layer

- **CHANGED:** `interface/api/container.py` — instantiate `InMemoryEventBus`, `TwoEngineDebate(llm_gateway=..., resolver_model=settings.council_resolver_model)`, `RunCouncilDebateUseCase(debate_port=..., event_bus=...)`, then pass `run_council_debate=...` and `council_enabled=settings.council_debate_enabled` into `RouteToEngineUseCase`.
- **CHANGED:** `shared/config/__init__.py` (or wherever `Settings` lives) — add two fields: `council_debate_enabled: bool = False` (env: `MORPHIC_COUNCIL_DEBATE`), `council_resolver_model: str = "gemini/gemini-2.5-flash"` (env: `MORPHIC_COUNCIL_RESOLVER_MODEL`).
- **NO new HTTP route, no new CLI command.** The spike is invisible at the interface boundary by design.

### Wiring point summary

| Concern | File | Edit |
|---|---|---|
| Feature flag definition | `shared/config/__init__.py` | add 2 fields |
| Flag → DI wiring | `interface/api/container.py` | construct event bus + debate adapter + use case; pass flag into `RouteToEngineUseCase` |
| Flag → behavior toggle | `application/use_cases/route_to_engine.py` | extend `_build_chain` |
| Decision audit trail | `application/use_cases/route_to_engine.py` | append to `SharedTaskState.decisions` via existing port |

## Data Model

```python
# domain/entities/council.py (pseudocode)
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field

from domain.entities.cognitive import Decision
from domain.value_objects.agent_engine import AgentEngineType
from domain.value_objects.model_tier import TaskType


class Argument(BaseModel):
    """One engine's case for taking a subtask."""
    model_config = ConfigDict(strict=True)
    engine: AgentEngineType
    capability_claim: str = Field(min_length=1)
    cost_claim: str = Field(min_length=1)
    risk_claim: str = Field(min_length=1)
    recommended_approach: str = Field(min_length=1)


class SubtaskBrief(BaseModel):
    """The unit a council debates over."""
    model_config = ConfigDict(strict=True)
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    task_type: TaskType


# Discriminated union — `kind` is the discriminator.
class _BaseEvent(BaseModel):
    model_config = ConfigDict(strict=True)
    debate_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class DebateStarted(_BaseEvent):
    kind: Literal["debate_started"] = "debate_started"
    subtask: SubtaskBrief
    candidates: list[AgentEngineType]
    started_at: datetime = Field(default_factory=datetime.now)


class ArgumentSubmitted(_BaseEvent):
    kind: Literal["argument_submitted"] = "argument_submitted"
    argument: Argument
    submitted_at: datetime = Field(default_factory=datetime.now)


class DecisionResolved(_BaseEvent):
    kind: Literal["decision_resolved"] = "decision_resolved"
    decision: Decision
    arguments: list[Argument]   # both arguments for renderer convenience
    resolved_at: datetime = Field(default_factory=datetime.now)


class DebateAbandoned(_BaseEvent):
    kind: Literal["debate_abandoned"] = "debate_abandoned"
    reason: str = Field(min_length=1)  # "timeout", "malformed_argument", "resolver_error"
    abandoned_at: datetime = Field(default_factory=datetime.now)


DebateEvent = Annotated[
    DebateStarted | ArgumentSubmitted | DecisionResolved | DebateAbandoned,
    Field(discriminator="kind"),
]
```

```python
# domain/ports/council_debate.py (pseudocode)
from __future__ import annotations
from abc import ABC, abstractmethod

from domain.entities.cognitive import Decision
from domain.entities.council import Argument, SubtaskBrief
from domain.value_objects.agent_engine import AgentEngineType


class CouncilDebatePort(ABC):
    """Two-engine debate over a subtask. Returns a Decision + the
    two Arguments that produced it. The application layer is responsible
    for emitting events; the port stays a pure deliberation function.

    Single-debate assumption: each call is independent (no cross-debate
    memory in this spike). Implementations MUST validate that
    len(candidates) == 2 and raise ValueError otherwise (spike scope).
    """

    @abstractmethod
    async def debate(
        self,
        subtask: SubtaskBrief,
        candidates: list[AgentEngineType],
    ) -> tuple[Decision, list[Argument]]: ...
```

```python
# domain/ports/event_bus.py (pseudocode)
from __future__ import annotations
from abc import ABC, abstractmethod

from domain.entities.council import DebateEvent


class EventBusPort(ABC):
    """Publish-only domain event bus.

    The subscribe / consume side is intentionally absent in this spike.
    The next sprint will introduce a transport-bound subscriber
    (SSE / WebSocket); until then the in-memory recording adapter
    in `infrastructure/events/` is the only consumer (test-only).
    """

    @abstractmethod
    async def publish(self, event: DebateEvent) -> None: ...
```

## Contracts

### API

**No HTTP API changes.** The flag is environment-only; no new routes, no payload changes on `POST /task` or `GET /task/{id}`. (`SharedTaskState.decisions` is already exposed via existing endpoints; the council adds rows to that list but does not change its schema.)

### CLI

**No CLI changes.** No new `morphic` subcommand for the spike. (A `morphic council debate <subtask>` command is plausible follow-up work but is explicitly out of scope.)

### Event payload (consumed by next sprint, not by this one)

The `DebateEvent` discriminated union shape above IS the contract that the next sprint's renderer will subscribe to. Pinning it here so the renderer sprint can begin in parallel against the schema (with the in-memory bus as a stand-in) once this spike merges.

## LLM / Engine Routing

- **Per-engine argument call:** routed through existing `LLMGateway.complete()`. Model selection delegated to the gateway's existing LOCAL_FIRST policy. The "engine" parameter is **passed in the user prompt only** (the gateway picks the underlying model); the spike does not invoke `AgentEnginePort` drivers for argument generation — it asks the LLM to *speak as* each engine. This is deliberate: invoking actual engines would multiply cost by 6× (each engine spins up its own runtime) for negligible deliberation quality, and is the kind of premature scaling the spike is meant to defer.
- **Resolver call:** routed through `LLMGateway.complete()` with `model=settings.council_resolver_model` (default `gemini/gemini-2.5-flash`). With budget ≤ 0 the gateway falls back to Ollama unchanged.
- **Default fallback chain (within gateway):** Gemini Flash → Ollama (existing gateway policy, unchanged).
- **Estimated cost per debate:**
  - Budget > 0, Gemini Flash for both args + resolver: ~3 × $0.005 = **$0.015** (well under NFR-3 $0.02).
  - Budget = 0, Ollama for everything: **$0** (NFR-4).

## LAEE touchpoints

- **None.** Risk classification: **N/A.** The debate is a deliberation that produces a `Decision` (a record of reasoning). It does not produce an action that LAEE governs (no filesystem write, no shell command, no network mutation). The downstream actions taken by the chosen engine are governed by their existing LAEE integration; that path is unchanged.

## Test Strategy

### Unit tests (DB-free, LLM-free)

1. **`tests/unit/domain/test_council_entities.py`** *(new, ≥ 4 tests)*
   - `Argument` / `SubtaskBrief` / each `DebateEvent` variant: round-trip serialization, required field validation, type strictness.
   - Discriminated union: deserializing `{"kind": "debate_started", ...}` produces `DebateStarted`, etc.

2. **`tests/unit/application/_fakes/in_memory_event_bus.py`** *(new, ~20 LOC)*
   - **NOTE on TD-187:** test code MAY import port-compliant `InMemory*` adapters from `infrastructure/`. To keep this fake decoupled from the production adapter (the production adapter may grow features the test does not want), the fake lives under `tests/unit/application/_fakes/` and is a minimal `EventBusPort` subclass storing events in a list. The production `InMemoryEventBus` in `infrastructure/events/` is imported by the integration test, not the unit tests.

3. **`tests/unit/application/_fakes/fake_council_debate.py`** *(new, ~30 LOC)*
   - `FakeCouncilDebate(CouncilDebatePort)` returns a pre-configured `(Decision, [Argument, Argument])` tuple. Has a `raise_on_call: Exception | None` knob to test FR-11 fallback. Has a `delay_seconds: float` knob to test NFR-1 timeout.

4. **`tests/unit/application/test_run_council_debate.py`** *(new, ≥ 4 tests)*
   - Happy path: 1 `DebateStarted` + 2 `ArgumentSubmitted` + 1 `DecisionResolved` events, in order.
   - Timeout path: `delay_seconds=20` with `timeout_seconds=15` → 1 `DebateStarted` + 1 `DebateAbandoned(reason="timeout")`, return value `None`.
   - Exception path: `raise_on_call=ValueError("boom")` → `DebateAbandoned(reason="...")`, return `None`.
   - Validation: `len(candidates) != 2` raises `ValueError` before any event is emitted.

5. **`tests/unit/application/test_route_to_engine_council.py`** *(new, ≥ 3 tests)*
   - `council_enabled=False`: `_build_chain` behavior is byte-identical to the current implementation (regression net).
   - `council_enabled=True` + fake debate returning `Decision(agent_engine=GEMINI_CLI)`: returned chain has `GEMINI_CLI` at head, original chain deduped after.
   - `council_enabled=True` + fake debate returning `None` (abandoned): returned chain equals the original deterministic chain.

### Integration tests (live LLM, exactly 1)

6. **`tests/integration/test_council_pilot_live.py`** *(new, marked `@pytest.mark.live`)*
   - Wires real `LiteLLMGateway` + real `TwoEngineDebate` + real `InMemoryEventBus` + real `RunCouncilDebateUseCase`.
   - Subtask: `"Summarize a 2-paragraph plan to bake bread."` (intentionally trivial; NFR-3 $0.02 cap enforces low complexity).
   - Candidates: `[OLLAMA, GEMINI_CLI]` (per FR-12).
   - Asserts: returned `Decision` is non-None; `Decision.agent_engine in {OLLAMA, GEMINI_CLI}`; `Decision.rationale` non-empty and contains both engine names (case-insensitive substring match); recording bus has ≥ 4 events in the right kinds; total wall-clock < 15s; total cost < $0.02 (read from `LLMResponse.cost_usd` accumulator).

### Live verification (manual, recorded as Round 21 in `MEMORY.md`)

7. Single manual run via `morphic doctor check` + the integration test above, results recorded under "Live Verification Summary" in `MEMORY.md` per project convention.

### Verification commands

```bash
# 1. Domain purity
rg -l "from (sqlalchemy|fastapi|litellm|redis|mem0|celery|httpx|infrastructure|application|interface)" \
   domain/ports/council_debate.py domain/ports/event_bus.py domain/entities/council.py
# expected: no output

# 2. Application purity (constitution #2)
rg -n "from infrastructure" application/use_cases/run_council_debate.py application/use_cases/route_to_engine.py
# expected: no output

# 3. Decision unchanged
git diff main -- domain/entities/cognitive.py
# expected: no output

# 4. Unit + integration suites
uv run --extra dev pytest tests/unit/domain/test_council_entities.py \
                          tests/unit/application/test_run_council_debate.py \
                          tests/unit/application/test_route_to_engine_council.py -v

# 5. Live integration (requires GEMINI_API_KEY + ollama running)
uv run --extra dev pytest tests/integration/test_council_pilot_live.py -v -m live

# 6. Regression: existing tests with flag off
uv run --extra dev pytest tests/unit/application/test_route_to_engine.py -v
```

## Migration Plan

- **Alembic migration:** none. No DB schema changes. `SharedTaskState.decisions` already accepts `Decision` instances; the council just adds rows.
- **Data migration:** none.
- **Operator action required:** zero (flag default-off; no new env var needs to be set to keep current behavior).

## Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **Debate doubles wall-clock latency** for the wired entry point. Three sequential LLM calls per debate (arg-A → arg-B → resolve). | MED | NFR-1 hard timeout 15s + FR-11 fallback. Flag default-off so production users opt in. Future sprint: parallelize argument generation via `asyncio.gather` (out of scope here, called out as next-sprint candidate). |
| **LLM-judge bias.** Resolver may systematically prefer one engine because of phrasing artifacts in the prompt. | MED | Stable prompt prefix (NFR-8) keeps system message byte-identical; per-debate values in user message; engine names in user message are presented in randomized order in the resolver prompt. Live integration test asserts `Decision.agent_engine` is one of two candidates but does NOT assert which (no expected-winner test = no built-in bias confirmation). Follow-up sprint: A/B the judge against a held-out set with engine-name swaps. |
| **Vacuous arguments.** Both engines produce "looks fine, ship it" arguments and the resolver has no signal. | MED-HIGH | The argument prompt requires four distinct claims (capability, cost, risk, approach) with `min_length=1` Pydantic validation. If any is missing → JSON parse fail → `DebateAbandoned`. Vacuous content that passes parsing is a quality issue surfaced in live test review (manual judgement on Round 21 transcript), not in automated test gates. |
| **Spike normalizes a flag-gated dead path** (flag stays off forever, code rots). | LOW | Tasks include explicit "next-sprint follow-up ADR" entry in `docs/TECH_DECISIONS.md` listing the criteria for promoting the flag to default-on (debate cost, decision quality, latency thresholds). If the follow-up sprint does not happen within 6 weeks, the spike is removed in a cleanup PR rather than left as zombie code. |
| **Test code importing `infrastructure/events/in_memory_event_bus.py`** muddies layer policy. | LOW | TD-187 explicitly allows test code to import port-compliant `InMemory*` adapters from `infrastructure/`. Unit tests use the test-local fake under `tests/unit/application/_fakes/`; only the live integration test imports the production adapter. Constitution-compliant per TD-187 amendment. |
| **`shared/config/Settings` does not exist as named** in this repo (the env-var loading mechanism may have moved). | LOW | Plan task T-CFG-01 verifies the location at edit time and adapts the field name accordingly. The contract is "one boolean read once at container construction"; the exact module path is implementation detail. |

## Rollout

- **Feature flag:** `MORPHIC_COUNCIL_DEBATE` (env, default `false`). Per spec FR-9.
- **Gradual rollout:** local opt-in only for the spike. No staging/prod toggle. Promotion to default-on is a separate spec (see Risks row 4).
- **Commit series (English, one task → one commit per project preference):**
  1. `test(council-pilot): add domain entity tests for council events (RED)`
  2. `feat(council-pilot): add Argument/SubtaskBrief/DebateEvent in domain/entities/council`
  3. `feat(council-pilot): add CouncilDebatePort + EventBusPort in domain/ports`
  4. `test(council-pilot): add fake debate + fake event bus + use case tests (RED)`
  5. `feat(council-pilot): add RunCouncilDebateUseCase`
  6. `test(council-pilot): add RouteToEngineUseCase council branch tests (RED)`
  7. `feat(council-pilot): wire council into RouteToEngineUseCase._build_chain behind flag`
  8. `feat(council-pilot): add InMemoryEventBus adapter (publish-only recorder)`
  9. `feat(council-pilot): add TwoEngineDebate adapter (LiteLLM-backed, LLM-judge resolver)`
  10. `feat(council-pilot): wire council into container with default-off flag`
  11. `test(council-pilot): live integration with Ollama + Gemini Flash`
  12. `docs(council-pilot): add TD-194 ADR + CHANGELOG entry`
- **Rollback:** revert the 12 commits in reverse order; no data migration to undo.

## Constitution Compliance Gate

- [x] **#1 Local-First Routing** — wired pair includes OLLAMA; resolver routes through LLMGateway whose default is Ollama at budget=0 (NFR-4).
- [x] **#2 Clean Architecture** — new domain files import only stdlib + Pydantic + `domain/*`; new application use case imports only domain ports / entities; verifiable via §Test Strategy verification commands 1–3.
- [x] **#3 KV-Cache** — debate prompts use stable system prefix; per-debate values in user message; no event mutation in the bus (NFR-8).
- [x] **#4 Safety over Capability** — N/A. The spike does not introduce LAEE actions.
- [x] **#5 TDD** — every production-code commit (2, 5, 7, 9, 10) is preceded by a RED test commit (1, 4, 6, 11 also serves as final live RED-then-GREEN gate).
- [x] **#6 Spec-Driven** — this plan accompanies an approved `spec.md` per the §Workflow contract in `specs/README.md`.
- [x] **#7 Cost Transparency** — debate cost is propagated through existing `LLMResponse.cost_usd`; live test asserts ≤ $0.02 (NFR-3); no new cost path bypassed.
- [x] **#8 Context Continuity** — the resolved `Decision` is appended to `SharedTaskState.decisions` (FR-10), preserving cross-engine handoff semantics.
- [x] **#9 Append-Only History** — events on the bus are append-only by adapter contract; no rewriting of past decisions; CHANGELOG entry is additive (commit 12).
- [x] **#10 Evolve, Don't Patch** — this is a generic deliberation mechanism (port + adapter + event bus), not a patch for a specific failing test case. The spike's dimensions (2 engines, single entry point, flag-gated) are the discipline boundary, not workarounds.

---

*Next: generate `tasks.md` via `/prp-implement` after this plan is approved.*
