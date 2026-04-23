# CLAUDE.md Changelog

## v0.5.2 → v0.6.0 (2026-04-22) — **Documentation & Agent Skills Rework**

- **[ARCH/TD-182]** `StrategyRepository` 抽象ポートを `domain/ports/` に追加し、`UpdateStrategyUseCase` を具象 `StrategyStore` から切り離し。Constitution principle 2 (Clean Architecture) 違反を解消。SDD pilot 1 件目 (spec → plan → tasks 完走、24 タスク TDD 実行)
- **[STRUCTURE]** CLAUDE.md を 95KB → ~10KB に圧縮。詳細を `docs/` 配下の peer file に分割 (`VISION.md`, `CONTEXT_ENGINEERING.md`, `AGENT_CLI.md`, `SEMANTIC_MEMORY.md`, `LAEE.md`, `UCL.md`, `PHASES.md`, `TECH_STACK.md`, `UI_DESIGN.md`, `ENV_VARS.md`, `REFERENCES.md`)
- **[NEW]** `AGENTS.md` (telegraph-style root rules, OpenClaw-pattern) — Codex CLI / 他 AGENTS.md-aware エージェント向け
- **[NEW]** `.claude/` 配下に subagents / skills / commands / rules スキャフォールド
- **[NEW]** 10 custom subagents: `engine-tester`, `laee-auditor`, `context-engineer`, `spec-writer`, `cost-guardian`, `memory-archaeologist`, `morphic-pr-reviewer`, `harness-optimizer`, `fractal-analyst`, `local-safety-gate`
- **[NEW]** 10 custom skills: `tdd-morphic`, `engine-e2e`, `laee-dry-run`, `fractal-analyze`, `prp-prd`, `prp-plan`, `prp-implement`, `memory-compact`, `cost-report`, `evolve-insights`
- **[NEW]** Spec-driven development scaffolding: `.specify/{memory,templates}/`, `specs/README.md`
- **[INSPIRED]** `affaan-m/everything-claude-code` (thin CLAUDE.md + peer files, skill-first pattern, meta-agents)
- **[INSPIRED]** `openclaw/openclaw` (telegraph AGENTS.md, two-phase approval decoupling, plugin-ize capabilities)
- **[INSPIRED]** `github/spec-kit` (spec.md → plan.md → tasks.md three-phase workflow)

---

## v0.4 → v0.5

- **[NEW]** Unified Cognitive Layer (UCL): 全エージェントの記憶・タスク状態・判断を統合する共有認知層
- **[NEW]** SharedTaskState: 判断 (Decision)・成果物・ブロッカー・エージェント行動履歴をクロスエージェント共有
- **[NEW]** Context Adapters: エンジンごとの双方向コンテキスト変換 (inject/extract)。OSのデバイスドライバ的設計
- **[NEW]** Insight Extraction Pipeline: 実行後自動知識抽出 → UCL メモリ + タスク状態更新
- **[NEW]** Agent Affinity Scoring: コンテキスト適合度でルーティング
- **[NEW]** Task Handoff: Agent A → Agent B、判断・成果物・ブロッカー含む完全引き継ぎ
- **[NEW]** Conflict Resolver: エージェント間の矛盾検出・信頼度重み付き解決
- **[UPDATE]** Phase 7 を全面再設計: A2A & Scale → Unified Cognitive Layer + Meta-Orchestration v2
- **[UPDATE]** 差別化軸追加: v0.5 共有認知 (他フレームワークにない独自性)

## v0.3 → v0.4

- **[NEW]** Local Autonomous Execution Engine (LAEE): ローカルPC直接操作。shell/fs/browser/gui/dev/cron 6カテゴリ・40+ツール
- **[NEW]** 3-Tier Approval Mode: full-auto / confirm-destructive / confirm-all でユーザー自己責任制御
- **[NEW]** Risk Assessment Engine: 全アクションを5段階 (SAFE → CRITICAL) で自動評価
- **[NEW]** Audit Trail: `.morphic/audit_log.jsonl` 全操作不変ログ
- **[NEW]** Undo Stack: 可逆操作の undo 機能
- **[UPDATE]** BUILT_IN_TOOLS: LAEE 40+ツールを追加
- **[UPDATE]** Tech Stack: Playwright, watchdog, APScheduler, psutil追加

## v0.2 → v0.3

- **[NEW]** AI Agent CLI Orchestration: OpenHands / Claude Code SDK / Gemini CLI+ADK / OpenAI Codex CLI をメタオーケストレーション
- **[NEW]** AgentCLIRouter: タスク特性 × コスト × 可用性で最適エンジンを選択
- **[NEW]** Semantic Memory Hierarchy: L1 → L4 階層 + LSH Semantic Fingerprint
- **[NEW]** ContextZipper: クエリ適応型圧縮 (10,000 → 500 トークン)
- **[NEW]** ForgettingCurve + DeltaEncoder: エビングハウス忘却 + Git方式差分
- **[UPDATE]** 競合差別化: v0.3 メタオーケストレーター軸を追加

## v0.1 → v0.2

- Ollama/ローカルLLM 統合 (vibe-local 分析結果に基づく)
- Manus 文脈工学 5原則の完全組み込み
- Cursor 並列実行鉄則 (DEFAULT TO PARALLEL)
- Windsurf: バックグラウンド計画エージェント + .windsurfrules 相当
- Devin 2.0: Interactive Planning + 自己評価スコア
- KV キャッシュ設計 (最大10倍コスト削減)
- ツール命名規則でマスキング制御を簡易化
- ダーク・シックUI テーマ詳細定義
