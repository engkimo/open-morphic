# Implementation Plan — Bypass Classifier Router (TD-196 / B)

> **Spec:** [`spec.md`](spec.md)
> **Status:** draft
> **Estimated effort:** 1.5 days (smaller than TD-195: no router service, no
> A/B benchmark, behavioural parity is the only quality bar)

## Architecture Decisions

### AD-1 — Port + adapter split, NOT a router service

TD-195 introduced both a `GoalClassifierPort` **and** a `PlannerModelRouter`
domain service because planner-model selection has confidence gating, a
fallback chain, and reason-category normalisation. Bypass classification has
none of those: the decision is consumed directly by `FractalEngine` as a
binary gate (`bypass=True` → skip fractal). There is no model selection,
no confidence threshold, no fallback chain to encode.

**Decision: ship a port + two adapters + an observability wrapper. No domain
service.** The `BypassClassifierPort` IS the contract. `FractalEngine` calls
it once per goal; the existing TD-192 TEXT-gate in `BypassClassifier._parse_response`
is preserved verbatim and lives in the adapter, not in a router.

This keeps the change strictly structural (NFR-1 / spec §Non-Goal N-1).

### AD-2 — Mirror TD-195's prompt module layout exactly

`infrastructure/routing/_prompts.py` is the reference shape:

1. Module-level `SYSTEM_PROMPT: str` constant (no f-strings, no env injection).
2. `ClassificationParseError(ValueError)` sentinel.
3. Pure parser function returning the domain VO or raising the sentinel.

`infrastructure/fractal/_bypass_prompts.py` mirrors this exactly. The
`_CLASSIFY_SYSTEM` and `_REQUIREMENT_VALUE_MAP` constants currently
inline in `bypass_classifier.py` move here unchanged. `_extract_json_object`
becomes the public `_extract_json_blob` helper (same logic, shared name).
The parser becomes `parse_bypass(raw: str) -> BypassDecision` and is the
ONLY place that contains the TD-192 TEXT-gate rule.

This is what unlocks two adapters sharing the same byte-identical prompt
(NFR-2 / NFR-4).

### AD-3 — Promote `BypassDecision` from dataclass to frozen Pydantic VO

Currently a `@dataclass(frozen=True)` in `infrastructure/fractal/
bypass_classifier.py`. Moving it to `domain/value_objects/bypass_decision.py`
serves three needs:

1. Domain layer can refer to the VO without importing infrastructure
   (clean-architecture rule).
2. Pydantic gives us a schema for the `BypassClassified` event field
   round-trip test (NFR-5).
3. Field types (`TaskComplexity`, `OutputRequirement`) are already domain
   value objects — promotion is mechanical.

The field set is unchanged: `bypass: bool, complexity: TaskComplexity,
reason: str, output_requirement: OutputRequirement`. The `reason` field
gets the same `max_length=200, no PII` constraint TD-195 used on
`GoalClassification.reason` (resolves a latent privacy hole).

### AD-4 — Event variant on `DebateEvent`, not a new union (resolves OQ-1)

Same logic as TD-195 AD-5: a sibling union would duplicate the
`EventBusPort.publish()` plumbing. `BypassClassified` joins the existing
discriminated union with `kind="bypass_classified"`. The variant carries:

- `correlation_id: UUID` — reuses `debate_id` field name for union shape
  consistency, but semantically is "fractal run id" here.
- `goal_hash: str` — `sha256(goal)[:16]`, mirrors TD-195's privacy primitive.
- `bypass: bool` — the binary decision (the headline metric).
- `complexity: str` — SIMPLE / MEDIUM / COMPLEX as string.
- `output_requirement: str` — text / file / code / data as string.
- `classifier_latency_ms: int`
- `classifier_cost_usd: float`

No raw goal field. Enforced by Pydantic schema (NFR-5) and asserted in a
round-trip test.

### AD-5 — Observability wrapper, NOT inline emission

Two paths were considered:

1. Make every `BypassClassifierPort` adapter emit the `BypassClassified`
   event itself.
2. Wrap any adapter in a `BypassObservingEventBus` decorator that emits
   the event and updates Prometheus counters.

**Decision: wrapper, exactly like `RouterObservingEventBus`.** Reasons:

- Keeps `LLMBypassClassifier` and `LocalBypassClassifier` free of any
  event-bus / metrics dependency (single-responsibility).
- One emission code path → no risk of remote+local adapters diverging on
  what gets logged.
- DI in `interface/api/container.py` can disable observability for unit
  tests by injecting the bare adapter.

The wrapper is a `BypassClassifierPort` itself (decorator pattern) that
takes another `BypassClassifierPort` + `EventBusPort` + `BypassMetrics`.

### AD-6 — Auto-detect default for `MORPHIC_BYPASS_CLASSIFIER` (resolves OQ-3)

DI order in `interface/api/container.py`:

```
remote   ← if ANTHROPIC_API_KEY set
local    ← elif ollama_manager.is_running()
disabled ← else (synthesize a NoOpBypassClassifier that always returns
            BypassDecision(bypass=False, complexity=MEDIUM, ...))
```

`disabled` is a real adapter implementation (`NoOpBypassClassifier`), not
a `None` injection. This keeps `FractalEngine` free of `if classifier is
None` branches — the port is always present.

### AD-7 — `BypassMetrics` lives alongside `RouterMetrics` (resolves OQ-2)

Flat layout, `infrastructure/metrics/bypass_metrics.py`. Same shape as
`router_metrics.py`: a small dataclass-style class wrapping Prometheus
counters/histograms. No subdirectory.

### Ports added / changed

- `domain/ports/bypass_classifier.py` — new ABC `BypassClassifierPort`
  with `async def classify(goal: str) -> BypassDecision`.
- `domain/ports/event_bus.py` — **unchanged contract**; new
  `BypassClassified` variant published through the same `publish()`.

### Entities / value objects added / changed

- `domain/value_objects/bypass_decision.py` — new frozen Pydantic VO.
  Old dataclass deleted from `infrastructure/fractal/bypass_classifier.py`.
- `domain/value_objects/council_events.py` — **extended** with
  `BypassClassified` variant (additive only).

### Domain services added

**None.** This is the spec's headline structural difference vs TD-195.
The port + observer wrapper is the entire abstraction.

### Infrastructure impls

- `infrastructure/fractal/_bypass_prompts.py` — NEW. Holds
  `SYSTEM_PROMPT`, `_REQUIREMENT_VALUE_MAP`, `parse_bypass()`,
  `ClassificationParseError`.
- `infrastructure/fractal/llm_bypass_classifier.py` — NEW.
  `LLMBypassClassifier(BypassClassifierPort)`, remote Anthropic Haiku 4.5
  adapter via existing `LLMGateway`.
- `infrastructure/fractal/local_bypass_classifier.py` — NEW.
  `LocalBypassClassifier(BypassClassifierPort)`, Ollama qwen3:8b adapter
  via existing `OllamaManagerPort`.
- `infrastructure/fractal/noop_bypass_classifier.py` — NEW.
  `NoOpBypassClassifier(BypassClassifierPort)` always returns
  `BypassDecision(bypass=False, complexity=MEDIUM, ...)`. Used when
  `MORPHIC_BYPASS_CLASSIFIER=disabled` or no LLM available.
- `infrastructure/observability/bypass_observing_event_bus.py` — NEW.
  Decorator wrapper mirroring `router_observing_event_bus.py`.
- `infrastructure/metrics/bypass_metrics.py` — NEW. Prometheus counters
  + latency histogram.
- `infrastructure/fractal/bypass_classifier.py` — **DELETED** after
  callers are migrated. Behaviour preserved entirely by
  `LLMBypassClassifier` + `_bypass_prompts.parse_bypass`.
- `infrastructure/fractal/fractal_engine.py` — **modified** to depend on
  `BypassClassifierPort` (line 67, 114 signature change).

### Application layer

No new use case. `FractalEngine` is infrastructure-resident (already);
the port lives in `domain/`. No `application/` changes.

### Interface layer

- `interface/api/container.py` — DI wiring: read
  `MORPHIC_BYPASS_CLASSIFIER` per AD-6, build adapter, wrap with
  `BypassObservingEventBus` if observability enabled, inject into
  `FractalEngine`.
- `shared/config/settings.py` — new fields:
  - `bypass_classifier_mode: Literal["remote", "local", "disabled", "auto"] = "auto"`
  - `bypass_classifier_timeout_ms: int = 2000`
- No HTTP route, no CLI command. Observability is via events + metrics + logs.

## Data Model

```python
# domain/value_objects/bypass_decision.py
class BypassDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    bypass: bool
    complexity: TaskComplexity
    reason: str = Field(max_length=200)
    output_requirement: OutputRequirement = OutputRequirement.TEXT


# domain/value_objects/council_events.py (additive variant)
class BypassClassified(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["bypass_classified"] = "bypass_classified"
    debate_id: UUID  # reused field name; semantically "fractal_run_id" here
    goal_hash: str = Field(pattern=r"^[0-9a-f]{16}$")
    bypass: bool
    complexity: str  # SIMPLE | MEDIUM | COMPLEX
    output_requirement: str  # text | file | code | data
    classifier_latency_ms: int = Field(ge=0)
    classifier_cost_usd: float = Field(ge=0.0)


# Updated discriminated union (additive)
DebateEvent = Annotated[
    DebateStarted
    | ArgumentSubmitted
    | DecisionResolved
    | GoalClassified
    | BypassClassified,
    Field(discriminator="kind"),
]
```

## Contracts

### Classifier prompt contract (stable system message, NFR-2)

Byte-identical to the current `_CLASSIFY_SYSTEM` constant in
`infrastructure/fractal/bypass_classifier.py:28-62`. No edits. No
re-wording. Move-only, then asserted byte-stable by AST test.

### Parser contract

```python
# infrastructure/fractal/_bypass_prompts.py
def parse_bypass(raw: str) -> BypassDecision:
    """Strip <think>...</think>, ```json fences, extract first {...},
    validate via Pydantic. On failure, return the safe fallback
    BypassDecision(bypass=False, complexity=MEDIUM, ...). Mirrors the
    existing FractalBypassClassifier._parse_response semantics exactly,
    including the TD-192 TEXT-gate."""
```

### Port contract

```python
# domain/ports/bypass_classifier.py
class BypassClassifierPort(ABC):
    @abstractmethod
    async def classify(self, goal: str) -> BypassDecision: ...
```

### CLI / API

No new HTTP or CLI surface. The env flag flips DI wiring; the existing
fractal endpoints are unchanged.

## LLM / Engine Routing

- **Classifier model — remote default:** `anthropic/claude-haiku-4-5`
  via existing `LLMGateway`. Per-call cost target ≤ $0.0003.
- **Classifier model — local default (LOCAL_FIRST / budget ≤ 0):**
  `ollama/qwen3:8b` via existing `OllamaManagerPort`. Per-call $0.
- **Fallback chain:** Remote Haiku → Local qwen3:8b → NoOp (disabled,
  all goals take fractal path).

No change to FractalEngine downstream chain.

## LAEE touchpoints (if any)

N/A. The classifier picks a control-flow gate; it does not propose or
execute an action that LAEE governs.

## Test Strategy

### Unit tests (DB-free, no LLM calls)

- `tests/unit/domain/value_objects/test_bypass_decision.py` — Pydantic
  validation, frozen semantics, default `output_requirement = TEXT`,
  `reason` max-length enforcement.
- `tests/unit/domain/value_objects/test_council_events_bypass_classified.py`
  — discriminated-union round-trip; `goal_hash` regex enforcement;
  raw-goal field absence assertion.
- `tests/unit/infrastructure/fractal/test_bypass_prompts.py` —
  `parse_bypass` golden cases:
  - happy path (SIMPLE/text → bypass=True)
  - TD-192 gate (SIMPLE/file → bypass=False)
  - MEDIUM, COMPLEX paths
  - malformed JSON → safe fallback
  - `<think>` block stripping
  - markdown fence stripping
- `tests/unit/infrastructure/fractal/test_prompt_stability.py` — AST
  walker: assert `SYSTEM_PROMPT` in `_bypass_prompts.py` is a
  module-level `ast.Constant` of type `str` (no f-string, no concat,
  no call).
- `tests/unit/infrastructure/fractal/test_llm_bypass_classifier.py` —
  fake `LLMGateway`: parse success / failure / non-JSON / timeout
  fallback.
- `tests/unit/infrastructure/fractal/test_local_bypass_classifier.py` —
  fake `OllamaManagerPort`: identical parser coverage.
- `tests/unit/infrastructure/fractal/test_noop_bypass_classifier.py` —
  always returns `bypass=False, complexity=MEDIUM`.
- `tests/unit/infrastructure/observability/test_bypass_observer.py`:
  - delegates to wrapped port
  - emits exactly one `BypassClassified` event per call
  - increments correct metric labels
  - event emission failure does NOT break classification
  - raw goal NEVER appears in event payload (string-match assertion)
  - `goal_hash` is sha256-truncated, 16-hex
- `tests/unit/infrastructure/fractal/test_fractal_engine_port_wiring.py`
  — fake `BypassClassifierPort`: `FractalEngine` accepts the port,
  calls it once per goal, uses the returned `BypassDecision` verbatim.

Fakes live at `tests/unit/application/_fakes/in_memory_bypass_classifier.py`
(per TD-187 amendment).

### Integration tests

- `tests/integration/test_bypass_classifier_local_live.py` — real
  Ollama qwen3:8b, 3 goals (1 EN-SIMPLE-text, 1 JP-slide, 1 EN-COMPLEX).
  Cost $0. Skipped if `OLLAMA_BASE_URL` not reachable.
- `tests/integration/test_bypass_classifier_remote_live.py` — real
  Anthropic Haiku 4.5, same 3 goals. Cost ≤ $0.0009 per CI run.
  Skipped if `ANTHROPIC_API_KEY` not set.

### Regression bar (NFR-1 / NFR-7)

- `tests/integration/test_round19_regression.py` — existing 6-case
  regression must pass byte-for-byte with `MORPHIC_BYPASS_CLASSIFIER`
  unset (auto-detect → remote) AND with `=disabled` (NoOp).

## Migration Plan

No Alembic migration. No data backfill.

**Code migration order** (each step is independently revertable):

1. Add new files (`_bypass_prompts.py`, `bypass_decision.py`, port ABC,
   3 adapters, observer wrapper, metrics). Old code unchanged.
2. Add `BypassClassified` variant to `council_events.py` discriminated
   union. Old subscribers ignore unknown `kind`.
3. Change `FractalEngine.__init__` signature: `FractalBypassClassifier
   | None` → `BypassClassifierPort | None`. Old `FractalBypassClassifier`
   still satisfies the port duck-wise (it has `should_bypass`, not
   `classify`) — so add a method alias OR rename in step 4.
4. Migrate `FractalEngine` caller to use `classify()` not `should_bypass()`.
5. Update `interface/api/container.py` DI wiring to pick adapter via
   `MORPHIC_BYPASS_CLASSIFIER` env (default auto-detect).
6. Delete `infrastructure/fractal/bypass_classifier.py` once no
   imports remain.

## Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Behavioural drift between old `_parse_response` and new `parse_bypass` | high | Step 1 of migration: copy logic byte-for-byte; golden parser test covers all 6 current paths; Round 19 regression is the release gate (NFR-1). |
| Discriminated-union extension breaks existing subscribers | med | Same as TD-195 AD-5 mitigation: subscribers are publish-only; union is additive. Covered by `test_council_events_bypass_classified.py` round-trip. |
| `SYSTEM_PROMPT` accidentally edited during the move and breaks KV-cache | med | AST-walker test (NFR-2) pins it as a module-level `str` constant; CI fails on any f-string conversion. |
| Privacy leak via raw goal in events/logs (NFR-5) | high | Pydantic schema has no `goal` field; observer constructs `goal_hash` and discards raw goal before publish; string-match unit test asserts absence. |
| Auto-detect picks wrong default on misconfigured boxes (e.g. API key set but invalid) | low | Auto-detect is a wiring-time choice, not a per-call fallback. Misconfigured remote keys surface as `classifier_failed` events; operators see metrics and flip `MORPHIC_BYPASS_CLASSIFIER=local` explicitly. |
| Ollama p95 latency exceeds NFR-3 budget (800ms) | med | `bypass_classifier_timeout_ms` (default 2000) caps worst case; on timeout the adapter returns the safe fallback (no bypass), so latency cap never blocks correctness. |
| Two adapters drift on the prompt over time | low | Single shared `SYSTEM_PROMPT` constant + AST test; both adapters import from `_bypass_prompts.py`. |

## Rollout

- **Feature flag:** `MORPHIC_BYPASS_CLASSIFIER=auto` (default — picks
  remote if API key set, else local, else disabled). Explicit values:
  `remote`, `local`, `disabled`.
- **Gradual rollout:**
  1. Local dev: run unit + integration suite. Run Round 19 regression
     in both `auto` and `disabled` modes — both must pass.
  2. Staging: deploy with `auto`. Observe 24h of `morphic_bypass_
     classifications_total` and latency histogram.
  3. Production: deploy with `auto`. If bypass-rate drifts >10pt from
     baseline within 1h, flip to `disabled` to revert.
- **Rollback:** flip flag to `disabled`; behaviour reverts to "all
  goals take fractal path" — byte-identical to TD-167 pre-bypass era
  for fractal output, only differing in that the classifier LLM call
  is skipped entirely.
- **Telemetry checkpoints:**
  - 24h: bypass-rate within ±10pt of `main` HEAD baseline; p95 latency
    in budget (remote <300ms, local <800ms); classifier cost ≤ $0.0003/call.
  - 7d: zero raw-goal log leakage incidents.

---

*Next: generate `tasks.md` via `/prp-implement` after this plan is approved.*
