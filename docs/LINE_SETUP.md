# LINE 連携セットアップガイド

> 5agents を LINE で使えるようにする手順。
> **コードは PR #12 でマージ済みの前提**。ユーザーの環境設定だけをここに集約。

## 全体構成

```
[あなたの LINE] → [LINE Platform] → [Tailscale Funnel HTTPS]
                                          ↓
                                   [Mac の FastAPI :8080]
                                          ↓ (BackgroundTask)
                                   [5agents.answer()]
                                          ↓
                                   [LINE Push API] → [あなたの LINE]
```

## やることリスト (約 30 分)

| # | 作業 | 所要 |
|---|---|---|
| 1 | Tailscale をインストールしてアカウント作成 | 5 分 |
| 2 | Tailscale Funnel を有効化 | 3 分 |
| 3 | LINE Business ID + Messaging API channel 作成 | 10 分 |
| 4 | `.env` に Channel Secret / Token / 自分の User ID を設定 | 5 分 |
| 5 | FastAPI を launchd で常駐化 | 1 分 |
| 6 | Tailscale Funnel で 8080 を公開 | 1 分 |
| 7 | LINE Console に Webhook URL を登録 + 検証 | 3 分 |
| 8 | 動作確認 (LINE で質問を送る) | 1 分 |

---

## Step 1: Tailscale インストール

### 1-1. アカウント作成 + Mac クライアント install

1. https://tailscale.com/download/mac から **Mac App Store 版**をインストール
2. 起動 → 「Sign in」→ **Google アカウントでログイン**（後で他デバイス追加時もこのアカウント）
3. 「Connect」ボタンを押して接続を確立
4. メニューバーに Tailscale アイコンが現れる

### 1-2. このマシンの Tailscale ドメインを確認

メニューバーアイコンをクリック → 上部にこのマシンの名前 (例: `koshiro-4`) と Tailscale IP (例: `100.x.x.x`) が表示される。

「Open admin console」を選択して https://login.tailscale.com/admin/machines を開き、**Magic DNS** で自動付与されるドメインを確認:
```
koshiro-4.tail-xxxx.ts.net
```
これがあなたのマシンの公開予定ドメインです。

## Step 2: Tailscale Funnel を有効化

Funnel はデフォルト無効。Admin Console で許可する必要あり。

### 2-1. Admin Console で Funnel を許可

1. https://login.tailscale.com/admin/acls/file を開く
2. ACL JSON の中に次の `nodeAttrs` を追加 (既存があればマージ):

```json
{
  "nodeAttrs": [
    {
      "target": ["autogroup:member"],
      "attr":   ["funnel"]
    }
  ]
}
```

3. 「Save」をクリック

### 2-2. ローカルで Funnel を起動 (一旦テスト)

```bash
# まず Streamlit / scheduler が動いていることを確認
launchctl list | grep 5agents

# Funnel を手動起動 (テスト用)
tailscale funnel --bg 8080
```

→ `https://koshiro-4.tail-xxxx.ts.net` がアクセス可能になる (FastAPI は次のステップで起動)。

> 一旦止めるには `tailscale funnel --https=443 off`。本番運用では `launchd` で常駐化します (Step 6 で説明)。

## Step 3: LINE Messaging API channel 作成

### 3-1. LINE Business ID 作成

1. https://account.line.biz/login にアクセス
2. **個人 LINE アカウントでログイン** (新規 ID 作成は不要、既存 LINE アカウントを連携)
3. 案内に従って LINE Business ID を有効化

### 3-2. Provider 作成

1. https://developers.line.biz/console/ にアクセス
2. 「Create a new provider」→ 名前は任意 (例: `koshiro-personal`)

### 3-3. Messaging API channel 作成

1. 作成した Provider の中で「Create a new channel」→ **「Messaging API」**を選択
2. 入力項目:
   - **Channel name**: `5agents` (任意)
   - **Channel description**: `個人用 5 エージェント調査ボット` (任意)
   - **Category**: 「個人」「テクノロジー」など
   - **Subcategory**: 任意
   - その他は規約同意して作成

### 3-4. Channel Secret と Channel Access Token を取得

1. channel 設定画面 → **「Basic settings」**タブ:
   - **Channel secret** をコピー (後で `.env` に貼る)
2. **「Messaging API」**タブ:
   - 一番下の「Channel access token」→ **「Issue」**をクリック → 表示された long-lived token をコピー

> ⚠️ **両方ともチャットには絶対貼らない**。`.env` に直接書き込んでください。

### 3-5. 不要な機能をオフ (推奨)

「Messaging API」タブで以下をオフ:
- **Auto-reply messages**: オフ (5agents が返すので、自動応答と二重になる)
- **Greeting messages**: お好みで

「Messaging API」タブの「LINE Official Account features」リンクから設定変更可能。

## Step 4: .env に LINE 設定を追記

```bash
cd ~/Desktop/5agents
open -e .env
```

以下を追記 (`Channel secret` / `Channel access token` は Step 3-4 で取得した値):

```
LINE_CHANNEL_SECRET=（Step 3-4 で取得した Channel Secret を貼る）
LINE_CHANNEL_ACCESS_TOKEN=（Step 3-4 で取得した Channel Access Token を貼る）
LINE_ALLOWED_USER_IDS=（Step 7 で取得するので一旦空のままで OK）
WEBHOOK_PORT=8080
STREAMLIT_BASE_URL=http://localhost:8501
```

## Step 5: FastAPI を launchd で常駐化

```bash
cd ~/Desktop/5agents
bash scripts/install-autostart.sh --with-line
```

これで以下 2 つが登録される:
- `com.5agents.streamlit` (既存) localhost:8501
- `com.5agents.webhook` (新規) localhost:8080

確認:
```bash
launchctl list | grep 5agents
tail -f logs/webhook.log
# → "Uvicorn running on http://127.0.0.1:8080" が出れば成功
```

簡易疎通テスト:
```bash
curl http://localhost:8080/health
# → {"status":"ok"}
```

## Step 6: Tailscale Funnel を launchd で常駐化 (任意だが推奨)

Step 2-2 で起動した `tailscale funnel --bg 8080` はそのまま使えますが、Mac 再起動後も自動で立ち上がるよう launchd に登録すると安心。

```bash
tailscale funnel --bg 8080
# `--bg` はそのままにすると Tailscale が次回起動時に自動復元する
```

Tailscale 自体が macOS の Login Items に登録されているので、Mac ログイン時に Tailscale が起動 → Funnel 設定が復元される流れ。

## Step 7: LINE Console に Webhook URL を登録

### 7-1. Webhook URL の設定

1. https://developers.line.biz/console/ → 作成した channel
2. 「Messaging API」タブ → 「Webhook settings」
3. **Webhook URL** に以下を入力:
   ```
   https://koshiro-4.tail-xxxx.ts.net/line/webhook
   ```
   (Step 1-2 で確認したあなたの Tailscale ドメイン)
4. 「Update」→ 「Verify」をクリック → **Success** が出れば成功 ✅
5. **Use webhook** を **オン** にする

### 7-2. 自分の User ID を取得

最初のメッセージ送信時にログから取得します。

1. 作成したボットの **「Messaging API」**タブ → 一番上の **QR コード** を LINE で読み取って友だち追加
2. LINE で何でもいいのでメッセージを送る (例: 「test」)
3. Mac で:
   ```bash
   tail -20 ~/Desktop/5agents/logs/webhook.log | grep "user_id="
   ```
4. `user_id=Uxxxxxxxxxxxxxxx text=test...` の `Uxxxxxxxxxxxxxxx` が **あなたの LINE User ID**

### 7-3. .env を更新

```bash
open -e ~/Desktop/5agents/.env
```

`LINE_ALLOWED_USER_IDS=` の行を取得した User ID で更新:
```
LINE_ALLOWED_USER_IDS=Uxxxxxxxxxxxxxxx
```

webhook を再起動:
```bash
launchctl unload ~/Library/LaunchAgents/com.5agents.webhook.plist
launchctl load ~/Library/LaunchAgents/com.5agents.webhook.plist
```

## Step 8: 動作確認

LINE で 5agents ボットにメッセージを送る (例: 「IONQ の最新の決算」)。

期待される挙動:
1. **数秒以内**: 「🤔 5 エージェントが調査・分析中...」が即返信される
2. **1〜2 分後**: メッセージ 1 (結論 + 根拠) が届く
3. **続けて**: メッセージ 2 (リスク・反論 + 出典) が届く
4. **最後に**: 「📊 Streamlit で詳細を見る」ボタン付き Flex Message
   (このボタンは Mac でしか開けない `http://localhost:8501` を指す)

完成です 🎉

---

## トラブルシューティング

| 症状 | 確認方法・対策 |
|---|---|
| LINE Console の Verify が失敗 | `curl https://your-domain.ts.net/line/webhook -X POST` で 403 か 503 が返るか確認。`tailscale funnel status` で 8080 が公開されているか。 |
| メッセージを送っても返事なし | `tail -f logs/webhook.log` でリクエストが届いているか確認。`LINE_ALLOWED_USER_IDS` が間違っていると静かに無視される。 |
| Push メッセージが届かない | `Channel Access Token` が正しいか再確認。有効期限切れの可能性 (long-lived token は通常切れないが) |
| 上限到達メッセージが頻発する | Gemini 無料枠 20 RPD を消費している。Streamlit のダッシュボードで使用量を確認 |
| FastAPI が起動しない | `tail logs/webhook.error.log` で詳細確認。`uv sync` し忘れ or .env 未設定が多い |

## セキュリティの要点

このセットアップで守られているもの:
- ✅ LINE 署名検証で偽 webhook を即破棄 (`X-Line-Signature` チェック)
- ✅ 許可ユーザー以外の User ID は静かに無視 (個人ボットを露呈しない)
- ✅ Tailscale Funnel が公開する経路は **8080 ポートのみ**、他のローカルサービスは公開されない
- ✅ Gemini Quota guard が同時に効くので、攻撃者が大量送信しても API 課金は発生しない (上限到達で停止)

守られていないもの (許容範囲):
- ⚠️ 公開 URL が知れたら、HTTPS POST で任意リクエストが送られうる
  → 署名検証で全部 403 になるので問題なし
- ⚠️ Tailscale アカウントのセキュリティに依存
  → 2FA 必須、Tailscale 側で Funnel 解除も即時可能
