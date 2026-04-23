# Morphic-Agent Constitution

> Non-negotiable principles. Every spec, plan, and task must comply.
> Updated only by explicit amendment PR.

## Core Principles

### 1. Local-First Routing
`LOCAL_FIRST=true` by default. Every new LLM integration must include an Ollama path. Budget exhaustion falls back to Ollama, never to "unavailable".

### 2. Clean Architecture (4-layer)
- `domain/` has zero framework deps (stdlib + Pydantic + pure-math libs only).
  Allowed pure-math libs: `numpy` (vector ops, LSH, cosine similarity). Adding a new one to this list requires a constitution amendment.
- Dependencies flow inward. Infrastructure implements `domain/ports/*` ABCs.
- No `from infrastructure` / `from application` / `from interface` anywhere in `domain/` (TYPE_CHECKING-only included — see TD-183/TD-184).
- Violating this is grounds for rejecting any PR, regardless of feature value.

### 3. KV-Cache is a first-class design concern
- System prompt prefix is stable. No timestamps, session IDs, or user data in the first N bytes.
- Context is append-only. Never edit or reorder past messages.
- Tool definitions are masked, not removed.

### 4. Safety over Capability
- LAEE default mode: `confirm-destructive`. `full-auto` requires explicit user opt-in per session.
- Risk classification is decoupled from approval transport.
- Every action is logged to an append-only audit trail before execution.
- Credentials (`~/.ssh`, `~/.aws`, `.env*`) are CRITICAL read, refused write.

### 5. TDD, Always
- RED → GREEN → REFACTOR. Unit tests precede implementation.
- Unit tests mock ports. Integration tests hit real PG / Redis / Qdrant.
- Never mock the DB in migration-touching tests.

### 6. Spec-Driven Development
- Features with >3 day scope must produce `spec.md` → `plan.md` → `tasks.md` before code.
- Agents consume specs directly. Requirements ambiguity is a spec bug, not an implementation bug.

### 7. Cost Transparency
- Every LLM call is tracked. Total cost visible per task.
- Monthly budget enforced; 95% = circuit breaker kicks in.
- Cache hit rate is a success metric, not a nice-to-have.

### 8. Context Continuity (UCL)
- Cross-engine handoffs preserve decisions, artifacts, and blockers (v0.5 UCL).
- No agent hoards private state when another agent will continue the task.

### 9. Append-Only History
- `docs/CHANGELOG.md` is additive. Never rewrite past entries.
- Audit logs are immutable (`.morphic/audit_log.jsonl`).
- Git history: no force-push to `main`, no destructive resets without explicit user approval.

### 10. Evolve, Don't Patch
- Failures feed `.morphic/evolution/`. Repeated failures indicate prompts / models / tools that need changing, not a single bug fix.
- Never specialize for a specific test case. Fix as a generic framework improvement.

## Amendments

Amendments to this constitution require:
1. An issue describing the change and rationale.
2. A PR updating this file.
3. Explicit approval from the project owner (Ryousuke).
4. An entry in `docs/CHANGELOG.md` under a dedicated "Constitution" heading.
