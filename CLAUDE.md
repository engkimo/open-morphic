# Morphic-Agent — Self-Evolving AI Agent Framework

> *"Mission Control for Intelligence"*
> ユーザーの意図を汲み取り、タスクをこなし、失敗を糧に自己進化する。
>
> **Version:** 0.5.2 | **Last updated:** 2026-04-22

---

## 🗺️ Where to Look

This file is a **thin router**. Load what you need:

| Topic | File |
|---|---|
| Vision & differentiation | [`docs/VISION.md`](docs/VISION.md) |
| Full architecture | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Context Engineering (Manus 5原則) | [`docs/CONTEXT_ENGINEERING.md`](docs/CONTEXT_ENGINEERING.md) |
| Agent CLI Orchestration (v0.3) | [`docs/AGENT_CLI.md`](docs/AGENT_CLI.md) |
| Semantic Memory Hierarchy | [`docs/SEMANTIC_MEMORY.md`](docs/SEMANTIC_MEMORY.md) |
| LAEE — Local Execution (v0.4) | [`docs/LAEE.md`](docs/LAEE.md) |
| UCL — Unified Cognitive (v0.5) | [`docs/UCL.md`](docs/UCL.md) |
| Tech stack & dev commands | [`docs/TECH_STACK.md`](docs/TECH_STACK.md) |
| Development phases & metrics | [`docs/PHASES.md`](docs/PHASES.md) |
| UI theme & layout | [`docs/UI_DESIGN.md`](docs/UI_DESIGN.md) |
| Environment variables | [`docs/ENV_VARS.md`](docs/ENV_VARS.md) |
| External references | [`docs/REFERENCES.md`](docs/REFERENCES.md) |
| Changelog | [`docs/CHANGELOG.md`](docs/CHANGELOG.md) |
| Coding rules & conventions | [`docs/CODING_RULES.md`](docs/CODING_RULES.md) |
| Technical decisions (ADRs) | [`docs/TECH_DECISIONS.md`](docs/TECH_DECISIONS.md) |
| Competitive analysis | [`docs/COMPETITIVE_ANALYSIS.md`](docs/COMPETITIVE_ANALYSIS.md) |
| Handoff state | [`docs/CONTINUATION.md`](docs/CONTINUATION.md) |

**Custom tooling:**
- Subagents: [`.claude/agents/`](.claude/agents/)
- Skills: [`.claude/skills/`](.claude/skills/)
- Slash commands: [`.claude/commands/`](.claude/commands/)
- Path-specific rules: [`.claude/rules/`](.claude/rules/)
- Spec-driven workflow: [`specs/`](specs/) + [`.specify/`](.specify/)

---

## 🎯 Implementation Rules (Always Active)

### Cursor Agent Rules
1. 「やります」と言ったら即実行。宣言だけして待たない
2. ユーザーの問題が完全解決するまで実行を止めない
3. 独立タスクは **DEFAULT TO PARALLEL**。順次は A の出力が B に必要なときだけ
4. 各アクションの前に `todo.md` を読み、後に更新する
5. ツール名をユーザーに見せず、自然言語で説明する

### 禁止事項
- ❌ システムプロンプト先頭にタイムスタンプを入れない (KV キャッシュ破壊)
- ❌ コンテキストを遡って編集しない (append-only 原則)
- ❌ タスク実行中にツール定義を追加/削除しない (マスキングで対応)
- ❌ API 優先でローカル LLM を後回しにしない (`LOCAL_FIRST=true`)
- ❌ 計画なしに実行しない (Interactive Planning 必須)

### 実装優先順位
1. `ollama_manager.py` + `llm_router.py` — まず $0 で動かす
2. `task_graph/engine.py` — コア DAG
3. `context_engineering/` — Manus 5 原則を最初から実装
4. 基本 UI (グラフ + コスト表示)
5. `marketplace/auto_discoverer.py`
6. `evolution/` — データが貯まってから

---

## 🏗️ Architecture Overview

**4-layer Clean Architecture**: `Interface → Application → Domain ← Infrastructure`

```
domain/           # 純粋ビジネスロジック (依存ゼロ)
application/      # ユースケース
infrastructure/   # ポート実装 (DB, LLM, LAEE, Agent CLI drivers)
interface/        # FastAPI + CLI エントリーポイント
```

- `domain/` はフレームワーク依存ゼロ (SQLAlchemy, FastAPI, LiteLLM を import しない)
- `infrastructure/` は `domain/ports/` の ABC を実装する
- `application/` は `domain/` のエンティティとポートだけ使う
- `interface/` は `application/` のユースケースを呼ぶ (DI でポート→実装を注入)

詳細: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

---

## 🚀 Quick Start

```bash
# 1. Ollama セットアップ (まず無料で動かす)
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull qwen3:8b

# 2. プロジェクト
uv sync
docker compose up -d                                   # PG + Redis + Qdrant
uv run --extra dev pytest tests/unit/ -v               # Test (3,035 tests)
uv run --extra dev ruff check .                        # Lint
uv run uvicorn interface.api.main:app --port 8001     # Server

# 3. Health check
morphic doctor check

# 4. タスク実行 ($0 local)
curl -X POST localhost:8001/task \
  -H "Content-Type: application/json" \
  -d '{"goal": "Pythonでフィボナッチ数列を実装", "model": "ollama/qwen3:8b"}'
```

---

## 🤖 Custom Agents & Skills

| Subagent | 役割 |
|---|---|
| `engine-tester` | 6 エンジン E2E 検証 (フォーク実行) |
| `laee-auditor` | LAEE アクション + `audit_log.jsonl` レビュー |
| `context-engineer` | Manus 5 原則 + KV キャッシュ検証 |
| `spec-writer` | `spec.md` → `plan.md` → `tasks.md` 生成 |
| `cost-guardian` | LLM コスト監視・超過アラート |
| `memory-archaeologist` | L1-L4 セマンティックメモリ検索 |
| `morphic-pr-reviewer` | 4 層アーキテクチャ違反・Clean Arch ルール検出 |
| `harness-optimizer` | 自己進化エンジンチューニング |
| `fractal-analyst` | Fractal bypass 判定の監査 |
| `local-safety-gate` | LAEE リスク評価 + 承認モード検証 |

| Skill | 用途 |
|---|---|
| `tdd-morphic` | TDD RED→GREEN→REFACTOR (4 層アーキ) |
| `engine-e2e` | 6 エンジン ライブ E2E |
| `laee-dry-run` | LAEE アクションをプレビュー (承認前) |
| `fractal-analyze` | `task_graph` を検査 |
| `prp-prd` | PRP Product Requirements Prompt |
| `prp-plan` | PRP Planning |
| `prp-implement` | PRP Implementation |
| `memory-compact` | セマンティックメモリ圧縮をトリガー |
| `cost-report` | 月次コストレポート生成 |
| `evolve-insights` | セッション後のインサイト抽出 |

---

## 📋 Spec-Driven Workflow

Complex features should follow: `spec.md` → `plan.md` → `tasks.md`.

```
specs/<feature>/
├── spec.md       # What to build (requirements, user stories, acceptance criteria)
├── plan.md       # How to build (architecture, data model, contracts)
└── tasks.md      # Executable work items ([P] = parallelizable)

.specify/
├── memory/constitution.md    # Non-negotiable principles
└── templates/                # spec/plan/tasks templates
```

Use skills: `/prp-prd` → `/prp-plan` → `/prp-implement`

See [`specs/README.md`](specs/README.md).

---

## 🚨 Known Issues

- OpenHands v0.59 sends `temperature` + `top_p` to Claude API → rejected. Use Gemini or upgrade OH image.
- OpenAI GPT-4o quota insufficient. `o4-mini` works fine.

## 🔒 Safety Summary

- LAEE: 3-tier approval, risk classification 5段階, audit log, undo stack, concurrent limits
- Circuit breaker: 月次予算 95% で API 全停止
- Tool Sandboxing: 全ツールを Docker コンテナで隔離
- Credential Guard: `~/.ssh`, `~/.aws`, `.env` 等は CRITICAL

Full safety model: [`docs/LAEE.md`](docs/LAEE.md)

---

*Morphic-Agent — Intelligence that grows with every task.*
*"The boat on the rising tide of model progress, not the pillar stuck to the seabed." — Manus*
