# Hugging Face Spaces デプロイガイド

> **目的**: Mac を起動しなくても LINE とブラウザから 24/7 アクセスできるよう、
> 5agents を Hugging Face Spaces に Docker SDK でデプロイする。**完全無料**。

---

## なぜ HF Spaces？

| 項目 | HF Spaces (CPU Basic) | Oracle Always Free | GCP Always Free |
|---|---|---|---|
| 料金 | ✅ 完全無料 (CPU 2 vCPU / 16 GB RAM) | ⚠️ Out of capacity 多発 | ⚠️ 個人クレカ登録必要 |
| Docker サポート | ✅ Docker SDK | △ 自前 | △ 自前 |
| 永続化 | ✅ Persistent Storage 20 GB 無料 | ✅ Block Storage 200 GB | ✅ 30 GB |
| 24/7 起動 | ✅ Sleep 設定でも可 | ✅ | ✅ |
| HTTPS | ✅ `*.hf.space` 自動 | ✋ 自分で証明書 | ✋ 自分で証明書 |
| セットアップ難度 | ⭐ 低 (git push だけ) | ⭐⭐⭐ 高 | ⭐⭐ 中 |

5agents のように "Streamlit + FastAPI を 1 つの URL で公開" したい用途なら **HF Spaces が最楽**。

---

## アーキテクチャ

```
┌─────────────── HF Space (Docker SDK) ────────────────┐
│                                                       │
│   internet ─HTTPS─▶ nginx :7860                       │
│                       │                               │
│                       ├─ /line/*   ─▶ uvicorn :8080  │
│                       │              └ src.line.webhook:app
│                       ├─ /health   ─▶ uvicorn :8080  │
│                       └─ /         ─▶ streamlit :8501│
│                                       └ src/app.py    │
│                                                       │
│   supervisord: nginx + uvicorn + streamlit を統括      │
│   /data (Persistent 20 GB) ─ sqlite + chromadb       │
└───────────────────────────────────────────────────────┘
```

1 つのコンテナで FastAPI と Streamlit を同時に動かし、nginx が外部 port 7860 を
両者に振り分ける構成。HF Spaces は外部に出すポートを 1 つしか許さないため。

---

## 事前準備

| 項目 | 必須 | 取得先 |
|---|---|---|
| Hugging Face アカウント | ✅ | <https://huggingface.co/join> |
| Gemini API key | ✅ | <https://aistudio.google.com/apikey> |
| Groq API key | ✅ | <https://console.groq.com/keys> |
| Tavily API key | ✅ | <https://tavily.com/> (無料 1,000 req/月) |
| LINE Channel | △ (LINE 連携時) | <https://developers.line.biz/console/> |

---

## デプロイ手順

### 1. Space を作る

1. <https://huggingface.co/new-space> を開く
2. 設定:
   - **Owner**: 自分の HF ユーザー名
   - **Space name**: `5agents` (好きな名前で OK)
   - **License**: MIT
   - **SDK**: **Docker** (← ここ重要)
   - **Hardware**: `CPU basic · 2 vCPU · 16 GB · FREE`
   - **Visibility**: Public でも Private でも可
     - Public + STREAMLIT_PASSWORD あり = 推奨
     - Private = 自分の HF アカウントでしか開けない
3. "Create Space" をクリック → 空のリポジトリができる

### 2. Persistent Storage を有効化

履歴と ChromaDB を再起動後も残すために必要。

1. Space の **Settings** タブ → 下の方の **"Persistent Storage"** セクション
2. **"Small (20 GB) · FREE"** を選ぶ
3. **Confirm** で確定

これで `/data` がマウントされる。

> ⚠️ Persistent Storage 無効でも動くが、Space が再起動するとログ・履歴が全部消える。

### 3. Secrets を登録

Settings → **"Variables and secrets"** で以下を **"Secret" (公開しない)** として追加。

| Key | 必須 | 値の例 / 説明 |
|---|---|---|
| `GOOGLE_API_KEY` | ✅ | Gemini の API key (`AIza...`) |
| `GROQ_API_KEY` | ✅ | Groq の API key (`gsk_...`) |
| `TAVILY_API_KEY` | ✅ | Tavily の API key (`tvly-...`) |
| `STREAMLIT_PASSWORD` | ✅ | UI のパスワード (英数 16 文字以上推奨) |
| `LINE_CHANNEL_SECRET` | △ | LINE 連携時のみ |
| `LINE_CHANNEL_ACCESS_TOKEN` | △ | LINE 連携時のみ |
| `LINE_ALLOWED_USER_IDS` | △ | 許可する LINE User ID (カンマ区切り) |
| `STREAMLIT_BASE_URL` | △ | `https://<ユーザー>-<space名>.hf.space` (Flex Message の詳細ボタン用) |
| `APP_ENV` | — | `production` (デフォルト `development`) |

### 4. リポジトリを HF Space に push

```bash
# ローカル (5agents のクローン) で
git remote add hf https://huggingface.co/spaces/<HFユーザー名>/5agents
git fetch hf

# main を Space に push (HF は --force が必要なことが多い)
git push hf feature/huggingface-spaces-deploy:main
```

`huggingface/README.md` を Space ルートの `README.md` として読ませる必要があるため、
push 前に **1 度だけ** 以下を実行する:

```bash
cp huggingface/README.md README.hf.md
# Space リポジトリのトップにこの README.hf.md を README.md として置く必要があるが、
# 既存の README.md と衝突するため、HF Space 専用のブランチで運用するのが簡単。
```

> **推奨運用**: `hf-deploy` という別ブランチを切り、`huggingface/README.md` を
> ルートの `README.md` にリネームしてコミット → そのブランチを `hf main` に push。
> 普段の開発は `main` で行い、デプロイ時だけリベース。

### 5. ビルドログを見守る

Space ページの上部に **"Building"** が表示される。約 5〜10 分。

- **Logs** タブ → **Build** で Docker ビルドの進捗
- **Logs** タブ → **Container** で起動後の supervisord ログ

成功すると `https://<ユーザー>-<space>.hf.space/` が緑ランプになる。

### 6. 動作確認

```bash
# ヘルスチェック (nginx → FastAPI 経由)
curl https://<ユーザー>-<space>.hf.space/health
# → {"status":"ok"}

# Streamlit UI
open https://<ユーザー>-<space>.hf.space/
# → パスワード入力画面 → STREAMLIT_PASSWORD で入る
```

### 7. LINE Webhook URL を更新

LINE Developers Console → 該当 Channel → **Messaging API** タブ →
**Webhook URL** を以下に変更:

```
https://<ユーザー>-<space>.hf.space/line/webhook
```

→ **Verify** ボタンで `200 OK` が返ればOK。
→ **Webhook の利用** を ON。

これで Mac を起動しなくても LINE から質問できる。

---

## トラブルシュート

### ビルドが失敗する: `failed to solve: process ... did not complete successfully`

- `pyproject.toml` の `requires-python` と Dockerfile の `FROM python:3.11` の整合を確認
- `uv.lock` がコミットされているか確認 (`git ls-files uv.lock`)

### 起動はするが /health が 502 を返す

supervisord のログを確認:

1. Space → Logs → Container タブ
2. `fastapi.error.log` / `streamlit.error.log` の内容をチェック
3. よくある原因:
   - `GOOGLE_API_KEY` 未設定で起動時クラッシュ
   - `chromadb` の初回起動が遅い (60 秒待つ → 自動回復)

### LINE Webhook で 403

`LINE_CHANNEL_SECRET` の値が間違っている。Console の値とコピーし直す。

### Streamlit のパスワード画面が出ない

`STREAMLIT_PASSWORD` Secret が未設定 → 設定して **Restart Space**。

### Persistent Storage の容量を超えそう

`/data/agents.sqlite3` と `/data/chroma_db/` のサイズを確認:

```bash
# Space の Files タブ → terminal → 
du -sh /data/*
```

不要な実行ログは `RunLogger` の `cleanup_old_runs()` で消せる。

---

## 運用 Tips

### Sleep モード

CPU Basic は 48 時間無アクセスで自動 Sleep に入る (起動時に 30 秒程度の遅延)。
LINE webhook が来ると自動起動するので普段は気にしなくて OK。

### コスト管理

- Gemini Flash: 20 RPD (無料) → 1 質問あたり 2 calls なので 10 質問/日
- Groq Llama: 14,400 RPD (実質無制限)
- Tavily: 1,000 req/月

UI の右上で残数バッジを見られる。`get_flash_quota_status()` 参照。

### バックアップ

`/data/agents.sqlite3` を定期的にローカルに落としたい場合:

```bash
# HF CLI で Space に SSH
hf spaces ssh <ユーザー>/<space>
# →  scp で吸い出すか、HF Datasets repo に push して保管
```
