# Morphic-Agent 競合分析レポート

> 作成日: 2026-03-27
> 方法: 実際にMorphic-Agentを起動・実行し、主要8フレームワークと比較

---

## 1. 実行検証結果 — 何が動き、何が動かないか

### 実際に動作確認したもの

| 機能 | ステータス | 検証方法 | 結果 |
|------|-----------|---------|------|
| **FastAPIサーバー起動** | ✅ 完全動作 | `uvicorn` 起動 | 38 LAEE + 1 MCP = 39ツール登録 |
| **Ollama直接実行** | ✅ 完全動作 | `POST /api/engines/run` | フィボナッチ関数生成、$0、3.5秒 |
| **MCPサーバー接続** | ✅ 完全動作 | 起動ログ | `mcp-server-fetch` 自動接続 |
| **マーケットプレイス検索** | ✅ 完全動作 | `GET /api/marketplace/search` | MCP Registry v0.1リアル検索 |
| **コスト追跡** | ✅ 完全動作 | `GET /api/cost` | local_usage_rate=100%、予算追跡 |
| **APIドキュメント** | ✅ 完全動作 | `/docs` | Swagger UI + 45エンドポイント |
| **プラン作成** | ✅ 完全動作 | `POST /api/tasks` | プラン生成・レビュー・承認フロー |
| **A2A/認知API** | ✅ レスポンスOK | `GET /api/a2a/agents` 等 | 空リスト返却（初期状態として正常） |
| **Unit Tests** | ✅ 全パス | pytest | 2,714テスト、0失敗、10.8秒 |
| **Lint** | ✅ クリーン | ruff check | All checks passed |

### 発見した問題点（実行により判明）

| 問題 | 深刻度 | 詳細 |
|------|--------|------|
| **Plan承認後にタスクが実行されない** | 🔴 Critical | `approve_plan`がCelery無しの場合に`asyncio.create_task()`を呼ばない。タスクが永久にpending |
| **エンジン指定がフォールバック** | 🟡 Major | `claude_code`/`gemini_cli`を指定してもOllamaにフォールバック。CLI未起動時の正常動作だが、ユーザーに不透明 |
| **エンジン実行記録が残らない** | 🟡 Major | evolution/statsが全て0。エンジン実行結果がSharedTaskStateやCostRecordに記録されていない |
| **ポート8000固定前提** | 🟢 Minor | 既存アプリとポート競合。環境変数でのポート指定は設定ファイルにあるが、UIが8000固定 |
| **PG/Redis/Neo4j未接続** | 🟢 Info | Docker Compose未起動のため全InMemory。開発時は問題ないが、永続性なし |

---

## 2. 競合フレームワーク詳細分析

### 2.1 OpenClaw — 338K⭐（史上最速成長OSS）

| 項目 | 内容 |
|------|------|
| **タイプ** | パーソナルAIアシスタント（汎用） |
| **強み** | SOUL.mdで人格定義、ClawHub 13,700+スキル、50+メッセージング統合、音声操作、ローカルファースト |
| **弱み** | **セキュリティ地獄**: CVE 7件+、ClawHub上12-20%が悪意スキル、135,000+インスタンス公開露出 |
| **価格** | 無料（MIT）+ API課金。マネージド$59/月 |
| **本質的違い** | **パーソナルアシスタント** vs **ソフトウェアエンジニアリングフレームワーク**。カテゴリが異なる |

### 2.2 Manus — Meta $2B買収

| 項目 | 内容 |
|------|------|
| **タイプ** | 汎用自律エージェント（クラウド + デスクトップ） |
| **強み** | "My Computer"デスクトップ操作、Context Engineering 5原則の発祥、Manus 1.6 Maxの高精度 |
| **弱み** | クローズドソース、Meta傘下でプライバシー懸念、エコシステム閉鎖的 |
| **価格** | $20/月 |
| **本質的違い** | 単一エージェント製品 vs メタオーケストレーター。Manus「の中で」動くか、Morphicが「Manusを制御する」か |

### 2.3 Devin — コーディング特化エージェント

| 項目 | 内容 |
|------|------|
| **タイプ** | 自律ソフトウェアエンジニア（クラウドサンドボックス） |
| **強み** | Interactive Planning、クラウドIDE、レガシーコード移行、並列Devin |
| **弱み** | **実際の成功率15%**（20タスク中3成功）、曖昧な要件に弱い、エラーのrabbit hole |
| **価格** | $20-$500/月 + ACU |
| **本質的違い** | コーディング専用 vs 汎用フレームワーク。Morphicのエンジンの1つに位置づけ可能 |

### 2.4 Windsurf — IDE統合エージェント

| 項目 | 内容 |
|------|------|
| **タイプ** | IDE内蔵AIアシスタント |
| **強み** | Cascade、バックグラウンド計画、自律メモリ（48時間学習）、Rulebooks |
| **弱み** | IDE内に閉じる、ローカルLLM非対応、マルチエージェント不可 |
| **価格** | 無料-$60/月 |
| **本質的違い** | IDE製品 vs エージェントフレームワーク。カテゴリが異なる |

### 2.5 OpenHands — 65K⭐（SWE-bench 77.6%）

| 項目 | 内容 |
|------|------|
| **タイプ** | OSSコーディングエージェント（Docker沙箱） |
| **強み** | **SWE-bench 77.6%**（業界最高）、V1 SDK再設計、OpenHands Index |
| **弱み** | Docker必須、コーディング専用、メモリ/マーケットプレイスなし |
| **価格** | 無料（MIT）+ API課金 |
| **本質的違い** | Morphicの実行エンジンの1つ。ドライバー実装済み（`openhands_driver.py`） |

### 2.6 Claude Code — Anthropic公式

| 項目 | 内容 |
|------|------|
| **タイプ** | CLIコーディングエージェント |
| **強み** | Auto Mode（2026/3月）、Agent SDK、headless並列、Hooks |
| **弱み** | Claude専用、永続メモリなし、マルチLLM不可 |
| **価格** | $20-$200/月 |
| **本質的違い** | Morphicの実行エンジンの1つ。ドライバー実装済み（`claude_code_driver.py`） |

### 2.7 Gemini CLI — 99K⭐

| 項目 | 内容 |
|------|------|
| **タイプ** | ターミナルエージェント + ADKワークフロー |
| **強み** | **無料で1Mトークンコンテキスト**、ADK (Seq/Par/Loop)、MCP対応 |
| **弱み** | Google依存、永続メモリなし、マーケットプレイスなし |
| **価格** | **無料** (60 req/min, 1,000/day) |
| **本質的違い** | Morphicの実行エンジンの1つ。ドライバー実装済み（`gemini_driver.py`） |

### 2.8 Codex CLI — 68K⭐

| 項目 | 内容 |
|------|------|
| **タイプ** | Rust製ターミナルエージェント |
| **強み** | **MCPサーバーモード**（他エージェントのツールになれる）、AGENTS.md、exec mode |
| **弱み** | OpenAI依存、マルチエージェント実験段階 |
| **価格** | 無料（Apache 2.0）+ API課金 |
| **本質的違い** | Morphicの実行エンジンの1つ。ドライバー実装済み（`codex_driver.py`） |

---

## 3. 機能マトリクス — Morphic-Agent vs 全競合

| 機能 | Morphic | OpenClaw | Manus | Devin | Windsurf | OpenHands | Claude Code | Gemini CLI | Codex CLI |
|------|---------|----------|-------|-------|----------|-----------|-------------|-----------|-----------|
| **マルチLLMルーティング** | ✅ 6エンジン | ✅ 複数対応 | ❌ | ❌ | ❌ | ✅ モデル選択 | ❌ Claude専用 | ❌ Gemini専用 | ❌ OpenAI主体 |
| **Agent CLI統合** | ✅ 6 CLI制御 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **ローカルPC操作(LAEE)** | ✅ 38ツール | ✅ 100+スキル | ✅ My Computer | ❌ クラウド | ❌ IDE内 | ❌ Docker | ✅ Auto Mode | ✅ ツール | ✅ 承認モード |
| **タスクグラフ(DAG)** | ✅ LangGraph | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ ADK | ❌ |
| **セマンティックメモリ** | ✅ L1-L4階層 | ✅ 永続記憶 | ❌ | ❌ | ✅ 自律メモリ | ❌ | ❌ | ❌ | ❌ |
| **自己進化** | ✅ Level 1-4 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **コスト最適化** | ✅ $0優先 | 部分的 | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ 無料枠 | ❌ |
| **MCPサーバー統合** | ✅ クライアント | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ サーバー＆クライアント |
| **マーケットプレイス** | ✅ MCP Registry | ✅ ClawHub | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **A2Aプロトコル** | ✅ 9エンドポイント | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **UCL (統合認知層)** | ✅ 6アダプタ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Interactive Planning** | ✅ プラン→承認 | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Docker沙箱** | 🟡 計画 | ❌ | ❌ | ✅ | ❌ | ✅ | 🟡 Auto Mode | ❌ | ❌ |
| **Web UI** | ✅ Next.js 15 | ✅ Web UI | ✅ Web | ✅ Web IDE | ✅ IDE | ✅ VS Code | ❌ CLI | ❌ CLI | ❌ CLI |
| **メッセージング統合** | ❌ | ✅ 50+アプリ | ❌ | ✅ Slack | ❌ | ❌ | ❌ | ❌ | ❌ |
| **音声インターフェース** | ❌ | ✅ 音声操作 | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **ライセンス** | MIT (予定) | MIT | クローズド | クローズド | クローズド | MIT | クローズド | Apache 2.0 | Apache 2.0 |
| **GitHub Stars** | N/A (private) | 338K | N/A | N/A | N/A | 65K | N/A | 99K | 68K |

---

## 4. Morphic-Agentの明確な優位性

### 4.1 唯一無二の機能（他にない）

1. **メタオーケストレーション**: 6つのAgent CLIを統合制御する唯一のフレームワーク
   - OpenHands, Claude Code, Gemini CLI, Codex CLI, ADK, Ollamaを「エンジン」として使い分け
   - 他は全て「自分だけが動く」設計

2. **UCL (統合認知層)**: 複数AIの記憶・判断・文脈を統合する共有認知
   - SharedTaskState → エンジン間でタスク引き継ぎ
   - 6つのContext Adapter → 各エンジン形式に双方向変換
   - **他フレームワークはエンジン間のコンテキスト断絶を解決していない**

3. **A2Aプロトコル**: エージェント間の公式通信規約
   - REQUEST/RESPONSE/BROADCAST/ACK/ERROR の5メッセージタイプ
   - 自動ルーティング（能力+親和性スコア）
   - **他は上意下達のみ、エージェント間対話は不可能**

4. **自己進化エンジン (Level 1-4)**: 失敗から自律的に学習
   - Level 1: タスク内リアルタイム適応
   - Level 2: セッション間学習（プロンプト改善）
   - Level 3: ツールギャップ検知→自律取得
   - Level 4: プロンプトテンプレート進化（51テスト済み）
   - **他は全て「学習しない」**

5. **Fractal Recursive Engine**: 計画→評価→実行→再評価の再帰ループ
   - Gate ① (Plan Evaluator) + Gate ② (Result Evaluator)
   - N-gram学習マッチで過去の失敗/成功パターンを注入
   - **Devinを除き、他に自己評価ゲートを持つフレームワークはない**

### 4.2 アーキテクチャ的優位

1. **Clean Architecture 4層分離**: Domain(依存ゼロ) → Application → Infrastructure → Interface
   - 26ポート(ABC)による完全な依存性逆転
   - テスト2,714個が10.8秒で実行完了
   - **OpenClawのモノリスや他のフレームワークとは設計品質が異なる**

2. **LOCAL_FIRST設計**: Ollama $0が常にデフォルト
   - 他はAPI課金が前提（例外: Gemini CLIの無料枠）
   - コスト制御: 月次予算、サーキットブレーカー、自動ダウングレード

3. **Context Engineering 5原則を初日から組み込み**:
   - KVキャッシュ最適化、ツールマスキング、FS無限コンテキスト、todo.md注意操作、観察多様性
   - Manusが4回作り直して到達した知見を最初から実装

---

## 5. Morphic-Agentの明確な弱点・不足

### 5.1 致命的な不足（競合に大きく劣る）

| 不足点 | 深刻度 | 競合の状態 | 対策案 |
|--------|--------|-----------|--------|
| **ユーザーベースゼロ** | 🔴 | OpenClaw 338K⭐ | OSSとして公開、コミュニティ構築 |
| **Plan承認→実行が壊れている** | 🔴 | 全競合は動く | `approve_plan`にasyncio.create_task追加 |
| **エンジン直接呼び出しがフォールバック頻発** | 🔴 | 各CLIは直接動く | エラーメッセージ改善、ドライバー診断モード |
| **実行記録が永続化されない** | 🟡 | Devin/Windsurf: 自動記録 | Celery無しでもevolution/statsに記録 |
| **メッセージング統合ゼロ** | 🟡 | OpenClaw: 50+アプリ | Slack/Discord webhookから着手 |
| **音声インターフェースなし** | 🟡 | OpenClaw: Wake Word対応 | Phase 15+で検討 |

### 5.2 構造的な弱点

| 弱点 | 詳細 | 影響 |
|------|------|------|
| **Celery依存** | 非同期タスク実行がCelery/Redis前提。なしだとプラン承認後に実行不可 | 開発体験が悪い |
| **Docker Compose必須** | PG+Redis+Neo4j。InMemory fallbackはあるが永続性なし | 「5分で試せる」体験が不可能 |
| **UIとバックエンドの統合テスト不在** | Next.js UIは存在するがE2Eブラウザテストがない | UI品質が不明 |
| **マーケットプレイスのセキュリティ** | MCP Registryからの取得時、安全性スコアは計算するがサンドボックス実行なし | OpenClawの二の舞の危険 |
| **エンジンドライバーの真の自律実行** | 多くのタスクがOllamaフォールバックで処理され、Claude Code/Geminiの真価を活用していない | メタオーケストレーションの価値が薄い |

### 5.3 体験面の不足

| 不足 | 競合はどうか | 重要度 |
|------|-------------|--------|
| **ワンコマンド起動** | OpenClaw: `docker run`一発、Gemini CLI: `npm -g install` | 🔴 必須 |
| **初回体験のガイド** | Claude Code: `/help`、Devin: Web UI誘導 | 🟡 重要 |
| **プログレス表示** | Devin: リアルタイムUI、Windsurf: ストリーミング | 🟡 重要 |
| **エラー復帰の透明性** | ユーザーにフォールバック理由が不明 | 🟡 重要 |

---

## 6. 機会 — 競合が手薄な領域

### 6.1 OpenClawのセキュリティ問題を逆手に

OpenClawはClawHubの12-20%が悪意スキルという深刻なセキュリティ問題を抱える。
**Morphic-Agentの機会**: MCP Registryベースの検証済みマーケットプレイス + LAEEの5段階リスク評価 + サンドボックス実行で「安全なスキルマーケット」を差別化軸にできる。

### 6.2 Manus Meta買収後の空白

ManusがMeta傘下になったことで、プライバシー重視ユーザーの受け皿が不在。
**Morphic-Agentの機会**: LOCAL_FIRST + OSS + セルフホストで「Manusの思想をOSSで」を訴求。

### 6.3 マルチAIの「記憶断絶」問題

Claude Code、Gemini CLI、Codex CLIを併用するユーザーは増加中だが、コンテキストが断絶。
**Morphic-Agentの機会**: UCL + Context Adapterで「どのAIに聞いても同じ文脈を持つ」体験を提供。これは現在**誰も解決していない**。

### 6.4 エージェントフレームワークの「実行エンジン化」トレンド

Claude Code SDK、Codex MCPサーバーモード、OpenHands SDK — 各エージェントが「統合される前提」で設計を進めている。
**Morphic-Agentの機会**: 彼らが「統合される」設計を進めるなら、「統合する側」のMorphicの価値は自動的に高まる。

---

## 7. 今すぐ修正すべきバグ（実行検証で発見）

### BUG-001: Plan承認後にタスクが実行されない 🔴

**場所**: `interface/api/routes/plans.py:69-73`
**原因**: `approve_plan`がCelery有効時のみ実行をトリガー。Celery無しの場合、タスクは永久にpending
**修正**: `tasks.py`の`_create_and_execute`と同様に`asyncio.create_task(_safe_execute(c, task.id))`を追加

```python
# 現在のコード (L69-73)
if c.settings.celery_enabled:
    from infrastructure.queue.tasks import execute_task_worker
    execute_task_worker.delay(task.id)
return TaskResponse.from_task(task)

# 修正案
if c.settings.celery_enabled:
    from infrastructure.queue.tasks import execute_task_worker
    execute_task_worker.delay(task.id)
else:
    import asyncio
    asyncio.create_task(_safe_execute(c, task.id))
return TaskResponse.from_task(task)
```

### BUG-002: エンジン実行結果が記録されない 🟡

**場所**: `interface/api/routes/engines.py:62-71`
**原因**: `route_to_engine.execute()`の結果がCostRecordやEvolutionStatsに保存されていない
**影響**: evolution/stats、cost/logsに何も蓄積されず、自己進化エンジンのデータソースが空

### BUG-003: エンジンフォールバックの非透明性 🟡

**場所**: エンジンルーティング全体
**症状**: `claude_code`を指定してもOllamaで実行されるが、レスポンスに「フォールバック理由」がない
**修正案**: EngineRunResponseに`fallback_reason`フィールドを追加

---

## 8. 優先アクション（推奨ロードマップ）

### 即座（今スプリント）

1. **BUG-001修正**: Plan承認→実行のCelery無し対応
2. **BUG-002修正**: エンジン実行結果をCostRecord/EvolutionStatsに記録
3. **BUG-003修正**: フォールバック理由の透明化

### 短期（1-2週間）

4. **ワンコマンド起動**: `morphic-agent serve` でDB+サーバー一括起動（SQLite fallback検討）
5. **エンジンドライバー診断**: `morphic-agent doctor` で全エンジンの状態確認・修復提案
6. **README.md作成**: OSS公開に向けたQuickStart（5分で動く体験）

### 中期（1ヶ月）

7. **マーケットプレイスセキュリティ**: MCP Registryからのインストール時にDockerサンドボックス実行
8. **Slack/Discord統合**: Webhook + Bot APIで基本的なメッセージング連携
9. **CLIインタラクティブモード**: `morphic-agent chat` でターミナル内対話

### 長期（3ヶ月）

10. **OSS公開**: GitHub公開、ドキュメント整備、コミュニティ構築
11. **Chrome Extension**: Context Bridge実装（クロスAIコンテキスト共有）
12. **音声インターフェース**: macOS SpeechRecognition + Whisper

---

## 9. 総合評価

### ポジショニングマップ

```
            汎用 ←────────────────────→ コーディング特化
          ↑
    自律度高 │  OpenClaw        Manus      Devin
          │     ☆               ★          ☆
          │
          │  Morphic-Agent ─────────── OpenHands
          │     ★★★                      ★★
          │
          │              Windsurf    Claude Code
          │                ★           ★★
          │
    自律度低 │              Gemini CLI   Codex CLI
          ↓                 ☆            ☆

  ★ = 出荷済み製品  ☆ = 成長中  ★★★ = 最も機能豊富（未公開）
```

### 結論

**Morphic-Agentは技術的に最も野心的なエージェントフレームワーク**。6エンジンオーケストレーション、UCL、A2A、自己進化、Fractal Recursive Engineなど、他のどのフレームワークも持たない機能を2,714テストで裏付けた堅牢な実装として持つ。

しかし、**「動いている」と「使える」の間にギャップがある**:
- Plan承認→実行のバグは致命的（ユーザーの最初の体験が壊れる）
- エンジンフォールバックの頻発は、メタオーケストレーションの価値を薄める
- ワンコマンド起動できないのは、2026年のOSSとして致命的

**3つのバグ修正 + ワンコマンド起動 + README**だけで、「技術的に最強だが触れない」から「触って驚く」に変わる。
これが最も費用対効果の高い投資。

---

*Generated: 2026-03-27 | Method: Live execution + competitor web research + codebase deep analysis*
