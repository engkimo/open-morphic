# Morphic-Agent Vision

> *"Mission Control for Intelligence"*
> ユーザーの意図を汲み取り、タスクをこなし、失敗を糧に自己進化する。

## Mission

**Morphic-Agent** は、単体のアルゴリズムでは解決できない複雑なタスクを、複数のAI・ツール・エージェントを動的に組み合わせることで解決し、**実行履歴・失敗・フィードバックから自己進化し続けるAIエージェントフレームワーク**である。

## North Star

- **意図の汲み取り**: ユーザーが曖昧に言ってもゴールに到達する
- **自律実行**: タスクをノード分解し、並列・順次・再帰的に実行
- **自己進化**: 成功・失敗から学習し、プロンプト・モデル選択・ツール群を改善
- **$0運用可**: Ollama優先ルーティングでローカルLLMを第一選択肢に

## Competitive Differentiation

| 競合 | Morphic-Agent の差別化 |
|---|---|
| **Manus** | タスクグラフ可視化 + ノード単位コスト制御 + 文脈工学5原則を初期から実装 |
| **Devin** | Interactive Planning + ローカルLLM対応でコスト$0運用可能 |
| **Windsurf** | クロスプラットフォームコンテキストブリッジ (複数AIアプリの断絶解消) |
| **OpenClaw** | 自律ツール発見・マーケットプレイス登録・他エージェント共有 + LAEEでPC直接制御 |
| **OpenHands** | Docker沙箱に閉じず、ローカル実機をエージェントの「手足」にするLAEE |

### v0.3 軸: メタオーケストレーター
OpenHands / Claude Code / Gemini CLI / Codex CLIを「専門実行エンジン」として統合管理。Semantic Fingerprintで全AIの記憶を統一。

### v0.4 軸: Local Autonomous Execution Engine (LAEE)
ユーザーのローカルPCを直接操作。シェル・ファイル・ブラウザ・GUI・開発ツールをエージェントが自律制御。3段階承認モードでユーザー自己責任のもと full-auto 運用可能。

### v0.5 軸: Unified Cognitive Layer (UCL)
全エージェントの記憶・タスク状態・判断を統合する共有認知層。タスクを Agent A → Agent B へ完全引き継ぎ。個々のAIは「脳の領域」、UCLは「記憶と意識の統合」。

## Guiding Motto

> "The boat on the rising tide of model progress, not the pillar stuck to the seabed." — *Manus*

モデル進化の潮流に乗る船であれ。海底に固定された柱ではなく。
