# Tasks — Strategy Persistence Port

> **Spec:** [`spec.md`](spec.md)
> **Plan:** [`plan.md`](plan.md)
> **Slug:** `strategy-store-port`
> **`[P]` = parallelizable** — the marked task touches a disjoint file set
> from every other unfinished task in the list and shares no in-flight state.
> **TDD:** every production-code task is preceded by a failing test task.
> **Commit cadence:** one task → one commit → one push (per project preference
> "1 fix → commit & push → report. No batching."). Verification-only tasks
> (pytest / ruff / rg) do not produce commits.

---

## Milestone 0 — Setup

- [ ] **T-01** — Create feature branch `feature/strategy-store-port` off `main`.
  - Command: `git switch -c feature/strategy-store-port`
  - **Done when:** `git rev-parse --abbrev-ref HEAD` prints `feature/strategy-store-port`.
  - **Commit:** none (branch creation only).

- [ ] **T-02** — Capture pre-refactor green baseline (RED-protection).
  - Command: `uv run --extra dev pytest tests/unit/application/test_update_strategy.py tests/unit/infrastructure/test_strategy_store.py tests/integration/test_evolution_pipeline.py -v`
  - **Done when:** the three suites all pass on `main` HEAD; record the test
    counts in the task tracker for later comparison (used as regression net
    by every later GREEN gate).
  - **Commit:** none.

---

## Milestone 1 — RED: in-memory fake + contract test

> Per plan §Rollout commit 1: `test(strategy-store-port): add InMemoryStrategyRepository fake + contract test (RED)`.
> These tests reference a not-yet-existing `domain.ports.strategy_repository`
> module, so they MUST fail to import. That is the RED gate.

- [ ] **T-03** `[P]` — Create `tests/unit/application/_fakes/__init__.py` (empty package marker).
  - File: `/Users/ryousuke/open-morphic/tests/unit/application/_fakes/__init__.py`
  - Content: empty file (the leading underscore prevents pytest auto-collection
    of contained modules; per plan §Test Strategy item 1).
  - **Done when:** file exists and `ls tests/unit/application/_fakes/` lists it.

- [ ] **T-04** `[P]` — Add `InMemoryStrategyRepository` test double.
  - File: `/Users/ryousuke/open-morphic/tests/unit/application/_fakes/in_memory_strategy_repository.py`
  - Content (per plan §Test Strategy item 1): a class
    `InMemoryStrategyRepository(StrategyRepository)` that holds three
    `list[...]` instance attributes for recovery rules, model preferences,
    engine preferences, and implements all 7 abstract methods with trivial
    list-copy semantics. Imports `StrategyRepository` from
    `domain.ports.strategy_repository` (which does not exist yet — this is the
    RED-by-import-error step).
  - Target ≤ 30 LOC.
  - **Done when:** file exists; `python -c "import tests.unit.application._fakes.in_memory_strategy_repository"`
    raises `ModuleNotFoundError: domain.ports.strategy_repository` (RED proof).

- [ ] **T-05** — Add the parametrised contract test.
  - File: `/Users/ryousuke/open-morphic/tests/unit/domain/test_strategy_repository_contract.py`
  - Content (per plan §Test Strategy item 3): `pytest.mark.parametrize` over two
    factories — one returning `InMemoryStrategyRepository()`, the other returning
    `StrategyStore(base_dir=tmp_path / "evolution")`. Each test asserts the
    same observable contract: round-trip of `RecoveryRule`, `ModelPreference`,
    `EnginePreference`; `append_recovery_rule` followed by `load_recovery_rules`
    returns the appended rule; `save_*` followed by `load_*` is order-preserving
    within a single writer; idempotent save (saving twice yields the second list).
  - Target ≤ 80 LOC.
  - **Done when:** file exists; running
    `uv run --extra dev pytest tests/unit/domain/test_strategy_repository_contract.py -v`
    fails at collection time with `ImportError: cannot import name 'StrategyRepository'`
    (RED proof for the port itself).
  - **Commit (covers T-03..T-05):** `test(strategy-store-port): add InMemoryStrategyRepository fake + contract test (RED)`

---

## Milestone 2 — GREEN: domain port

> Per plan §Rollout commit 2: `feat(strategy-store-port): add StrategyRepository ABC in domain/ports`.

- [ ] **T-06** — Create the `StrategyRepository` ABC.
  - File: `/Users/ryousuke/open-morphic/domain/ports/strategy_repository.py`
  - Content (verbatim from plan §Data Model code block): module docstring,
    `from __future__ import annotations`, `abc.ABC` + `abc.abstractmethod`,
    import `EnginePreference, ModelPreference, RecoveryRule` from
    `domain.entities.strategy`. Exactly **7 abstract methods**, sync return
    types, declared in this order: `load_recovery_rules`, `save_recovery_rules`,
    `append_recovery_rule`, `load_model_preferences`, `save_model_preferences`,
    `load_engine_preferences`, `save_engine_preferences`. Class docstring must
    document single-writer assumption, unspecified load order, and partial-read
    tolerance (per spec Resolved Questions).
  - **Done when:**
    - `rg -n "from (sqlalchemy|fastapi|litellm|redis|mem0|celery)" domain/ports/strategy_repository.py`
      returns nothing (constitution #2 gate).
    - `python -c "from domain.ports.strategy_repository import StrategyRepository; import inspect; assert sum(1 for _, m in inspect.getmembers(StrategyRepository, predicate=inspect.isfunction) if getattr(m, '__isabstractmethod__', False)) == 7"`
      succeeds.
  - **Commit:** `feat(strategy-store-port): add StrategyRepository ABC in domain/ports`

- [ ] **T-07** — Verify the contract test now collects but in-memory fake half passes while the concrete half also passes (port exists, fake imports cleanly, both impls satisfy the contract because `StrategyStore`'s methods already match by name and signature even before we add the inheritance line — this is the design invariant called out in plan §Architecture Decisions).
  - Command: `uv run --extra dev pytest tests/unit/domain/test_strategy_repository_contract.py -v`
  - **Done when:** all parametrised cases pass.
  - **Commit:** none (verification only).

---

## Milestone 3 — GREEN: infrastructure inheritance

> Per plan §Rollout commit 3: `refactor(strategy-store-port): make StrategyStore inherit StrategyRepository`.

- [ ] **T-08** — Make `StrategyStore` inherit from `StrategyRepository`.
  - File: `/Users/ryousuke/open-morphic/infrastructure/evolution/strategy_store.py`
  - Edits (per plan §Infrastructure impls):
    1. Add `from domain.ports.strategy_repository import StrategyRepository` to
       the import block (alphabetically after `from domain.entities.strategy`).
    2. Change line 18 from `class StrategyStore:` to
       `class StrategyStore(StrategyRepository):`.
    3. No body changes; no method changes; no docstring rewrite.
  - **Done when:**
    - `rg -n "class StrategyStore\(StrategyRepository\):" infrastructure/evolution/strategy_store.py`
      returns 1 line.
    - `python -c "from infrastructure.evolution.strategy_store import StrategyStore; from domain.ports.strategy_repository import StrategyRepository; assert issubclass(StrategyStore, StrategyRepository)"`
      succeeds.
  - **Commit:** `refactor(strategy-store-port): make StrategyStore inherit StrategyRepository`

- [ ] **T-09** — Add a one-line `isinstance` assertion to existing infra tests
  to lock in the inheritance contract (per plan §Test Strategy item 4
  "an additional one-line assertion to that effect would make the inheritance
  contract testable").
  - File: `/Users/ryousuke/open-morphic/tests/unit/infrastructure/test_strategy_store.py`
  - Edit: append a new test
    `def test_strategy_store_satisfies_repository_port(tmp_path)` that
    constructs `StrategyStore(base_dir=tmp_path)` and asserts
    `isinstance(store, StrategyRepository)`. Add the import for
    `StrategyRepository` at the top of the file.
  - **Done when:** `uv run --extra dev pytest tests/unit/infrastructure/test_strategy_store.py -v` passes,
    and the new test name appears in the output.
  - **Commit:** `test(strategy-store-port): assert StrategyStore satisfies StrategyRepository port`

---

## Milestone 4 — GREEN: application retype

> Per plan §Rollout commit 4: `refactor(strategy-store-port): retype UpdateStrategyUseCase against StrategyRepository`.

- [ ] **T-10** — Retype `UpdateStrategyUseCase` constructor against the ABC.
  - File: `/Users/ryousuke/open-morphic/application/use_cases/update_strategy.py`
  - Edits (per plan §Use cases changed):
    1. Remove line 17: `from infrastructure.evolution.strategy_store import StrategyStore`.
    2. Add `from domain.ports.strategy_repository import StrategyRepository`
       in the domain-imports block (alphabetically after
       `from domain.ports.execution_record_repository import ExecutionRecordRepository`).
    3. Change line 36 from `strategy_store: StrategyStore,` to
       `strategy_store: StrategyRepository,`.
    4. Do **NOT** rename the kwarg, the parameter, or the
       `self._strategy_store` attribute (plan §Use cases changed and
       §Risks both forbid this).
  - **Done when:**
    - `rg -n "from infrastructure" application/use_cases/update_strategy.py`
      returns no output (constitution-#2 success metric, also Spec §Success Metrics row 1).
    - `rg -n "strategy_store: StrategyRepository" application/use_cases/update_strategy.py`
      returns 1 line.
  - **Commit:** `refactor(strategy-store-port): retype UpdateStrategyUseCase against StrategyRepository`

---

## Milestone 5 — GREEN: rewrite use-case unit tests against the fake

> Same logical commit as T-10's intent (the spec's "use case unit-testable
> without filesystem" success metric becomes observable here), but
> separated to honor "1 fix → 1 commit".

- [ ] **T-11** — Rewrite `test_update_strategy.py` to use `InMemoryStrategyRepository`.
  - File: `/Users/ryousuke/open-morphic/tests/unit/application/test_update_strategy.py`
  - Edits (per plan §Test Strategy item 2):
    1. Remove `import tempfile` (line 5) and `from pathlib import Path` (line 6)
       — the latter is no longer used after the rewrite (verify by re-reading
       after edit; if `Path` is still referenced anywhere, leave the import).
    2. Remove `from infrastructure.evolution.strategy_store import StrategyStore`
       (line 14).
    3. Add `from tests.unit.application._fakes.in_memory_strategy_repository
       import InMemoryStrategyRepository`.
    4. In each of the **four** `setup_method` blocks (currently at lines
       ~42, ~96, ~133, ~179 — `TestUpdateModelPreferences`,
       `TestUpdateEnginePreferences`, `TestUpdateRecoveryRules`,
       `TestRunFullUpdate`), replace
       `self.store = StrategyStore(base_dir=Path(tempfile.mkdtemp()))` with
       `self.store = InMemoryStrategyRepository()`.
    5. Existing `self.store.load_model_preferences()` /
       `self.store.load_engine_preferences()` assertions in
       `test_persists_to_store` (×2) continue to compile unchanged because
       the fake exposes the same method names.
  - **Done when:**
    - `rg -n "tempfile|StrategyStore" tests/unit/application/test_update_strategy.py`
      returns no output.
    - `uv run --extra dev pytest tests/unit/application/test_update_strategy.py -v`
      passes (every test in the file).
    - Spec NFR-2 evidence: `rg -n "tmp_path|tempfile|mkdtemp" tests/unit/application/test_update_strategy.py`
      returns no output.
  - **Commit:** `test(strategy-store-port): rewrite UpdateStrategyUseCase tests to use in-memory fake`

---

## Milestone 6 — Re-export from `domain.ports`

> Per plan §Rollout commit 5: `chore(strategy-store-port): re-export StrategyRepository from domain.ports`.

- [ ] **T-12** — Add `StrategyRepository` to `domain/ports/__init__.py`.
  - File: `/Users/ryousuke/open-morphic/domain/ports/__init__.py`
  - Edits (preserving the existing convention — explicit imports block at top,
    alphabetical `__all__` block at bottom):
    1. Insert `from domain.ports.strategy_repository import StrategyRepository`
       in the imports block, alphabetically between
       `from domain.ports.shared_task_state_repository import SharedTaskStateRepository`
       and `from domain.ports.task_repository import TaskRepository`.
    2. Insert `"StrategyRepository",` into the `__all__` list at the
       corresponding alphabetical position (between `"SharedTaskStateRepository",`
       and `"TaskRepository",`).
  - **Done when:**
    - `python -c "from domain.ports import StrategyRepository; print(StrategyRepository.__name__)"`
      prints `StrategyRepository`.
    - `rg -n "StrategyRepository" domain/ports/__init__.py` returns exactly 2 lines.
  - **Commit:** `chore(strategy-store-port): re-export StrategyRepository from domain.ports`

---

## Milestone 7 — Verification gates

> All of these are command-only; no commits are produced unless a regression
> requires a fixup task (in which case the fixup follows its own RED→GREEN cycle).

- [ ] **T-13** — Full unit suite green.
  - Command: `uv run --extra dev pytest tests/unit/ -v`
  - **Done when:** exit code 0; total passing count ≥ baseline captured in T-02
    (3,035 unit tests per `MEMORY.md`); zero failures, zero new warnings.

- [ ] **T-14** `[P]` — Integration suite green for evolution pipeline.
  - Command: `uv run --extra dev pytest tests/integration/test_evolution_pipeline.py -v`
  - **Done when:** exit code 0. Validates plan FR-9 (default DI still uses file
    backend) and FR-10 (JSONL format unchanged) end-to-end.

- [ ] **T-15** `[P]` — Lint clean for all touched files.
  - Command: `uv run --extra dev ruff check domain/ports/strategy_repository.py domain/ports/__init__.py application/use_cases/update_strategy.py infrastructure/evolution/strategy_store.py tests/unit/application/_fakes/in_memory_strategy_repository.py tests/unit/application/test_update_strategy.py tests/unit/domain/test_strategy_repository_contract.py tests/unit/infrastructure/test_strategy_store.py`
  - **Done when:** exit code 0, "All checks passed!" or no findings.

- [ ] **T-16** `[P]` — Constitution-#2 gate: zero infra imports in the use case.
  - Command: `rg -n "from infrastructure" application/use_cases/update_strategy.py`
  - **Done when:** no output. This is Spec §Success Metrics row 1
    (target = 0) and the explicit verification in plan §Test Strategy step 3.

- [ ] **T-17** `[P]` — Domain-purity gate: zero framework imports in the new port.
  - Command: `rg -n "from (sqlalchemy|fastapi|litellm|redis|mem0|celery)" domain/ports/strategy_repository.py`
  - **Done when:** no output (plan §Test Strategy step 4 and constitution
    `clean-architecture.md` verification block).

- [ ] **T-18** `[P]` — Filesystem-free gate for the rewritten use-case test.
  - Command: `rg -n "tmp_path|tempfile|mkdtemp|Path\(" tests/unit/application/test_update_strategy.py`
  - **Done when:** no output. Spec NFR-2 evidence.

- [ ] **T-19** — Constitution Compliance checklist in `spec.md` all checked.
  - File: `/Users/ryousuke/open-morphic/specs/strategy-store-port/spec.md`
  - Action: re-read the bottom checklist; confirm every box is `[x]`. (It
    already is per the frozen spec; this gate exists to catch accidental edits.)
  - **Done when:** `grep -c "\\- \\[x\\]" specs/strategy-store-port/spec.md`
    returns ≥ 5 (the 5 constitution-compliance lines plus the Resolved-Questions ticks).

---

## Milestone 8 — Documentation

- [ ] **T-20** — Add CHANGELOG entry under the existing v0.5.2 → v0.6.0 heading.
  - File: `/Users/ryousuke/open-morphic/docs/CHANGELOG.md`
  - Edit: append (do NOT rewrite past entries — constitution #9 append-only)
    a new bullet under the existing
    `## v0.5.2 → v0.6.0 (2026-04-22) — **Documentation & Agent Skills Rework**`
    heading:
    `- **[REFACTOR]** Introduce \`domain.ports.StrategyRepository\` ABC; \`UpdateStrategyUseCase\` no longer imports from \`infrastructure/\` (Constitution #2 compliance). See \`specs/strategy-store-port/\` and TD-182.`
  - **Done when:** the bullet is present and `git diff docs/CHANGELOG.md` shows
    only an addition (no deletions or reorderings).
  - **Commit:** `docs(strategy-store-port): note StrategyRepository ABC in CHANGELOG`

- [ ] **T-21** — Add ADR entry as **TD-182** in `docs/TECH_DECISIONS.md`.
  - File: `/Users/ryousuke/open-morphic/docs/TECH_DECISIONS.md`
  - Edit: append a new section at end of file:
    ```
    ## TD-182: StrategyRepository Port — Domain Abstraction for Learned Strategies

    **Date**: 2026-04-22
    **Status**: Accepted

    ### Decision

    Introduce `domain/ports/strategy_repository.py` as a sync ABC with 7
    methods mirroring the existing concrete `StrategyStore` surface 1:1.
    `StrategyStore` inherits the new ABC; `UpdateStrategyUseCase` retypes its
    `strategy_store` parameter from the concrete class to the ABC and removes
    the last `from infrastructure...` import in the application layer.

    ### Rationale

    - Constitution #2 (Clean Architecture) violation: application →
      infrastructure dependency in `application/use_cases/update_strategy.py`.
    - Sync ABC chosen to preserve current behavior (existing concrete is sync;
      no async wrappers needed). Async sibling port deferred to a follow-up
      spec when a PG-backed realization is requested.
    - Naming convention follows sibling repository ports
      (`execution_record_repository`, `fractal_learning_repository`).

    ### Consequences

    - Use case is now unit-testable with an in-memory fake (NFR-2).
    - JSONL format and DI wiring unchanged (NFR-6 / FR-9 / FR-10).
    - Future Postgres-backed realization will introduce a separate
      `AsyncStrategyRepository` ABC rather than retrofitting this one.

    ### References

    - `specs/strategy-store-port/spec.md`
    - `specs/strategy-store-port/plan.md`
    ```
  - **Done when:** `rg -n "^## TD-182" docs/TECH_DECISIONS.md` returns 1 line;
    `rg -n "^## TD-183" docs/TECH_DECISIONS.md` returns nothing.
  - **Commit:** `docs(strategy-store-port): add TD-182 StrategyRepository ABC ADR`

---

## Milestone 9 — Ship

- [ ] **T-22** — Self-review via `/morphic-pr-reviewer` subagent.
  - Action: invoke `/morphic-pr-reviewer` against the diff. Confirm the
    reviewer reports zero Clean-Architecture violations and zero layer-import
    regressions.
  - **Done when:** the reviewer's summary contains no `[VIOLATION]` entries.

- [ ] **T-23** — Push branch and open PR.
  - Commands:
    `git push -u origin feature/strategy-store-port`
    then open a PR titled `refactor(strategy-store-port): introduce StrategyRepository ABC`
    with a body that links `specs/strategy-store-port/spec.md` and
    `specs/strategy-store-port/plan.md`.
  - **Done when:** PR URL is captured and the PR body contains both spec/plan links.

- [ ] **T-24** — Post-merge: delete feature branch.
  - Commands: `git switch main && git pull && git branch -d feature/strategy-store-port`
  - **Done when:** `git branch --list feature/strategy-store-port` is empty.

---

## Parallel execution groups

```
# Group A — Setup (sequential, blocks everything)
T-01 → T-02

# Group B — RED scaffolding (after T-02; T-03 and T-04 share the _fakes/ dir
#                              but write disjoint files, so safe to parallel)
T-03 [P], T-04 [P], T-05      # T-05 independent of T-03/T-04 (different dir)

# Group C — Domain port (after Group B; T-06 then T-07 verify)
T-06 → T-07

# Group D — Infra inheritance (after T-06; T-08 then T-09)
T-08 → T-09

# Group E — Application retype (after T-06; serial wrt T-08 only by file path,
#                                actually disjoint files — T-08 edits infra,
#                                T-10 edits application; both depend only on T-06)
# T-08 and T-10 may run in parallel: disjoint files, both depend on T-06.
T-08 [P], T-10 [P]

# Group F — Test rewrite (after T-10 makes the new constructor signature live
#                          AND after T-04 makes the fake importable)
T-11

# Group G — Re-export (after T-06 only; independent of T-08/T-10/T-11)
T-12 [P]                        # may run anytime after T-06

# Group H — Verification (after every GREEN task: T-09, T-11, T-12)
T-13 → (T-14 [P], T-15 [P], T-16 [P], T-17 [P], T-18 [P]) → T-19

# Group I — Documentation (after T-19 confirms compliance)
T-20 [P], T-21 [P]              # disjoint files, no shared state

# Group J — Ship
T-22 → T-23 → T-24
```

### Wall-clock estimate (serial execution)

| Milestone | Tasks | Est. minutes |
|---|---|---|
| 0. Setup | T-01..T-02 | 5 |
| 1. RED scaffolding | T-03..T-05 | 35 |
| 2. Domain port | T-06..T-07 | 20 |
| 3. Infra inheritance | T-08..T-09 | 15 |
| 4. App retype | T-10 | 10 |
| 5. Test rewrite | T-11 | 15 |
| 6. Re-export | T-12 | 5 |
| 7. Verification gates | T-13..T-19 | 15 |
| 8. Docs | T-20..T-21 | 15 |
| 9. Ship | T-22..T-24 | 10 |
| **Total (serial)** | **24 tasks** | **≈ 145 min (≈ 2 h 25 min)** |

With Group E and Group G parallelism, realistic wall-clock ≈ 2 hours.
