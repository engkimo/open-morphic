# Specs — Spec-Driven Development

> Features larger than 3 days of work go through `spec.md → plan.md → tasks.md`
> before code is written. This is a **constitution requirement** (see `.specify/memory/constitution.md`, Principle 6).

## Structure

```
specs/
├── README.md                   # this file
├── unified-cognitive-layer/
│   ├── spec.md                 # what
│   ├── plan.md                 # how
│   ├── tasks.md                # executable work items
│   ├── research.md             # (optional) technical context
│   ├── data-model.md           # (optional) schema
│   ├── contracts/              # (optional) OpenAPI, protobuf, etc.
│   └── quickstart.md           # (optional) validation scenarios
└── <next-feature>/
    └── ...
```

## Workflow

1. **Phase 1 — Specification** (`spec.md`): user stories, acceptance criteria, success metrics, constitution compliance checklist.
2. **Phase 2 — Planning** (`plan.md`): architecture decisions, ports, entities, contracts, test strategy.
3. **Phase 3 — Tasks** (`tasks.md`): atomic work items, `[P]` = parallelizable.

Generate via skills:
- `/prp-prd` — draft `spec.md` from a problem statement
- `/prp-plan` — generate `plan.md` from an approved `spec.md`
- `/prp-implement` — generate `tasks.md` from `plan.md`

## Templates

Copy from `.specify/templates/` when starting a new feature:

```bash
mkdir specs/<feature-slug>
cp .specify/templates/spec.md  specs/<feature-slug>/
cp .specify/templates/plan.md  specs/<feature-slug>/
cp .specify/templates/tasks.md specs/<feature-slug>/
```

## Constitution Check

Every spec must close the constitution compliance checklist:
- [ ] `domain/` has zero framework deps
- [ ] KV-cache safe (stable prefix, append-only)
- [ ] LAEE risk classification declared (if touching LAEE)
- [ ] Unit + integration test strategy defined
- [ ] Ollama path included (LOCAL_FIRST)

## Retirement

When a feature ships, leave the spec folder in place for historical reference. Do not delete it. Move `status: done` in the header.
