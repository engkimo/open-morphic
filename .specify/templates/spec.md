# Feature Specification — {{feature_name}}

> **Branch:** `feature/{{slug}}`
> **Status:** draft | ready-for-plan | in-progress | done
> **Owner:** {{owner}}
> **Created:** {{date}}

## Problem Statement

*One paragraph: what user problem does this solve, and why now?*

## Goals

- Goal 1 (measurable)
- Goal 2 (measurable)

## Non-Goals

- What this spec explicitly does **not** cover.

## User Stories

### As a {{role}}, I want to {{action}}, so that {{benefit}}.

**Acceptance Criteria:**
- [ ] Given *precondition*, when *action*, then *observable outcome*.
- [ ] Given *precondition*, when *action*, then *observable outcome*.

## Functional Requirements

- FR-1: The system shall ...
- FR-2: The system shall ...

## Non-Functional Requirements

- NFR-1 (Performance): ...
- NFR-2 (Security): ...
- NFR-3 (Cost): Per-task cost must stay under $X.
- NFR-4 (LOCAL_FIRST): Must have Ollama path.

## Success Metrics

| Metric | Target |
|---|---|
| ... | ... |

## Open Questions

- [ ] Question 1
- [ ] Question 2

## Constitution Compliance

- [ ] `domain/` has zero framework deps
- [ ] KV-cache safe (stable prefix, append-only)
- [ ] LAEE risk classification declared (if touching LAEE)
- [ ] Unit + integration test strategy defined

---

*Next: generate `plan.md` via `/prp-plan`.*
