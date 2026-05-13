# 5agents

> 5体構成のマルチエージェント AI 調査システム — Research → Analysis → Critique → Fact-check → Finalize

調査・分析・予測を自動化する個人専用 AI システム。Gemini 2.5 Flash と LangGraph を組み合わせて、5つの専門エージェントが連携して質問に回答します。

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
- **オーケストレーション**: [LangGraph](https://langchain-ai.github.io/langgraph/)
- **UI**: [Streamlit](https://streamlit.io/)
- **記憶・検索**: [ChromaDB](https://www.trychroma.com/)
- **ログ永続化**: SQLite
- **データ取得**: yfinance / [Tavily](https://tavily.com/)
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

- [ ] **Phase 1** — 環境構築・単体動作確認 (1〜2週間)
- [ ] **Phase 2** — 5エージェント構築 (2〜3週間)
- [ ] **Phase 3** — データ連携・記憶の実装 (2〜3週間)
- [ ] **Phase 4** — ダッシュボード UI・自動化 (2〜4週間)

詳細は [docs/AIエージェント構築計画書.docx](./docs/AIエージェント構築計画書.docx) を参照。

## ライセンス

MIT
