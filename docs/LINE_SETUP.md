# LINE 連携セットアップガイド

> 5agents を LINE で使えるようにする手順。
> **コードはマージ済み**の前提で、ユーザーの環境設定だけをここに集約。

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

## やることリスト (約 40 分)

| # | 作業 | 所要 |
|---|---|---|
| 1 | **公式版 Tailscale (.pkg)** をインストール | 5 分 |
| 2 | Tailscale Funnel + HTTPS Certificates を有効化 | 5 分 |
| 3 | `tailscale funnel --bg 8080` で公開経路を確立 | 2 分 |
| 4 | LINE Business ID + Messaging API channel 作成 | 10 分 |
| 5 | `.env` に Channel Secret / Token / 自分の User ID を設定 | 5 分 |
| 6 | FastAPI webhook + Funnel auto-restart を launchd で常駐化 | 1 分 |
| 7 | LINE Console に Webhook URL を登録 + 検証 | 3 分 |
| 8 | 動作確認 (LINE で質問を送る) | 1 分 |

---

## ⚠️ 重要: App Store 版ではなく公式 .pkg 版を使う

Mac App Store 版 Tailscale は **CLI が使えない**（サンドボックス制約で `tailscale funnel` 等が動かない）ため、必ず **公式 .pkg 版** を使ってください。

**症状**: App Store 版だと `tailscale --version` で
```
Tailscale/BundleIdentifiers.swift:41: Fatal error: The current bundleIdentifier is unknown to the registry
```
というエラーが出ます。

## Step 1: 公式版 Tailscale (.pkg) をインストール

### 1-1. アカウント作成 + Mac にインストール

1. https://pkgs.tailscale.com/stable/#tailscale-pkg から **`.pkg`** ファイルをダウンロード
   - または https://tailscale.com/download/mac → **「Download for macOS (.pkg)」**
2. ダウンロードした `.pkg` をダブルクリックでインストール
3. 起動 → **「Log in」** → Google または GitHub アカウントでサインイン
4. メニューバーに Tailscale アイコンが現れる
5. **「Connect」** をクリック → 接続を確立

### 1-2. CLI が使えることを確認

```bash
which tailscale
# → /usr/local/bin/tailscale

tailscale --version
# → 1.96.x or 1.98.x など正常表示

tailscale status
# → 自分のマシンが表示される
```

### 1-3. ログイン時に自動起動する設定

- メニューバー Tailscale → **「Preferences...」** → **「Start Tailscale on login」** にチェック
- または System Settings → General → Login Items → Tailscale.app を追加

### 1-4. このマシンのドメインを確認

ブラウザで https://login.tailscale.com/admin/machines を開き、登録されているマシン (例: `koshiro-1`) と Tailnet 名 (例: `tail6a31ed.ts.net`) を確認。

→ 完全な公開ドメイン名は **`{machine}.{tailnet}.ts.net`** (例: `koshiro-1.tail6a31ed.ts.net`)

## Step 2: Tailscale Funnel + HTTPS Certificates を有効化

### 2-1. ACL で Funnel 機能を許可

1. https://login.tailscale.com/admin/acls/file を開く
2. ACL JSON に **`nodeAttrs`** セクションを追加 (既存にあればマージ):

```json
{
  "acls": [
    {"action": "accept", "src": ["*"], "dst": ["*:*"]}
  ],
  "nodeAttrs": [
    {
      "target": ["autogroup:member"],
      "attr":   ["funnel"]
    }
  ],
  "ssh": [
    {"action": "check", "src": ["autogroup:member"], "dst": ["autogroup:self"], "users": ["autogroup:nonroot", "root"]}
  ]
}
```

3. **「Save」** をクリック → 緑のトーストが出れば成功

### 2-2. HTTPS Certificates を有効化（重要・忘れがち）

LINE は HTTPS 必須。Tailscale は Let's Encrypt で自動取得しますが、**この機能はデフォルト無効**です。

1. https://login.tailscale.com/admin/dns を開く
2. ページ最下部までスクロール → **「HTTPS Certificates」** セクション
3. **「Enable HTTPS」** をクリック → 確認ダイアログで同意

> ✅ ボタンが「**Disable HTTPS...**」と表示されていれば、既に有効化済み

### 2-3. デバイスごとに Funnel を opt-in

1. ターミナルで `tailscale funnel --bg 8080` を一度実行
2. 「Funnel is not enabled on your tailnet. To enable, visit: https://login.tailscale.com/f/funnel?node=xxxxx」と URL が出る
3. その URL をブラウザで開く → **「Enable Funnel for this machine」** をクリック
4. もう一度 `tailscale funnel --bg 8080` → 今度は `Available on the internet:` と出るはず

## Step 3: Tailscale Funnel を起動

```bash
tailscale funnel --bg 8080
```

期待出力:
```
Available on the internet:
https://koshiro-1.tail6a31ed.ts.net/
|-- proxy http://127.0.0.1:8080
Funnel started and running in the background.
```

### 3-1. 証明書取得を明示的に実行 (推奨)

初回は証明書 propagation に時間がかかることがあります。明示的に取得しておくと安心：

```bash
tailscale cert koshiro-1.tail6a31ed.ts.net
# → Wrote public cert / Wrote private key と出れば OK
```

### 3-2. 公開疎通テスト (重要)

```bash
# Mac 内部ルーティングを迂回して公開 IP 経由で curl
PUBLIC_IP=$(dig +short koshiro-1.tail6a31ed.ts.net @8.8.8.8 | head -1)
curl --resolve koshiro-1.tail6a31ed.ts.net:443:${PUBLIC_IP} https://koshiro-1.tail6a31ed.ts.net/health -v 2>&1 | tail -10
```

期待: `HTTP/2 200` と `{"status":"ok"}` (※webhook が後で起動するので、この時点では `502 Bad Gateway` でも OK)

### 3-3. もし TLS エラー (SSL_ERROR_SYSCALL) が出たら

Tailscale 再起動後によく起きる。**完全リセット**で直る:

```bash
tailscale funnel --https=443 off
tailscale logout
tailscale up   # ブラウザで再ログイン
tailscale funnel --bg 8080
sleep 240      # 4 分待つ (証明書の propagation)
# 再度 curl で確認
```

## Step 4: LINE Messaging API channel 作成

### 4-1. LINE Business ID 有効化

1. https://account.line.biz/login にアクセス
2. **「LINE アカウントでログイン」** で個人 LINE と連携
3. 規約同意 → LINE Business ID が有効化される

### 4-2. Provider 作成

1. https://developers.line.biz/console/ にアクセス
2. **「Create a new provider」** → 名前は任意 (例: `koshiro-personal`)

### 4-3. Messaging API channel 作成

1. Provider の中で **「Create a new channel」** → **「Messaging API」**
2. 入力項目:
   - **Channel name**: `5agents`
   - **Category**: 個人
   - **Subcategory**: その他
   - その他は規約同意して作成

### 4-4. Channel Secret と Channel Access Token を取得

**⚠️ どちらもチャットに貼らず、メモ帳など安全な場所に一時保管**

#### Channel Secret
1. **「Basic settings」** タブ → 下部の **「Channel secret」** をコピー

#### Channel Access Token
1. **「Messaging API」** タブ → 一番下の **「Channel access token (long-lived)」** → **「Issue」** をクリック
2. 発行された長い文字列をコピー

> 💡 上記が表示されない場合、LINE Official Account Manager 側で API が未有効。Manager → Messaging API → 「Messaging APIを利用する」を先に有効化してください

### 4-5. 自動応答をオフ (重要)

LINE Official Account Manager (https://manager.line.biz) で:
1. 左メニュー **「応答設定」**
2. **「応答メッセージ」** を **オフ** に切替
3. **「あいさつメッセージ」** も任意でオフ

これで 5agents の回答と自動応答の二重送信を防げます。

## Step 5: `.env` に LINE 設定を追記

```bash
cd ~/Desktop/5agents
open -e .env
```

ファイル末尾に追記:

```
# --- LINE Messaging API ---
LINE_CHANNEL_SECRET=（メモした Channel Secret）
LINE_CHANNEL_ACCESS_TOKEN=（メモした Channel Access Token）
# 自分の User ID は Step 7 で取得して書き換えるので一旦空のまま
LINE_ALLOWED_USER_IDS=
WEBHOOK_PORT=8080
STREAMLIT_BASE_URL=http://localhost:8501
```

保存後、長さチェックで設定が反映されたか確認:

```bash
grep -E "^(LINE_CHANNEL_SECRET|LINE_CHANNEL_ACCESS_TOKEN)=" .env | awk -F= '{
  if (length($2) > 20) print $1 "= ✅ 長さ" length($2) "文字"
  else print $1 "= ❌ 値が不正"
}'
```

期待: 両方とも `✅ 長さ XX 文字` と表示。

## Step 6: FastAPI webhook + Tailscale Funnel を launchd で常駐化

```bash
cd ~/Desktop/5agents
bash scripts/install-autostart.sh --with-line
```

これで 3 つの launchd ジョブが登録されます:
- `com.5agents.streamlit` : Streamlit UI (常駐)
- `com.5agents.webhook`   : FastAPI webhook (常駐, 127.0.0.1:8080)
- `com.5agents.funnel`    : Tailscale Funnel (ログイン時に `tailscale funnel --bg 8080` 実行)

確認:
```bash
launchctl list | grep 5agents
# → 4 つ表示 (scheduler は --with-scheduler 付けたときのみ)

# webhook が起動しているか
sleep 5
curl http://localhost:8080/health
# → {"status":"ok"}
```

## Step 7: LINE Console に Webhook URL 登録 + 自分の User ID 取得

### 7-1. Webhook URL の設定

1. https://developers.line.biz/console/ → 作成した channel → **「Messaging API」** タブ
2. **「Webhook URL」** 欄に以下を入力:
   ```
   https://koshiro-1.tail6a31ed.ts.net/line/webhook
   ```
3. **「Update」** → **「Verify (検証)」** をクリック → **「Success (成功)」** が出れば疎通 OK ✅
4. **「Use webhook (Webhookの利用)」** を **オン** に

> ⚠️ **「Webhook URLに無効なホストが指定されています」と出たら、Step 2-2 (HTTPS Certificates) や Step 3-2 (証明書取得) が完了していない可能性大**

### 7-2. ボットを LINE 友だち追加

1. 「Messaging API」タブの上部 **QR コード** を LINE アプリで読み取り → 友だち追加

### 7-3. 自分の User ID を取得

1. LINE で 5agents に何でもいいので 1 つメッセージ送信（例: `test`）
2. Mac で:
   ```bash
   tail -30 ~/Desktop/5agents/logs/webhook.log | grep "user_id="
   ```
3. `user_id=Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` の **U + 32 文字** が自分の LINE User ID

### 7-4. `.env` を更新

```bash
open -e ~/Desktop/5agents/.env
```

`LINE_ALLOWED_USER_IDS=` の行を取得した User ID で更新:
```
LINE_ALLOWED_USER_IDS=Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

webhook を再起動して `.env` を反映:
```bash
launchctl unload ~/Library/LaunchAgents/com.5agents.webhook.plist
launchctl load ~/Library/LaunchAgents/com.5agents.webhook.plist
```

## Step 8: 動作確認

LINE で 5agents に質問を送る (例: `NVDA の最新の業績見通しを教えて`)。

期待される挙動:
1. **数秒以内**: 「🤔 5 エージェントが調査・分析中...」が即返信
2. **1〜2 分後**: 「結論+根拠」のメッセージが届く
3. **続けて**: 「リスク・反論+出典」のメッセージが届く
4. **最後に**: 「📊 Streamlit で詳細を見る」ボタン付き Flex Message

🎉 ここまで来れば LINE 連携完成です。

---

## 運用ノート

### Mac の電源状態と動作可否

| Mac の状態 | LINE 使える？ |
|---|---|
| 起動中 (ログイン済み) | ✅ |
| クラムシェルモード (外部モニター + 電源接続) | ✅ |
| 通常スリープ (ノート PC でフタ閉じる) | ❌ ネットワーク停止 |
| シャットダウン | ❌ |

24/7 で使いたいなら **クラムシェル運用**、または **VPS にデプロイ** を検討してください。

### Funnel が止まったときの復旧

スリープ復帰や Tailscale 再起動後に Funnel が止まる場合があります:

```bash
# 現状確認
tailscale funnel status
# → "No serve config" なら Funnel 停止中

# 復旧
tailscale funnel --bg 8080

# それでも繋がらない場合はリセット
tailscale logout
tailscale up
tailscale funnel --bg 8080
sleep 240   # 4 分待つ
```

### ログの確認

```bash
# webhook の通常運用ログ (LINE 受信履歴等)
tail -f logs/webhook.log

# webhook のエラーログ
tail -f logs/webhook.error.log

# Funnel の launchd ログ
tail -f logs/funnel.log
tail -f logs/funnel.error.log

# Streamlit のログ
tail -f logs/streamlit.log
```

## トラブルシューティング

| 症状 | 原因と対策 |
|---|---|
| LINE Console の Verify が「無効なホスト」 | Step 2-2 HTTPS Certificates 未有効化 or Step 3-2 証明書未取得 |
| Verify が Timeout | webhook が起動していない (`curl http://localhost:8080/health` で確認) |
| Verify は成功するが LINE 送信に応答なし | `LINE_ALLOWED_USER_IDS` が間違っている (許可外は静かに無視) |
| 応答が来てもエラーで終わる (LINE には何も届かない) | SSL 証明書エラーの可能性 (`tail logs/webhook.error.log`) |
| 上限到達メッセージが頻発 | Gemini Flash 無料枠 20 RPD 消費、Streamlit で残量確認 |
| FastAPI が起動しない | `tail logs/webhook.error.log`、`.env` 未設定や uv sync 忘れが多い |
| `tailscale: command not found` | App Store 版を使ってる。公式 .pkg 版に切替 (Step 1) |
| `Tailscale is stopped.` | Tailscale.app が起動してない、メニューバーから起動 |

## セキュリティの要点

このセットアップで守られているもの:
- ✅ LINE 署名検証で偽 webhook を即破棄 (`X-Line-Signature` チェック)
- ✅ 許可ユーザー以外の User ID は静かに無視 (個人ボットを露呈しない)
- ✅ Tailscale Funnel が公開する経路は **8080 ポートのみ**
- ✅ Gemini Quota guard が同時に効くので、攻撃者が大量送信しても API 課金は発生しない

守られていないもの (許容範囲):
- ⚠️ 公開 URL が知れたら HTTPS POST で任意リクエストが送られうる
  → 署名検証で全部 403 になるので問題なし
- ⚠️ Tailscale アカウントのセキュリティに依存
  → 2FA 必須、Tailscale 側で Funnel 解除も即時可能
