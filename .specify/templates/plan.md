# Implementation Plan — {{feature_name}}

> **Spec:** [`spec.md`](spec.md)
> **Status:** draft | approved | in-progress | done
> **Estimated effort:** {{days}} days

## Architecture Decisions

### Ports added / changed
- `domain/ports/{{port_name}}.py` — ABC for ...

### Entities added / changed
- `domain/entities/{{entity}}.py` — ...

### Infrastructure impls
- `infrastructure/{{subsystem}}/{{impl}}.py` — implements {{port}}

### Use cases added
- `application/use_cases/{{use_case}}.py` — orchestrates ...

### Interface layer
- `interface/api/routes/{{route}}.py` — HTTP endpoint
- `interface/cli/commands/{{cmd}}.py` — CLI command

## Data Model

```python
# Pseudocode for new / changed entities
class {{Entity}}(BaseModel):
    ...
```

## Contracts

### API
```yaml
# OpenAPI snippet
paths:
  /{{resource}}:
    post: ...
```

### CLI
```
morphic {{cmd}} [--flag]
```

## LLM / Engine Routing

- Default engine: ...
- Fallback chain: Ollama → {{cheap}} → {{expensive}}
- Estimated cost per invocation: $...

## LAEE touchpoints (if any)

- New tools: ...
- Risk levels: ...
- Approval mode behavior: ...

## Test Strategy

### Unit tests (DB-free)
- `tests/unit/domain/test_{{entity}}.py`
- `tests/unit/application/test_{{use_case}}.py`

### Integration tests (Docker Compose required)
- `tests/integration/test_{{flow}}.py`

### E2E tests
- ... (if user-facing)

## Migration Plan

- Alembic migration: `migrations/versions/{{timestamp}}_{{name}}.py`
- Backfill / data migration: ...

## Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| ... | high / med / low | ... |

## Rollout

- Feature flag: `MORPHIC_{{FLAG}}=true`
- Gradual rollout: local → staging → prod

---

*Next: generate `tasks.md` via `/prp-implement`.*
