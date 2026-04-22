# Feature Specification — Strategy Persistence Port

> **Branch:** `feature/strategy-store-port`
> **Status:** draft
> **Owner:** Ryousuke (ryosuke.ohori@ulusage.com)
> **Created:** 2026-04-22

## Problem Statement

The Level-2 cross-session learning use case (which recalculates model and engine
preferences and extracts new recovery rules from execution history) currently
reaches across the architectural boundary to talk to a concrete file-backed
persistence component. As a result, authors who want to unit-test the learning
logic are forced to touch the real filesystem, and anyone wanting to move
learned strategies off local disk (to a shared database, a cache, or a remote
store) must edit the use case itself. This is exactly the kind of inward-pointing
dependency that the Morphic-Agent Constitution (principle #2, Clean Architecture)
forbids: the application layer is supposed to depend only on abstractions
declared in the domain layer. The violation is small today, but it is a live
example that newer contributors will copy, so it should be fixed before more
Level-2 learning behavior is added on top of it.

## Goals

- Eliminate the application layer's dependency on any concrete persistence
  component for learned strategies (measurable: zero imports from the
  infrastructure layer inside `application/use_cases/update_strategy.py`).
- Make the Level-2 learning use case unit-testable without any filesystem,
  network, or database access (measurable: unit tests run with a fully
  in-memory test double and complete in the same order of magnitude as other
  application-layer unit tests, i.e. under 50 ms per test on average).
- Preserve existing runtime behavior end-to-end (measurable: all current unit
  and integration tests continue to pass, the API contract of the
  `POST /task` path and CLI surface is unchanged, and on-disk JSONL files
  written by earlier versions continue to load correctly).

## Non-Goals

- Introducing a new persistence backend (PostgreSQL, Redis, Qdrant, etc.) for
  learned strategies. That is a follow-up spec that will consume the
  abstraction introduced here.
- Changing the semantics of the learning algorithms themselves (min-sample
  thresholds, how preferences are aggregated, what counts as a recovery
  pattern). This spec is a pure dependency-direction refactor.
- Adding new strategy types beyond the three that exist today
  (`RecoveryRule`, `ModelPreference`, `EnginePreference`).
- Migrating or reformatting existing JSONL files on disk.
- Changing how or when the learning use case is scheduled / triggered.

## User Stories

### As a use-case author, I want to write unit tests for Level-2 learning without touching the filesystem, so that my tests stay fast and deterministic.

**Acceptance Criteria:**
- [ ] Given a unit test for the Level-2 learning use case, when the test
  supplies an in-memory test double for the strategy persistence
  dependency, then the test runs to completion without creating, reading,
  or writing any file on disk.
- [ ] Given the same unit test, when it asserts what was persisted, then
  it can inspect the test double's in-memory state directly (no JSONL
  parsing required in the test).

### As a future integrator, I want to swap the local JSONL storage for a database-backed store, so that learned strategies can be shared across machines without changing the use case.

**Acceptance Criteria:**
- [ ] Given a new persistence implementation (e.g. Postgres-backed) that
  conforms to the same abstraction, when it is wired in through the
  existing dependency-injection container, then no change is required in
  `application/use_cases/update_strategy.py`.
- [ ] Given the Level-2 learning use case, when its constructor is
  inspected, then it declares its dependency only in terms of the domain
  abstraction, not a concrete storage class.

### As a PR reviewer, I want to confirm Constitution compliance at a glance, so that Clean Architecture violations do not get merged.

**Acceptance Criteria:**
- [ ] Given the application layer source tree, when grepped for imports
  from the infrastructure layer, then the Level-2 learning use case does
  not appear.
- [ ] Given the domain layer, when listing its ports, then an abstraction
  covering persistence of learned strategies is present and documented.

### As an operator running an existing installation, I want my previously-learned strategies to keep working after the refactor, so that the agent does not forget what it has learned.

**Acceptance Criteria:**
- [ ] Given a directory of JSONL files produced by the current
  implementation, when the refactored system starts up with the same
  base directory, then all previously-persisted recovery rules, model
  preferences, and engine preferences load with identical content and
  ordering semantics.
- [ ] Given the same directory, when the refactored system writes an
  update, then the resulting on-disk files remain readable by the current
  implementation (no schema break).

## Functional Requirements

- FR-1: The Level-2 learning use case shall obtain access to learned-strategy
  persistence exclusively through an abstraction defined in the domain layer;
  it shall not reference any concrete persistence component.
- FR-2: The abstraction shall expose the ability to **load all
  currently-persisted recovery rules** as a list of domain `RecoveryRule`
  entities.
- FR-3: The abstraction shall expose the ability to **load all
  currently-persisted model preferences** as a list of domain
  `ModelPreference` entities.
- FR-4: The abstraction shall expose the ability to **load all
  currently-persisted engine preferences** as a list of domain
  `EnginePreference` entities.
- FR-5: The abstraction shall expose the ability to **replace the full set
  of persisted model preferences** with a supplied list (overwrite semantics,
  matching today's behavior).
- FR-6: The abstraction shall expose the ability to **replace the full set
  of persisted engine preferences** with a supplied list (overwrite
  semantics, matching today's behavior).
- FR-7: The abstraction shall expose the ability to **replace the full set
  of persisted recovery rules** with a supplied list (overwrite semantics,
  matching today's behavior).
- FR-8: The abstraction shall expose the ability to **append a single
  recovery rule** without rewriting the full set.
- FR-9: The default runtime wiring shall continue to use the existing
  file-backed implementation so that no operator action (migration,
  configuration change) is required for current installations.
- FR-10: The existing on-disk JSONL files produced by prior versions shall
  remain the source of truth for the default implementation; no format
  change, no rename, no relocation.
- FR-11: The Level-2 learning use case shall be unit-testable by injecting
  a test double that conforms to the abstraction and holds its state in
  memory only.
- FR-12: Behavior observable through the existing public surfaces (CLI
  commands, API endpoints, and the `StrategyUpdate` result object returned
  by the use case) shall be identical before and after the refactor for
  identical inputs.

## Non-Functional Requirements

- NFR-1 (Performance): The refactor shall not introduce a measurable
  latency regression for load, save, or append operations against the
  existing file-backed store. Target: within ±10% of current read/write
  latency on an unchanged corpus.
- NFR-2 (Testability): At least one unit test per public method of the
  abstraction shall exercise the use case with a purely in-memory test
  double, and shall not require `tmp_path` or any filesystem access.
- NFR-3 (Security / Safety): LAEE risk classification = **LOW**. The
  change touches persistence code but does not add new filesystem paths,
  does not read or write credential directories (`~/.ssh`, `~/.aws`,
  `.env*`), does not perform destructive actions on user data, and does
  not change the network surface.
- NFR-4 (Cost): $0. This is a local refactor that issues no LLM calls at
  build, test, or runtime.
- NFR-5 (LOCAL_FIRST): Unaffected. The Level-2 learning use case does not
  issue LLM calls; the Ollama-first routing policy continues to apply
  unchanged to the rest of the system.
- NFR-6 (Backward compatibility): The default runtime composition after
  the refactor shall read and write the same JSONL files, in the same
  location, with the same record shape, as before.
- NFR-7 (Clean Architecture): The domain layer shall continue to import
  only stdlib + Pydantic + typing. The new abstraction shall live in the
  domain layer; its file-backed realization shall live in the
  infrastructure layer.

## Success Metrics

| Metric | Target |
|---|---|
| Infrastructure imports in `application/use_cases/update_strategy.py` | 0 |
| Unit tests for Level-2 learning that touch the filesystem | 0 |
| Existing unit + integration tests still passing after refactor | 100% (3,035 unit + 148 integration) |
| Load / save / append latency against unchanged JSONL corpus | within ±10% of baseline |
| Operator-visible migration steps required to upgrade | 0 |
| LLM cost introduced by this change | $0 |

## Resolved Questions (2026-04-22)

- [x] **Bulk save of recovery rules (FR-7):** RESOLVED — include bulk
  overwrite in the abstraction's contract. Preserving the existing concrete
  surface keeps callers unchanged and avoids a follow-up workflow to add
  it back when a future integrator needs it.
- [x] **Error handling contract:** RESOLVED — treated as an implementation
  detail. The abstraction's documented contract is "returns a list; partial
  data is acceptable when persistence medium reports recoverable I/O
  errors." Specific behaviors (skip vs. raise, log level) are decided by
  each realization.
- [x] **Concurrency contract:** RESOLVED — single-writer assumption is
  preserved. The only caller is the Level-2 learning use case, which runs
  serially. Adding multi-writer guarantees now would be over-engineering.
- [x] **Ordering guarantees on load:** RESOLVED — unspecified in the
  contract. Callers that require a specific order shall sort after
  loading. This preserves implementation freedom for a future
  database-backed realization.
- [x] **Naming of the abstraction:** RESOLVED — follow the repository
  naming convention used by sibling ports (`execution_record_repository`,
  `fractal_learning_repository`). The new port shall be named after that
  pattern. The concrete file-backed class keeps its current name so that
  existing integrators and import sites in `infrastructure/` are not
  disturbed beyond the ABC inheritance line.

## Constitution Compliance

- [x] `domain/` has zero framework deps — the new abstraction will use
  stdlib + Pydantic only, matching every other port in `domain/ports/`.
- [x] KV-cache safe — refactor does not touch system prompts, context
  assembly, or tool definitions; append-only history is preserved.
- [x] LAEE risk classification declared — **LOW** (see NFR-3). No
  credential paths, no destructive operations, no new network surface.
- [x] Unit + integration test strategy defined — unit tests exercise the
  use case with an in-memory test double that conforms to the new
  abstraction (no filesystem); integration tests continue to cover the
  file-backed realization against a real temp directory, preserving
  end-to-end parity with the current behavior.
- [x] Ollama path included (LOCAL_FIRST) — not applicable at the call
  site (no LLM calls in this use case); unaffected elsewhere.

---

*Next: generate `plan.md` via `/prp-plan` once this spec is approved.*
