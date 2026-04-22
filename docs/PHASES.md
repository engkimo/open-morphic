# Development Phases (v0.5)

## Phase 1: Foundation (Week 1-2) — まず動かす
- [x] Ollama + LiteLLM ローカル接続テスト ($0で動くことを確認)
- [x] コアタスクグラフエンジン (LangGraph)
- [x] **LAEE基盤: LocalExecutor + ApprovalEngine + AuditLog** ★v0.4
- [x] **LAEE shell/fs/system ツール実装** ★v0.4
- [x] KVキャッシュ最適化基盤 (安定プレフィックス・append-only)
- [x] todo.md 自動管理
- [x] コスト追跡 (LiteLLM callbacks)
- [x] 基本UI (タスクリスト + コスト表示)
- [x] mem0 インテグレーション (Semantic Memory の最小実装)

## Phase 2: Parallel & Planning (Week 3-4)
- [x] 並列実行エンジン
- [x] Interactive Planning (Devin式)
- [x] バックグラウンド計画エージェント (Windsurf式)
- [x] ツールマスキング状態機械
- [x] React Flow グラフビジュアライザー
- [x] **LAEE browser/dev/gui/cron ツール実装** ★v0.4
- [x] **LAEE UndoManager + リスク評価エンジン** ★v0.4

## Phase 3: Context Bridge & Semantic Memory (Week 5-6) ★v0.3拡張
- [x] クロスプラットフォームコンテキストブリッジ
- [x] MCP Server 実装
- [ ] Chrome Extension (コンテキスト自動付与)
- [x] SemanticFingerprint (LSH) 実装
- [x] ContextZipper (クエリ適応型圧縮)
- [ ] ForgettingCurve + DeltaEncoder 実装
- [ ] L1 → L4 Memory Hierarchy 完全実装

## Phase 4: Agent CLI Orchestration (Week 7-8) ★v0.3 NEW
- [x] AgentEngine 共通インターフェース定義
- [x] OpenHands Driver (REST + WebSocket)
- [x] Claude Code SDK Driver (headless + 並列)
- [x] Gemini CLI + ADK Driver (Sequential/Parallel/Loop)
- [x] OpenAI Codex CLI Driver (exec + MCP server mode)
- [x] AgentCLIRouter (タスク特性 → エンジン選択)
- [ ] AGENTS.md / llms-full.txt 知識ファイル管理

## Phase 5: Marketplace & Tools (Week 9-10)
- [ ] 自律ツール発見・インストール
- [x] MCPツール統合
- [ ] マーケットプレイスUI
- [ ] Ollama モデル管理UI

## Phase 6: Self-Evolution (Week 11-12)
- [x] 実行履歴収集・分析
- [ ] プロンプト自動進化 (Level 2)
- [ ] モデル選択基準の自動更新
- [ ] エージェントエンジン選択の自動最適化
- [ ] 進化レポートダッシュボード

## Phase 7: Unified Cognitive Layer + Meta-Orchestration v2 (Week 13-16)
> 全AIエージェントの記憶・タスク状態・判断を共有する「統合認知層」。A2Aを超え、共有認知へ。
- [ ] UCL ドメインモデル (SharedTaskState, Decision, AgentAction, CognitiveMemoryType)
- [ ] Context Adapters (エンジンごとの双方向コンテキスト変換)
- [ ] Insight Extraction Pipeline (実行後自動知識抽出)
- [ ] Agent Affinity Scoring
- [ ] Task Handoff (判断・成果物・ブロッカー含む完全引き継ぎ)
- [ ] Conflict Resolver (エージェント間の矛盾検出・信頼度重み付き解決)
- [ ] UCL API + CLI + UI
- [ ] クロスエンジン統合テスト + コンテキスト継続性ベンチマーク

---

## Success Metrics (v0.5)

| 指標 | Phase 1 目標 | 3ヶ月目標 | 現在 |
|---|---|---|---|
| タスク成功率 | 70% | 90%+ | 90%+ |
| ローカルLLM 使用率 | 60% | 85%+ | — |
| 平均コスト/タスク | $0.30 | $0.05 | $0.024 (Round 17) |
| KVキャッシュヒット率 | 70% | 90%+ | — |
| コンテキスト復元精度 | 80% | 95% | — |
| 進化による改善率 | N/A | +15%/月 | — |
| Memory 圧縮率 | N/A | 10,000→500 tokens (98%) | — |
| コンテキスト引継ぎ精度 | N/A | 95%+ (マルチAI間) | — |
| Agent CLI 使用率 (OpenHands) | N/A | 長時間タスクの40%+ | — |
| LAEE ツール実行成功率 | 80% | 95%+ | — |
| LAEE Undo 成功率 | 90% | 98%+ | — |
| LAEE Audit Log 完全性 | 100% | 100% | — |
