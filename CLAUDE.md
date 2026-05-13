# CLAUDE.md

このファイルは Claude Code（および将来の AI ペアプログラマ）が本リポジトリで作業する際の指針です。
**コードを書く前に必ず最後まで読むこと。**

---

## 1. プロジェクト概要

`5agents` は、5体のエージェントが連携して調査・分析・予測を行うマルチエージェント AI システムです。
個人の調べもの（株・金融、テック動向、業務関連）を自動化することが目的です。

詳細仕様は [docs/AIエージェント構築計画書.docx](./docs/AIエージェント構築計画書.docx) を参照。

### エージェントパイプライン

```
ユーザー質問
   ↓
[A] Researcher  (Gemini 2.5 Flash)        Web検索・情報収集
   ↓
[B] Analyst     (Gemini 2.5 Flash)        数値処理・分析・予測
   ↓
[C] Critic      (Gemini 2.5 Flash-Lite)   反論・別視点
   ↓
[D] Fact-checker(Gemini 2.5 Flash-Lite)   根拠・矛盾・誇張の検出
   │  ← NG なら B へ差し戻し（最大 N 回ループ）
   ↓
[E] Finalizer   (Gemini 2.5 Flash)        統合・整形して出力
```

**重要**: D の差し戻しループには必ず上限（デフォルト 2 回）を設けること。無限ループはコストが青天井になる。

---

## 2. 技術スタック

| カテゴリ | 採用技術 | バージョン | 選定理由 |
|---|---|---|---|
| 言語 | Python | 3.11+ | LangGraph / LangChain エコシステムの標準 |
| パッケージ管理 | [uv](https://docs.astral.sh/uv/) | 0.11+ | pip 比 10〜100倍高速。pyproject.toml + lockfile |
| LLM | Gemini 2.5 Flash / Flash-Lite | API | 無料枠が大きい、マルチエージェント構成に十分な性能 |
| エージェント基盤 | [LangGraph](https://langchain-ai.github.io/langgraph/) | 0.2+ | 状態を持つグラフベースのオーケストレーション。差し戻しループ表現が容易 |
| LLM 呼び出し | langchain-google-genai | 2.0+ | Gemini 公式統合 |
| Web 検索 | [Tavily](https://tavily.com/) | 0.5+ | AI エージェント向けに最適化、無料枠 1,000 req/月 |
| UI | [Streamlit](https://streamlit.io/) | 1.40+ | Python 単独で完結、プロトタイプから本番まで対応 |
| 記憶 / 検索 | [ChromaDB](https://www.trychroma.com/) | 0.5+ | 軽量で local-first、外部依存なし |
| ログ永続化 | SQLite | 標準 | セットアップ不要、十分高速 |
| 金融データ | yfinance | 0.2+ | 無料、Yahoo Finance データへの簡易アクセス |
| Lint / Format | [Ruff](https://docs.astral.sh/ruff/) | 0.7+ | Rust 製で高速、formatter も内蔵 |
| 型検査 | mypy | 1.13+ | 型ヒントの静的検証 |
| テスト | pytest | 8.0+ | 業界標準 |

---

## 3. ディレクトリ構成

```
5agents/
├── src/
│   ├── __init__.py
│   ├── config.py           # pydantic-settings: 環境変数・モデル名等の集中管理
│   ├── llm.py              # Gemini クライアントのファクトリ
│   ├── app.py              # Streamlit エントリポイント
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── state.py        # LangGraph で共有する State 型
│   │   ├── orchestrator.py # 5エージェントを束ねるグラフ定義
│   │   ├── researcher.py   # A: Web検索・情報収集
│   │   ├── analyst.py      # B: 分析・予測
│   │   ├── critic.py       # C: 反論・別視点
│   │   ├── factchecker.py  # D: 事実確認・監視
│   │   └── finalizer.py    # E: 統合・整形
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── web_search.py   # Tavily ラッパー
│   │   └── finance.py      # yfinance ラッパー
│   └── memory/
│       ├── __init__.py
│       ├── vector_store.py # ChromaDB クライアント
│       └── logger.py       # SQLite ロガー
├── tests/                  # pytest テスト（src/ と同階層構造）
├── docs/                   # 計画書・設計書
├── data/                   # SQLite / ChromaDB 永続化先（.gitignore 済み）
├── .env.example            # 環境変数テンプレート
├── .env                    # ローカルのみ、Git 管理外
├── pyproject.toml          # 依存関係・ツール設定
├── uv.lock                 # 依存関係ロックファイル
├── README.md
└── CLAUDE.md               # 本ファイル
```

**新規モジュールを追加する際は必ずこのツリーに追記すること。**

---

## 4. よく使うコマンド

### 環境構築・実行

```bash
# 依存関係インストール
uv sync

# 環境変数セットアップ（初回のみ）
cp .env.example .env

# Streamlit アプリ起動
uv run streamlit run src/app.py

# 単体スクリプト実行（例: オーケストレーター動作確認）
uv run python -m src.agents.orchestrator
```

### 依存関係の追加

```bash
# 本体依存
uv add <package>

# 開発依存
uv add --dev <package>

# 削除
uv remove <package>
```

### テスト・品質チェック

```bash
# テスト実行
uv run pytest
uv run pytest tests/test_orchestrator.py -v   # 特定ファイル
uv run pytest -k "test_factchecker"           # 名前一致

# Lint（チェックのみ）
uv run ruff check .

# Lint（自動修正）
uv run ruff check --fix .

# Format
uv run ruff format .

# 型検査
uv run mypy src/
```

### Git ワークフロー（GitHub Flow）

```bash
# 機能ブランチを作成
git checkout main && git pull
git checkout -b feature/<task-name>

# こまめにコミット
git add <files>
git commit -m "feat: ..."

# プッシュして PR を作成
git push -u origin feature/<task-name>
gh pr create --base main --title "..." --body "..."

# レビュー後マージ
gh pr merge --squash --delete-branch
```

---

## 5. コーディング規約

### Python 一般

- **型ヒントは必須**。関数シグネチャ・公開 API には必ず付ける
- **docstring** は公開関数・クラスに付ける（Google スタイル簡易版で OK）
- **import 順序**は Ruff の isort 設定に従う（標準 → サードパーティ → ローカル）
- **f-string** を優先、`%` や `.format()` は使わない
- **pathlib.Path** を使い、`os.path` は避ける

### 命名

- 変数・関数: `snake_case`
- クラス: `PascalCase`
- 定数: `UPPER_SNAKE_CASE`
- プライベート: `_leading_underscore`
- エージェント関数は **`agent_<role>` または `run_<role>`** で統一（例: `run_researcher`）

### LLM 呼び出し

- LLM クライアントは **`src/llm.py` で集中管理**し、各エージェントから直接 `ChatGoogleGenerativeAI` をインスタンス化しない
- モデル名は **環境変数経由**で渡す（`GEMINI_MODEL_MAIN`, `GEMINI_MODEL_SUB`）
- `temperature` などのパラメータは各エージェントの責務に応じて明示する（リサーチは低め、批判は高めなど）
- **プロンプトは agents/ 配下のモジュール冒頭に定数として定義**し、外部 yaml/json には分離しない（小規模なため）

### LangGraph

- State は **`src/agents/state.py` の単一 TypedDict** に集約
- 各エージェントノードは `def node(state: AgentState) -> AgentState:` のシグネチャに統一
- ループは `add_conditional_edges` で表現、**必ず上限を設ける**（State にループカウンタを持つ）

### テスト

- ファイル名: `tests/test_<module>.py`
- LLM を呼ぶテストは **常時実行しない**。`@pytest.mark.live` でマーク、CI では除外
- ロジック検証は **モック**（`unittest.mock`）で完結させる
- カバレッジ目標: コアロジック（agents/, tools/）で 70% 以上

### エラーハンドリング

- API 呼び出し失敗は **3 回までリトライ**（指数バックオフ）してから諦める
- ユーザー入力のバリデーションは pydantic で
- 例外を握りつぶさない。最低でも `logger.exception()` を残す

---

## 6. ブランチ・コミット規約

### ブランチ命名

- `feature/<task-name>` — 新機能
- `fix/<bug-name>` — バグ修正
- `chore/<task-name>` — 設定・依存関係・雑務
- `docs/<task-name>` — ドキュメントのみ

### コミットメッセージ（Conventional Commits）

```
<type>: <subject>

<body 任意>
```

| type | 用途 |
|---|---|
| `feat` | 新機能 |
| `fix` | バグ修正 |
| `chore` | 設定・依存関係・雑務 |
| `docs` | ドキュメントのみ |
| `refactor` | 機能変更を伴わないリファクタ |
| `test` | テスト追加・修正 |
| `style` | フォーマット（コードの動作に影響なし） |

**例**:
- `feat: Researcher エージェントを Tavily 統合で実装`
- `fix: D エージェントの差し戻しループが上限を無視する不具合を修正`
- `chore: ruff を 0.7.0 から 0.8.0 にアップグレード`

### Pull Request

- **main への直接コミットは禁止**
- PR テンプレート（最低限）:
  - 概要（何を・なぜ）
  - 動作確認手順
  - 関連 Issue / Phase
- マージ方法: **squash merge** をデフォルトに（履歴を綺麗に保つ）

---

## 7. 5エージェント実装時の注意

### コスト管理

- **無料枠の意識を常に持つ**。Gemini 2.5 Flash は 1 日 250 req、5 エージェントで 1 質問 = 5 req → 50 質問/日が上限
- 開発中は `gemini-2.5-flash-lite` の比率を増やす
- ループ系のテスト中は **必ずダミーモード**（`APP_ENV=development` で API を呼ばない経路）を用意

### プロンプト設計

- 各エージェントのプロンプトは **役割（Role）/ 入力 / 期待出力フォーマット** を明示
- 出力は可能な限り **構造化**（JSON か Markdown の決まったセクション）
- Fact-checker (D) の出力は **`{"verdict": "OK" | "NG", "issues": [...]}`** の固定フォーマットにする（オーケストレーターが判定に使う）

### モデル選択

| 役割 | 推奨モデル | 理由 |
|---|---|---|
| A Researcher | Flash | 検索結果の要約に十分な性能、コストも許容 |
| B Analyst | Flash | 数値推論には Flash の精度が必要 |
| C Critic | Flash-Lite | 反論生成は軽量モデルでも質を保てる |
| D Fact-checker | Flash-Lite | 構造化判定のためコスト優先 |
| E Finalizer | Flash | 最終出力の品質が UX に直結 |

### Web 検索（Tavily）

- 1 クエリで `max_results=5` を上限の目安に（コスト・レイテンシ・精度のバランス）
- ニュース系は `topic="news"` / `days=7` を活用
- Researcher 以外は **直接 Tavily を呼ばない**（責務分離）

### 記憶（ChromaDB）

- collection 名は機能ごとに分ける（例: `qa_history`, `analysis_results`）
- 永続化先は `CHROMA_PERSIST_DIR`（デフォルト `./data/chroma_db`）
- メタデータには **`timestamp` と `agent` を必ず含める**

---

## 8. やってはいけないこと

- ❌ **`.env` をコミット**（`.gitignore` で防御済みだが、`git add -A` には注意）
- ❌ **API キーをハードコード**
- ❌ **main ブランチへの直接コミット・直接プッシュ**
- ❌ **D エージェントの差し戻しループに上限を設けない**
- ❌ **大量のテストデータや ChromaDB の永続化ファイルをコミット**（`data/` は `.gitignore`）
- ❌ **本番モデル名をコード中にハードコード**（環境変数経由）
- ❌ **無断で外部 API（特に有料）の追加導入**。事前に相談すること

---

## 9. 開発フェーズ（ロードマップ）

現在地: **Phase 1 着手前**

| Phase | 期間目安 | ゴール |
|---|---|---|
| 1 | 1〜2 週間 | Gemini API 疎通 / 単体エージェント / Streamlit 最小チャット |
| 2 | 2〜3 週間 | 5 エージェントを LangGraph で接続、差し戻しループ実装 |
| 3 | 2〜3 週間 | yfinance 連携 / ChromaDB 記憶 / SQLite ログ |
| 4 | 2〜4 週間 | Streamlit ダッシュボード化 / 定期実行 / 通知連携 |

各 Phase は **1 つ以上の PR** で完了させ、main にマージしてから次へ進む。

---

## 10. 困ったら

- 計画書の意図に迷ったら **必ずユーザーに確認**してから実装する
- Gemini / LangGraph / Tavily の API 仕様変更があるため、コードを書く前に最新ドキュメントを確認:
  - [Gemini API](https://ai.google.dev/gemini-api/docs)
  - [LangGraph](https://langchain-ai.github.io/langgraph/)
  - [Tavily](https://docs.tavily.com/)
- 設計判断が必要な場面では、選択肢と trade-off を提示してユーザーの承認を得る
