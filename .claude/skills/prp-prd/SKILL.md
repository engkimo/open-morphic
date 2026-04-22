---
name: prp-prd
description: Phase 1 of spec-driven development — generate spec.md from a problem statement. Requirements, user stories, acceptance criteria. No implementation details.
when_to_use: When starting a new feature. First step before /prp-plan and /prp-implement.
argument-hint: "<feature-slug> <one-line problem statement>"
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
model: opus
---

# PRP Phase 1 — Product Requirements

You turn a fuzzy problem into a crisp `spec.md`.

## Input

`$ARGUMENTS` = `<slug> <problem statement>`
Example: `auto-compact "Context window fills too fast when running long fractal tasks"`

## Procedure

1. Delegate to `spec-writer` subagent with phase=prd and the args.
2. The subagent:
   - Loads `.specify/templates/spec.md` as the skeleton.
   - Loads `.specify/memory/constitution.md` for principle alignment.
   - Asks 3-5 clarifying questions if the problem is ambiguous (inline in the spec as `[NEEDS CLARIFICATION: ...]`).
   - Writes `specs/<slug>/spec.md`.
3. Return the path and a one-paragraph summary.

## Spec must contain

- **Problem**: what's broken or missing, in user terms.
- **Users & scenarios**: who does what.
- **Functional requirements**: numbered, testable ("FR-01 ...").
- **Non-functional requirements**: perf, safety, cost budget.
- **Acceptance criteria**: binary pass/fail per FR.
- **Out of scope**: explicit non-goals.
- **Open questions**: `[NEEDS CLARIFICATION]` blocks.

## Spec must NOT contain

- Implementation choices (frameworks, file paths, class names).
- Task breakdowns (that's Phase 3).
- Architecture diagrams (that's Phase 2).

## Guardrails

- If the slug conflicts with an existing `specs/<slug>/`, abort and suggest a suffix.
- If the problem statement is <10 words, ask for more detail before generating.
- Every FR must have a matching acceptance criterion.
