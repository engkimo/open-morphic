# Morphic-Agent Coding Rules

> Rules every contributor must follow. Violations are caught by CI.

---

## 1. Clean Architecture — Dependency Rules

### Forbidden

```python
# ❌ domain/ importing from infrastructure
# domain/services/risk_assessor.py
from infrastructure.persistence.models import TaskModel   # FORBIDDEN
from sqlalchemy import Column                              # FORBIDDEN
import litellm                                             # FORBIDDEN

# ❌ application/ importing from infrastructure
# application/use_cases/create_task.py
from infrastructure.persistence.pg_repo import PgTaskRepo  # FORBIDDEN
```

### Correct Patterns

```python
# ✅ domain/ references only itself
from domain.entities.task import TaskEntity
from domain.value_objects import RiskLevel
from domain.ports.task_repository import TaskRepository  # ABC

# ✅ application/ uses domain/ ports
class CreateTaskUseCase:
    def __init__(self, repo: TaskRepository):  # ABC, not concrete
        self._repo = repo

# ✅ infrastructure/ implements domain/ ports
from domain.ports.task_repository import TaskRepository
class PgTaskRepository(TaskRepository):
    async def save(self, task: TaskEntity) -> None: ...
```

---

## 2. Pydantic Strict Mode

### Required on All Domain Entities

```python
from pydantic import BaseModel, ConfigDict, Field

class MyEntity(BaseModel):
    model_config = ConfigDict(strict=True, validate_assignment=True)

    name: str = Field(min_length=1)          # Empty string rejected
    count: int = Field(default=0, ge=0)      # Negative rejected
    score: float = Field(default=0.5, ge=0.0, le=1.0)  # Range constraint
    status: MyStatus                          # Enum required (raw string rejected)
```

### Rules

| Rule | Example |
|---|---|
| `strict=True` required | No type coercion. `"123"` for `int` field raises error |
| `validate_assignment=True` | Validates on attribute assignment too |
| Status fields use `str, Enum` | `status: str = "pending"` → `status: SubTaskStatus = SubTaskStatus.PENDING` |
| Numeric fields have `ge`/`le` | `cost_usd: float = Field(ge=0.0)` |
| Required strings have `min_length=1` | `goal: str = Field(min_length=1)` |
| `dict` is `dict[str, Any]` | Explicit type parameters |

### What strict=True Rejects

```python
# ❌ raw string → Enum field
TaskEntity(goal="test", status="pending")           # ValidationError
# ✅
TaskEntity(goal="test", status=TaskStatus.PENDING)  # OK

# ❌ empty string → min_length=1 field
SubTask(description="")                             # ValidationError
# ✅
SubTask(description="step A")                       # OK

# ❌ negative → ge=0 field
CostRecord(model="test", cost_usd=-1.0)            # ValidationError
# ✅
CostRecord(model="test", cost_usd=0.0)             # OK
```

---

## 3. OSS-First Principle

### Before Writing Custom Code

1. Search PyPI / npm / MCP Registry for existing solutions
2. If an OSS library covers 80%+ of the requirement, use it
3. Custom code belongs in `domain/` or `application/` only
4. Infrastructure layer must be OSS wrappers

### Never Do This

```python
# ❌ Implementing your own HTTP server
class CustomHTTPServer:  # Use FastAPI instead

# ❌ Implementing your own CLI parser
class CustomArgParser:   # Use typer instead

# ❌ Implementing your own ORM
class CustomQueryBuilder:  # Use SQLAlchemy instead

# ❌ Generating a massive single-file tool implementation
# Instead: use Playwright for browser, psutil for processes, etc.
```

---

## 4. TDD (Test-Driven Development)

### Process

```
1. Red:      Write tests first (no implementation yet → FAIL)
2. Green:    Minimum code to pass tests
3. Refactor: Clean up (tests are the safety net)
```

### Test Classification

| Category | Location | DB Required? | Speed |
|---|---|---|---|
| Unit/Domain | `tests/unit/domain/` | No | ~0.03s |
| Unit/Application | `tests/unit/application/` | No (mock) | Fast |
| Integration | `tests/integration/` | Yes (Docker) | Slow |
| E2E | `tests/e2e/` | Yes (Full) | Slowest |

### Test Naming Convention

```python
# File: test_{module_name}.py
# Class: Test{ClassName}
# Method: test_{what_it_does} or test_{condition}_{expected_result}

class TestRiskAssessor:
    def test_fs_read_is_safe(self): ...
    def test_shell_exec_sudo_is_critical(self): ...

class TestStrictTaskValidation:
    def test_rejects_empty_goal(self): ...
    def test_rejects_negative_cost(self): ...
```

### Commands

```bash
# Unit tests only (no DB required)
uv run pytest tests/unit/ -v

# Specific test class
uv run pytest tests/unit/domain/test_entities.py::TestStrictTaskValidation -v

# With coverage
uv run pytest tests/unit/ --cov=domain --cov-report=term-missing
```

---

## 5. Value Objects — Enum Design

### When a New Status is Needed

1. Add Enum to `domain/value_objects/`
2. Add export to `__init__.py`
3. Update entity type
4. Write tests first (TDD)

```python
# domain/value_objects/status.py
class NewStatus(str, Enum):
    STATE_A = "state_a"
    STATE_B = "state_b"
```

### Naming Convention

| Pattern | Example |
|---|---|
| Status: `{Entity}Status` | `TaskStatus`, `SubTaskStatus` |
| Type: `{Entity}Type` | `MemoryType`, `TaskType` |
| Level: `{Concept}Level` | `RiskLevel` |
| Mode: `{Concept}Mode` | `ApprovalMode` |

---

## 6. File Structure Rules

### Domain Entities

```
domain/entities/{entity_name}.py    # 1 file = 1 entity (related sub-models co-located)
```

### Domain Services

```
domain/services/{service_name}.py   # Pure functions only. No I/O.
```

### Ports (ABC)

```
domain/ports/{resource}_repository.py  # CRUD interfaces
domain/ports/{resource}_gateway.py     # External API interfaces
```

### Tests

```
tests/unit/domain/test_{module}.py     # Matches domain/{module}.py
tests/unit/application/test_{usecase}.py
tests/integration/test_{adapter}.py
```

---

## 7. Import Rules

```python
# ✅ Preferred: explicit imports
from domain.entities.task import TaskEntity
from domain.value_objects.status import TaskStatus

# ✅ OK: via package __init__
from domain.value_objects import RiskLevel, ApprovalMode

# ❌ Forbidden: wildcard imports
from domain.entities import *

# ❌ Forbidden: relative imports (prevents confusion in monorepo)
from ..value_objects import RiskLevel
```

---

## 8. Commit Messages

```
feat: add LAEE risk assessment with 5-tier classification
fix: correct credential path detection in RiskAssessor
refactor: extract status enums to value objects
test: add strict validation tests for all domain entities
docs: add architecture and coding rules documentation
```

- English only
- Concise, single line (50 chars recommended)
- Prefix: `feat` / `fix` / `refactor` / `test` / `docs` / `chore`

---

## 9. Code Quality Tools

```bash
# Linter + Formatter
uv run ruff check .          # lint
uv run ruff format .         # format

# Type checker
uv run mypy domain/ application/ infrastructure/ interface/ shared/

# Tests
uv run pytest tests/unit/ -v --cov=domain
```

### pyproject.toml Config

```toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.12"
strict = true
```
