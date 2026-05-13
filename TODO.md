# TODO — 5agents 開発計画

> **凡例**
> - 🤖 **自動 (Claude 側)** — コード実装・テスト・PR 作成・ドキュメント更新など、AI ペアプログラマで完結する作業
> - 👤 **手動 (ユーザー側)** — 外部サービスのアカウント作成・API キー発行・本人確認・有償契約・PR レビュー＆マージなど、人間にしかできない作業
> - ⚙️ **協働** — Claude が下準備し、ユーザーが最終判断・実行する作業

---

## 🚦 Phase 0 — 開発開始前の準備（最優先）

ここを通過しないと Phase 1 のコードが動きません。

### 👤 手動（ユーザー）

- [ ] **Gemini API キーを取得**
  - [Google AI Studio](https://aistudio.google.com/app/apikey) にアクセス
  - 「Create API key」で発行
  - 取得した key を控える
- [ ] **Tavily API キーを取得**（Phase 2 で使用するが今から準備推奨）
  - [Tavily](https://tavily.com/) でサインアップ
  - 無料枠 1,000 req/月
  - dashboard から API key をコピー
- [ ] **`.env` ファイルを作成**
  ```bash
  cd ~/Desktop/5agents
  cp .env.example .env
  # エディタで .env を開き、以下を設定:
  #   GOOGLE_API_KEY=取得したGeminiキー
  #   TAVILY_API_KEY=取得したTavilyキー
  ```
- [ ] **PR #1 (CLAUDE.md) をレビュー → マージ**
  - https://github.com/koshiro-y-0/5agents/pull/1
- [ ] **PR #2 (Phase 1 基盤) をレビュー → マージ**
  - https://github.com/koshiro-y-0/5agents/pull/2
- [ ] **PR #3 (本 TODO.md) をレビュー → マージ**

### ⚙️ 協働

- [ ] **動作確認** — `.env` 設定後、ユーザーが起動・Claude が結果を解釈
  ```bash
  uv run streamlit run src/app.py
  # → http://localhost:8501 で質問を入力
  ```

---

## 🛠️ Phase 1 — 環境構築・単体動作確認 (進行中)

### 🤖 自動（Claude 側で実装済み）

- [x] uv による Python 3.11 プロジェクト初期化
- [x] 依存関係定義 (LangGraph / Streamlit / ChromaDB / Tavily / yfinance)
- [x] `.gitignore` / `.env.example` / `README.md`
- [x] `CLAUDE.md` (AI 開発指針)
- [x] `src/config.py` (pydantic-settings)
- [x] `src/llm.py` (役割別 Gemini ファクトリ)
- [x] `src/agents/state.py` (LangGraph State 型)
- [x] `src/agents/orchestrator.py` (単体エージェント)
- [x] `src/app.py` (Streamlit 最小チャット UI)
- [x] テスト 8 件 (`tests/test_config.py`, `tests/test_llm.py`)
- [x] GitHub Flow ブランチ戦略確立 (PR 必須)

### 🤖 自動（残作業）

- [ ] **疎通確認テスト**を `tests/test_orchestrator_live.py` として追加
  - `@pytest.mark.live` でマーク（通常は除外、明示時のみ実行）
  - `uv run pytest -m live` で実行可能
- [ ] **CI ワークフロー** (`.github/workflows/ci.yml`) を追加
  - `uv sync` → `ruff check` → `pytest` を main / PR で自動実行
- [ ] **PR テンプレート** (`.github/pull_request_template.md`) を追加

### 👤 手動

- [ ] **Phase 1 の体感確認**
  - Streamlit でいくつか質問を投げる
  - 回答の質・速度・エラー有無を確認
  - 気づきを Claude にフィードバック

---

## 🤖 Phase 2 — 5 エージェント構築 (次の山場)

### 🤖 自動（Claude 側）

- [ ] **Researcher (A)** 実装 — `src/agents/researcher.py`
  - Tavily で Web 検索 → 上位 5 件を要約
- [ ] **Tavily ラッパー** — `src/tools/web_search.py`
- [ ] **Analyst (B)** 実装 — `src/agents/analyst.py`
  - Researcher の出力を受けて分析・予測
- [ ] **Critic (C)** 実装 — `src/agents/critic.py`
  - A/B の出力に反論・別視点を加える
- [ ] **Fact-checker (D)** 実装 — `src/agents/factchecker.py`
  - 構造化判定 `{"verdict": "OK"|"NG", "issues": [...]}` を返す
- [ ] **Finalizer (E)** 実装 — `src/agents/finalizer.py`
  - 全エージェントの出力を統合・整形
- [ ] **LangGraph パイプライン** — `src/agents/orchestrator.py` を書き直し
  - A → B → C → D → E の StateGraph
  - D が NG の場合 B へ差し戻し（最大 2 回、`max_factcheck_retries` で制御）
- [ ] **Streamlit UI 拡張**
  - 各エージェントの中間出力を expand パネルで可視化
  - 差し戻し回数をバッジ表示
- [ ] **テスト**（各エージェントのプロンプト・パイプライン・ループ上限）

### 👤 手動

- [ ] Phase 2 PR のレビュー＆マージ
- [ ] 実際の質問で 5 エージェント挙動を確認・フィードバック

### ⚙️ 協働

- [ ] **コスト確認** — Gemini API ダッシュボードで消費量を観察し、必要なら設計調整

---

## 💾 Phase 3 — データ連携・記憶

### 🤖 自動（Claude 側）

- [ ] **yfinance ラッパー** — `src/tools/finance.py`
- [ ] **株価データ取得**を Analyst に接続
- [ ] **ChromaDB クライアント** — `src/memory/vector_store.py`
  - 過去の Q&A・分析結果をベクトル化して保存
- [ ] **会話履歴の文脈活用**
  - 「先週と比べて」「前回の分析と比較して」等の質問に対応
- [ ] **SQLite ロガー** — `src/memory/logger.py`
  - 全エージェントの呼び出しログ・コスト・所要時間を記録
- [ ] **テスト**（in-memory ChromaDB / 一時 SQLite）

### 👤 手動

- [ ] Phase 3 PR のレビュー＆マージ
- [ ] 蓄積データの妥当性確認

---

## 📊 Phase 4 — ダッシュボード・自動化

### 🤖 自動（Claude 側）

- [ ] **Streamlit ダッシュボード** — チャート・グラフ表示
- [ ] **定期実行スクリプト** — `src/scheduler.py`
  - 毎朝 9 時にウォッチリスト銘柄のレポート生成
- [ ] **通知連携** (オプション) — LINE Notify or Discord Webhook

### 👤 手動

- [ ] **(オプション) LINE Notify トークン取得** — https://notify-bot.line.me/
- [ ] **(オプション) Discord Webhook URL 作成** — サーバー設定 → 連携サービス
- [ ] **(オプション) デプロイ先の選定**
  - 案 A: ローカル常駐（Mac の `launchd` で cron 化、コストゼロ）
  - 案 B: 軽量 VPS（さくらの VPS 月数百円〜）
  - 案 C: AWS Lambda + EventBridge（無料枠でほぼ収まる）
- [ ] **デプロイ実行**（選定後、Claude が手順書を作成しユーザーが実行）

### ⚙️ 協働

- [ ] **本番運用に向けた最終調整** — ログレベル / エラー通知 / コストアラート

---

## 🧹 横断的タスク（任意・余裕があれば）

### 🤖 自動

- [ ] `pre-commit` フック導入 (ruff / mypy を commit 時に自動実行)
- [ ] `mypy` 型エラーを 0 に
- [ ] エージェントごとのプロンプトを評価する eval ハーネス
- [ ] README に「実行例 GIF」を埋め込み（GIF 自体はユーザー側で録画）

### 👤 手動

- [ ] **GitHub リポジトリ設定**
  - [ ] Branch protection (main): PR 必須、CI パス必須
  - [ ] (任意) Public/Private 切り替えの判断
- [ ] **Google Cloud Billing アラート**
  - [ ] 月次予算（例: ¥500）を設定し超過時にメール通知

---

## 📝 メモ・運用ルール

- このファイルは **完了したタスクのチェックボックスを `[x]` にして更新**する
- Phase 単位で大きく進んだら **CLAUDE.md の「開発フェーズ」セクションも更新**
- 新しい TODO が発生したら、該当 Phase or 横断的タスクに追記
- 仕様変更・方針転換が発生したら、まず CLAUDE.md と TODO.md を更新してから実装に入る
