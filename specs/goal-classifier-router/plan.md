# Implementation Plan — Goal Classifier Router (Planner Model Selection)

> **Spec:** [`spec.md`](spec.md)
> **Status:** draft
> **Estimated effort:** 2 days

## Architecture Decisions

### AD-1 — Routing mechanism: pure-LLM classifier (not rule-based pre-filter)

Two mechanisms were considered:

1. **Pure-LLM classifier (CHOSEN).** A small LLM call (Haiku 4.5 remote or
   qwen3:8b local) reads the goal and emits `{"model": "haiku"|"sonnet", "reason": "..."}`.
   The classifier is the single source of truth.

2. **Hybrid: regex pre-filter then LLM on ambiguous.** Detect Japanese/CJK chars,
   quoted spans, file extensions; route confident cases without an LLM call.

**Decision: pure-LLM, no rule-based pre-filter.** This is consistent with the user
preference recorded in `memory/feedback_no_rulebased.md` ("AIっぽくない"). The
trade-off is one extra ~300ms LLM call per planner invocation; the cost ceiling
(NFR-2: ≤ 5% of the planner cost it gates) holds because the eligible Haiku slice
saves ~$0.0065/call and the classifier costs ≤ $0.0005/call. The pre-filter
hybrid is recorded here as a future optimization, gated on observed latency
problems; it is **not** in scope for this spec.

### AD-2 — Confidence gating: route to Haiku only if `confidence ≥ 0.7`

`GoalClassification.confidence` is parsed from the classifier output (the prompt
asks for it explicitly). `PlannerModelRouter` requires `confidence ≥ 0.7` to
route to Haiku; below that, it falls back to Sonnet with `reason` prefixed
`"low_confidence: "`. This resolves spec open question #2 conservatively (the
safe model is the fallback). The threshold lives in `Settings` (default 0.7) for
post-hoc tuning without a release.

### AD-3 — Reason taxonomy (resolves spec open question #3)

Prometheus `reason_category` label values, normalized by `PlannerModelRouter`
before emission:

| Category | Trigger |
|---|---|
| `generic_tech_english` | classifier returned `haiku` with high confidence |
| `non_ascii_entity` | classifier returned `sonnet` and reason mentions non-ASCII / Japanese / CJK |
| `quoted_specific_entity` | classifier returned `sonnet` and reason mentions quotes / specific filename or column |
| `multilingual_or_proper_noun` | classifier returned `sonnet` and reason mentions multilingual / proper noun |
| `low_confidence` | confidence < threshold, fallback to Sonnet |
| `classifier_failed` | classifier raised, timed out, or returned malformed output |

The router maps the free-form `reason` to a category via a small keyword map
that lives **inside the router service** (not the classifier prompt) to avoid
prompt churn breaking label cardinality.

### AD-4 — Eligible-slice definition for NFR-9 (resolves spec open question #1)

The router's own decision on each benchmark goal is the slice definition. The
`benchmarks/planner_quality_ab.py --router` mode shall:

1. Run the router on each of the 10 benchmark goals → record per-goal `chosen_model`.
2. Run planner+judge with the chosen model on each goal (3 trials).
3. Run planner+judge with Sonnet on every goal (3 trials, baseline).
4. Report: (a) router-gated mean across all 10 goals vs Sonnet baseline (NFR-9 axes);
   (b) "captured saving" = `(Sonnet baseline cost - router-gated cost) / (Sonnet baseline cost - Haiku-only cost)`.

### AD-5 — Event union extension vs. sibling union

The existing `domain/value_objects/council_events.py::DebateEvent` is a
discriminated union for council debate. Adding a `GoalClassified` variant there
overloads the union semantically. **Decision: extend the union anyway**, because:

- The `EventBusPort.publish(event: DebateEvent)` signature is already publish-only;
  adding a variant is additive.
- A sibling union would force a second `EventBusPort` or a generic event type, both
  of which expand the port surface for a single new event.
- The renderer sprint that consumes these events benefits from one subscription
  point.

The variant is `kind="goal_classified"` and the discriminator handles it cleanly.
Per FR-4 the variant is renamed to `RoutingEvent` if reviewers reject the overload;
that is a non-blocking refactor.

### Ports added / changed

- `domain/ports/goal_classifier.py` — new ABC `GoalClassifierPort` with
  `async def classify(goal: str) -> GoalClassification`.
- `domain/ports/event_bus.py` — **unchanged contract**; the new `GoalClassified`
  variant is published through the same `publish()` method.

### Entities / value objects added / changed

- `domain/value_objects/planner_model.py` — new `PlannerModel` `StrEnum`
  (`SONNET`, `HAIKU`) + `to_gateway_id() -> str`.
- `domain/value_objects/goal_classification.py` — new `GoalClassification`
  Pydantic VO.
- `domain/value_objects/council_events.py` — **extended** with `GoalClassified`
  variant (no entity bump; additive only).

### Domain services added

- `domain/services/planner_model_router.py` — new `PlannerModelRouter` service
  taking a `GoalClassifierPort` + settings + `EventBusPort` and exposing
  `async def select_for(goal: str) -> tuple[PlannerModel, GoalClassification | None]`.
  Handles confidence gating (AD-2), reason-category normalization (AD-3),
  classifier-failure fallback, and event emission.

### Infrastructure impls

- `infrastructure/routing/llm_goal_classifier.py` — `LLMGoalClassifier(GoalClassifierPort)`,
  remote-LLM adapter on Anthropic Haiku 4.5 via existing `LLMGateway`.
- `infrastructure/routing/local_goal_classifier.py` — `LocalGoalClassifier(GoalClassifierPort)`,
  Ollama qwen3:8b adapter via existing `OllamaManagerPort`.
- `infrastructure/routing/_prompts.py` — shared stable system prompt + parser
  (KV-cache safe; identical text for remote + local adapters).
- `infrastructure/fractal/llm_planner.py` — **modified** to accept an injected
  `PlannerModelRouter`; calls `router.select_for(goal)` before each LLM call and
  passes the resolved gateway model id to `LLMGateway.complete()`. Stable system
  prompt (TD-190) is untouched.

### Application layer

- No new use case. The router is a **domain service** consumed by the existing
  `LLMPlanner` adapter (which already lives in `infrastructure/`). The
  `application/use_cases/` layer is unchanged. This is intentional: the router's
  responsibility is sub-planner concern, not workflow orchestration.

### Interface layer

- `interface/api/container.py` — DI wiring: read `MORPHIC_PLANNER_ROUTER`, build
  the active classifier (Local if `LOCAL_FIRST=true` and budget ≤ 0, else
  Remote), construct the `PlannerModelRouter`, inject into `LLMPlanner`.
- `shared/config/settings.py` — new fields:
  - `planner_router_mode: Literal["disabled", "enabled"] = "disabled"`
  - `planner_router_haiku_confidence_threshold: float = 0.7`
  - `planner_router_classifier_timeout_ms: int = 1500`
- No HTTP route, no CLI command. Observability is via events + metrics + logs.

## Data Model

```python
# domain/value_objects/planner_model.py
class PlannerModel(StrEnum):
    SONNET = "sonnet"
    HAIKU = "haiku"

    def to_gateway_id(self) -> str:
        return {
            PlannerModel.SONNET: "anthropic/claude-sonnet-4-6",
            PlannerModel.HAIKU: "anthropic/claude-haiku-4-5",
        }[self]


# domain/value_objects/goal_classification.py
class GoalClassification(BaseModel):
    chosen_model: PlannerModel
    reason: str = Field(max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)
    classifier_latency_ms: int = Field(ge=0)
    classifier_cost_usd: float = Field(ge=0.0)


# domain/value_objects/council_events.py (additive variant)
class GoalClassified(BaseModel):
    kind: Literal["goal_classified"] = "goal_classified"
    debate_id: UUID  # reused field name; semantically "correlation_id" here
    goal_hash: str  # sha256(goal)[:16]
    chosen_model: str  # "sonnet" | "haiku"
    reason: str
    reason_category: str  # AD-3 taxonomy
    classifier_latency_ms: int
    classifier_cost_usd: float


# Updated discriminated union (additive)
DebateEvent = Annotated[
    DebateStarted | ArgumentSubmitted | DecisionResolved | GoalClassified,
    Field(discriminator="kind"),
]
```

## Contracts

### Classifier prompt contract (stable system message, NFR-5)

```text
SYSTEM (byte-identical across all calls):
You are a 2-class goal router for a planning LLM. Decide which planner model
should handle the user goal. Return ONLY a JSON object with these keys:
  "model"      (string) — exactly "haiku" or "sonnet".
  "confidence" (number) — 0.0 to 1.0.
  "reason"    (string) — ≤200 chars, English, no PII.

Choose "haiku" only if ALL of the following hold:
  - goal is generic-tech / English
  - no Japanese / CJK / non-ASCII characters
  - no quoted specific entities (file names, column names, place names)
  - no proper nouns referring to a specific real-world entity

Otherwise choose "sonnet" (the safe default for entity-preservation).

Return JSON only. No prose outside the JSON object.

USER (per-call):
GOAL:
<goal>
```

### Parser contract

```python
# infrastructure/routing/_prompts.py
def parse_classification(raw: str) -> GoalClassification:
    """Strip <think>...</think>, ```json fences, extract first {...}, validate via Pydantic.
    On any failure, raise ClassificationParseError (caller maps to SONNET fallback)."""
```

### CLI / API

No new HTTP or CLI surface in this spec. The feature flag flips behavior; the
existing planner endpoints are unchanged.

## LLM / Engine Routing

- **Classifier model — remote default:** `anthropic/claude-haiku-4-5` via
  existing `LLMGateway` adapter. Per-call cost target ≤ $0.0005.
- **Classifier model — local default (LOCAL_FIRST / budget ≤ 0):**
  `ollama/qwen3:8b` via existing `OllamaManagerPort`. Per-call cost $0.
- **Fallback chain (per Constitution §1):** Remote Haiku → Local qwen3:8b →
  Sonnet hardcoded fallback (skip classifier entirely, route everything to
  Sonnet — equivalent to `MORPHIC_PLANNER_ROUTER=disabled`).
- **Planner model — selected by router:** `anthropic/claude-sonnet-4-6` or
  `anthropic/claude-haiku-4-5`. No change to the planner gateway path beyond
  the model id selection.
- **Estimated cost per planner invocation, router enabled:**
  - Eligible-slice (Haiku path): $0.0005 classifier + ~$0.0072 Haiku planner ≈ $0.0077.
  - Ineligible-slice (Sonnet path): $0.0005 classifier + ~$0.01375 Sonnet planner ≈ $0.0143.
  - Baseline (router disabled, all Sonnet): ~$0.01375.
  - **Net win:** depends on the eligible-slice share; break-even at ~4%.

## LAEE touchpoints (if any)

N/A. The router selects a planner model; it does not propose or execute an
action that LAEE governs. No new tools, no risk classification.

## Test Strategy

### Unit tests (DB-free, no LLM calls)

- `tests/unit/domain/value_objects/test_planner_model.py` — enum + `to_gateway_id()`.
- `tests/unit/domain/value_objects/test_goal_classification.py` — Pydantic validation, range checks.
- `tests/unit/domain/value_objects/test_council_events_goal_classified.py` — discriminated-union round-trip.
- `tests/unit/domain/services/test_planner_model_router.py`:
  - router-disabled returns `(default_model, None)` and does NOT call classifier
  - router-enabled + classifier returns Haiku high-confidence → routes Haiku
  - router-enabled + classifier returns Haiku low-confidence → routes Sonnet, reason `"low_confidence: ..."`
  - router-enabled + classifier raises → routes Sonnet, reason `"classifier_failed: ..."`
  - router-enabled + classifier timeout > 1500ms → routes Sonnet, reason `"classifier_failed: timeout"`
  - reason-category normalization (AD-3) covers all 6 buckets
  - event emission failure does NOT break routing
  - goal hashing is sha256-truncated, 16-hex; raw goal never appears in event
- `tests/unit/infrastructure/routing/test_llm_goal_classifier.py` — fake `LLMGateway`, parse success / parse failure / non-JSON / malformed enum.
- `tests/unit/infrastructure/routing/test_local_goal_classifier.py` — fake `OllamaManagerPort`, identical parser coverage.
- `tests/unit/infrastructure/fractal/test_llm_planner_router_integration.py` — fake router + fake gateway: planner consults router, passes correct gateway id.

Fakes live at `tests/unit/application/_fakes/in_memory_goal_classifier.py`
(per TD-187 amendment, test code may import port-compliant InMemory adapters).

### Integration tests (Docker Compose required for some)

- `tests/integration/test_goal_classifier_local_live.py` — real Ollama qwen3:8b,
  3 goals (1 EN-generic, 1 JP, 1 quoted). Cost $0. Skipped if `OLLAMA_BASE_URL`
  not reachable.
- `tests/integration/test_goal_classifier_remote_live.py` — real Anthropic
  Haiku 4.5, same 3 goals. Cost ≤ $0.0015 per CI run. Skipped if
  `ANTHROPIC_API_KEY` not set.

### Benchmark / A/B re-run (NFR-9 success bar)

- `benchmarks/planner_quality_ab.py` — extend with `--router` mode (AD-4).
  Acceptance: router-gated mean within `−5pt` on `entity_preserved` and within
  `−0.030` on `plan_eval`, capturing `≥ 30%` of the Haiku per-call saving on
  the eligible slice. Pinned as the final verification task.

## Migration Plan

No Alembic migration. No data backfill. Settings additions are env-var
defaults; existing deployments keep current behavior (`planner_router_mode`
defaults to `"disabled"`).

## Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Classifier itself regresses (mis-classifies entity-heavy goals as Haiku) | high | NFR-9 A/B re-run is the release gate. Confidence threshold (AD-2) keeps low-confidence calls on Sonnet. |
| Classifier latency eats the savings (NFR-2) | med | Hard timeout (NFR-1) + local Ollama path keeps p95 in budget; cache prompt is stable so LiteLLM cache hits on Haiku adapter. |
| Discriminated-union extension (AD-5) breaks existing subscribers | med | Subscribers today are only the in-memory recording adapter (publish-only port); union is additive, discriminator key unchanged. Verified in `tests/unit/domain/value_objects/test_council_events_goal_classified.py`. |
| Prompt drift causes `reason_category` cardinality to explode | med | Categorization happens in `PlannerModelRouter` via a closed keyword map (AD-3), not from raw classifier output. |
| Privacy leak via raw goal in events/logs (NFR-6) | high | Router never accepts raw goal in event construction; only `goal_hash`. Unit test asserts no string match between raw goal and event payload. |
| Pure-LLM classifier conflicts with user "no rule-based" preference but we still need a small `reason_category` keyword map | low | Map is internal post-processing for Prometheus label cardinality, not user-facing routing logic. Documented in AD-3 as the only rule-shaped artifact in scope. |
| Haiku 4.5 model id churns and `to_gateway_id()` becomes stale | low | Centralized in `PlannerModel.to_gateway_id()`; single point of update; covered by unit test. |

## Rollout

- **Feature flag:** `MORPHIC_PLANNER_ROUTER=disabled` (default) → `=enabled`.
- **Gradual rollout:**
  1. Local dev: flip flag, run `benchmarks/planner_quality_ab.py --router`.
  2. Staging: flip flag, observe 24h of `morphic_goal_classifier_decisions_total`
     and per-task cost dashboards.
  3. Production: flip flag if staging metrics meet NFR-9.
- **Rollback:** flip flag back to `disabled`; behavior reverts to byte-identical
  Sonnet-everywhere (NFR-8).
- **Telemetry checkpoints:**
  - 24h: ≥ 100 classifications, p95 latency in budget, $0.0005 cost ceiling holding.
  - 7d: re-run A/B harness on production goal sample; NFR-9 axes within budget.

---

*Next: generate `tasks.md` via `/prp-implement` after this plan is approved.*
