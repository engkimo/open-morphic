# AGENTS.md — Morphic-Agent

> Telegraph style. Root rules only. Read scoped AGENTS.md before touching a subtree.
> Every rule actionable. See `CLAUDE.md` for the thin router + full doc index.

## Start

- Version 0.5.2. Status: 82 sprints done, 3,035 unit tests passing, 0 failures.
- Primary entry point for human context: `CLAUDE.md` (thin router).
- Primary entry point for Codex CLI / Gemini CLI: this file.
- Detailed docs: `docs/*.md`. Never load all at once.

## Repo Map

- `domain/` — pure business logic, zero deps. Never imports SQLAlchemy / FastAPI / LiteLLM.
- `application/` — use cases, DTOs.
- `infrastructure/` — port impls, LLM gateway, LAEE, agent CLI drivers, persistence.
- `interface/` — FastAPI + CLI entry points, DI wiring.
- `shared/` — cross-cutting (config only).
- `tests/{unit,integration,e2e}/` — TDD, unit runs DB-free.
- `migrations/` — Alembic async.
- `ui/` — Next.js 15 dark theme.
- `specs/` — spec-driven feature folders.
- `.specify/` — constitution + templates.
- `.claude/agents/` — subagents. `.claude/skills/` — skills. `.claude/commands/` — slash commands.

## Architecture

- 4-layer Clean Architecture: `Interface → Application → Domain ← Infrastructure`.
- Dependency rule: inner layers never import outer. Reverse via `domain/ports/*` ABCs.
- 23 ports, 17 use cases, 18 domain services, 6 agent CLI drivers.
- Execution priority: Engine routing → ReactExecutor fallback → Direct LLM fallback.
- Fractal bypass: LLM intent analysis classifies SIMPLE vs COMPLEX; SIMPLE skips planning (TD-167).
- Persistence: PG (primary), SQLite (fallback), InMemory (default).

## Commands

- `uv sync` — install deps.
- `uv run --extra dev pytest tests/unit/ -v` — fast unit tests (DB-free).
- `uv run --extra dev pytest tests/integration/ -v` — requires Docker Compose up.
- `uv run --extra dev ruff check .` — lint.
- `uv run uvicorn interface.api.main:app --port 8001 --reload` — dev server.
- `morphic doctor check` — health check.

## Gates (must pass before commit)

- All unit tests pass (0 failures, 0 warnings).
- Lint clean (`ruff check`).
- No `domain/` imports of infrastructure / framework code.
- No `@imports` expanding CLAUDE.md past 40KB warning.

## Code Style

- Python: `from __future__ import annotations`, Pydantic v2, async-first.
- No emojis in code unless user asks.
- No trailing summary comments.
- Domain entities: immutable Pydantic models, no ORM.
- Ports: ABCs in `domain/ports/`, implementations in `infrastructure/`.

## Tests

- TDD: RED → GREEN → REFACTOR. Never ship without tests.
- Unit tests mock ports; integration tests use real PG/Redis/Qdrant.
- Never mock the DB in tests that cover migrations.

## Git / Commits

- Commit messages: concise English, imperative mood.
- Never push to main without explicit user request.
- Never use `--no-verify`, `--no-gpg-sign` unless user asks.
- 1 fix → commit & push → report. No batching.

## Security / LAEE

- Secrets under `~/.ssh`, `~/.aws`, `.env` → CRITICAL risk level.
- LAEE default approval mode: `confirm-destructive`. `full-auto` requires explicit user opt-in.
- All LAEE actions logged to `.morphic/audit_log.jsonl` (append-only).
- Risk classification is separate from approval transport (OpenClaw pattern).

## Prompt Caching

- System prompt prefix must be stable. Never put timestamps in the first N bytes.
- Append-only context. Never edit past messages.
- Tool definitions: mask, don't delete. See `domain/services/tool_state_machine.py`.
- JSON/YAML serialization: `sort_keys=True` deterministic.

## Agent CLI Routing

- Long-running dev → OpenHands (Docker sandbox).
- Complex reasoning → Claude Code SDK.
- Long context (>100K) → Gemini CLI.
- Fast code gen → Codex CLI.
- Cost-zero / draft → Ollama (`qwen3:8b`).
- Workflow pipeline (Seq/Par/Loop) → Google ADK.

## Docs / Changelog

- Thin `CLAUDE.md` is the router. Full details in `docs/<topic>.md`.
- Update `docs/CHANGELOG.md` for any structural change.
- Update `docs/CONTINUATION.md` at session end for handoff.

## Scoped AGENTS.md children

Add these as the codebase grows:
- `domain/AGENTS.md` — domain invariants, ports contract rules.
- `infrastructure/local_execution/AGENTS.md` — LAEE-specific safety rules.
- `infrastructure/agent_cli/AGENTS.md` — engine driver conventions.
- `interface/api/AGENTS.md` — FastAPI + DI conventions.
- `tests/AGENTS.md` — TDD conventions, mock/real rules.

## Misc Footguns

- OpenHands v0.59 sends `temperature` + `top_p` to Claude API → rejected. Use Gemini or upgrade image.
- OpenAI GPT-4o quota insufficient on this account; use `o4-mini`.
- `qwen3:8b` is the default Ollama model (16GB RAM machines).
- Fractal bypass misclassifies some complex tasks as SIMPLE — see Round 19 regression (TD-181).
