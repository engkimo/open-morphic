# Tasks — {{feature_name}}

> **Plan:** [`plan.md`](plan.md)
> **`[P]` = parallelizable** (no deps on prior unfinished tasks in the list)

## Setup

- [ ] T001 — Create feature branch `feature/{{slug}}`
- [ ] T002 — Update `docs/CHANGELOG.md` with feature scope

## Domain layer (write first — TDD RED)

- [ ] T010 `[P]` — Add `domain/entities/{{entity}}.py` + unit tests (expected to fail)
- [ ] T011 `[P]` — Add `domain/ports/{{port}}.py` ABC
- [ ] T012 `[P]` — Add `domain/services/{{service}}.py` + unit tests (expected to fail)

## Application layer

- [ ] T020 — Add `application/use_cases/{{use_case}}.py` + unit tests (mocking ports)
- [ ] T021 `[P]` — Add `application/dto/{{dto}}.py`

## Infrastructure layer (TDD GREEN)

- [ ] T030 — Implement `infrastructure/{{subsystem}}/{{impl}}.py` (makes T011 port real)
- [ ] T031 `[P]` — Add Alembic migration `migrations/versions/{{ts}}_{{name}}.py`
- [ ] T032 — Wire DI in `interface/api/container.py`

## Interface layer

- [ ] T040 `[P]` — Add HTTP route `interface/api/routes/{{route}}.py` + tests
- [ ] T041 `[P]` — Add CLI command `interface/cli/commands/{{cmd}}.py` + tests

## Integration tests (require Docker Compose up)

- [ ] T050 — `tests/integration/test_{{flow}}.py` — end-to-end happy path
- [ ] T051 `[P]` — `tests/integration/test_{{flow}}_errors.py` — failure modes

## Observability / Docs

- [ ] T060 `[P]` — Add metrics / logging
- [ ] T061 `[P]` — Update `docs/{{relevant}}.md`
- [ ] T062 `[P]` — Add ADR entry in `docs/TECH_DECISIONS.md`

## Verification

- [ ] T070 — `uv run --extra dev pytest tests/unit/ -v` passes
- [ ] T071 — `uv run --extra dev pytest tests/integration/ -v` passes
- [ ] T072 — `uv run --extra dev ruff check .` clean
- [ ] T073 — Constitution compliance checklist in `spec.md` all checked

## Ship

- [ ] T080 — Self-review via `/morphic-pr-reviewer` subagent
- [ ] T081 — Create PR with `spec.md` + `plan.md` linked in description
- [ ] T082 — Update `docs/CHANGELOG.md`
- [ ] T083 — Close feature branch after merge

---

## Parallel execution groups

```
T010, T011, T012   # Domain entities/ports/services — can write in parallel
T020, T021         # After T010-T012 done
T030, T031         # After T020 done
T040, T041         # After T030 done
T050, T051         # After all impl done
T060, T061, T062   # Can start once any impl is green
```
