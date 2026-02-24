# Morphic-Agent Technical Decisions

> 設計判断の根拠を記録する。後から「なぜこうしたか」を追跡可能にする。

---

## TD-001: ストレージ統合 — pgvector + Redis(queue) + Neo4j

**決定日**: 2026-02-24
**ステータス**: Accepted

### 決定

Phase 1 のストレージバックエンドを以下の3つに統合する:

| サービス | 役割 | 選定理由 |
|---|---|---|
| **PostgreSQL 16 + pgvector** | メインDB + ベクトル検索 | リレーショナルデータとベクトル検索を1サービスで。Qdrant不要 |
| **Redis 7** | タスクキュー (Celery broker/backend) | キュー専用。汎用キャッシュには使わない |
| **Neo4j 5 Community** | L3 知識グラフ | エンティティ・関係のグラフ走査に特化。Cypher クエリ、ACID、永続化 |

### 却下した選択肢

| 選択肢 | 却下理由 |
|---|---|
| Qdrant (ベクトルDB) | pgvector で Phase 1 規模は十分。サービス数を減らして運用負荷軽減 |
| Redis を汎用キャッシュにも使用 | 役割肥大化を防ぐ。KV-Cache最適化はLLM側（LiteLLM disk cache）で行う |
| NetworkX (in-memory graph) | 永続化なし。プロセス再起動で消失。Neo4j は永続+クエリ言語あり |
| SQLite | 並行アクセスに弱い。複数ワーカーでの非同期実行に不向き |

### リスクと緩和策

- **pgvector の検索精度**: Phase 1 規模（~100K vectors）では問題なし。Phase 3 で規模拡大時に Qdrant 移行を再評価
- **Neo4j の運用コスト**: Community Edition で$0。Docker Compose で起動のみ
- **Redis 単一障害点**: Phase 1 はローカル開発のみ。本番では Sentinel/Cluster を検討

---

## TD-002: LangGraph を DAG エンジンに採用

**決定日**: 2026-02-24
**ステータス**: Accepted

### 決定

タスクグラフエンジンの基盤に LangGraph を採用する。

### 根拠

- **StateGraph**: 状態管理 + 条件分岐エッジ + チェックポイントを標準提供
- **Human-in-the-Loop**: `interrupt_before` / `interrupt_after` でインタラクティブ計画に直結
- **並列ノード実行**: `Send` API で動的並列タスク生成
- **永続化**: PostgreSQL checkpointer でグラフ状態をDB保存可能

### リスク

- **LangChain エコシステム結合**: LangGraph は LangChain に依存する部分がある
- **緩和策**: `core/task_graph/engine.py` に薄いラッパーを作り、LangGraph API を直接露出させない。将来の差し替えを可能にする

---

## TD-003: mem0 で Semantic Memory を Bootstrap

**決定日**: 2026-02-24
**ステータス**: Accepted (Phase 1 限定)

### 決定

Phase 1 の L2 Semantic Cache は mem0 で実装する。Phase 3 で LSH + ContextZipper に段階移行。

### 根拠

- mem0 は `pip install mem0ai` で即使用可能
- 会話から自動的にファクト抽出 + ベクトルDB保存
- pgvector をバックエンドに指定可能
- 「8割の記憶問題を解決」できる（CLAUDE.md Phase 1 方針）

### 移行パス

```
Phase 1: mem0 (自動抽出 + pgvector)
Phase 3: mem0 + SemanticFingerprint(LSH) + ContextZipper
Phase 3+: カスタム実装で mem0 を置換（必要な場合のみ）
```

---

## TD-004: Ollama + LiteLLM の LOCAL_FIRST アーキテクチャ

**決定日**: 2026-02-24
**ステータス**: Accepted

### 決定

LLM呼び出しは常に Ollama（ローカル）を最優先し、API は予算とタスク複雑度に応じてフォールバック。

### ルーティングロジック

```
1. Ollama が起動中 AND タスクが free tier 対応 → Ollama (コスト: $0)
2. Ollama 非対応 or 品質不足 → LiteLLM で API ルーティング
   - low tier:  Claude Haiku / Gemini Flash
   - medium:    Claude Sonnet / GPT-4o-mini
   - high:      Claude Opus / GPT-4o
3. 予算超過 → 強制 Ollama フォールバック（品質低下を許容）
```

### LiteLLM の役割

- 100+ モデルの統一 API
- `completion()` でモデル名を差し替えるだけで切替可能
- `success_callback` でコスト自動追跡
- `cache={"type": "disk"}` で KV-Cache 最適化

---

## TD-005: Python パッケージ管理に uv を採用

**決定日**: 2026-02-24
**ステータス**: Accepted

### 決定

pip / poetry / pdm ではなく uv を採用する。

### 根拠

- Rust 製で pip 比 10-100x 高速
- lockfile (`uv.lock`) でビルド再現性保証
- `uv run` でvirtualenv自動管理
- `uv add` で依存追加が1コマンド

---

## TD-006: フロントエンド — Next.js 15 + Shadcn/ui + React Flow

**決定日**: 2026-02-24
**ステータス**: Accepted

### 決定

| 技術 | 役割 |
|---|---|
| Next.js 15 (App Router) | フレームワーク。RSC でデータ重いダッシュボードに最適 |
| Shadcn/ui | UIコンポーネント。ダークテーマとの親和性高い |
| React Flow | タスクグラフDAGの可視化 (Phase 2 本格実装) |
| Recharts | コスト推移グラフ |

### UI テーマ

CLAUDE.md の `morphicAgentTheme` に準拠:
- Background: `#0A0A0F` (深宇宙ブラック)
- Accent: `#6366F1` (インディゴ)
- LOCAL FREE バッジ: `#34D399` (ブライトグリーン)

---

## TD-007: モノレポ構成

**決定日**: 2026-02-24
**ステータス**: Accepted

### 決定

Python バックエンド + Next.js フロントエンドを1リポジトリで管理する。

### 構造

```
morphic-agent/
├── core/          # Python バックエンド
├── api/           # FastAPI
├── ui/            # Next.js 15
├── tests/         # Python テスト
├── docs/          # ドキュメント
├── docker-compose.yml
├── pyproject.toml
└── CLAUDE.md
```

### 根拠

- 開発初期は単一チーム。分割リポは管理コストが上回る
- docker-compose で一発起動
- CI/CD パイプラインが1本で済む
- Phase 5+ で規模拡大時にモノレポツール (turborepo等) or リポ分割を再評価

---

## TD-008: Local Autonomous Execution Engine (LAEE) — ローカルPC直接制御

**決定日**: 2026-02-25
**ステータス**: Accepted

### 決定

エージェントがユーザーのローカルPCを直接操作する実行レイヤー (LAEE) を Phase 1 から組み込む。Docker沙箱ではなく、**実マシン上で実行**し、ユーザーの自己責任のもと3段階承認モードで安全性を制御する。

### 根拠

- 実際のユースケースの80%は「自分のPCで何かしてほしい」（環境構築、ファイル操作、ブラウザ自動化等）
- OpenHands のDocker沙箱は安全だがローカル環境を触れない制約がある
- OpenClaw的な「PCを手足にする」能力こそがAIエージェントの真のパワー
- 3段階承認モードでリスクとユーザビリティのバランスを取る

### 設計判断

| 判断項目 | 決定 | 理由 |
|---|---|---|
| 承認モデル | 3-tier (full-auto / confirm-destructive / confirm-all) | Codex CLIの3段階モデルを参考。ユーザーが自分でリスクレベルを選択 |
| リスク評価 | 5段階 (SAFE→CRITICAL) | ツール名+引数パターンから自動判定。sudo, rm -rf 等を検知 |
| ログ形式 | JSONL append-only | Manus原則3準拠。grep/jqで即座にクエリ可能 |
| Undo方式 | スタック型 | 可逆操作のみ。fs_delete はゴミ箱移動→本削除の2段階 |
| ブラウザ | Playwright | Chromium/Firefox/WebKit対応。headless + headed両対応 |
| GUI自動化 | AppleScript (macOS) | ネイティブ。Linux対応時に xdotool を追加 |
| スケジューラ | APScheduler | Pythonネイティブ。cron式 + interval式 + ワンショット |
| プロセス管理 | psutil | クロスプラットフォーム。CPU/メモリ/プロセス情報 |

### 却下した選択肢

| 選択肢 | 却下理由 |
|---|---|
| 全操作Docker沙箱内で実行 | ローカル環境を触れない。ユースケースの80%をカバーできない |
| 承認なし完全自動 | 安全性の担保なし。初心者が rm -rf / を実行するリスク |
| Selenium (ブラウザ) | Playwright の方が高速・安定・API設計が優れている |
| macOS Accessibility APIのみ | AppleScriptの方が記述が簡潔。複雑な操作時にAccessibility APIにフォールバック |

### リスクと緩和策

- **rm -rf等の致命的操作**: CRITICAL リスク自動検知 + confirm-destructive モードでデフォルト確認
- **認証情報漏洩**: ~/.ssh, ~/.aws, .env 等のパスをCRITICALに自動分類
- **ブラウザ操作のセキュリティ**: headlessモードデフォルト。認証サイトへの操作は MEDIUM 以上
- **cron暴走**: 同時ジョブ数上限 (LAEE_MAX_CONCURRENT_SHELLS) で制御
- **ユーザー自己責任の明示**: full-auto モード選択時に明示的な警告を表示
