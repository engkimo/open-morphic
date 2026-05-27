# Feature Specification — Bypass Classifier Router (TD-196 / B)

> **Branch:** `feature/bypass-classifier-router`
> **Status:** draft
> **Owner:** RYo
> **Created:** 2026-05-27

## Problem Statement

`FractalBypassClassifier` (TD-167, TD-192) decides whether a goal can skip
fractal decomposition. It currently lives **only in the infrastructure
layer** as a single `LLMGateway`-backed class with the system prompt
hardcoded inline. The Goal Classifier Router (TD-195) proved that the
same problem shape — "LLM picks one of N branches per user goal" —
benefits from a domain port + adapter split, a shared byte-stable
SYSTEM_PROMPT constant, and an observability event with a privacy hash.
None of those wins have been retrofitted to bypass classification.

Concretely today:

- The bypass classifier has **no port** — `FractalEngine` couples
  directly to a concrete `FractalBypassClassifier` (`infrastructure/
  fractal/fractal_engine.py:67,114`). Tests must monkeypatch.
- The system prompt is **not provably byte-stable** for KV-cache
  (TD-190 audit only covered the planner evaluators). It is currently
  stable, but nothing pins it that way.
- There is **no observability event** — no `BypassClassified` event,
  no `goal_hash`-style privacy primitive, no router metrics.
- There is **no Ollama-backed adapter** — the LOCAL_FIRST principle
  is satisfied only transitively because `LLMGateway` can fall through
  to Ollama; we cannot pin a specific local-only classifier impl.

## Goals

- G-1: Add `domain/ports/bypass_classifier.py` (ABC), and refactor
  `FractalEngine` to depend on the port — not the concrete impl.
- G-2: Mirror TD-195's adapter split — `LLMBypassClassifier` (remote
  Haiku 4.5) and `LocalBypassClassifier` (Ollama qwen3:8b), both
  sharing a single byte-stable SYSTEM_PROMPT constant.
- G-3: Emit a `BypassClassified` event variant on the existing event
  bus, carrying `goal_hash = sha256(goal)[:16]` (privacy preserved),
  classifier latency, and decision (bypass/complexity/output_requirement).
- G-4: Wire a `BypassObservingEventBus` adapter into the observability
  stack so the same Grafana surface (TD-193 cache_hit_rate dashboard)
  can show bypass decisions, latency p95, and classifier cost.

## Non-Goals

- N-1: Do **not** change the bypass DECISION semantics. The TD-167
  intent rules + TD-192 TEXT-gate are correct; this sprint is a
  **structural lift**, not a behavioural change.
- N-2: Do **not** add a router (like `PlannerModelRouter`). Bypass is
  not a model-selection problem — it is a binary gate. No need for
  a router service; the port + adapter is enough.
- N-3: Do **not** ship a 3-way A/B benchmark — this is structural;
  the existing live regression tests (`tests/integration/
  test_round19_regression.py`) are the bar.

## User Stories

### US-1: As an SRE, I want to see bypass decisions on the observability dashboard so that I can detect bypass-rate drift.

**Acceptance Criteria:**
- [ ] Bypass decisions appear in `BypassMetrics` counter, broken down
      by `complexity` and `output_requirement`.
- [ ] An INFO log line is emitted per classification with `goal_hash`
      (not raw goal), `decision`, `complexity`, `latency_ms`.
- [ ] Raw goal NEVER appears in log lines (string-match test).

### US-2: As a developer, I want to swap the bypass classifier without monkey-patching.

**Acceptance Criteria:**
- [ ] `FractalEngine.__init__` accepts a `BypassClassifierPort | None`
      (not a `FractalBypassClassifier`).
- [ ] DI wiring in `interface/api/container.py` picks the adapter via
      the same `MORPHIC_PLANNER_ROUTER` env-style flag — new flag:
      `MORPHIC_BYPASS_CLASSIFIER=remote|local|disabled`.
- [ ] With `disabled`, all goals take the fractal path (no LLM call).

### US-3: As a privacy reviewer, I want raw goals to never reach the event bus.

**Acceptance Criteria:**
- [ ] `BypassClassified` event has a `goal_hash: str` field constrained
      to `^[0-9a-f]{16}$` (frozen Pydantic VO, mirrors TD-195's
      `GoalClassified`).
- [ ] No `goal` / `raw_goal` field exists on the event (round-trip
      test verifies absence).

## Functional Requirements

- **FR-1:** Define `domain/ports/bypass_classifier.py` with one
  abstract method `async def classify(goal: str) -> BypassDecision`.
- **FR-2:** Promote `BypassDecision` from `infrastructure/fractal/
  bypass_classifier.py` into `domain/value_objects/bypass_decision.py`
  (frozen Pydantic VO). Keep the same fields:
  `bypass, complexity, reason, output_requirement`.
- **FR-3:** Move `_CLASSIFY_SYSTEM` and `_REQUIREMENT_VALUE_MAP` into
  `infrastructure/fractal/_bypass_prompts.py` (mirrors TD-195
  `_prompts.py` layout). The SYSTEM_PROMPT constant must be
  byte-identical across all adapters.
- **FR-4:** Implement `LLMBypassClassifier` (Anthropic Haiku 4.5) and
  `LocalBypassClassifier` (Ollama qwen3:8b). Both satisfy
  `BypassClassifierPort`.
- **FR-5:** Add `BypassClassified` variant to the existing
  `DebateEvent` discriminated union — fields: `kind` (literal),
  `goal_hash`, `bypass`, `complexity`, `output_requirement`,
  `classifier_latency_ms`, `classifier_cost_usd`.
- **FR-6:** Add `BypassObservingEventBus` wrapper (mirrors
  `RouterObservingEventBus`) — increments `BypassMetrics` and emits
  an INFO log per classification.
- **FR-7:** Refactor `FractalEngine.__init__` signature so the
  positional `bypass_classifier: FractalBypassClassifier | None`
  param becomes `bypass_classifier: BypassClassifierPort | None`.
- **FR-8:** Update `interface/api/container.py` DI wiring to pick
  the adapter based on `MORPHIC_BYPASS_CLASSIFIER` config (default
  `remote` if `ANTHROPIC_API_KEY` set, else `local` if Ollama up,
  else `disabled`).

## Non-Functional Requirements

- **NFR-1 (Behavioral parity):** All existing bypass-related tests
  must pass with the new port wiring — same SIMPLE/MEDIUM/COMPLEX
  decisions, same TEXT-gate behaviour, same Round 19 regression
  outcome.
- **NFR-2 (KV-cache stability):** `_BYPASS_SYSTEM_PROMPT` must be a
  module-level `str` constant; no f-string interpolation, no env
  injection, no runtime templating. Verified by an AST-walking unit
  test (`tests/unit/infrastructure/fractal/test_prompt_stability.py`).
- **NFR-3 (Cost):** Per-classification cost must stay below the
  TD-195 envelope ($0.0003 / call median for Haiku 4.5; $0 for
  Ollama).
- **NFR-4 (LOCAL_FIRST):** `LocalBypassClassifier` must work end-to-end
  with no API keys set, verified by a live integration test that
  requires only a running Ollama instance.
- **NFR-5 (Privacy):** `BypassClassified` event must never contain the
  raw goal string. Enforced by Pydantic schema (no `goal` field) and
  asserted by round-trip test.
- **NFR-6 (Observability):** `BypassMetrics` exposes:
  `classifications_total{decision,complexity}`,
  `classifier_latency_ms` histogram, `classifier_cost_usd_total`.
- **NFR-7 (Backward compatibility):** With `MORPHIC_BYPASS_CLASSIFIER`
  unset, behaviour must match `main` HEAD byte-for-byte on the
  Round 19 regression suite.

## Success Metrics

| Metric | Target |
|---|---|
| Framework imports in new domain files (`sqlalchemy\|fastapi\|litellm\|...`) | 0 |
| `from infrastructure.fractal` in `application/` or `domain/` | 0 |
| Unit tests added (port, VO, adapters, observer, prompt-stability) | ≥ 15 |
| Live integration test (real Ollama, $0) | ≥ 1 |
| Live integration test (real Anthropic Haiku) | ≥ 1 |
| `MORPHIC_BYPASS_CLASSIFIER=disabled` Round 19 regression | PASS |
| Classifier p95 latency, remote (Haiku 4.5) | < 300ms |
| Classifier p95 latency, local (qwen3:8b) | < 800ms |
| `BypassClassified` event raw-goal leakage | 0 occurrences |

## Open Questions

- [ ] OQ-1: Should `BypassClassified` join `DebateEvent` union, or
      form a new `RoutingEvent` union? (Initial answer: extend
      `DebateEvent` for consistency with TD-195 `GoalClassified`.)
- [ ] OQ-2: Should we co-locate `BypassMetrics` with `RouterMetrics`
      in `infrastructure/metrics/`, or split into
      `infrastructure/metrics/bypass/`? (Initial answer: keep flat.)
- [ ] OQ-3: Default for `MORPHIC_BYPASS_CLASSIFIER` when unset —
      `remote` or `disabled`? (Initial answer: `remote` if API key
      present, else `local`, else `disabled` — auto-detect.)

## Constitution Compliance

- [x] `domain/` has zero framework deps (new port + VO use only
      stdlib + Pydantic)
- [x] KV-cache safe (stable prefix, append-only — NFR-2 pins it)
- [ ] LAEE risk classification declared (N/A — no LAEE actions)
- [x] Unit + integration test strategy defined (see Success Metrics)

---

*Next: generate `plan.md` via `/prp-plan`.*
