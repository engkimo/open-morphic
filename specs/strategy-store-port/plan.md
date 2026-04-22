# Implementation Plan — Strategy Persistence Port

> **Spec:** [`spec.md`](spec.md)
> **Status:** draft
> **Estimated effort:** 0.5 day (internal Clean-Architecture refactor; ~5 file touches; no migration; no LLM cost)

## Summary

Introduce a domain-layer abstract base class `StrategyRepository` that mirrors
the public surface of the existing concrete `infrastructure.evolution.strategy_store.StrategyStore`
1:1, retype `UpdateStrategyUseCase` against the new ABC, and remove the
last `from infrastructure...` import in `application/use_cases/update_strategy.py`.
The concrete `StrategyStore` inherits the new ABC unchanged so on-disk JSONL
files, DI wiring, and all existing tests continue to work without modification.
This is a pure dependency-direction refactor: zero behavior change, zero
migration, zero LLM cost.

## Architecture Decisions

### Why a sync ABC (not async)

Sibling ports `ExecutionRecordRepository` and `FractalLearningRepository` are
async because their canonical realizations are PG-backed (network I/O). The
existing `StrategyStore` is **synchronous** (`open()` / blocking JSONL reads)
and its only caller (`UpdateStrategyUseCase`) calls it from inside `async def`
methods without `await`. To preserve FR-12 ("behavior observable through public
surfaces shall be identical") and NFR-1 ("within ±10% latency"), the new ABC
**must declare sync methods**. A future Postgres-backed realization can wrap
its async I/O in `asyncio.run_in_executor` or this ABC can be split via a
follow-up spec; that decision is explicitly out of scope here (Non-Goal: "no
new persistence backend").

### Why keep the concrete class name `StrategyStore`

The Resolved Question on naming says: port follows the `*_repository` convention
(`StrategyRepository` in `domain/ports/strategy_repository.py`), but the
infrastructure class keeps its current name (`StrategyStore`) so that
the 6 existing import sites (1 production, 5 tests) need no rename, and any
external embedder of the concrete class (none today, but a stable public surface
nonetheless) is undisturbed.

### Ports added / changed

- **NEW:** `domain/ports/strategy_repository.py` — `StrategyRepository(ABC)`.
  - Sync methods only (matches existing concrete behavior, see "Why sync" above).
  - Imports allowed: `abc`, `domain.entities.strategy` only. Zero framework deps (constitution #2).
  - 9 abstract methods (3 loads × 3 strategy types + 3 saves × 3 strategy types — wait, the spec says **9 methods**: 3 loads + 3 bulk saves + 1 append. Let me restate precisely):
    - `load_recovery_rules() -> list[RecoveryRule]` (FR-2)
    - `load_model_preferences() -> list[ModelPreference]` (FR-3)
    - `load_engine_preferences() -> list[EnginePreference]` (FR-4)
    - `save_model_preferences(prefs: list[ModelPreference]) -> None` (FR-5)
    - `save_engine_preferences(prefs: list[EnginePreference]) -> None` (FR-6)
    - `save_recovery_rules(rules: list[RecoveryRule]) -> None` (FR-7, Resolved Q1)
    - `append_recovery_rule(rule: RecoveryRule) -> None` (FR-8)
  - That is **7 abstract methods**, not 9. The plan brief in the prompt
    overcounted (3 loads + 3 saves + 3 appends = 9), but the existing
    concrete surface has **3 loads + 3 saves + 1 append = 7**, and the spec's
    FR-2..FR-8 enumerate exactly those 7. Locking in 7.
- **CHANGED:** `domain/ports/__init__.py` — add `StrategyRepository` to the
  re-export list, keeping alphabetical convention with sibling ports.

### Entities added / changed

- None. `domain/entities/strategy.py` (`RecoveryRule`, `ModelPreference`,
  `EnginePreference`) is unchanged.

### Infrastructure impls

- **CHANGED:** `infrastructure/evolution/strategy_store.py`
  - Add `from domain.ports.strategy_repository import StrategyRepository`.
  - Change class declaration from `class StrategyStore:` to
    `class StrategyStore(StrategyRepository):`.
  - All method signatures already match the ABC by construction — no body
    changes, no behavior changes.

### Use cases changed

- **CHANGED:** `application/use_cases/update_strategy.py`
  - Remove `from infrastructure.evolution.strategy_store import StrategyStore`.
  - Add `from domain.ports.strategy_repository import StrategyRepository`.
  - Constructor parameter `strategy_store: StrategyStore` → `strategy_store: StrategyRepository`.
  - Internal attribute name `self._strategy_store` is preserved (no caller-visible
    rename).
  - **The keyword-argument name `strategy_store=` is preserved** so that
    `interface/api/container.py` (line 285) and the 5 test files that pass
    `strategy_store=...` continue to compile without edit.

### Interface layer

- **No change.** `interface/api/container.py` already constructs
  `StrategyStore(...)` and passes it positionally-or-by-kwarg to
  `UpdateStrategyUseCase(strategy_store=...)`. Because the use-case parameter
  type is widened (concrete → ABC) and `StrategyStore` will inherit from the
  ABC, this assignment continues to type-check. **No DI change required.**

## Layer Map (FR → file)

| FR | Method on port | File path (production) | Test path (unit) |
|---|---|---|---|
| FR-1 | (no infra import in app) | `application/use_cases/update_strategy.py` | `tests/unit/application/test_update_strategy.py` |
| FR-2 | `load_recovery_rules` | `domain/ports/strategy_repository.py` | `tests/unit/domain/test_strategy_repository_contract.py` (new) |
| FR-3 | `load_model_preferences` | same | same |
| FR-4 | `load_engine_preferences` | same | same |
| FR-5 | `save_model_preferences` | same | same |
| FR-6 | `save_engine_preferences` | same | same |
| FR-7 | `save_recovery_rules` | same | same |
| FR-8 | `append_recovery_rule` | same | same |
| FR-9 | default DI unchanged | `interface/api/container.py` (no edit) | covered by `tests/unit/interface/test_evolution_api.py` (existing) |
| FR-10 | JSONL format unchanged | `infrastructure/evolution/strategy_store.py` (body untouched) | `tests/unit/infrastructure/test_strategy_store.py` (existing) |
| FR-11 | in-memory test double | `tests/unit/application/_fakes/in_memory_strategy_repository.py` (new) | consumed by `tests/unit/application/test_update_strategy.py` (rewritten to use fake) |
| FR-12 | identical observable behavior | end-to-end via `tests/integration/test_evolution_pipeline.py` (existing, unchanged) | — |

## Data Model

No new entities. Pseudocode for the new port:

```python
# domain/ports/strategy_repository.py
from __future__ import annotations
from abc import ABC, abstractmethod
from domain.entities.strategy import EnginePreference, ModelPreference, RecoveryRule


class StrategyRepository(ABC):
    """Persistence port for learned strategies (recovery rules + preferences).

    Single-writer assumption: the only caller is the Level-2 learning use case,
    which runs serially. Ordering on load is unspecified; callers requiring a
    specific order shall sort after loading. Partial reads are acceptable when
    the persistence medium reports recoverable I/O errors (specific behavior
    is implementation-local).
    """

    @abstractmethod
    def load_recovery_rules(self) -> list[RecoveryRule]: ...

    @abstractmethod
    def save_recovery_rules(self, rules: list[RecoveryRule]) -> None: ...

    @abstractmethod
    def append_recovery_rule(self, rule: RecoveryRule) -> None: ...

    @abstractmethod
    def load_model_preferences(self) -> list[ModelPreference]: ...

    @abstractmethod
    def save_model_preferences(self, prefs: list[ModelPreference]) -> None: ...

    @abstractmethod
    def load_engine_preferences(self) -> list[EnginePreference]: ...

    @abstractmethod
    def save_engine_preferences(self, prefs: list[EnginePreference]) -> None: ...
```

## Contracts

### API

No HTTP API surface changes. The existing `/evolution/*` routes (covered by
`tests/unit/interface/test_evolution_api.py`) remain bit-identical because they
go through `container.update_strategy`, whose external behavior is unchanged.

### CLI

No CLI surface changes. `morphic evolution *` commands continue to work
unchanged.

## LLM / Engine Routing

- **Not applicable.** The Level-2 learning use case issues **zero LLM calls**
  (it processes already-stored execution records mathematically). No engine
  routing decision is made or changed by this refactor.
- LOCAL_FIRST policy is unaffected: no new LLM call sites are introduced.
- Estimated cost per invocation: **$0** (build, test, runtime).

## LAEE Touchpoints

- **None.** Risk classification: **LOW** (NFR-3).
  - No new filesystem paths.
  - No reads or writes to credential directories (`~/.ssh`, `~/.aws`, `.env*`).
  - No destructive actions on user data (the existing JSONL writes are
    overwrite-with-known-content, identical to today).
  - No change to network surface.
  - Approval-mode behavior unchanged.

## Test Strategy

### Unit tests (DB-free, filesystem-free)

1. **`tests/unit/application/_fakes/in_memory_strategy_repository.py`** *(new)*
   - `InMemoryStrategyRepository(StrategyRepository)`: holds three lists in
     instance attributes, implements all 7 abstract methods. ~30 LOC.
   - Lives under `_fakes/` (underscore prefix = private to tests; not
     auto-collected by pytest).
2. **`tests/unit/application/test_update_strategy.py`** *(modified)*
   - Replace `StrategyStore(base_dir=Path(tempfile.mkdtemp()))` with
     `InMemoryStrategyRepository()` in all four `setup_method` blocks (lines
     44, 98, 135, 181 of the current file).
   - Remove `import tempfile` and the
     `from infrastructure.evolution.strategy_store import StrategyStore` import.
   - Assertion lines that read back via `self.store.load_*()` continue to work
     unchanged (the fake exposes the same method names).
   - **Outcome:** zero filesystem I/O in this file. Satisfies NFR-2.
3. **`tests/unit/domain/test_strategy_repository_contract.py`** *(new — optional but recommended)*
   - Parametrised contract test that runs against both
     `InMemoryStrategyRepository` *and* a temp-dir-backed `StrategyStore`,
     verifying both honor the same observable contract (round-trip of each
     entity type, append-then-load equivalence, idempotent save). ~80 LOC.
   - This is the runtime guarantee that the fake and the real impl don't
     drift; it also serves as living documentation of the port's semantics.
4. **`tests/unit/infrastructure/test_strategy_store.py`** *(unchanged)*
   - Existing JSONL-on-disk behavioral tests continue to pass against the
     concrete impl. Only change is that `StrategyStore` now also satisfies
     `isinstance(store, StrategyRepository)`; an additional one-line assertion
     to that effect would make the inheritance contract testable.

### Integration tests (Docker not required)

5. **`tests/integration/test_evolution_pipeline.py`** *(unchanged)*
   - Continues to use `StrategyStore(base_dir=tmp_path / "evolution")`.
   - Validates FR-9 (default wiring still uses file backend) and FR-10 (JSONL
     format unchanged) end-to-end.

### E2E tests

- **None required.** The refactor is fully internal: no API contract change,
  no CLI flag change, no observable runtime change. The existing 17 Live E2E
  rounds remain valid as-is.

### Verification commands

```bash
# 1. RED: run unit + integration before code change → expect existing pass
uv run --extra dev pytest tests/unit/ tests/integration/test_evolution_pipeline.py -v

# 2. GREEN: after the refactor → all should still pass
uv run --extra dev pytest tests/unit/ tests/integration/test_evolution_pipeline.py -v

# 3. Constitution compliance: zero infra imports in the use case
rg -n "from infrastructure" application/use_cases/update_strategy.py
# expected: no output

# 4. Domain layer purity: zero framework imports in the new port
rg -n "from (sqlalchemy|fastapi|litellm|redis|mem0|celery)" domain/ports/strategy_repository.py
# expected: no output

# 5. Lint
uv run --extra dev ruff check domain/ports/strategy_repository.py \
    application/use_cases/update_strategy.py \
    infrastructure/evolution/strategy_store.py
```

## Migration Plan

- **Alembic migration:** none. No DB schema changes.
- **Data migration:** none. JSONL files on disk are read and written by the
  same concrete class with identical code paths (NFR-6, FR-10).
- **Operator action required:** zero. After upgrade, the system reads existing
  `recovery_rules.jsonl`, `model_preferences.jsonl`, `engine_preferences.jsonl`
  unchanged.

## Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Constructor signature change of `UpdateStrategyUseCase` breaks the 6 callers (1 production + 5 test files). | LOW | We **widen** the type annotation only (`StrategyStore` → `StrategyRepository`); we keep the kwarg name `strategy_store=` and the positional order. Because `StrategyStore` will be a subclass of `StrategyRepository`, all existing call sites continue to satisfy the new annotation. Verified by re-running the existing test suite after the rename. |
| Future async backend (PG-backed strategy store) will need an async sibling port. | LOW | Out of scope for this spec (Non-Goal). Captured here so a follow-up spec knows to introduce an `AsyncStrategyRepository` ABC rather than retrofitting this one. |
| In-memory fake drifts from concrete behavior over time. | LOW | The optional `tests/unit/domain/test_strategy_repository_contract.py` parametrised test runs both implementations against the same assertions. Recommended, not gating. |
| Class inheritance line accidentally changes method resolution for a method already overridden in `StrategyStore`. | NEGLIGIBLE | All concrete methods are already concrete in `StrategyStore`; the ABC declares them `@abstractmethod` only, so MRO behavior is unchanged. |
| Cross-spec coupling: someone else opens a PR that adds an 8th method to `StrategyStore` while this PR is in flight. | LOW | Resolution: rebase, add the same method to the ABC, ship together. |

## Rollout

- **Feature flag:** none. Internal refactor with zero observable behavior change
  does not warrant a runtime gate (constitution #6 — spec-driven, not
  flag-driven).
- **Gradual rollout:** N/A. Single PR, single merge to `main`. No staging
  environment toggle.
- **Commit series (English messages, separate per file per project preference):**
  1. `test(strategy-store-port): add InMemoryStrategyRepository fake + contract test (RED)`
  2. `feat(strategy-store-port): add StrategyRepository ABC in domain/ports`
  3. `refactor(strategy-store-port): make StrategyStore inherit StrategyRepository`
  4. `refactor(strategy-store-port): retype UpdateStrategyUseCase against StrategyRepository`
  5. `chore(strategy-store-port): re-export StrategyRepository from domain.ports`
- **Rollback:** trivial — revert the 5 commits; on-disk JSONL files are
  unaffected.

## Constitution Compliance Gate

- [x] **#2 Clean Architecture** — `domain/ports/strategy_repository.py` imports
  only `abc` and `domain.entities.strategy` (zero framework deps).
  `application/use_cases/update_strategy.py` imports only from `domain.ports`
  and `domain.entities` after the refactor (verifiable: `rg "from infrastructure"
  application/use_cases/update_strategy.py` → empty).
  `infrastructure/evolution/strategy_store.py` inherits the ABC.
- [x] **#5 TDD** — RED commit (test + fake) precedes GREEN commits (ABC + impl
  + retype). Existing tests in `tests/unit/infrastructure/test_strategy_store.py`
  continue to provide the GREEN-after-refactor regression net.
- [x] **#9 Append-Only History** — no audit log rewrites; no changelog edits to
  past entries; a single new CHANGELOG entry under the next unreleased heading.
- [x] **#10 Evolve, Don't Patch** — this refactor *is* the evolved response to
  the Constitution-#2 violation flagged in the spec; it is implemented as a
  generic Clean-Architecture pattern (port + impl + DI), not as a workaround
  for a specific test case (per user preference: "Never specialize for specific
  test cases").
- [x] **KV-cache safe** — no system-prompt or tool-definition changes.
- [x] **LAEE risk: LOW** — declared in NFR-3; no new filesystem paths, no
  credential access, no destructive actions, no network surface change.
- [x] **LOCAL_FIRST** — N/A at the call site (no LLM calls in this use case);
  unaffected elsewhere.
- [x] **Cost transparency** — $0 introduced (NFR-4).

---

*Next: generate `tasks.md` via `/prp-implement` after this plan is approved.*
