# Local Autonomous Execution Engine (LAEE) — v0.4

> **OpenClaw的発想**: エージェントがユーザーのローカルPCを「手足」として直接操作する。
> Docker沙箱ではなく、**ユーザーの実マシン上でリアルタイムにタスクを実行**する。
> 安全性はユーザーの自己責任。3段階の承認モードで制御。

## なぜ必要か

```
OpenHands はDocker沙箱 → 安全だがユーザーのローカル環境を触れない
実際のユースケースの80%は「自分のPCで何かしてほしい」:
  - "brew で〇〇をインストールして環境構築して"
  - "このフォルダの画像を全部リサイズして"
  - "Chrome で〇〇を検索してスプレッドシートにまとめて"
  - "毎朝9時に Slack の未読をサマリーして"

ユーザーが「自己責任で OK」と言えば、full-auto で全自動化可能
```

## 承認モード (Approval Mode)

```python
from enum import Enum

class ApprovalMode(Enum):
    FULL_AUTO = "full-auto"                    # ユーザーが全リスクを受容。確認なし
    CONFIRM_DESTRUCTIVE = "confirm-destructive" # 破壊的操作のみ確認
    CONFIRM_ALL = "confirm-all"                # 全操作を確認

class RiskLevel(Enum):
    SAFE = 0     # 読み取り専用・完全可逆 (ls, cat, grep, screenshot)
    LOW = 1      # ファイル作成・プロセス起動 (mkdir, touch, open)
    MEDIUM = 2   # ファイル変更・パッケージインストール (edit, brew install)
    HIGH = 3     # ファイル削除・プロセス強制終了 (rm, kill -9, config変更)
    CRITICAL = 4 # 再帰削除・システム設定・認証情報アクセス (rm -rf, sudo)

class ApprovalEngine:
    APPROVAL_MATRIX = {
        # ApprovalMode →  SAFE  LOW  MED  HIGH  CRIT
        "full-auto":           [True, True, True, True, True],
        "confirm-destructive": [True, True, True, False, False],
        "confirm-all":         [True, False, False, False, False],
    }

    async def check(self, action: Action, mode: ApprovalMode) -> bool:
        needs_approval = not self.APPROVAL_MATRIX[mode.value][action.risk.value]
        if needs_approval:
            return await self.ask_user(
                action=action.description,
                risk=action.risk.name,
                reversible=action.undo_hint or "N/A",
            )
        return True
```

## ツールカテゴリ

```python
LOCAL_TOOLS = {
    # ── シェル実行 ──
    "shell_exec":        {"risk": "MEDIUM", "desc": "コマンド同期実行"},
    "shell_background":  {"risk": "LOW",    "desc": "バックグラウンドジョブ起動"},
    "shell_stream":      {"risk": "MEDIUM", "desc": "stdout/stderrをリアルタイムストリーム"},
    "shell_pipe":        {"risk": "MEDIUM", "desc": "パイプライン構築・実行"},

    # ── ファイルシステム ──
    "fs_read":           {"risk": "SAFE",   "desc": "ファイル読み取り"},
    "fs_write":          {"risk": "MEDIUM", "desc": "ファイル書き込み"},
    "fs_edit":           {"risk": "MEDIUM", "desc": "部分編集 (sed的)"},
    "fs_delete":         {"risk": "HIGH",   "desc": "ファイル/ディレクトリ削除"},
    "fs_move":           {"risk": "MEDIUM", "desc": "移動・リネーム"},
    "fs_glob":           {"risk": "SAFE",   "desc": "パターン検索"},
    "fs_watch":          {"risk": "LOW",    "desc": "ファイル変更監視 (watchdog)"},
    "fs_tree":           {"risk": "SAFE",   "desc": "ディレクトリ構造表示"},

    # ── ブラウザ自動化 (Playwright) ──
    "browser_navigate":   {"risk": "LOW",    "desc": "URLへ移動"},
    "browser_click":      {"risk": "MEDIUM", "desc": "要素クリック"},
    "browser_type":       {"risk": "MEDIUM", "desc": "テキスト入力"},
    "browser_screenshot": {"risk": "SAFE",   "desc": "スクリーンショット取得"},
    "browser_extract":    {"risk": "SAFE",   "desc": "ページデータ抽出"},
    "browser_pdf":        {"risk": "LOW",    "desc": "ページをPDF保存"},

    # ── システム制御 ──
    "system_process_list":   {"risk": "SAFE",   "desc": "プロセス一覧"},
    "system_process_kill":   {"risk": "HIGH",   "desc": "プロセス終了"},
    "system_service_status": {"risk": "SAFE",   "desc": "サービス状態確認"},
    "system_resource_info":  {"risk": "SAFE",   "desc": "CPU/メモリ/ディスク情報"},
    "system_clipboard_get":  {"risk": "SAFE",   "desc": "クリップボード読み取り"},
    "system_clipboard_set":  {"risk": "LOW",    "desc": "クリップボード書き込み"},
    "system_notify":         {"risk": "LOW",    "desc": "デスクトップ通知"},
    "system_screenshot":     {"risk": "SAFE",   "desc": "画面全体スクリーンショット"},

    # ── 開発ツール ──
    "dev_git":         {"risk": "MEDIUM", "desc": "Git操作 (add/commit/push等)"},
    "dev_docker":      {"risk": "MEDIUM", "desc": "Docker操作"},
    "dev_pkg_install": {"risk": "MEDIUM", "desc": "パッケージインストール (brew/pip/npm)"},
    "dev_pkg_search":  {"risk": "SAFE",   "desc": "パッケージ検索"},
    "dev_env_setup":   {"risk": "MEDIUM", "desc": "開発環境セットアップ"},

    # ── GUI自動化 (macOS) ──
    "gui_applescript":    {"risk": "MEDIUM", "desc": "AppleScript実行"},
    "gui_open_app":       {"risk": "LOW",    "desc": "アプリケーション起動"},
    "gui_screenshot_ocr": {"risk": "SAFE",   "desc": "画面キャプチャ+OCR"},
    "gui_accessibility":  {"risk": "MEDIUM", "desc": "Accessibility APIで要素操作"},

    # ── スケジュール ──
    "cron_schedule":  {"risk": "MEDIUM", "desc": "定期タスク登録"},
    "cron_once":      {"risk": "LOW",    "desc": "ワンショットタイマー"},
    "cron_list":      {"risk": "SAFE",   "desc": "登録済みジョブ一覧"},
    "cron_cancel":    {"risk": "LOW",    "desc": "ジョブキャンセル"},
}
```

## 実行フロー

```python
class LocalExecutor:
    """
    LAEE の中核。LLM が生成したアクション計画をローカルマシンで実行する。
    全アクションは AuditLog に記録。リスク評価→承認→実行→観察の4ステップ。
    """
    def __init__(self, approval_mode: ApprovalMode = ApprovalMode.CONFIRM_DESTRUCTIVE):
        self.approval = ApprovalEngine()
        self.mode = approval_mode
        self.audit = AuditLog()
        self.undo_stack: list[UndoAction] = []

    async def execute(self, action: Action) -> Observation:
        risk = self.assess_risk(action)
        approved = await self.approval.check(action, self.mode)
        if not approved:
            return Observation(status="denied", result="User denied this action")
        if action.reversible:
            self.undo_stack.append(action.create_undo())
        try:
            result = await self.run_tool(action.tool, action.args)
            self.audit.log(action, result, risk)
            return Observation(status="success", result=result)
        except Exception as e:
            self.audit.log(action, str(e), risk, success=False)
            return Observation(status="error", result=str(e))

    async def undo_last(self) -> Observation:
        if not self.undo_stack:
            return Observation(status="error", result="Nothing to undo")
        undo = self.undo_stack.pop()
        return await self.run_tool(undo.tool, undo.args)


class AuditLog:
    """全アクションの不変ログ。セキュリティ・デバッグ・進化学習に使用"""
    LOG_PATH = ".morphic/audit_log.jsonl"

    def log(self, action: Action, result: str, risk: RiskLevel, success: bool = True):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "tool": action.tool,
            "args": action.args,
            "risk": risk.name,
            "success": success,
            "result_summary": result[:500],
            "approval_mode": self.current_mode.value,
        }
        with open(self.LOG_PATH, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

## 設計原則 (OpenClaw からの学び)

1. **Two-Phase Approval with Timeout**: `ExecApprovalRegistration {id, expiresAtMs, finalDecision?}` で非同期承認 (通知・プッシュ)。タイムアウト時は null → 自動拒否
2. **Risk Classification ≠ Approval Transport**: リスク判定 (`risk_assessor`) と承認 UI (`approval_engine`) は別モジュール
3. **Opt-in Dockerfile Sandboxes**: `browser_*` ツールは optional に Playwright-in-Docker モードを持つ
4. **Plugin-ize Each Capability**: `shell_tools.py` / `browser_tools.py` / `gui_tools.py` をマニフェスト経由でプラグイン登録

## Safety Model

```
- 3-Tier Approval: full-auto / confirm-destructive / confirm-all
- Risk Assessment: 全アクションを5段階(SAFE→CRITICAL)で自動評価
- Audit Trail: .morphic/audit_log.jsonl に全操作を不変ログ
- Undo Stack: 可逆操作は undo 可能。rm → ゴミ箱移動で安全削除
- Concurrent Limit: 同時バックグラウンドジョブ数を制限
- Credential Guard: ~/.ssh, ~/.aws, .env 等の読み取りは CRITICAL レベル
- User Responsibility: ユーザーが明示的に full-auto を選択した場合のみ全自動
```

## ユースケース例

```
# ユーザー: "開発環境をセットアップして" (full-auto)
1. shell_exec:       brew install python@3.12 node docker
2. dev_pkg_install:  pip install uv && uv sync
3. shell_exec:       docker compose up -d
4. dev_git:          git clone ... && git checkout -b feature/xxx
5. shell_exec:       uv run pytest   # 動作確認
6. system_notify:    "開発環境セットアップ完了 ✓"

# ユーザー: "毎朝9時にSlackの未読をサマリーして"
1. browser_navigate:  slack.com/api/conversations.history
2. browser_extract:   未読メッセージ取得
3. LLM:               サマリー生成
4. system_clipboard_set: サマリーをクリップボードに
5. system_notify:     "Slackサマリー準備完了"
6. cron_schedule:     上記を毎朝9:00に繰り返し

# ユーザー: "このフォルダの画像を全部リサイズして"
1. fs_glob:       ./images/**/*.{png,jpg,jpeg}
2. shell_exec:    magick mogrify -resize 800x600 (並列)
3. fs_tree:       処理結果確認
4. system_notify: "42枚の画像をリサイズ完了"
```
