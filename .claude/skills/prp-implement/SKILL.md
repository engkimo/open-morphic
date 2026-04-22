---
name: prp-implement
description: Phase 3 of spec-driven development — generate tasks.md from plan.md. Executable [P]-parallelizable tasks, TDD-first, layer-ordered.
when_to_use: After /prp-plan produces plan.md. Produces a task checklist you can execute top-down.
argument-hint: "<feature-slug>"
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
model: opus
---

# PRP Phase 3 — Executable Tasks

You turn `plan.md` into a TDD-ordered `tasks.md` that any agent can execute.

## Input

`$ARGUMENTS` = `<slug>`. Reads `specs/<slug>/plan.md`.

## Procedure

1. Verify `specs/<slug>/plan.md` exists and constitution-check passed.
2. Delegate to `spec-writer` subagent with phase=tasks.
3. The subagent:
   - Loads plan + `.specify/templates/tasks.md`.
   - Breaks each layer into a task sequence:
     - RED: failing test (must come before impl).
     - GREEN: minimum impl.
     - REFACTOR: cleanup.
     - INTEGRATION: wire into DI container.
   - Marks tasks `[P]` when they touch disjoint files and can run in parallel.
   - Groups tasks into milestones (layer-by-layer: domain → application → infra → interface).
   - Writes `specs/<slug>/tasks.md`.

## tasks.md format

```markdown
# Tasks — <slug>

## Milestone 1: Domain
- [ ] T-01 Write failing test `tests/unit/domain/test_foo_entity.py::test_bar`
- [ ] T-02 Implement `domain/entities/foo.py::Foo`
- [ ] T-03 [P] Write failing test `tests/unit/domain/test_foo_service.py`
- [ ] T-04 [P] Implement `domain/services/foo_service.py`

## Milestone 2: Application
- [ ] T-05 Write failing test `tests/unit/application/test_do_foo.py` (mock ports)
- [ ] T-06 Implement `application/use_cases/do_foo.py`

## Milestone 3: Infrastructure
- [ ] T-07 [P] Port ABC `domain/ports/foo_port.py`
- [ ] T-08 [P] Impl `infrastructure/foo/foo_adapter.py`
- [ ] T-09 Integration test `tests/integration/test_foo_adapter.py` (real PG)

## Milestone 4: Interface
- [ ] T-10 Route `interface/api/routes/foo.py`
- [ ] T-11 Wire DI `interface/api/container.py`
- [ ] T-12 API integration test

## Milestone 5: Gates
- [ ] T-13 Update `docs/TECH_DECISIONS.md` with TD-<next>
- [ ] T-14 Update `docs/CHANGELOG.md`
- [ ] T-15 Run full suite + lint
```

## Guardrails

- Every impl task must have a preceding test task (TDD).
- `[P]` only when tasks touch disjoint files. Same-file edits serialize.
- No task may skip the test → impl → lint order.
- Target: each task ≤ 30 minutes of work. Split larger ones.
