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

## 🛠️ Phase 1 — 環境構築・単体動作確認 ✅ 完了

### 🤖 自動

- [x] uv による Python 3.11 プロジェクト初期化
- [x] 依存関係定義 (LangGraph / Streamlit / ChromaDB / Tavily / yfinance)
- [x] `.gitignore` / `.env.example` / `README.md` / `CLAUDE.md` / `TODO.md`
- [x] `src/config.py` (pydantic-settings)
- [x] `src/llm.py` (役割別 Gemini ファクトリ)
- [x] `src/agents/state.py` (LangGraph State 型)
- [x] `src/agents/orchestrator.py` (単体エージェント版)
- [x] `src/app.py` (Streamlit 最小チャット UI)
- [x] テスト 8 件 (`tests/test_config.py`, `tests/test_llm.py`)
- [x] GitHub Flow ブランチ戦略確立 (PR 必須)
- [x] **Streamlit 起動時の `ModuleNotFoundError` 修正** (PR #4, editable install)

### 👤 手動

- [x] Gemini API キー取得・`.env` 設定
- [x] Streamlit で動作確認 (Gemini API key OK 表示済み)

### 🤖 自動（任意・後回し）

- [ ] CI ワークフロー (`.github/workflows/ci.yml`)
- [ ] PR テンプレート (`.github/pull_request_template.md`)
- [ ] `tests/test_orchestrator_live.py` (`@pytest.mark.live`)

---

## 🤖 Phase 2 — 5 エージェント構築 (現フェーズ)

### 🤖 自動（Claude 側で実装済み）

- [x] **Tavily ラッパー** — `src/tools/web_search.py` (キー未設定時は空結果を返すフォールバック)
- [x] **Researcher (A)** — `src/agents/researcher.py` (Tavily → LLM 要約)
- [x] **Analyst (B)** — `src/agents/analyst.py`
- [x] **Critic (C)** — `src/agents/critic.py`
- [x] **Fact-checker (D)** — `src/agents/factchecker.py` (JSON 構造化判定 + 頑健なパース)
- [x] **Finalizer (E)** — `src/agents/finalizer.py`
- [x] **LangGraph パイプライン** — `src/agents/orchestrator.py` 全面書き換え
  - START → A → B → C → D → (条件分岐) → E → END
  - D=NG かつ retry<max なら B に差し戻し、retry≥max なら E に進む
- [x] **Streamlit UI 拡張** — エージェント別 expander、Fact-check バッジ
- [x] **テスト追加** — 計 20 件パス (Phase 1 の 8 + Phase 2 の 12)
  - `tests/test_factchecker.py` (JSON パースの頑健性)
  - `tests/test_orchestrator.py` (差し戻しルーティング)
  - `tests/test_web_search.py` (Tavily スタブ動作)

### 👤 手動

- [ ] **Tavily API キー取得** — https://tavily.com/ (無料枠 1,000 req/月)
- [ ] **`.env` の `TAVILY_API_KEY=` を更新**
- [ ] **Phase 2 PR をレビュー＆マージ**
- [ ] **実質問で 5 エージェント挙動を確認** — 中間出力パネルで各エージェントの貢献を観察
- [ ] **コスト監視** — [Google AI Studio](https://aistudio.google.com/) の Usage で消費量を確認

### ⚙️ 協働

- [ ] **プロンプト調整** — 出力品質を見て各エージェントの system prompt を微調整
- [ ] **モデル選択の妥当性検証** — Critic/Fact-checker の Flash-Lite が十分か確認

---

## 💾 Phase 3 — データ連携・記憶

### 🤖 自動（Claude 側）

- [x] **yfinance ラッパー** — `src/tools/finance.py` (社名→ティッカー逆引き + スナップショット取得)
- [x] **株価データ取得**を Analyst に接続 (質問からティッカー自動抽出 → プロンプト注入)
- [x] **テスト追加**: `tests/test_finance.py` (10 件パス、ネットワーク不要)
- [x] **ChromaDB クライアント** — `src/memory/vector_store.py`
  - `QAMemory` クラスで Q&A の保存・類似検索を提供
  - ChromaDB のデフォルト embedding (all-MiniLM-L6-v2) で外部 API 不要
- [x] **会話履歴の文脈活用**
  - Researcher が類似する過去 Q&A を取得しプロンプト注入
  - Finalizer が最終回答を保存 (失敗時もユーザー応答は止めない)
- [x] **テスト**: `tests/test_vector_store.py` 9 件 (一時ディレクトリ使用、ネットワーク不要)
- [ ] **SQLite ロガー** — `src/memory/logger.py`
  - 全エージェントの呼び出しログ・コスト・所要時間を記録

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
