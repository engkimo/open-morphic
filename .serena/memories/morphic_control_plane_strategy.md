# Morphic Control Plane Strategy

Decision date: 2026-07-14
Last updated: 2026-07-15

## Product decision

Morphic will not try to beat Claude Code, Codex CLI, or Gemini CLI by cloning
their terminal UX and reimplementing every native harness feature. Morphic will
be the multi-engine control plane that preserves and coordinates those native
agent runtimes.

The winning category is:

> One terminal and canonical workspace harness for routing, supervising,
> comparing, handing off, and auditing work across Claude Code, Codex CLI,
> Gemini CLI, OpenHands, Ollama, and direct LLM gateways.

Native engines remain responsible for their strongest internal agent loops,
tools, subagents, skills, MCP integrations, and provider-specific behavior.
Morphic owns cross-engine session state, context projection, permission policy,
audit events, cost, normalized results, worktree isolation, evidence-based
selection, and handoff.

## Current-state finding

The Chat CLI foundation is strong and well tested, but it is still a technical
preview rather than a daily-driver coding agent:

- `morphic chat` and `morphic code` default to `LocalChatCouncilRuntime`, which
  returns deterministic planning text instead of running a coding agent.
- Chat hook and tool executors default to no-op.
- Route-backed council always invokes planner, critic, and leader sequentially,
  adding latency and cost even when one engine is enough.
- External CLI drivers are one-shot subprocess adapters. They do not yet expose
  streaming events, steering, approvals, resume, subagent state, or native
  harness activity through Morphic.
- Skills, MCP, hooks, memory, and context features exist in the wider product,
  but are not yet one coherent Chat CLI agent loop.

Validation on 2026-07-14: 3,478 unit tests passed and Ruff was clean.

## Implementation priorities

1. Connect `morphic code` to a single real routed engine without forcing a
   three-role council. Start behind explicit opt-in until permission propagation
   and failure behavior are verified.
2. Define a normalized engine event stream: engine start, assistant delta, tool
   request/result, approval, file change, verification, subagent activity, cost,
   wait state, and completion.
3. Upgrade Claude Code, Codex CLI, and Gemini CLI adapters from one-shot result
   capture to resumable, steerable native sessions while preserving their skills,
   MCP, hooks, and permission behavior.
4. Use adaptive orchestration: one engine for simple work, critic on risk or
   uncertainty, council only for complex or disputed work, worktrees for parallel
   writers, and cross-engine handoff after failure.
5. Build `.morphic` harness inspect/diff/export projections for AGENTS.md,
   CLAUDE.md, GEMINI.md, skills, hooks, MCP, and permissions. Never overwrite
   tool-specific files silently.
6. Prove the advantage with real repository benchmarks against Claude Code and
   Codex alone: completion rate, accepted patch rate, elapsed time, cost, human
   interventions, recovery rate, and context-handoff fidelity.

## First implementation slice

Add a route-backed direct runtime for Chat CLI that makes exactly one
`RouteToEngineUseCase` call, supports an explicit preferred engine, records the
engine result through existing chat events, and reports route failures rather
than silently presenting the deterministic local response as success.

Expose this first as an explicit CLI mode. Keep the current local deterministic
mode available as dry-run/fallback behavior until external-engine permission
mapping and live verification are complete.

## Phase 27 update

Codex CLI is the first permission-aware native direct adapter. The deprecated
`--full-auto` path was replaced with explicit `--sandbox` mapping and `--cd`
workspace scoping. Morphic `read-only`, `workspace-write`, and
`danger-full-access` map to the equivalent Codex sandbox. Morphic
`confirm-destructive` is deliberately rejected because `codex exec` is
non-interactive and cannot preserve an approval prompt channel.

Codex `--json` output is JSONL, not a single JSON object. Morphic now normalizes
thread, turn, tool, file change, plan, assistant, completion, failure, and error
records into provider-independent engine events while retaining the raw payload.
Until equivalent permission/workspace mappings exist for other native engines,
Chat CLI direct route explicitly requires `--engine codex_cli`.

## Phase 28 update

Normalized native events are now durable chat state rather than metadata visible only
on the final engine result. Direct-runtime turns carry `AgentEngineEvent` values, and
the send-message use case appends each one to the session ledger before the matching
council argument and assistant response. Raw Codex JSONL payloads remain attached for
audit and future parser evolution.

Workspace and permission controls now travel through `ScopedAgentEnginePort`, a narrow
capability separate from the common engine contract. Routing skips engines that do not
implement it instead of calling them with controls they might ignore. Codex is the first
scoped adapter. At the end of Phase 28, execution still buffered subprocess output until
completion; Phase 29 below closes that delivery gap.

## Phase 29 update

Codex direct execution now has a real incremental path. The subprocess runner drains
stdout and stderr concurrently; each JSONL stdout line is decoded with stateful thread
and sequence tracking and published before process completion. The application persists
the user message first, then appends native events immediately through its own ledger
sink. Buffered result metadata remains available for other callers without duplicating
streamed chat events.

Streaming is expressed as narrow capabilities (`StreamingScopedAgentEnginePort` and
`StreamingCouncilRuntimePort`), so adapters that cannot honor live delivery are never
mistaken for adapters that can. The next gaps are terminal live rendering and Codex
thread resume/steering; the durability pipeline itself is now in place.

## Phase 30 update

The line-oriented terminal now surfaces selected native events as concise progress after
their durable ledger append. Rendering is allowlisted to run, tool, file, plan,
completion, and error state. Raw provider payloads, generic progress/reasoning, unknown
events, and assistant-message content stay out of the progress channel. Details are
whitespace-normalized and capped, and presentation failure cannot cancel execution or
erase audit history.

The next control-plane primitive is native session continuity: resume the stored Codex
thread without losing Morphic workspace and permission guarantees, then expose steering
and cross-engine handoff on top of the same normalized ledger.

## Phase 31 update

Morphic now resumes an explicit Codex thread from its own append-only ledger. Native
session identity is stored with engine, original workspace root, and permission mode;
ledger replay reconstructs that binding after `morphic chat --resume`. The direct runtime
fails closed if current scope differs. Codex receives explicit sandbox/cwd options plus
`resume <thread_id> <prompt>`; Morphic never relies on Codex's ambiguous global `--last`.

Resume is a separate adapter capability rather than an assumption attached to all
streaming engines. The next gap is interactive steering/cancellation, followed by a
Claude Code adapter implementing the same scoped event and continuity contracts.

## Phase 32 update

Native process cancellation is now resource-safe. Both buffered and streaming subprocess
paths terminate the child when their asyncio task is cancelled, escalate to kill after a
two-second grace period, and re-raise the original cancellation. This closes the orphan
process risk before adding a user-facing `/cancel` or steering control channel.

## Phase 33 update

Claude Code is now a permission-aware scoped adapter. Morphic maps read-only to `plan`,
workspace-write to `acceptEdits`, and danger-full-access to an explicit bypass mode; it
rejects confirm-destructive in headless execution. The driver runs in the requested cwd.

More importantly for the control-plane strategy, Morphic no longer forces Claude to
user-only settings or a hard-coded tool allowlist. Claude's project/local settings,
CLAUDE.md discovery, skills, hooks, MCP, plugins, and native tool policy remain intact.
The next slice is `stream-json` normalization and explicit session resume; only after
that should Chat CLI direct mode allow `claude_code` alongside `codex_cli`.

## Publication checkpoint (2026-07-15)

Phases 26-31 form the first complete native Codex control-plane vertical slice:
single-engine direct routing, explicit workspace/permission mapping, provider-neutral
events, incremental durable streaming, safe terminal progress, and provenance-checked
thread resume. The implementation passed 3,513 unit tests with repository-wide Ruff
clean before publication. The next development sequence is cancellation/steering first,
then a Claude Code adapter behind the same scoped streaming and resume capabilities.
