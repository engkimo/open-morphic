---
name: tdd-morphic
description: TDD workflow for Morphic-Agent's 4-layer Clean Architecture. RED → GREEN → REFACTOR, placing tests and impls in the correct layer directories.
when_to_use: When implementing any new domain entity, use case, port, or infrastructure impl. Invoke before writing production code.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash(uv run pytest *)
  - Bash(ruff check *)
  - Grep
  - Glob
model: sonnet
---

# TDD for Morphic-Agent

You execute the RED → GREEN → REFACTOR loop while respecting Morphic's layer boundaries.

## Layer → Test location map

| Code layer | Test folder |
|---|---|
| `domain/entities/` | `tests/unit/domain/test_entities.py` |
| `domain/services/` | `tests/unit/domain/test_<service>.py` |
| `domain/ports/` | No tests (ABCs only) |
| `application/use_cases/` | `tests/unit/application/test_<use_case>.py` (mock ports) |
| `infrastructure/*/` | `tests/integration/test_<impl>.py` (real PG/Redis/Qdrant) |
| `interface/api/routes/` | `tests/integration/test_api_<route>.py` (TestClient) |
| `interface/cli/commands/` | `tests/integration/test_cli_<cmd>.py` |

## Workflow

### RED
1. Read the spec / plan to understand intent.
2. Write the failing test in the correct folder.
3. Run:
   ```bash
   uv run --extra dev pytest tests/unit/<layer>/test_<name>.py -v
   ```
   Expect: FAIL with specific assertion error.
4. Confirm the test actually exercises the target. No false passes.

### GREEN
1. Write the **minimum** code to pass the test.
2. No premature abstractions. No "future-proofing".
3. Re-run the test. Must pass.
4. Run the full unit suite to catch collateral damage:
   ```bash
   uv run --extra dev pytest tests/unit/ -v
   ```

### REFACTOR
1. Only if tests pass. Otherwise fix first.
2. Remove duplication.
3. Name things correctly.
4. Split long functions.
5. Re-run all unit tests.
6. Lint:
   ```bash
   uv run --extra dev ruff check .
   ```

## Layer-specific rules

- **Domain tests**: zero imports from `infrastructure/` or `application/`. Use plain `pytest`, no `TestClient`, no DB.
- **Application tests**: mock all ports with `unittest.mock.AsyncMock` or a hand-rolled in-memory port. Never real DB.
- **Infrastructure integration tests**: require `docker compose up`. Skip with `pytest.importorskip` for external services.

## Commit cadence

After each GREEN, make a micro-commit:
```
git add <only changed files>
git commit -m "tests(<layer>): add <what>" -m "then" -m "feat(<layer>): implement <what>"
```
(or two separate commits).

## Output

```
# TDD <feature>

## RED
- Test: tests/unit/<...>/test_<...>.py::test_<name>
- Failure: <assertion>

## GREEN
- Impl: <file>:<line>
- Passing: <N>/<N> tests

## REFACTOR
- Changes: <summary>
- Lint: clean
```

## Guardrails

- **Never skip RED.** Writing code first and tests after is not TDD.
- **Never mock in integration tests.** If you find yourself mocking, it's a unit test — move it.
- **Never commit red.** Pre-commit hook should catch this.
