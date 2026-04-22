---
name: prp-plan
description: Phase 2 of spec-driven development — turn spec.md into plan.md. Architecture, data model, contracts, layer placement in Morphic's 4-layer Clean Architecture.
when_to_use: After /prp-prd produces a spec.md. Before /prp-implement.
argument-hint: "<feature-slug>"
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
model: opus
---

# PRP Phase 2 — Implementation Plan

You transform `spec.md` into `plan.md` — *how* to build, not *what* to build.

## Input

`$ARGUMENTS` = `<slug>`. Reads `specs/<slug>/spec.md`.

## Procedure

1. Verify `specs/<slug>/spec.md` exists. If not, abort with "run /prp-prd first".
2. Delegate to `spec-writer` subagent with phase=plan.
3. The subagent:
   - Loads the spec and `.specify/templates/plan.md`.
   - Maps each FR to a Clean Architecture layer:
     - Business rule → `domain/entities/` or `domain/services/`
     - Workflow → `application/use_cases/`
     - External system → `domain/ports/` + `infrastructure/<subsystem>/`
     - HTTP/CLI surface → `interface/api/routes/` or `interface/cli/commands/`
   - Proposes data model (Pydantic entities, SQLAlchemy if persisted).
   - Proposes port interfaces (ABCs) when new external deps are needed.
   - Flags constitution violations as `[CONSTITUTION WARNING]`.
   - Writes `specs/<slug>/plan.md`.
4. Run `constitution-check` skill as a gate — must pass before Phase 3.

## Plan must contain

- **Layer map**: FR-01 → `domain/services/foo.py::Foo.bar()`
- **Data model**: entities + relations, JSON schema for any persistence.
- **Ports & adapters**: new ABCs, new infra impls.
- **Dependencies**: what needs to be installed (trigger `/tool-scout` if non-trivial).
- **Migration**: DB migrations, backfill strategy.
- **Test strategy**: unit / integration / E2E split.
- **Rollout**: feature flag? staged? fullauto-enabled by default?
- **Risks**: LAEE risk level of new actions, cost estimate.

## Guardrails

- No code. Just structure and contracts.
- If a port already exists, reuse it — don't add a parallel one.
- If the feature requires >3 new infra impls, split into sub-features.
- Infrastructure must never appear in the domain layer map.
