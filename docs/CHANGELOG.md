# CLAUDE.md Changelog

## Unreleased

- **[FEAT/CHAT-CLI]** Phase 20 manual hook run CLIをTDDで追加: `morphic hooks run <hook_type>` を追加し、hook execution eventsを `.morphic/sessions/*.jsonl` に永続化。`--json` はsession id / hook execution mode / diagnostics / events / results / summaryを返す。defaultはsafeなno-opのまま維持し、`MORPHIC_CHAT_HOOK_EXECUTION=shell` opt-in時はLAEE `shell_exec` 経由で実行しaudit logへ記録されることを検証。
- **[FEAT/CHAT-CLI]** Phase 19 hook execution mode wiringをTDDで追加: Chat CLI hook executor factoryを追加し、defaultはsafeな `NoopHookExecutor`、`MORPHIC_CHAT_HOOK_EXECUTION=shell` の明示opt-in時のみ `ShellHookExecutor` を選択するようにした。shell modeはLAEE local executor settingsからapproval/audit/undo設定を引き継ぐ。未知modeはvalidation errorにし、`morphic chat --doctor --json` に `hook_execution_mode` を出力。
- **[FEAT/CHAT-CLI]** Phase 18 shell-backed hook executorをTDDで追加: `ShellHookExecutor` が hook command を LAEE `LocalExecutorPort` の `shell_exec` actionへ変換し、workspace root `cwd` と timeout を付与して実行する。LAEE successはhook successへ、DENIED/ERRORはfailed hook resultへ正規化。`ExecuteChatToolUseCase` は injected `pre_tool` hook runner がfailed resultを返した場合、tool本体を実行せず停止する。post-tool hook failureはrollbackせずledger dataとして残す。
- **[FEAT/CHAT-CLI]** Phase 17 hook runner wiringをTDDで追加: safe wiring用の `NoopHookExecutor` adapterを追加し、`ExecuteChatToolUseCase` がoptional `ExecuteChatHookUseCase` を受け取れるようにした。hook runner注入時は `pre_tool` hook execution eventsをtool execution前に、`post_tool` hook execution eventsをexecution後にsession ledgerへ記録。既存のhook planner注入時のplanning挙動は維持し、real shell-backed hook executionは引き続きdeferred。
- **[FEAT/CHAT-CLI]** Phase 16 hook execution use caseをTDDで追加: `HookExecutionRequest` / `HookExecutionResult` と `HookExecutorPort` を追加し、`ExecuteChatHookUseCase` が enabled hook をport越しに実行して `hook_execution_requested` / `hook_execution_completed` eventsをsession ledgerへ記録。disabled hookはexecutorを呼ばず `hook_execution_skipped` として記録し、FAIL diagnosticsがある場合は実行を拒否。shell-backed hook executorとapproval/risk wiringは引き続きdeferred。
- **[FEAT/CHAT-CLI]** Phase 15 hook planningをtool harnessへ接続: `ExecuteChatToolUseCase` がoptional `PlanChatHooksUseCase` を受け取り、`pre_tool` hook plan eventsをtool execution前に、`post_tool` hook plan eventsをexecution後にsession ledgerへ記録。hook planner未注入時の既存tool execution挙動は維持し、actual hook command executionは引き続きdeferred。
- **[FEAT/CHAT-CLI]** Phase 14 hook execution planningをTDDで追加: `.morphic/hooks/*.json` のvalidated metadataを `HookRegistryPort` 経由で取得し、`PlanChatHooksUseCase` が `hook_execution_planned` / `hook_execution_skipped` eventsをsession ledgerへ記録。FAIL diagnosticsがある場合はplanningを拒否し、actual shell command executionは未実装のままdeferred。
- **[FEAT/CHAT-CLI]** Phase 13 hook diagnosticsをTDDで追加: `.morphic/hooks/*.json` を実行せずread-only validationし、hook type / command / enabled flag / secret-path risk を診断する `morphic doctor hooks` と `morphic doctor hooks --json` を追加。Invalid hooksはisolated reportされ、FAILのみexit 1、WARNはexit 0。
- **[FIX/CHAT-CLI]** Phase 12 routed council diagnosticsをTDDで追加: `--planner-engine` / `--critic-engine` / `--leader-engine` の未知engine idをlocal fallbackで隠さず、valid engine一覧付きの user-facing diagnostic と exit code 2 を返すよう修正。
- **[FEAT/CHAT-CLI]** Phase 11 routed council role preferencesをTDDで追加: `RouteChatCouncilRuntime` が planner/critic/leader ごとの preferred engine を `RouteToEngineUseCase.execute(preferred_engine=...)` に渡せるようにし、`morphic chat` / `morphic code` に `--planner-engine` `--critic-engine` `--leader-engine` を追加。Unit testsはfake route/factoryのみで外部CLI/DBを呼ばない。
- **[FEAT/CHAT-CLI]** Phase 10 route council opt-inをTDDで追加: `morphic chat --route-council` と `morphic code --route-council` を追加し、明示flagまたは `MORPHIC_CHAT_ROUTE_COUNCIL=1` のときだけ route-backed council runtime を使うよう整理。defaultはlocal deterministic councilのまま維持し、unit testsはfake runtime injectionで外部CLI/DBを呼ばないことを固定。
- **[FEAT/CHAT-CLI]** Phase 9 route-backed council runtimeをTDDで追加: `RouteChatCouncilRuntime` が既存 `RouteToEngineUseCase` 経由で planner/critic/leader role prompt を実行し、`CouncilTurn`/`CouncilDecision` へ正規化。route失敗・空出力・例外時は `LocalChatCouncilRuntime` へfallback。Chat CLIのlive route council実行はunit/通常利用で外部CLIを誤起動しないよう `MORPHIC_CHAT_ROUTE_COUNCIL=1` で明示opt-in。
- **[FEAT/CHAT-CLI]** Phase 8 route-backed engine registryをTDDで追加: 既存 `RouteToEngineUseCase` / agent CLI drivers の availability/capabilities を Chat CLI `EngineRegistryPort` へ変換する `RouteEngineRegistry` adapterを追加。`morphic chat --doctor` と Chat REPL `/engines` は live route registry を使えるようにし、container利用不可時は従来の `StaticEngineRegistry` にfallback。
- **[FIX/CHAT-CLI]** `morphic doctor agents --json` の実CLI出力でcontainer初期化ログがJSON前に混入しないよう、JSON diagnostics実行中のみroot loggingを一時停止。Phase 7 manual validationで `morphic chat` `/status` `/context` `/quit`、append-only JSONL、context index、`.claude/`非破壊を確認。
- **[FEAT/CHAT-CLI]** Phase 6 diagnostics/automationをTDDで追加: `morphic context scan`、`morphic context scan --json`、`morphic doctor agents`、`morphic doctor agents --json`。Machine-readable JSONはRich wrappingを避けるため`typer.echo`で出力し、non-interactive commandsはFAILのみexit 1、WARNはexit 0の安定exit codeに統一。
- **[FEAT/CHAT-CLI]** Phase 5 approval/execution harnessをTDDで追加: read-only mutation blocking、diff proposal/tool requested/tool completed/verification result event sequencing、LAEE-compatible `LaeeToolExecutor` adapter、approval prompt renderer。Chat tool executionは`ToolExecutorPort`越しに行い、LAEE `Action`/`Observation`へ変換。
- **[FEAT/CHAT-CLI]** Phase 4 CLI interfaceをTDDで追加: `morphic chat` line-oriented REPL、`morphic code "<goal>"` one-shot、slash command parser、`/help` `/status` `/context` `/engines` `/diff` `/quit`、`morphic chat --doctor --json` diagnostics。Session ledgerは`.morphic/sessions/*.jsonl`へ永続化。
- **[FEAT/CHAT-CLI]** Phase 3 infrastructure adaptersをTDDで追加: append-only JSONL session store、read-only workspace context discovery + `.morphic/context/index.json` writer、deterministic local council runtime、static engine registry skeleton。Unit testsは`tmp_path`に閉じ、既存instruction files非破壊を検証。
- **[FEAT/CHAT-CLI]** Phase 2 application use casesをTDDで追加: start/resume/send message/context discovery/slash command/approval/session summary。Use case層はdomain entities + portsのみへ依存し、session ledger event appendをapplication orchestrationとして固定。
- **[FEAT/CHAT-CLI]** Phase 1 domain layerをTDDで追加: append-only `ChatEvent`、immutable `ChatSession` sequencing、workspace `ContextIndex`、approval request/decision、council role/decision primitives、chat session/context/council/tool executor/engine registry ports。`tests/unit/domain/test_chat_cli_domain.py` と import-boundary test でClean Architecture境界を固定。
- **[SPEC/CHAT-CLI]** Morphic Chat CLI のspec-driven設計を追加: `specs/morphic-chat-cli/{spec,plan,tasks,operational-catalog}.md`。Claude Code / Gemini CLI / Codex CLI 風のterminal chat体験をMorphic独自のmulti-engine council runtimeとcanonical `.morphic/` metadataで統合する方針を定義。`claw-code` は実装供給元ではなく「良いagent CLIが備えるべき運用面の仕様カタログ」として扱うclean-room方針を明記。

---

## v0.6.2 → v0.6.3 (2026-05-22) — **Planner cost work + Goal Classifier Router (SDD pilot #3)**

- **[FEAT/TD-195]** Goal Classifier Router for planner model selection (PR #40, merged 2026-05-21) — `domain/ports/goal_classifier.py` (ABC) + `infrastructure/routing/{llm,local}_goal_classifier.py` (LLM + Ollama impls) + `domain/services/planner_model_router.py`. Per-goal routing of `LLMPlanner` between Sonnet 4.6 and Haiku 4.5, gated by confidence threshold and `MORPHIC_PLANNER_ROUTER` flag (default `disabled`; opt-in `enabled` auto-selects remote Haiku 4.5 when `ANTHROPIC_API_KEY` present, else local qwen3:8b — both share byte-identical SYSTEM_PROMPT per TD-190). `GoalClassified` event published with `sha256(goal)[:16]` privacy hash (frozen VO, hex pattern). Live A/B (3 arms × 10 goals × 3 trials, $0.97): entity_preserved −2.5pt (≤5pt ✓), plan_eval −0.014 (≤0.030 ✓), captured-saving 20.9% on 4/10 Haiku-eligible goals. See `specs/goal-classifier-router/` and `memory/planner_router_ab_2026_05_20.md`. SDD pilot #3 (43 tasks, full TDD, CodeRabbit Major 5件 fixup 含む)
- **[FIX/PLAN-EVAL]** (#39) `plan_evaluator` の JSON 応答が任意ネスト list で包まれていても unwrap して評価できるよう修正
- **[BENCH/PLANNER]** (#38) Haiku 4.5 vs Sonnet 4.6 plan-quality A/B (10 goals × 3 trials)。Haiku 47.6% cost 削減を確認するも entity_preserved −11.4pt / plan_eval −7pt 回帰 → blanket switch せず TD-195 の per-goal router 設計に直結
- **[FIX/PRICING]** (#37) Claude Haiku 4.5 を Anthropic 公開料金 ($1.00 in / $5.00 out per 1M tokens) に修正
- **[FEAT/BENCH]** (#36) Planner cost simulation harness を追加: Sonnet vs Haiku × cache padding 有/無 の 4 セルで cost / cache-hit-rate を見積もり。短プロンプト workload では padding が net-negative である事実を確立
- **[FEAT/CLI/TD-189]** (#35) step 5 — `morphic task show` + `morphic cost task` に per-task `cache_hit_rate` を surface。TD-189 5-step plumbing 完結

---

## v0.6.1 → v0.6.2 (2026-05-15) — **Council Pilot full merge + TD-189 per-task cache_hit_rate + TD-192 fractal-entry latency cut + Haiku 4.5 threshold pinned**

- **[PERF/TD-192]** `OutputRequirementClassifier.classify()` を `FractalBypassClassifier.should_bypass()` 内に折り畳み、fractal-entry の LLM 呼出を **2 → 1** に削減。`BypassDecision` を `(bypass, complexity, output_requirement, reason)` に拡張、`FractalTaskEngine` 側の二重呼出を撤廃。Round 22 live regression (`test_round22_td192_latency.py`, real qwen3:8b) で実測: 2 ゴール × 1 call = 2 total (baseline 4)、artifact ゴール 7.80s, text ゴール 1.08s。TD-191 architectural guard は完全維持
- **[OBSERVABILITY/TD-189]** Per-task `cache_hit_rate` 集計のための plumbing を 4 step で完成: (step 1) `CostRecord.task_id` 追加、(step 2) `CostRepository.get_cache_hit_rate_for_task(task_id)` port メソッド追加、(step 3) `cost_logs.task_id` カラム + PG aggregation SQL、(step 4) `ContextVar` ベースの task_id propagation (request-scoped、async-safe)。**Next:** step 5 = UI/CLI 可視化
- **[FEAT/TD-194]** Council Pilot full merge (#20): 2-engine debate (`CouncilDebatePort` + `EventBusPort`) を `RouteToEngineUseCase` に `MORPHIC_COUNCIL_DEBATE` flag 越しに wiring 完了。SDD pilot 2 件目 (32 tasks, 全 TDD)。LLM-judge resolver, 1 round, 2 candidates。Round 21 live verify: Ollama qwen3:8b + Gemini Flash、決定 `gemini_cli`、4 events 発火、12.50s, $0.00251
- **[FIX/COUNCIL]** Council Pilot post-merge 修正: (#24) `DebateEvent` を `domain/entities/council/` → `domain/value_objects/` に relocate、(#25) `task_state_repo` を port 型で型付け + `update_decisions` 経由で Decision を永続化、(#26) `_match_engine` の substring fallback を overlapping engine name に対して pin する regression test
- **[FIX/CI]** (#22) `uv.lock` を commit して docker build の再現性を確保、(#23) `morphic doctor check` で optional CLI binary 不在を FAIL → WARN にダウングレード (engine drivers は optional のため)
- **[BENCH/CACHE]** (#33) `benchmarks/cache_hit_rate.py` に `--pad-entries N` を追加 (default 160 ≈ 8.4K tokens)。**Haiku 4.5 cache threshold を binary-search で pin: ≈4096 tokens** (4112=miss, 4161=hit)。Sonnet 4.6 ≈2048 (2^11), Haiku 4.5 ≈4096 (2^12) — 共に clean power of 2。documented 1024 minimum は両モデルとも不正確
- **[VERSION]** pyproject 0.6.1 → 0.6.2、`interface/api/main.py` + `tests/unit/test_version_consistency.py` 同期

---

## v0.6.0 → v0.6.1 (2026-05-12) — **Observability + Round 19 fix + KV-cache hardening + live cache baseline**

- **[FEAT/TD-194]** Council Pilot — 2-engine debate (`CouncilDebatePort` + `EventBusPort`) wired into `RouteToEngineUseCase` behind `MORPHIC_COUNCIL_DEBATE` flag (default off). See `specs/council-pilot/` and TD-194.
- **[KV-CACHE/TD-193]** Anthropic prompt cache を実際に発火させる配線を完成。`LiteLLMGateway` に `_maybe_extract_anthropic_system` を追加し、Claude モデルの system message を **top-level `system=` kwarg** に持ち上げて `cache_control: {"type": "ephemeral"}` マーカーを付与。**Why this matters:** LiteLLM 1.81 は `role: "system"` content blocks 内の `cache_control` を silently strip するため、message 経由では発火不可能だった。差分テスト (raw Anthropic SDK / litellm message-form / litellm system-kwarg) で経路を切り分け、kwarg 経由を採用。`benchmarks/cache_hit_rate.py` で実測ベースライン取得 — Sonnet 4.6 / 5 calls で **cache_hit_rate = 0.795** (4/5 hit, ~70%/call コスト削減 $0.0407 → ~$0.012). Empirical: Sonnet 4.6 cache minimum ≈ 2048 tokens (1024 ではない); Haiku 4.5 は 3K でも cache せず (要追跡). 5 新 gateway テスト + ベンチマークスクリプト
- **[KV-CACHE/TD-190]** `LLMPlanner._build_messages` を再設計: direction / nesting_level / candidates_per_node / parent context を **system → user message** に移送。system prompt は byte-identical で全呼び出し共通 (Manus 5原則 stable prefix の遵守)。新 `_SYSTEM_PROMPT` に FORWARD/BACKWARD 定義を組込み、user message は `Direction: FORWARD\nNesting level: N\n...\nGoal: ...` 形式。**結果: TD-188 で計測する cache_hit_rate が伸びる前提条件が成立 (実 LLM 呼出 0)。** 6 新テスト (TestStablePrefix, byte-equality across direction/nesting/context/candidates_per_node + module-constant identity)
- **[SAFETY/TD-191]** Bypass classifier の前に `OutputRequirementClassifier` を移動し、bypass 発火条件に `output_requirement == TEXT` を追加。**結果: file/code/data 出力要求のあるタスク (Round 19 のスライド作成等) が SIMPLE 誤分類で短絡される経路を architectural に閉鎖。** TD-181 (hard timeout, 症状治療) → TD-191 (root cause). Round 19 の元の日本語ゴールを regression test として固定 (6 新テスト). Fail-open: classifier error 時は bypass を許可 (TEXT Q&A の latency 維持). Round 20 live verify (real qwen3:8b, 6/6 PASS in 13s, $0)
- **[OBSERVABILITY/TD-188]** Cache-read tokens を LLM 応答 → CostRecord に通す配線を完成。`LLMResponse.cached_tokens` 追加、LiteLLMGateway が `usage.prompt_tokens_details.cached_tokens` (OpenAI/normalized) と `usage.cache_read_input_tokens` (Anthropic raw) の両方から抽出、CostTracker のハードコード `0` を撤廃。**結果: 安定 prefix 設計の効果が初めて DB に記録されるようになった** (cache_hit_rate 集計は次スプリント)

---

## v0.5.2 → v0.6.0 (2026-04-22) — **Documentation & Agent Skills Rework**

- **[CONSTITUTION/TD-187]** Test-code port-borrowing policy を明文化。`tests/unit/application/` から `infrastructure/` の `InMemory*` adapter (port 実装) を import するのは許可される DI wiring パターン (production source flow ではない)。Audit 8 件全て port-compliant adapter 借用と確認、ファイル移動 0 件
- **[CONSTITUTION/TD-186]** Constitution amendment: 原則 2 に numpy (純粋数学ライブラリ) を明示許可、TYPE_CHECKING 含む `from infrastructure`/`application`/`interface` を `domain/` 全面禁止に明文化。Audit 結果: 3 種の leak grep すべて 0 件
- **[CHORE/TD-185]** Pre-existing ruff debt 解消 (`test_skill_acquisition.py` の F401/F841 ×8、`test_artifact_pipeline.py` の F401/I001)。`ruff check .` が再びクリーンに
- **[ARCH/TD-184]** `EngineCostRecorderPort` (1 method narrow port) を追加し、`RouteToEngineUseCase` を具象 `CostTracker` から切り離し。**結果: `application/` から `from infrastructure` import が完全消滅 (0 件)**
- **[ARCH/TD-183]** `OllamaManagerPort` 抽象ポートを `domain/ports/` に追加し、`ManageOllamaUseCase` を具象 `OllamaManager` から切り離し (TYPE_CHECKING-only でも違反扱い)。`AsyncMock(spec=OllamaManagerPort)` で既存テストを port 強制に upgrade
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
