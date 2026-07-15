# Implementation Plan - Morphic Chat CLI

> **Spec:** [`spec.md`](spec.md)
> **Status:** draft
> **Estimated effort:** 4 to 6 sprints for production quality; 1 sprint for MVP REPL.

## Summary

Build a first-party terminal chat CLI for Morphic. The MVP should validate the core loop without overbuilding a full-screen TUI:

```
morphic chat
  -> starts session
  -> discovers context
  -> accepts user goal
  -> runs planner/critic/leader loop
  -> requests approvals for mutation
  -> executes through existing harness ports
  -> verifies with tests/lint when requested
  -> writes append-only session ledger
```

The first implementation should be line-oriented and portable. A richer Textual UI can come after the event model, session store, slash command registry, and approval flow are stable.

## Architecture Decisions

### CLI first, TUI later

A full-screen TUI is attractive, but it couples rendering decisions to the earliest domain and application design. The MVP should start with a line-oriented REPL using the existing CLI stack. The event stream should be rich enough that a Textual UI can subscribe later without changing domain concepts.

### `.morphic` as canonical metadata

Tool-specific metadata should remain supported, but Morphic should create a canonical project layer:

```
.morphic/
  context/
    index.json
  memory/
    facts.jsonl
    decisions.jsonl
    preferences.jsonl
  hooks/
  sessions/
  exports/
    claude/
    codex/
    gemini/
```

The MVP writes only context index and sessions. Memory and exports can be introduced incrementally.

### Roles are not engines

Roles describe responsibility. Engines describe runtime.

Example:

```
planner role -> may run on Ollama for cheap draft
critic role -> may run on Claude Code for hard architecture review
researcher role -> may run on Gemini CLI for long context
executor role -> may use Codex CLI or local LAEE tools
```

Keeping these separate prevents the design from hard-coding "Claude is the architect" or "Codex is always implementer."

### Direct route before always-on council

Council is a quality mechanism, not the default execution topology for every task. The
CLI should also support a direct runtime that delegates one goal to one routed native
agent engine. Direct mode reuses `CouncilRuntimePort` temporarily so session/event
orchestration stays unchanged, but emits one `IMPLEMENTER` turn and one decision.

Direct mode is explicit while native permission propagation is incomplete. The first
supported adapter is Codex CLI: `read-only`, `workspace-write`, and
`danger-full-access` map to explicit Codex sandboxes, while `confirm-destructive` is
rejected because `codex exec` has no interactive approval channel. Direct mode makes
exactly one route call and never converts route failure into deterministic local success.
Other native engines remain unavailable in direct mode until their permission and
workspace controls are mapped explicitly.

Native adapter output is normalized into `AgentEngineEvent` values and attached to the
single implementer turn. `SendChatMessageUseCase` writes each value as an independent
`engine_event` before the council argument, decision, and assistant response. This makes
tool activity, file changes, plans, and lifecycle state replayable without parsing a
provider blob embedded only in the final response. Workspace and permission propagation
uses a separate `ScopedAgentEnginePort`; ordinary adapters keep the smaller common port
and are skipped when a scoped run is requested.

For live execution, `StreamingScopedAgentEnginePort` adds an event sink without widening
the ordinary or buffered scoped contracts. Codex drains stdout and stderr concurrently,
decodes each JSONL stdout line with stateful thread/sequence tracking, and publishes it
before process completion. `StreamingCouncilRuntimePort` carries the sink to the
application layer, where the user message is persisted first and each native event is
appended immediately. The final result still retains its complete event metadata for
non-streaming consumers, but the streaming send path does not append it twice.

Terminal progress is a best-effort observer downstream of durable event append. The
renderer uses an allowlist of lifecycle, tool, file, and plan event types, normalizes
whitespace, and truncates detail. It never reads the raw payload and ignores assistant
messages, generic progress/reasoning, and unknown provider events. A renderer exception
is logged but does not cancel native execution or roll back the already-written ledger.

Native thread continuity is reconstructed from the Morphic ledger, not from a global
provider "last session" lookup. `ChatSession` records engine id, provider session id,
workspace root, and permission mode when a native event first identifies a thread.
Resume replays the ledger to rebuild that binding. `ResumableStreamingScopedAgentEnginePort`
is a separate capability; Codex implements it with `exec` scope flags before
`resume <thread_id> <prompt>`. Direct runtime compares stored workspace and permission
provenance with the current turn and fails before route execution on mismatch.

### Morphic owns execution state

External CLIs can contribute proposals or execute delegated tasks, but Morphic should own:
- Session ledger.
- Approval policy.
- Tool call normalization.
- Final decision.
- Memory writes.
- Context index.
- User-facing transcript.

This avoids recreating the same fragmentation the feature is meant to solve.

## Layered Design

### Domain

New domain concepts should be framework-free:

```
domain/entities/chat_session.py
domain/entities/chat_event.py
domain/entities/council_runtime.py
domain/entities/workspace_context.py
domain/entities/approval.py
domain/ports/chat_session_store.py
domain/ports/context_discovery.py
domain/ports/council_runtime.py
domain/ports/tool_executor.py
domain/ports/engine_registry.py
```

Potential entities:
- `ChatSession`
- `ChatEvent`
- `SessionId`
- `CouncilRole`
- `CouncilTurn`
- `WorkspaceContextSource`
- `ContextIndex`
- `ApprovalRequest`
- `ApprovalDecision`
- `ToolCallRecord`

### Application

Use cases:

```
application/use_cases/start_chat_session.py
application/use_cases/send_chat_message.py
application/use_cases/execute_slash_command.py
application/use_cases/discover_workspace_context.py
application/use_cases/request_tool_approval.py
application/use_cases/resume_chat_session.py
application/use_cases/summarize_chat_session.py
```

Responsibilities:
- Manage session state.
- Append events.
- Call context discovery.
- Invoke council runtime.
- Request approvals.
- Execute tools through ports.
- Return renderable events to interface.

### Infrastructure

Adapters:

```
infrastructure/chat/jsonl_session_store.py
infrastructure/context/workspace_context_discovery.py
infrastructure/engines/engine_registry.py
infrastructure/engines/claude_code_adapter.py
infrastructure/engines/gemini_cli_adapter.py
infrastructure/engines/codex_cli_adapter.py
infrastructure/engines/ollama_adapter.py
infrastructure/tools/laee_tool_executor.py
```

Rules:
- External CLI invocation lives here.
- JSONL persistence lives here.
- File scanning lives here.
- LAEE integration lives here.

### Interface

CLI:

```
interface/cli/chat_command.py
interface/cli/chat_repl.py
interface/cli/slash_commands.py
interface/cli/renderers.py
```

Responsibilities:
- Parse CLI args.
- Render events.
- Read user input.
- Dispatch slash commands.
- Display approvals and diffs.

## Event Model

Events should be append-only and replayable.

```json
{
  "type": "user_message",
  "session_id": "20260624-...",
  "sequence": 12,
  "created_at": "2026-06-24T10:00:00+09:00",
  "payload": {
    "text": "unit testsを直して"
  }
}
```

Required fields:
- `type`
- `session_id`
- `sequence`
- `created_at`
- `payload`

Recommended types:
- `session_started`
- `context_indexed`
- `user_message`
- `assistant_message`
- `slash_command`
- `council_started`
- `council_argument`
- `council_decision`
- `tool_call_requested`
- `approval_requested`
- `approval_resolved`
- `tool_call_completed`
- `diff_proposed`
- `verification_started`
- `verification_result`
- `memory_candidate`
- `session_summary`
- `session_ended`

## Command UX

Initial commands:

```bash
morphic chat
morphic chat --resume latest
morphic code "fix failing unit tests"
morphic doctor agents
morphic context scan
```

Inside chat:

```text
> /status
> /context
> /engines
> /diff
> /doctor
> /quit
```

## MVP Scope

MVP should include:
- `morphic chat` line-oriented REPL.
- Session JSONL store.
- Context discovery for `AGENTS.md`, `CLAUDE.md`, `.claude/`, `GEMINI.md`, `.morphic/`.
- Slash commands: `/help`, `/status`, `/context`, `/engines`, `/diff`, `/quit`.
- Council roles: planner, critic, leader.
- Engine registry with at least Ollama/direct LLM fakeable adapter.
- Read-only planning mode.
- Workspace-write path with approval prompt for edits.
- Unit tests with fake engines and fake tool executor.

MVP should not include:
- Full-screen TUI.
- Automatic export to other CLI metadata formats.
- Real multi-engine external CLI execution in unit tests.
- Git commit/push automation.

## Follow-Up Scope

After MVP:
- Textual UI.
- `/memory` and memory candidate approval.
- `.morphic` to `.claude`/Codex/Gemini projections.
- Hook validation and execution.
- External CLI adapters for Claude Code, Gemini CLI, Codex CLI.
- Council event viewer.
- JSON event streaming for automation.
- Integration with `council-pilot` debate events.

## Test Strategy

Unit tests:
- Session store appends and replays events.
- Slash command parser handles known and unknown commands.
- Context discovery indexes expected files and preserves provenance.
- Permission mode blocks mutation in read-only mode.
- Approval flow records request and resolution.
- Council leader selects by evidence, not majority.
- Clean Architecture import checks for new domain files.

Integration tests:
- `morphic chat` can start, run `/status`, and quit.
- `morphic context scan` creates `.morphic/context/index.json`.
- `morphic code "..."` can run in read-only planning mode with fake/local engine.

Manual validation:
- Run in this repo.
- Confirm `AGENTS.md` and `CLAUDE.md` are discovered.
- Confirm session ledger is append-only.
- Confirm no existing metadata files are overwritten.

## Risks

| Risk | Mitigation |
|---|---|
| Building a TUI too early slows core loop | Start with REPL and event stream |
| External CLI adapters cause brittle subprocess behavior | Make them later infrastructure adapters behind fakeable ports |
| Metadata sync overwrites user files | Discovery first, explicit export later |
| Multi-agent debate becomes noisy | Leader must summarize evidence and ask before high-risk execution |
| Unit tests accidentally call real models | Fakes only in unit tests; integration tests opt-in |
| Prompt prefixes become unstable | Dynamic values in user/context payloads only |

## Implementation Order

1. Define domain event/session/context entities and ports.
2. Implement JSONL session store.
3. Implement context discovery and `.morphic/context/index.json`.
4. Implement slash command parser and REPL shell.
5. Implement fake/local council runtime for planner/critic/leader.
6. Wire `morphic chat`.
7. Add approval flow and workspace-write guard.
8. Add `morphic code "<goal>"` one-shot entry.
9. Add diagnostics commands.
10. Add first external engine adapter behind registry.
11. Add an explicit single-engine direct route before making real execution the default.
12. Add normalized streaming/resume/approval events and native permission mappings.
