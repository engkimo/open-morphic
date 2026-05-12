# Tasks — Council Pilot (2-Engine Debate Spike)

> **Spec:** [`spec.md`](spec.md)
> **Plan:** [`plan.md`](plan.md)
> **Slug:** `council-pilot`
> **`[P]` = parallelizable** — the marked task touches a disjoint file set
> from every other unfinished task in the list and shares no in-flight state.
> **TDD:** every production-code task is preceded by a failing test task.
> **Commit cadence:** one task → one commit → one push (per project preference
> "1 fix → commit & push → report. No batching."). Verification-only tasks
> (pytest / ruff / rg) do not produce commits.

---

## Milestone 0 — Setup & constitution check

- [ ] **T-01** — Constitution audit before code: confirm the new domain files will
  not violate `.specify/memory/constitution.md` Principle #2 or
  `.claude/rules/clean-architecture.md`.
  - Action: re-read both files; record in the task tracker that the planned
    `domain/ports/council_debate.py`, `domain/ports/event_bus.py`, and
    `domain/entities/council.py` will import only `abc`, `enum`, `typing`,
    Pydantic, and `domain/*` modules.
  - **Done when:** the spike has no open `[ ]` constitution-compliance line in
    `spec.md` (already satisfied at spec time; this is a gate against drift).
  - **Commit:** none.

- [ ] **T-02** — Create feature branch `feature/council-pilot` off `main`.
  - Command: `git switch -c feature/council-pilot`
  - **Done when:** `git rev-parse --abbrev-ref HEAD` prints `feature/council-pilot`.
  - **Commit:** none.

- [ ] **T-03** — Capture pre-spike baseline (RED-protection).
  - Command: `uv run --extra dev pytest tests/unit/application/test_route_to_engine.py tests/unit/domain/test_agent_engine_router.py -v`
  - **Done when:** both suites pass on `main` HEAD; record pass count and
    duration for later regression comparison (NFR-7 evidence).
  - **Commit:** none.

- [ ] **T-04** — Draft TD-194 ADR header in `docs/TECH_DECISIONS.md` (body filled at T-22).
  - File: `/Users/ryousuke/open-morphic/docs/TECH_DECISIONS.md`
  - Edit: append a stub section
    `## TD-194: Council Pilot — 2-Engine Debate as a Domain Port` with
    `**Date:** 2026-05-12`, `**Status:** Proposed`, and a one-line
    "Body to be filled on landing — see `specs/council-pilot/`."
  - **Done when:** `rg -n "^## TD-194" docs/TECH_DECISIONS.md` returns 1 line.
  - **Commit:** `docs(council-pilot): stub TD-194 ADR header`

---

## Milestone 1 — RED: domain entity tests

- [ ] **T-05** `[P]` — Add `tests/unit/domain/test_council_entities.py`.
  - File: `/Users/ryousuke/open-morphic/tests/unit/domain/test_council_entities.py`
  - Content (per plan §Test Strategy item 1, ≥ 4 tests):
    1. `test_argument_round_trip` — instantiate `Argument(...)` with all fields,
       `model_dump_json()` then `model_validate_json()`, assert equality.
    2. `test_subtask_brief_required_fields` — Pydantic raises `ValidationError`
       when `description` is empty (`min_length=1`).
    3. `test_debate_event_discriminator` — `DebateEvent.model_validate({"kind":
       "decision_resolved", ...})` produces a `DecisionResolved` instance.
    4. `test_debate_started_minimal` — instantiate `DebateStarted` with only
       `subtask` and `candidates`; assert `debate_id` autogen, `started_at`
       autogen, `kind == "debate_started"`.
  - Imports reference not-yet-existing `domain.entities.council` — this is the
    RED-by-import-error step.
  - Target ≤ 80 LOC.
  - **Done when:** `uv run --extra dev pytest tests/unit/domain/test_council_entities.py -v`
    fails at collection time with `ModuleNotFoundError: domain.entities.council`.
  - **Commit:** `test(council-pilot): add domain entity tests for council events (RED)`

---

## Milestone 2 — GREEN: domain entities

- [ ] **T-06** — Create `domain/entities/council.py` (per plan §Data Model code block).
  - File: `/Users/ryousuke/open-morphic/domain/entities/council.py`
  - Content: verbatim from plan §Data Model — `Argument`, `SubtaskBrief`,
    `DebateStarted`, `ArgumentSubmitted`, `DecisionResolved`, `DebateAbandoned`,
    `DebateEvent` discriminated union. Module docstring documents the
    publish-only event contract.
  - **Done when:**
    - `rg -n "from (sqlalchemy|fastapi|litellm|redis|mem0|celery|httpx|infrastructure|application|interface)" domain/entities/council.py` returns nothing.
    - `uv run --extra dev pytest tests/unit/domain/test_council_entities.py -v`
      passes (4/4).
  - **Commit:** `feat(council-pilot): add Argument/SubtaskBrief/DebateEvent in domain/entities/council`

---

## Milestone 3 — GREEN: domain ports

> Both ports may be added in parallel (disjoint files). The re-export edit in
> T-09 is sequential after both.

- [ ] **T-07** `[P]` — Create `domain/ports/council_debate.py` (per plan §Data Model).
  - File: `/Users/ryousuke/open-morphic/domain/ports/council_debate.py`
  - Content: verbatim from plan code block — `CouncilDebatePort(ABC)` with one
    abstract method `debate(subtask, candidates) -> tuple[Decision, list[Argument]]`.
    Class docstring documents `len(candidates) == 2` validation requirement
    and single-debate-no-memory assumption.
  - **Done when:**
    - `python -c "from domain.ports.council_debate import CouncilDebatePort; import inspect; assert sum(1 for _, m in inspect.getmembers(CouncilDebatePort, predicate=inspect.isfunction) if getattr(m, '__isabstractmethod__', False)) == 1"`
      succeeds.
    - `rg -n "from (sqlalchemy|fastapi|litellm|redis|mem0|celery|httpx)" domain/ports/council_debate.py` returns nothing.
  - **Commit:** `feat(council-pilot): add CouncilDebatePort ABC in domain/ports`

- [ ] **T-08** `[P]` — Create `domain/ports/event_bus.py` (per plan §Data Model).
  - File: `/Users/ryousuke/open-morphic/domain/ports/event_bus.py`
  - Content: verbatim from plan code block — `EventBusPort(ABC)` with one
    abstract method `publish(event: DebateEvent) -> None`. Class docstring
    documents publish-only intent and the next-sprint subscriber boundary.
  - **Done when:**
    - `python -c "from domain.ports.event_bus import EventBusPort; assert hasattr(EventBusPort, 'publish')"` succeeds.
    - `rg -n "from (sqlalchemy|fastapi|litellm|redis|mem0|celery|httpx)" domain/ports/event_bus.py` returns nothing.
  - **Commit:** `feat(council-pilot): add EventBusPort ABC in domain/ports`

- [ ] **T-09** — Re-export both new ports from `domain/ports/__init__.py`.
  - File: `/Users/ryousuke/open-morphic/domain/ports/__init__.py`
  - Edit: insert two import lines (alphabetical: `council_debate` between
    `context_adapter` and `cost_repository`; `event_bus` between
    `engine_cost_recorder` and `execution_record_repository`); add both names
    to `__all__` at the corresponding alphabetical positions.
  - **Done when:** `python -c "from domain.ports import CouncilDebatePort, EventBusPort"` succeeds.
  - **Commit:** `chore(council-pilot): re-export CouncilDebatePort + EventBusPort from domain.ports`

---

## Milestone 4 — RED: use case tests + fakes

- [ ] **T-10** `[P]` — Create `tests/unit/application/_fakes/__init__.py` if missing
  (already exists per TD-187; verify and skip if present).
  - Command: `test -f tests/unit/application/_fakes/__init__.py || touch tests/unit/application/_fakes/__init__.py`
  - **Done when:** `ls tests/unit/application/_fakes/__init__.py` succeeds.
  - **Commit:** none if already present; otherwise none (tracked under T-11/T-12 commits).

- [ ] **T-11** `[P]` — Add `tests/unit/application/_fakes/in_memory_event_bus.py`.
  - File: `/Users/ryousuke/open-morphic/tests/unit/application/_fakes/in_memory_event_bus.py`
  - Content: minimal `FakeEventBus(EventBusPort)` with `self.events: list[DebateEvent] = []`
    and `async def publish(event)` that appends. ~20 LOC. Imports the port
    from `domain.ports.event_bus`.
  - **Done when:** file exists; `python -c "from tests.unit.application._fakes.in_memory_event_bus import FakeEventBus; from domain.ports.event_bus import EventBusPort; b=FakeEventBus(); assert isinstance(b, EventBusPort)"` succeeds.

- [ ] **T-12** `[P]` — Add `tests/unit/application/_fakes/fake_council_debate.py`.
  - File: `/Users/ryousuke/open-morphic/tests/unit/application/_fakes/fake_council_debate.py`
  - Content: `FakeCouncilDebate(CouncilDebatePort)` with constructor knobs
    `decision_to_return`, `arguments_to_return`, `raise_on_call: Exception | None = None`,
    `delay_seconds: float = 0.0`. ~30 LOC. Implements `debate()` to optionally
    `await asyncio.sleep(delay_seconds)`, optionally raise, otherwise return
    the configured tuple.
  - **Done when:** file exists; importable; `isinstance` check against
    `CouncilDebatePort` succeeds.

- [ ] **T-13** — Add `tests/unit/application/test_run_council_debate.py` (per plan §Test Strategy item 4, ≥ 4 tests).
  - File: `/Users/ryousuke/open-morphic/tests/unit/application/test_run_council_debate.py`
  - Content:
    1. `test_happy_path_emits_four_events_in_order` — fake debate returns a real
       Decision + 2 Arguments; assert events == [DebateStarted, ArgumentSubmitted×2, DecisionResolved].
    2. `test_timeout_emits_debate_abandoned` — `delay_seconds=20`, `timeout_seconds=0.1`,
       assert last event is `DebateAbandoned(reason="timeout")` and return is `None`.
    3. `test_exception_emits_debate_abandoned` — `raise_on_call=ValueError("boom")`,
       assert `DebateAbandoned` event and return is `None`.
    4. `test_validation_two_candidates_required` — pass `len(candidates)=1`, assert `ValueError`,
       assert no events emitted.
  - References not-yet-existing `application.use_cases.run_council_debate` —
    RED-by-import-error.
  - Target ≤ 100 LOC.
  - **Done when:** `uv run --extra dev pytest tests/unit/application/test_run_council_debate.py -v`
    fails at collection time with `ModuleNotFoundError: application.use_cases.run_council_debate`.
  - **Commit (covers T-10..T-13):** `test(council-pilot): add fake debate + fake event bus + use case tests (RED)`

---

## Milestone 5 — GREEN: use case

- [ ] **T-14** — Implement `application/use_cases/run_council_debate.py`.
  - File: `/Users/ryousuke/open-morphic/application/use_cases/run_council_debate.py`
  - Content (per plan §Use cases added):
    - `RunCouncilDebateUseCase` constructor `(debate_port, event_bus, timeout_seconds=15.0)`.
    - `async def execute(subtask, candidates) -> Decision | None`:
      - Validate `len(candidates) == 2`, else `ValueError`.
      - Generate `debate_id = str(uuid.uuid4())`.
      - Emit `DebateStarted(debate_id=..., subtask=..., candidates=...)`.
      - `try: decision, args = await asyncio.wait_for(debate_port.debate(...), timeout=...)` else emit `DebateAbandoned` and return `None`.
      - For each `arg` in `args`: emit `ArgumentSubmitted(debate_id=..., argument=arg)`.
      - Emit `DecisionResolved(debate_id=..., decision=decision, arguments=args)`.
      - Return `decision`.
    - Imports allowed: stdlib (`asyncio`, `uuid`, `logging`), domain ports
      (`CouncilDebatePort`, `EventBusPort`), domain entities (`Decision`,
      `Argument`, `SubtaskBrief`, all 4 event variants).
  - Target ≤ 80 LOC.
  - **Done when:**
    - `rg -n "from infrastructure" application/use_cases/run_council_debate.py` returns nothing.
    - `uv run --extra dev pytest tests/unit/application/test_run_council_debate.py -v` passes (4/4).
  - **Commit:** `feat(council-pilot): add RunCouncilDebateUseCase`

---

## Milestone 6 — RED: route-to-engine council branch tests

- [ ] **T-15** — Add `tests/unit/application/test_route_to_engine_council.py` (per plan §Test Strategy item 5, ≥ 3 tests).
  - File: `/Users/ryousuke/open-morphic/tests/unit/application/test_route_to_engine_council.py`
  - Content:
    1. `test_council_disabled_chain_unchanged` — `council_enabled=False`, `run_council_debate=None`,
       assert `_build_chain` returns the same value as today's deterministic path
       for a representative `(task_type, budget, ...)` tuple.
    2. `test_council_enabled_decision_promotes_engine_to_head` — `council_enabled=True`,
       `run_council_debate.execute` returns `Decision(agent_engine=GEMINI_CLI)`;
       assert returned chain[0] == GEMINI_CLI, original chain elements deduped after, OLLAMA last.
    3. `test_council_enabled_abandoned_chain_unchanged` — `council_enabled=True`,
       fake debate returns `None`; assert chain equals deterministic path.
  - This RED gate fails because `RouteToEngineUseCase` does not yet accept
    the new constructor kwargs.
  - **Done when:** `uv run --extra dev pytest tests/unit/application/test_route_to_engine_council.py -v`
    fails (constructor signature mismatch).
  - **Commit:** `test(council-pilot): add RouteToEngineUseCase council branch tests (RED)`

---

## Milestone 7 — GREEN: wire council into route-to-engine

- [ ] **T-16** — Extend `application/use_cases/route_to_engine.py`.
  - File: `/Users/ryousuke/open-morphic/application/use_cases/route_to_engine.py`
  - Edits (per plan §Use cases changed):
    1. Constructor: add `run_council_debate: RunCouncilDebateUseCase | None = None`,
       `council_enabled: bool = False`. Store on `self`.
    2. Add `from application.use_cases.run_council_debate import RunCouncilDebateUseCase`
       (allowed: application → application).
    3. `_build_chain`: after the affinity-aware branch, add:
       ```
       if (
           self._council_enabled
           and self._run_council_debate is not None
           and preferred_engine is None
           and len(base_chain) >= 2
       ):
           top_two = [e for e in base_chain if e != AgentEngineType.OLLAMA][:2]
           if len(top_two) == 2:
               brief = SubtaskBrief(id=task_id or "anonymous", description=task, task_type=task_type)
               decision = await self._run_council_debate.execute(brief, top_two)
               if decision is not None:
                   new_chain = [decision.agent_engine]
                   for engine in base_chain:
                       if engine not in new_chain:
                           new_chain.append(engine)
                   if AgentEngineType.OLLAMA in new_chain:
                       new_chain.remove(AgentEngineType.OLLAMA)
                   new_chain.append(AgentEngineType.OLLAMA)
                   await self._record_council_decision(task_id, decision)
                   return new_chain
       return base_chain
       ```
       Refactor minimally: extract the existing `_build_chain` body into a
       helper that returns the deterministic `base_chain`, and wrap it with the
       council branch above.
    4. Add `async def _record_council_decision(self, task_id, decision)`:
       fire-and-forget append to `self._task_state_repo.add_decision(task_id, decision)`
       when both are non-None (FR-10). Mirror the existing `_record_action` shape.
    5. **Signature change risk:** the `_build_chain` helper signature gains a
       `task` and `task_id` parameter (currently only takes routing inputs).
       Verify all in-tree callers (only `execute()` itself) pass the new args.
  - Constraints: zero new `from infrastructure` imports; `task` parameter is
    the existing positional `task: str` already at the top of `execute()`.
  - **Done when:**
    - `rg -n "from infrastructure" application/use_cases/route_to_engine.py` returns nothing.
    - `uv run --extra dev pytest tests/unit/application/test_route_to_engine_council.py -v` passes (3/3).
    - `uv run --extra dev pytest tests/unit/application/test_route_to_engine.py -v` passes byte-identically vs. baseline (NFR-7).
  - **Commit:** `feat(council-pilot): wire council into RouteToEngineUseCase._build_chain behind flag`

---

## Milestone 8 — Infrastructure adapters

> Adapters are independent of each other. T-17 and T-18 may run in parallel.

- [ ] **T-17** `[P]` — Create `infrastructure/events/in_memory_event_bus.py`.
  - File: `/Users/ryousuke/open-morphic/infrastructure/events/in_memory_event_bus.py`
  - Content: ~25 LOC. `InMemoryEventBus(EventBusPort)`:
    - `__init__(self) -> None: self._events: list[DebateEvent] = []`
    - `async def publish(self, event: DebateEvent) -> None: self._events.append(event)`
    - `@property def events(self) -> list[DebateEvent]: return list(self._events)` (defensive copy).
  - Also create empty `infrastructure/events/__init__.py`.
  - **Done when:** `python -c "from infrastructure.events.in_memory_event_bus import InMemoryEventBus; b=InMemoryEventBus(); assert b.events == []"` succeeds.
  - **Commit:** `feat(council-pilot): add InMemoryEventBus adapter (publish-only recorder)`

- [ ] **T-18** `[P]` — Create `infrastructure/council/two_engine_debate.py`.
  - File: `/Users/ryousuke/open-morphic/infrastructure/council/two_engine_debate.py`
  - Also create empty `infrastructure/council/__init__.py`.
  - Content (per plan §Infrastructure impls): `TwoEngineDebate(CouncilDebatePort)`.
    - Constructor: `(llm_gateway: LLMGateway, resolver_model: str = "gemini/gemini-2.5-flash", per_call_timeout_seconds: float = 8.0)`.
    - `async def debate(subtask, candidates) -> tuple[Decision, list[Argument]]`:
      1. Validate `len(candidates) == 2`, else `ValueError`.
      2. For each candidate (in order), call `_generate_argument(engine, subtask)` →
         constructs messages with stable system prefix (KV-cache safe per NFR-8)
         + per-debate user message naming the engine and the subtask. Parses
         JSON response into `Argument`. On parse fail → `ValueError("malformed_argument")`.
      3. Call `_resolve(arguments, subtask)` → resolver LLM call with both arguments
         (engine names randomized in the user-facing prompt section to mitigate
         judge bias per plan §Risks). Parses JSON into a `Decision` with `agent_engine`
         constrained to one of the two candidates. On parse fail or out-of-range
         engine → `ValueError("resolver_error")`.
      4. Return `(decision, arguments)`.
  - Stable system prompts for argument and resolver are module-level string
    constants; per-debate values go in user messages (NFR-8 compliance).
  - Target ≤ 200 LOC.
  - **Done when:** file exists; importable; `isinstance(TwoEngineDebate(...), CouncilDebatePort)` succeeds.
  - **Commit:** `feat(council-pilot): add TwoEngineDebate adapter (LiteLLM-backed, LLM-judge resolver)`

---

## Milestone 9 — DI wiring + feature flag

- [ ] **T-19** — Add settings fields and wire DI in container.
  - Files:
    - `/Users/ryousuke/open-morphic/shared/config/__init__.py` (or whichever file
      defines `Settings` — verify location at edit time per plan §Risks row 6):
      add `council_debate_enabled: bool = False` (env: `MORPHIC_COUNCIL_DEBATE`)
      and `council_resolver_model: str = "gemini/gemini-2.5-flash"`
      (env: `MORPHIC_COUNCIL_RESOLVER_MODEL`).
    - `/Users/ryousuke/open-morphic/interface/api/container.py`:
      construct `event_bus = InMemoryEventBus()`, `debate_port = TwoEngineDebate(llm_gateway=..., resolver_model=settings.council_resolver_model)`,
      `run_council_debate = RunCouncilDebateUseCase(debate_port=..., event_bus=...)`.
      Pass `run_council_debate=run_council_debate` and
      `council_enabled=settings.council_debate_enabled` into the existing
      `RouteToEngineUseCase(...)` call site.
  - **Done when:**
    - `MORPHIC_COUNCIL_DEBATE=true uv run --extra dev pytest tests/unit/interface/test_container.py -v` (or equivalent existing container test) passes.
    - `MORPHIC_COUNCIL_DEBATE=false` (default) leaves all existing container tests passing.
  - **Commit:** `feat(council-pilot): wire council into container with default-off flag`

---

## Milestone 10 — Live integration test

- [ ] **T-20** — Add `tests/integration/test_council_pilot_live.py`.
  - File: `/Users/ryousuke/open-morphic/tests/integration/test_council_pilot_live.py`
  - Content (per plan §Test Strategy item 6):
    - `pytest.mark.live` marker; `pytest.mark.asyncio` if needed.
    - Skip if `GEMINI_API_KEY` not set or Ollama not running.
    - Wires real `LiteLLMGateway` + real `TwoEngineDebate` + real
      `InMemoryEventBus` + real `RunCouncilDebateUseCase`.
    - Subtask: `"Summarize a 2-paragraph plan to bake bread."`
    - Candidates: `[AgentEngineType.OLLAMA, AgentEngineType.GEMINI_CLI]`.
    - Asserts:
      - returned `Decision` is non-None
      - `Decision.agent_engine in {OLLAMA, GEMINI_CLI}`
      - `Decision.rationale` non-empty
      - `Decision.rationale` lower-cased contains both `"ollama"` and `"gemini"` substrings
      - `len(event_bus.events) >= 4` and the first/last kinds are `debate_started`/`decision_resolved`
      - wall-clock < 15s
      - sum of `LLMResponse.cost_usd` from gateway telemetry < $0.02
  - **Done when:**
    - `uv run --extra dev pytest tests/integration/test_council_pilot_live.py -v -m live` passes (1/1).
    - The test prints the live `Decision.rationale` to stdout for manual review
      (vacuous-arguments risk per plan §Risks row 3).
  - **Commit:** `test(council-pilot): live integration with Ollama + Gemini Flash`

---

## Milestone 11 — Verification gates

- [ ] **T-21** `[P]` — Full unit suite green, no regressions.
  - Command: `uv run --extra dev pytest tests/unit/ -v`
  - **Done when:** exit code 0; total passing count ≥ baseline captured in T-03;
    zero new failures.

- [ ] **T-22** `[P]` — Domain purity gate.
  - Command: `rg -l "from (sqlalchemy|fastapi|litellm|redis|mem0|celery|httpx|infrastructure|application|interface)" domain/ports/council_debate.py domain/ports/event_bus.py domain/entities/council.py`
  - **Done when:** no output. Spec NFR-5 evidence.

- [ ] **T-23** `[P]` — Application purity gate.
  - Command: `rg -n "from infrastructure" application/use_cases/run_council_debate.py application/use_cases/route_to_engine.py`
  - **Done when:** no output. Constitution #2 + spec success-metrics row 1.

- [ ] **T-24** `[P]` — `Decision` entity unchanged (FR-4 evidence).
  - Command: `git diff main -- domain/entities/cognitive.py`
  - **Done when:** no output (the existing `Decision` is reused as-is).

- [ ] **T-25** `[P]` — Lint clean for all touched files.
  - Command: `uv run --extra dev ruff check domain/entities/council.py domain/ports/council_debate.py domain/ports/event_bus.py domain/ports/__init__.py application/use_cases/run_council_debate.py application/use_cases/route_to_engine.py infrastructure/council/two_engine_debate.py infrastructure/events/in_memory_event_bus.py interface/api/container.py shared/config/__init__.py tests/unit/domain/test_council_entities.py tests/unit/application/test_run_council_debate.py tests/unit/application/test_route_to_engine_council.py tests/integration/test_council_pilot_live.py tests/unit/application/_fakes/in_memory_event_bus.py tests/unit/application/_fakes/fake_council_debate.py`
  - **Done when:** exit code 0.

- [ ] **T-26** — Constitution-compliance checklist in `spec.md` all `[x]`.
  - File: `/Users/ryousuke/open-morphic/specs/council-pilot/spec.md`
  - Action: re-read the bottom checklist; confirm every box is `[x]`. (Already
    `[x]` at spec time; this is a drift gate.)
  - **Done when:** `grep -c "\\- \\[x\\]" specs/council-pilot/spec.md` returns ≥ 5.

---

## Milestone 12 — Documentation

- [ ] **T-27** — Fill in TD-194 ADR body in `docs/TECH_DECISIONS.md`.
  - File: `/Users/ryousuke/open-morphic/docs/TECH_DECISIONS.md`
  - Edit: replace the stub body inserted at T-04 with:
    - **Decision** — Introduce `CouncilDebatePort` + `EventBusPort` in
      `domain/ports/`; reuse existing `Decision` entity; LLM-judge resolver;
      single wiring point at `RouteToEngineUseCase._build_chain` behind
      `MORPHIC_COUNCIL_DEBATE` flag (default off).
    - **Rationale** — Vision constraint #2 (deliberation, not lookup); UX
      sprint blocked on event vocabulary; LLM-judge avoids re-baking the
      deterministic table into the resolver weights.
    - **Consequences** — Adds 1 domain port pair + 1 use case + 2 infra
      adapters + 1 live test (~$0.02). Flag-off by default → zero behavior
      change in production until follow-up promotion spec.
    - **Promotion criteria for follow-up sprint** — debate-induced p95 latency
      < 8s; decision quality ≥ deterministic baseline on a 50-task held-out set;
      cost per debate < $0.01 averaged over a CI week.
    - **References** — `specs/council-pilot/spec.md`, `specs/council-pilot/plan.md`,
      `project_vision_living_graph.md`, `project_vision_live_debate_ux.md`.
  - **Done when:** `rg -n "Promotion criteria for follow-up sprint" docs/TECH_DECISIONS.md` returns 1 line.
  - **Commit:** `docs(council-pilot): fill TD-194 ADR body`

- [ ] **T-28** — Append CHANGELOG entry under the next unreleased heading.
  - File: `/Users/ryousuke/open-morphic/docs/CHANGELOG.md`
  - Edit (additive only, constitution #9): add a bullet:
    `- **[FEAT]** Council Pilot — 2-engine debate (\`CouncilDebatePort\` + \`EventBusPort\`) wired into \`RouteToEngineUseCase\` behind \`MORPHIC_COUNCIL_DEBATE\` flag (default off). See \`specs/council-pilot/\` and TD-194.`
  - **Done when:** the bullet is present; `git diff docs/CHANGELOG.md` shows
    only an addition.
  - **Commit:** `docs(council-pilot): note council pilot in CHANGELOG`

---

## Milestone 13 — Memory + ship

- [ ] **T-29** — Update `MEMORY.md` with Round 21 live verification.
  - File: `/Users/ryousuke/.claude/projects/-Users-ryousuke-open-morphic/memory/MEMORY.md`
  - Edit: append under "Live Verification Summary":
    `- **Round 21** (2026-05-12+): Council Pilot live — 2-engine debate (Ollama + Gemini Flash) over a trivial subtask; Decision rationale cited both engines; cost ≤ $0.02; wall-clock ≤ 15s. Pinned as \`tests/integration/test_council_pilot_live.py\`.`
  - Also update "Project State" line to mention TD-194.
  - **Done when:** both lines present in MEMORY.md.
  - **Commit:** none (memory file is outside the repo).

- [ ] **T-30** — Self-review via `/morphic-pr-reviewer` subagent.
  - Action: invoke `/morphic-pr-reviewer` against the diff. Confirm zero
    Clean-Architecture violations and zero layer-import regressions.
  - **Done when:** the reviewer's summary contains no `[VIOLATION]` entries.

- [ ] **T-31** — Push branch and open PR.
  - Commands:
    `git push -u origin feature/council-pilot`
    then open a PR titled
    `feat(council-pilot): introduce 2-engine debate behind MORPHIC_COUNCIL_DEBATE flag`
    with a body that links `specs/council-pilot/spec.md` and `specs/council-pilot/plan.md`.
  - **Done when:** PR URL is captured and the PR body contains both spec/plan links.

- [ ] **T-32** — Post-merge: delete feature branch.
  - Commands: `git switch main && git pull && git branch -d feature/council-pilot`
  - **Done when:** `git branch --list feature/council-pilot` is empty.

---

## Parallel execution groups

```
# Group A — Setup (sequential, blocks everything)
T-01 → T-02 → T-03 → T-04

# Group B — Domain entity RED→GREEN
T-05 → T-06

# Group C — Domain ports (parallel; both depend on T-06 for entity import)
T-07 [P], T-08 [P] → T-09

# Group D — Use case RED scaffolding (after T-06..T-09)
T-10 [P], T-11 [P], T-12 [P] → T-13

# Group E — Use case GREEN
T-14

# Group F — Route-to-engine wiring (after T-14)
T-15 → T-16

# Group G — Infra adapters (parallel; depend on T-07/T-08 for port import,
#                                       independent of each other)
T-17 [P], T-18 [P]

# Group H — DI wiring (after T-16, T-17, T-18)
T-19

# Group I — Live integration test (after T-19)
T-20

# Group J — Verification gates (after every GREEN: T-16, T-19, T-20)
T-21 [P], T-22 [P], T-23 [P], T-24 [P], T-25 [P], T-26

# Group K — Documentation (after T-26 confirms compliance)
T-27 [P], T-28 [P]

# Group L — Memory + ship
T-29 → T-30 → T-31 → T-32
```

### Wall-clock estimate (serial execution)

| Milestone | Tasks | Est. minutes |
|---|---|---|
| 0. Setup + ADR stub | T-01..T-04 | 15 |
| 1. RED entities | T-05 | 20 |
| 2. GREEN entities | T-06 | 30 |
| 3. Domain ports | T-07..T-09 | 25 |
| 4. RED use case + fakes | T-10..T-13 | 45 |
| 5. GREEN use case | T-14 | 30 |
| 6. RED route-to-engine | T-15 | 25 |
| 7. GREEN route-to-engine | T-16 | 45 |
| 8. Infra adapters | T-17..T-18 | 90 |
| 9. DI wiring | T-19 | 30 |
| 10. Live integration | T-20 | 60 |
| 11. Verification | T-21..T-26 | 20 |
| 12. Docs | T-27..T-28 | 20 |
| 13. Memory + ship | T-29..T-32 | 30 |
| **Total (serial)** | **32 tasks** | **≈ 485 min (≈ 8 h)** |

With Group C, D, G, J, K parallelism, realistic wall-clock ≈ 6 hours (1 working day with the live test deferred to a second short session for Gemini API verification).
