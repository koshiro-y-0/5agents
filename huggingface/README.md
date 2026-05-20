---
title: 5agents
emoji: 🤖
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
suggested_storage: small
pinned: false
short_description: 5 体構成のマルチエージェント調査 AI (LINE + Web UI)
---

# 5agents on Hugging Face Spaces

5 つの LLM エージェント (Researcher / Analyst / Critic / Fact-checker / Finalizer) が
連携して質問に回答する汎用調査 AI。LINE と Web の両方からアクセスできる。

## デプロイ手順

1. **Persistent Storage を有効化** — Settings → Storage で "Small (20 GB)" を選ぶ
   (履歴を `/data` に永続化するため)
2. **Secrets を登録** — Settings → Variables and secrets で以下をセット:
   - `GOOGLE_API_KEY` (Gemini API key)
   - `GROQ_API_KEY` (Groq API key)
   - `TAVILY_API_KEY` (Web 検索)
   - `STREAMLIT_PASSWORD` (UI パスワード)
   - `LINE_CHANNEL_SECRET` / `LINE_CHANNEL_ACCESS_TOKEN` (LINE を使うなら)
   - `LINE_ALLOWED_USER_IDS` (許可する LINE User ID をカンマ区切り)
   - `STREAMLIT_BASE_URL` (この Space の URL、Flex Message の詳細ボタン用)
3. **LINE Console** で Webhook URL に
   `https://<ユーザー名>-<スペース名>.hf.space/line/webhook` を設定

## アクセス先

- **UI**     : `https://<ユーザー名>-<スペース名>.hf.space/`
- **LINE Webhook** : `https://<ユーザー名>-<スペース名>.hf.space/line/webhook`
- **ヘルスチェック** : `https://<ユーザー名>-<スペース名>.hf.space/health`

詳しいセットアップ手順とトラブルシュートは
[`docs/HF_SPACES_DEPLOY.md`](https://github.com/koshiro-y-0/5agents/blob/main/docs/HF_SPACES_DEPLOY.md) を参照。
