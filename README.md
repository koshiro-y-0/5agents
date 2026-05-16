# 5agents

> 5体構成のマルチエージェント AI **汎用調査システム** — Research → Analysis → Critique → Fact-check → Finalize

「**何かを調べてほしい**」という質問に対し、5 つの専門エージェントが連携して、Web 検索・分析・反論・事実確認・統合を経た **根拠付きの回答** を返す個人専用 AI システム。
Gemini 2.5 Flash と LangGraph で構築。トピックは不問 (AI 動向 / テック業界 / 株・金融 / 日常の疑問 など何でも)。

### 使い方の例

| あなたの質問 | 5 エージェントの動き |
|---|---|
| 「最近 1 週間の AI 業界の重要ニュースは?」 | Tavily で Web 検索 → 要約 → 分析 → 別視点追加 → 事実確認 → 統合 |
| 「Anthropic と OpenAI のモデル比較」 | 同上 (Web 中心の調査フロー) |
| 「NVDA の業績見通しと主要リスク」 | 上記に加え **yfinance が自動で最新株価・PER 等を Analyst に注入** |
| 「Python 3.13 の主な新機能」 | 通常の調査フロー (yfinance はスキップ) |

## エージェント構成

| 役割 | 名前 | 担当 | モデル |
|------|------|------|--------|
| A | Researcher | Web検索・ニュース収集・情報整理 | Gemini 2.5 Flash |
| B | Analyst | 数値処理・トレンド分析・予測 | Gemini 2.5 Flash |
| C | Critic | A・Bの結果に反論・別視点を追加 | Gemini 2.5 Flash-Lite |
| D | Fact-checker | 根拠なし・矛盾・誇張を検出・除去 | Gemini 2.5 Flash-Lite |
| E | Finalizer | 全エージェントの出力を統合・整形 | Gemini 2.5 Flash |

`D` が NG を出した場合は `B` へ差し戻しループが発動します。

## 技術スタック

- **LLM**: Gemini 2.5 Flash API (Google)
- **オーケストレーション**: [LangGraph](https://langchain-ai.github.io/langgraph/) — 差し戻しループ含む状態管理
- **UI**: [Streamlit](https://streamlit.io/) — チャット + 📊 ダッシュボード (タブ切替)
- **Web 検索**: [Tavily](https://tavily.com/) — Researcher エージェントが Web を探索
- **記憶**: [ChromaDB](https://www.trychroma.com/) — 過去 Q&A をベクトル検索して「先週と比べて」等の文脈質問に対応
- **観測ログ**: SQLite — 質問・エージェント所要時間・コスト傾向を記録
- **株価データ (任意・自動)**: yfinance — 質問に銘柄名/ティッカーが含まれた **時だけ** 起動して株価を注入
- **パッケージ管理**: [uv](https://docs.astral.sh/uv/)

## セットアップ

### 前提条件

- macOS / Linux (Windows は WSL 推奨)
- Python 3.11 以上
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (`brew install uv`)

### 手順

```bash
# 1. 依存関係をインストール
uv sync

# 2. 環境変数を設定
cp .env.example .env
# .env を編集して GOOGLE_API_KEY と TAVILY_API_KEY を設定

# 3. Streamlit を起動
uv run streamlit run src/app.py
```

### Mac で「開いただけで使える」状態にする (任意)

ログイン時に Streamlit を自動起動し、`http://localhost:8501` をブックマークするだけで使える状態にできます。

```bash
bash scripts/install-autostart.sh --with-scheduler
```

詳細は [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md) の「案 A」を参照。

### APIキーの取得

- **Gemini API key**: [Google AI Studio](https://aistudio.google.com/app/apikey)
- **Tavily API key**: [Tavily](https://tavily.com/) (無料枠 1,000 req/月)

## 開発

```bash
# テスト
uv run pytest

# Lint
uv run ruff check .
uv run ruff format .

# Type check
uv run mypy src/
```

## ブランチ戦略

GitHub Flow を採用しています。

- `main` は常にデプロイ可能な状態を保つ
- 機能開発は `feature/<task-name>` ブランチを切る
- 完了したら Pull Request を作成しレビューを経てマージ

## プロジェクト構成

```
5agents/
├── src/
│   ├── agents/         # 5体のエージェント実装
│   ├── tools/          # Web検索・データ取得ツール
│   └── app.py          # Streamlit エントリポイント
├── tests/              # pytest テスト
├── docs/               # 設計書・計画書
├── .env.example        # 環境変数テンプレート
├── pyproject.toml      # 依存関係・ツール設定
├── CLAUDE.md           # Claude Code 向け開発ガイド
└── README.md           # 本ファイル
```

## ロードマップ

- [x] **Phase 1** — 環境構築・単体動作確認 ✅
- [x] **Phase 2** — 5エージェント構築 (LangGraph + Tavily) ✅
- [x] **Phase 3** — データ連携・記憶 (yfinance / ChromaDB / SQLite) ✅
- [x] **Phase 4** — ダッシュボード UI・自動化 (定期実行 + 通知) ✅

定期実行・デプロイは `docs/DEPLOYMENT.md` を参照。

詳細は [docs/AIエージェント構築計画書.docx](./docs/AIエージェント構築計画書.docx) を参照。

## ライセンス

MIT
