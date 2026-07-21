# AI Agent CLI Orchestration (v0.3)

> 「どのLLMモデルか」だけでなく「**どのエージェントランタイムか**」を選ぶ時代。
> Morphic-Agent は各CLIエージェントを**専門実行エンジン**として統合するメタオーケストレーターになる。

## なぜこれが重要か

従来のマルチLLMルーターは「モデルを選ぶ」だけだった。しかし2025-2026年には、各AIプロバイダーが独自のエージェント実行環境を持ち、それぞれが異なる強みを持つ「実行エンジン」として成熟した。

```
問題: Claude.ai / ChatGPT / Cursor / Gemini — コンテキストが断絶
      毎回コピペ、再説明のコストが膨大

解決: Morphic-Agent が全エージェントの「記憶のハブ」兼「指揮官」になる
      どのエンジンで実行しても、同じコンテキストを持つ状態を実現
```

## 各Agent CLIの特性分析

| エンジン | 強み | 弱み | 最適タスク |
|---|---|---|---|
| **OpenHands** | Docker沙箱, SWE-bench 72%, multi-agent delegation | セットアップ重い | 長時間ソフトウェア開発 |
| **Claude Code SDK** | Anthropic最高品質推論, headless API, PTC並列 | API課金 | アーキテクチャ設計・複雑推論 |
| **Gemini CLI + ADK** | 2Mトークン長文脈, Sequential/Parallel/Loop agents | Google依存 | ドキュメント分析・最新情報 |
| **OpenAI Codex CLI** | Rust製高速, MCP serverモード, AGENTS.md | ChatGPT依存 | 高速コード生成・CI/CDワーカー |
| **Ollama (local)** | $0運用, プライバシー完全保護 | 品質・速度の限界 | 反復タスク・ドラフト生成 |

---

## OpenHands 統合

```python
# OpenHands: Docker沙箱で長時間自律実行
# SWE-bench 72% (Claude Sonnet 4.5使用)
# AgentDelegateActionで子エージェントに委任可能

class OpenHandsDriver:
    """
    OpenHands SDK/REST API ラッパー
    - 沙箱Docker環境でコード実行
    - AgentDelegateAction でサブエージェント委任
    - REST + WebSocket でリアルタイム監視
    """
    def __init__(self):
        self.base_url = "http://localhost:3000"  # OpenHands local

    async def run_task(
        self,
        task: str,
        model: str = "claude-sonnet-4-6",
        max_iterations: int = 50,
        sandbox: bool = True
    ) -> TaskResult:
        session = await self.create_session(model=model)
        async for event in self.stream_events(session.id, task):
            if event.type == "agent_message":
                yield AgentProgress(message=event.content)
            elif event.type == "action":
                yield ActionEvent(tool=event.tool, args=event.args)
            elif event.type == "observation":
                yield ObservationEvent(result=event.result)
            elif event.type == "finish":
                return TaskResult(success=event.success, artifacts=event.artifacts)

    async def delegate_to_specialist(self, subtask: str, specialist_agent: str = "CodeAct"):
        """AgentDelegateAction: 専門エージェントに委任"""
        return await self.send_delegate_action(subtask, specialist_agent)


# セットアップ
# docker run -it --rm -p 3000:3000 \
#   -e LLM_API_KEY=$ANTHROPIC_API_KEY \
#   -e LLM_MODEL="claude-sonnet-4-6" \
#   ghcr.io/all-hands-ai/openhands:latest
```

**OpenHands V0 → V1 アーキテクチャ進化の4原則:**
1. **Stateless + Event-Sourced**: 状態はイベントログで復元可能
2. **Opt-in Sandboxing**: ローカル実行とDockerを選択的に使い分け
3. **Immutable Config**: セッション開始後に設定変更しない
4. **Composable SDK**: agent/tools/workspace/serverを分離したパッケージ構成

→ Morphic-Agentへの適用: event-sourceアーキテクチャを参考にAgentStateを設計

---

## Claude Code SDK 統合

```python
# Claude Code: Anthropic本命エージェントエンジン
# headlessモードで完全プログラマブル制御
# Programmatic Tool Calling (PTC) で並列ツール実行

class ClaudeCodeDriver:
    async def run_headless(
        self,
        prompt: str,
        session_id: str = None,
        allowed_tools: list[str] = None,
        output_format: str = "json"
    ) -> ClaudeCodeResult:
        cmd = ["claude", "-p", prompt, f"--output-format={output_format}"]
        if session_id:
            cmd += ["--session-id", session_id]
        if allowed_tools:
            cmd += ["--allowedTools", ",".join(allowed_tools)]
        result = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE)
        stdout, _ = await result.communicate()
        return ClaudeCodeResult.from_json(stdout)

    async def run_parallel_workers(self, tasks: list[dict]) -> list[ClaudeCodeResult]:
        """複数 Claude Code インスタンスを並列起動"""
        coroutines = [
            self.run_headless(
                prompt=task["prompt"],
                session_id=f"worker-{i}",
                allowed_tools=task.get("tools", ["Bash", "Read", "Write"])
            )
            for i, task in enumerate(tasks)
        ]
        return await asyncio.gather(*coroutines)
```

### Programmatic Tool Calling (PTC)
```python
# PTC: Claudeがコードを書いてツールを並列オーケストレーション
# 通常の tool_use: 1ツール呼び出し = 1 API往復 × N回
# PTC: Claude が code_execution で Python を書き、内部で 50 ツール並列呼び出し → 結果だけをコンテキストに返す

response = client.beta.messages.create(
    model="claude-sonnet-4-6",
    betas=["advanced-tool-use-2025-11-20"],
    max_tokens=4096,
    messages=[{"role": "user", "content": "50サーバーの死活監視を実行"}],
    tools=[
        {"type": "code_execution_20250825", "name": "code_execution"},
        {"type": "function", "name": "check_server_status", ...}
    ]
)
# → Claude が asyncio.gather で 50 並列実行する Python を書く
# → コンテキストには最終サマリーのみ (50ツール分の中間データなし)
# → KVキャッシュへの影響を最小化
```

---

## Gemini CLI + ADK 統合

```python
# Gemini CLI: 2Mトークン長文脈 + Grounding (最新情報)
# Google ADK: Sequential/Parallel/Loop agents + Vertex AI

class GeminiCLIDriver:
    async def analyze_large_context(self, content: str, query: str, use_grounding: bool = False) -> str:
        """Gemini の 2M トークン窓を活用した大規模コンテキスト分析"""
        cmd = ["gemini", "-p", f"{query}\n\nContext:\n{content}"]
        if use_grounding:
            cmd += ["--grounding"]
        result = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE)
        stdout, _ = await result.communicate()
        return stdout.decode()

    def build_adk_workflow(self) -> SequentialAgent:
        parallel_fetcher = ParallelAgent(
            name="info_fetcher",
            agents=[
                LlmAgent(name="flight_agent", model="gemini-2.5-flash"),
                LlmAgent(name="hotel_agent", model="gemini-2.5-flash"),
            ]
        )
        return SequentialAgent(
            name="travel_planner",
            agents=[
                LlmAgent(name="sightseeing_agent", ...),
                parallel_fetcher,
                LlmAgent(name="summary_agent", ...),
                LlmAgent(name="reviewer_agent", ...),
            ]
        )
```

### ADKの重要設計パターン
```
SequentialAgent  → 決定論的パイプライン (出力が予測可能)
ParallelAgent    → 独立タスクの同時実行 (Cursor 原則と一致)
LoopAgent        → 品質基準を満たすまで反復 (自己改善ループ)
LlmAgent.transfer → 動的ルーティング (次のエージェントを LLM が判断)

⚠️ 落とし穴: 単純に LlmAgent をネストすると「良き受付係、悪きPM」問題
→ 最初のサブエージェントに制御が移ったら、親エージェントは文脈を失う
→ SequentialAgent で明示的に制御フローを設計することが重要
```

---

## OpenAI Codex CLI 統合

```python
# OpenAI Codex CLI: Rust製オープンソース
# MCP serverモードで「別エージェントのツール」として使える
# AGENTS.md でリポジトリ固有コンテキストを注入

class CodexCLIDriver:
    async def run_exec(
        self,
        prompt: str,
        approval_mode: str = "on-request",  # never | on-request | full-auto
        model: str = "gpt-5-codex",
        use_oss: bool = False
    ) -> CodexResult:
        cmd = ["codex", "exec", prompt,
               f"--approval-mode={approval_mode}",
               f"--model={model}"]
        if use_oss:
            cmd += ["--oss"]  # Ollama 互換ローカルモデルへ
        result = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE)
        stdout, _ = await result.communicate()
        return CodexResult.parse(stdout)

    async def start_as_mcp_server(self) -> subprocess.Popen:
        """Codex を MCP サーバーとして起動"""
        return subprocess.Popen(["codex", "mcp", "stdio"],
                                stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE)
```

`AGENTS.md` はリポジトリ固有の永続コンテキスト。`~/.codex/config.toml` や `AGENTS.md` に書くと、Codex が起動時に自動でプロジェクト知識を読み込む。Morphic-Agent の `CLAUDE.md` と同様の役割。

---

## Same-task comparative evidence

Morphicの優位性は主観的な総合点ではなく、同一課題・同一workspace revision・
同一verification checks・同一反復数で比較する。記録済み試行は次で評価する。

```bash
morphic benchmark agent-cli \
  --manifest benchmark-manifest.json \
  --results benchmark-results.json

# CI artifact向けのstable JSON
morphic benchmark agent-cli \
  --manifest benchmark-manifest.json \
  --results benchmark-results.json \
  --json
```

manifestは3 arms (`codex_cli`, `claude_code`, `morphic_control`)を必須とし、taskに
`id`, `goal`, `workspace_revision`, `checks`, `handoff_assertions`を宣言する。
resultsは各arm × trialをexactly once記録し、completion、accepted patch、通過した
checks/handoff assertions、elapsed time、cost、human interventions、recoveryを持つ。

評価器は以下をarm別に算出し、metricごとのleaderを示す。

- completion rate / accepted patch rate
- verification rate（宣言済みchecksから算出）
- median elapsed seconds / mean cost / mean human interventions
- recovery rate
- context-handoff fidelity（宣言済みhandoff assertionsから算出）

恣意的なweightを避けるためcomposite scoreは作らない。出力にはtimestampを含めず、
JSON keyをsortして同じ入力からbyte-stableなartifactを作る。このコマンドはファイルを
読むだけでnative engineやpaid APIを起動しない。将来のlive recorderはcost capを伴う
別のexplicit opt-inとして追加する。

### Isolated trial recorder

Phase 41のrecorderはdefaultでread-only planだけを返す。manifestとrecorder configを
検証し、trial count、command fingerprints、設定上の最大費用見積りを出すが、agent、
Git worktree、verification commandは起動しない。

```bash
# Read-only plan. No worktree or agent process is created.
morphic benchmark agent-cli-record \
  --manifest benchmark-manifest.json \
  --config recorder-config.json \
  --json

# Explicit live execution. worktree root must be outside the source repository.
morphic benchmark agent-cli-record \
  --manifest benchmark-manifest.json \
  --config recorder-config.json \
  --source-root . \
  --worktree-root ../morphic-benchmark-worktrees \
  --evidence benchmark-evidence.json \
  --execute \
  --acknowledge-paid \
  --cost-cap-usd 3.00 \
  --json
```

recorder configは3 armの`arm_commands`と`estimated_cost_usd_per_trial`、manifestと
exact matchする`check_commands` / `handoff_commands`、1 commandあたりの
`timeout_seconds`を持つ。argvは配列で指定し、`{goal}`, `{workspace}`, `{arm}`,
`{trial}`を使用できる。shell展開は行わない。

実行には`--execute`、`--acknowledge-paid`、全trialの最大見積りを覆う
`--cost-cap-usd`がすべて必要。各arm/trialはpinned revisionの別detached worktreeで
実行され、正常・失敗・例外を問わずcleanupする。evidenceはargv/stdout/stderrの
SHA-256、byte数、exit code、timeout、elapsed time、check/assertion結果だけを保存し、
raw prompt/outputは保存しない。既存evidenceは上書きしない。

このcost capは設定見積りに対する事前authorization gateであり、provider請求額を
process内でhard-stopするものではない。実費とaccepted-patch判定は
`pending_adjudication`として残す。provider receipt parserとreview adjudicatorが
揃うまでは、recorder evidenceをPhase 40の最終comparison resultへ自動変換しない。

### Receipt normalization and adjudication

Phase 42ではrecorderがagent stdoutを保持している瞬間だけreceiptを解析し、raw出力を
捨てる前に以下のnormalized fieldsへ変換する。

- provider / success / model
- non-negative token usage
- cost USD / cost source
- parse error count

CodexはJSONL usageと`model_hints.codex_cli`から既存のcost calculatorで再計算し、
receipt costが一致しない場合は拒否する。Claudeはstream-json resultの
`total_cost_usd`をprovider-reported valueとして保持する。Morphic-controlled commandは
最後に次のcanonical envelopeを出力する必要がある。

```json
{
  "type": "morphic_benchmark_receipt",
  "success": true,
  "model": "o4-mini",
  "usage": {"input_tokens": 120, "output_tokens": 30},
  "cost_usd": 0.02
}
```

全trialでreceiptが得られた場合だけevidenceの`cost_collection`が
`normalized_receipts`になる。欠損を0ドルとして補完しない。

independent review bundleは各arm/trialについてagent argv fingerprint、accepted patch、
human interventions、recovery、reviewer id、review artifact SHA-256を記録する。次のoffline
commandがmachine evidenceとreview bundleを結合する。

```bash
morphic benchmark agent-cli-finalize \
  --manifest benchmark-manifest.json \
  --evidence benchmark-evidence.json \
  --reviews benchmark-reviews.json \
  --output benchmark-results.json \
  --json

morphic benchmark agent-cli \
  --manifest benchmark-manifest.json \
  --results benchmark-results.json \
  --json
```

finalizerは完全なarm/trial matrix、task/revision identity、provider、argv fingerprint、
check/handoff evidence、receipt parse status、review consistency、actual-cost totalを検証する。
失敗trialをacceptedにするreview、authorized cap超過、既存outputへの上書きは拒否する。
この処理はagentやpaid APIを起動せず、同じ入力からtimestamp-free/sorted-key resultを作る。

### First-party Morphic receipt and zero-cost rehearsal

Morphic-controlled armはwrapperなしでcanonical receiptを出力できる。通常のone-shot出力を
維持し、最後のstdout lineだけをreceiptにする。

```bash
morphic code \
  --benchmark-receipt \
  --workspace . \
  "Implement the benchmark task"
```

`--benchmark-receipt`はcouncil turnのcostを合算し、normalized completion eventに含まれる
non-negative usage counterだけを集約する。model fieldは
`morphic-control[<sorted engine ids>]`となる。実行失敗またはCtrl-Cでは、未確定費用を
0ドルと偽らずreceiptを出さないため、recorder/finalizerは欠損としてfail closedする。
通常のflagなし出力は変えない。

Phase 43のlocal rehearsalは外部agentやAPIを起動せず、Phase 41-42の全経路を検査する。

```bash
morphic benchmark agent-cli-rehearse \
  --source-root . \
  --revision HEAD \
  --output-dir ../agent-cli-rehearsal
```

このコマンドが使うarm commandは内部生成された`python -c` fixtureだけで、利用者が
Codex/Claude commandへ差し替えるoptionはない。configured estimateとnormalized actual
costはともに0ドル。pinned detached worktreeで3 armを通し、次のbundleを新規directoryへ
exclusiveに発行する。

- `manifest.json`
- `recorder-config.json`
- `evidence.json`
- `reviews.json`
- `results.json`

rehearsal reviewは`accepted_patch=false`に固定される。これはreceipt/parser/join/isolationの
動作確認であり、agent品質比較ではない。既存output directoryは上書きしない。read-only
planの編集開始点として`benchmarks/templates/agent_cli_manifest.example.json`と
`agent_cli_recorder.example.json`も同梱する。実キャンペーンは従来どおり別の
`agent-cli-record --execute --acknowledge-paid --cost-cap-usd ...`による明示承認が必要。

### Campaign preflight and bound reviews

Phase 44では実キャンペーン前にimmutable revision、runtime declarations、全commandを
1つのnon-authorizing artifactへ固定する。runtime versionは利用者が収集してJSONへ記入し、
Morphic自身は`--version`を含むagent commandを実行しない。

```bash
morphic benchmark agent-cli-preflight \
  --manifest benchmark-manifest.json \
  --config recorder-config.json \
  --runtime-versions runtime-versions.json \
  --source-root . \
  --output benchmark-preflight.json \
  --json
```

manifestの`workspace_revision`はsymbolic `HEAD`ではなく、Gitで解決できるfull lowercase
40-character commit hashでなければならない。runtime declarationは3 armをexactly once持ち、
各`executable`がrecorder configのarm command先頭と一致する必要がある。version stringは
whitespace-normalize後にSHA-256化される。arm/check/handoff commandもPhase 41と同じ方法で
fingerprintされる。raw goalを公開せずにgoal/timeout/model hintを含む完全な契約変更を
検出するため、manifest全体とconfig全体のcanonical SHA-256も保持する。artifact自身の
SHA-256と`execution_authorized=false`を含み、preflight成功だけでagent実行は許可されない。

recording後はindependent reviewer用の未記入templateを生成する。

```bash
morphic benchmark agent-cli-review-template \
  --preflight benchmark-preflight.json \
  --evidence benchmark-evidence.json \
  --output benchmark-reviews.json \
  --json
```

templateは全arm/trialを持ち、human judgment fieldsはすべて`null`、
`review_completed=false`である。reviewerはaccepted patch、interventions、recovery、reviewer id、
review artifact SHA-256を埋め、最後に`review_completed=true`へ変更する。preflight/evidence
SHA-256とagent argv SHA-256は変更しない。

```bash
morphic benchmark agent-cli-finalize \
  --manifest benchmark-manifest.json \
  --preflight benchmark-preflight.json \
  --evidence benchmark-evidence.json \
  --reviews benchmark-reviews.json \
  --output benchmark-results.json
```

bound reviewを`--preflight`なしでfinalizeすること、別evidenceへ流用すること、fingerprintを
変更することは拒否される。Phase 42形式のbinding fieldを持たないlegacy reviewは後方互換で
利用できる。`benchmarks/templates/agent_cli_runtime_versions.example.json`を編集開始点として
同梱する。

### Reviewer separation and campaign status

Phase 45ではoperatorとreviewerの構造的分離をpolicy declarationで固定する。
`benchmarks/templates/agent_cli_review_policy.example.json`をコピーし、operator ID、許可する
reviewer IDs、必要なminimum distinct reviewer数を記入する。

```json
{
  "schema_version": 1,
  "benchmark_id": "campaign-001",
  "operator_id": "operator-1",
  "reviewer_ids": ["reviewer-1", "reviewer-2"],
  "minimum_distinct_reviewers": 2
}
```

このpolicyをreview template生成とfinalizeの両方へ渡す。

```bash
morphic benchmark agent-cli-review-template \
  --preflight benchmark-preflight.json \
  --evidence benchmark-evidence.json \
  --review-policy reviewer-policy.json \
  --output benchmark-reviews.json

morphic benchmark agent-cli-finalize \
  --manifest benchmark-manifest.json \
  --preflight benchmark-preflight.json \
  --evidence benchmark-evidence.json \
  --reviews benchmark-reviews.json \
  --review-policy reviewer-policy.json \
  --output benchmark-results.json
```

policyはreviewer IDsをsortしてcanonical SHA-256を作り、review artifactへbindする。
operator自身のreview、allowlist外ID、minimum distinct reviewer未達、decision数より大きく
実現不能なminimumは拒否する。これは宣言されたIDの構造的分離であり、本人確認や署名を
意味しない。

campaignの現在位置はartifactを変更せず確認できる。

```bash
morphic benchmark agent-cli-status \
  --manifest benchmark-manifest.json \
  --preflight benchmark-preflight.json \
  --evidence benchmark-evidence.json \
  --reviews benchmark-reviews.json \
  --review-policy reviewer-policy.json \
  --results benchmark-results.json \
  --json
```

status stageは`manifest_ready` → `preflight_ready` → `recorded` → `review_pending` →
`review_complete` → `finalized`。途中artifactの欠落、別manifest/evidenceの混入、estimate、
policy、review、resultsの不一致はfail closedになる。このcommandはファイルを読むだけで、
全stageにおいて`paid_execution_authorized=false`を返す。

### Signed reviewer attestations

Phase 46では、policyのreviewer IDをEd25519公開鍵へ結び付ける。まず
`benchmarks/templates/agent_cli_reviewer_trust.example.json`をコピーし、example公開鍵を
各reviewerが管理する実鍵へ必ず置き換える。trust declarationはreview policy SHA-256、
reviewer ID、key ID、公開鍵、`active` / `revoked` statusをcanonical SHA-256へ固定する。
key rotation時は旧鍵を`revoked`で残し、新しいactive keyを追加する。

trust-bound review templateを生成し、reviewerがdecisionを完了した後、canonical signing
payloadを生成する。

```bash
morphic benchmark agent-cli-review-template \
  --preflight benchmark-preflight.json \
  --evidence benchmark-evidence.json \
  --review-policy reviewer-policy.json \
  --reviewer-trust reviewer-trust.json \
  --output benchmark-reviews.json

# reviewerがbenchmark-reviews.jsonを完成させ、review_completed=trueにした後
morphic benchmark agent-cli-attestation-template \
  --reviews benchmark-reviews.json \
  --review-policy reviewer-policy.json \
  --reviewer-trust reviewer-trust.json \
  --output benchmark-attestation-template.json \
  --json
```

attestation templateはdistinct reviewerごとに1つのstatementと
`signing_payload_base64`を出す。statementはbenchmark/task/revision、preflight、evidence、
review policy、reviewer trust、completed reviews全体、当該reviewerのdecision集合をbindする。
Morphicは秘密鍵を読まず、reviewerはpayloadを自身のEd25519秘密鍵で外部署名し、署名とkey IDを
`ReviewAttestationBundle`へ格納する。

```bash
morphic benchmark agent-cli-finalize \
  --manifest benchmark-manifest.json \
  --preflight benchmark-preflight.json \
  --evidence benchmark-evidence.json \
  --reviews benchmark-reviews.json \
  --review-policy reviewer-policy.json \
  --reviewer-trust reviewer-trust.json \
  --attestations benchmark-attestations.json \
  --output benchmark-results.json
```

trust-bound reviewはdistinct reviewer全員の署名が揃わない限りfinalizeできない。unknown key、
revoked key、invalid signature、欠落reviewer、別review/evidence/policy/trustからの混入は拒否する。
statusには`review_attestation_pending`が加わり、検証後だけ`review_complete`へ進む。unsigned legacy
campaignは従来の6段階とfinalize behaviorを維持する。署名は登録済み秘密鍵の保有を証明するが、
trust declarationのkey enrollment自体は実在人物の本人確認ではない。組織CA、OIDC/Sigstore、
または外部key directoryとの結合は次段階である。

### Organization-authority anchored campaigns

Phase 47では、offline Ed25519 organization authorityをout-of-band trust anchorとして追加する。
`agent_cli_reviewer_authority.example.json`と`agent_cli_anchored_reviewer_trust.example.json`を
開始点にできるが、同梱example公開鍵は実運用で必ず組織管理鍵へ置き換える。authority artifactは
authority ID、algorithm、public key、public-key SHA-256、self fingerprintを固定する。秘密鍵は
Morphicへ渡さない。

anchored trustを作成後、全reviewer keyについてCA署名payloadを生成する。

```bash
morphic benchmark agent-cli-reviewer-enrollment-template \
  --review-policy reviewer-policy.json \
  --reviewer-trust anchored-reviewer-trust.json \
  --reviewer-authority reviewer-authority.json \
  --output reviewer-enrollment-template.json \
  --json
```

organization authorityは各`signing_payload_base64`を外部署名し、statementとsignatureを
`ReviewerEnrollmentBundle`へ格納する。statementはauthority、benchmark、review policy、
exact reviewer trust、reviewer/key ID、reviewer public-key fingerprintをbindする。trust内の
active/revokedを含む全鍵がexactly once CA enrollmentされなければ検証は失敗する。

authority-bound finalizeは通常のreview attestationsに加えてauthorityとenrollmentsを要求する。

```bash
morphic benchmark agent-cli-finalize \
  --manifest benchmark-manifest.json \
  --preflight benchmark-preflight.json \
  --evidence benchmark-evidence.json \
  --reviews benchmark-reviews.json \
  --review-policy reviewer-policy.json \
  --reviewer-trust anchored-reviewer-trust.json \
  --reviewer-authority reviewer-authority.json \
  --reviewer-enrollments reviewer-enrollments.json \
  --attestations benchmark-attestations.json \
  --output benchmark-results.json
```

results生成後、全artifactを1つのauthority signing payloadへ固定する。

```bash
morphic benchmark agent-cli-campaign-envelope-template \
  --manifest benchmark-manifest.json \
  --preflight benchmark-preflight.json \
  --evidence benchmark-evidence.json \
  --reviews benchmark-reviews.json \
  --review-policy reviewer-policy.json \
  --reviewer-trust anchored-reviewer-trust.json \
  --reviewer-authority reviewer-authority.json \
  --reviewer-enrollments reviewer-enrollments.json \
  --attestations benchmark-attestations.json \
  --results benchmark-results.json \
  --output campaign-envelope-template.json
```

envelopeはmanifest、preflight、evidence、reviews、policy、trust、enrollments、attestations、
resultsのSHA-256とidentityをbindし、`paid_execution_authorized=false`を固定する。authorityが
payloadを外部署名した`SignedCampaignEnvelope`をstatusへ渡した場合だけauthority-bound campaignは
`finalized`になる。署名前は`campaign_envelope_pending`、CA enrollment不足時は
`reviewer_enrollment_pending`を返す。unanchored Phase 46とunsigned legacy campaignは従来どおり。

このoffline CA経路はoperatorだけが作ったreviewer鍵を排除できる。ただしauthority root公開鍵の
安全なout-of-band配布、certificate expiry、root revocation/rotation、transparency logは別契約であり、
現在のartifactだけでは保証しない。

---

## Agent CLI Router

```python
class AgentCLIRouter:
    AGENT_ROUTING_MAP = {
        "long_running_dev":    "openhands",   # SWE-bench 72%, Docker 沙箱
        "complex_reasoning":   "claude_code", # Anthropic 最高品質
        "long_context":        "gemini_cli",  # 2M トークン, Grounding
        "fast_code_gen":       "codex_cli",   # Rust 製高速, MCP server
        "cost_zero":           "ollama",      # ローカル無料
        "workflow_pipeline":   "adk",         # Sequential / Parallel / Loop
    }

    async def route(self, task: Task) -> AgentEngine:
        task_type = await self.classify_task(task)
        if self.budget_exhausted():
            return self.engines["ollama"]
        engine_name = self.AGENT_ROUTING_MAP.get(task_type, "claude_code")
        engine = self.engines[engine_name]
        if not await engine.is_available():
            engine = self.fallback_engine(engine_name)
        return engine

    def classify_task(self, task: Task) -> str:
        if task.estimated_hours > 1:       return "long_running_dev"
        if task.context_tokens > 100_000:  return "long_context"
        if task.requires_ci_cd:            return "fast_code_gen"
        if task.budget == 0:               return "cost_zero"
        if len(task.pipeline_steps) > 3:   return "workflow_pipeline"
        return "complex_reasoning"


class AgentEngine(Protocol):
    async def is_available(self) -> bool: ...
    async def run(self, task: Task) -> TaskResult: ...
    async def get_cost_estimate(self, task: Task) -> float: ...
    def get_capabilities(self) -> list[str]: ...
```

**全体像:**
```
[Morphic-Agent Orchestrator]
         │
         ├── 長時間開発タスク ────→ [OpenHands] (Docker沙箱, 自律実行)
         ├── 設計・レビュー ─────→ [Claude Code SDK] (headless並列, PTC)
         ├── 長文脈分析 ─────────→ [Gemini CLI + ADK] (2M tokens, Grounding)
         ├── 高速生成・CI/CD ────→ [Codex CLI] (MCP server, exec)
         ├── コスト $0 タスク ───→ [Ollama] (ローカル完全無料)
         │
         └── [Shared Semantic Memory] ← 全エンジン共通の記憶ハブ
```
