---
paths:
  - domain/**
  - application/**
  - infrastructure/**
  - interface/**
---

# Clean Architecture — Dependency Rule

**The dependency direction is strictly inward.** Outer layers depend on inner layers; inner layers never depend on outer.

```
Interface → Application → Domain ← Infrastructure
                           (domain is the innermost)
```

## Hard Rules

1. **`domain/` imports nothing except Python stdlib + Pydantic + typing + pure-math libs.**
   - Allowed pure-math libs: `numpy` (used for LSH/cosine in `domain/services/semantic_fingerprint.py`). Adding a new one requires a constitution amendment.
   - NO SQLAlchemy, FastAPI, LiteLLM, Celery, Redis, mem0, httpx, etc.
   - NO `from infrastructure...` / `from application...` / `from interface...` — including under `TYPE_CHECKING`. Add a port (ABC) in `domain/ports/` and implement it in `infrastructure/` instead.

2. **`application/` imports only from `domain/`.**
   - Use cases orchestrate domain entities + domain services via ports.
   - No direct infrastructure imports.

3. **`infrastructure/` implements `domain/ports/*.py` ABCs.**
   - ORM models live in `infrastructure/persistence/models.py`, separate from domain entities.
   - Do not leak ORM objects into `application/` or `domain/`.

4. **`interface/` does DI wiring** (`interface/api/deps.py`).
   - Binds ports to concrete implementations based on config.
   - FastAPI routes call use cases, never infrastructure directly.

## If you're editing this area

- **Before writing**: ask "what layer am I in?" Check imports match the rule.
- **Before adding a dep**: can this be done via an existing port? Add a new port if not.
- **Before touching `domain/`**: no `import` statements allowed outside stdlib + `domain/*`.
- **Before deleting**: check port implementations are still consistent.

## Verification

```bash
# Detect domain → framework leaks (should return nothing)
rg -l "from (sqlalchemy|fastapi|litellm|redis|mem0|celery|httpx|qdrant_client)" domain/

# Detect domain → outer-layer leaks (should return nothing)
rg -l "from (infrastructure|application|interface)" domain/

# Detect application → infrastructure leaks (should return nothing — TD-184 baseline)
rg -l "from infrastructure" application/

# Verify ports have impls
ls domain/ports/ | xargs -I{} rg -l "class.*Port\b" infrastructure/
```
