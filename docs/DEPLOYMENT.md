# デプロイ・常時稼働ガイド

> 5agents を毎朝レポート生成や常時起動の自分専用 AI として運用するためのガイド。

選択肢を 3 つ用意しています。**個人利用ならまず「案 A: Mac ローカル + launchd」を推奨**します（追加コスト 0 円・最低限の手間）。

---

## 案 A: Mac ローカル + launchd ⭐推奨

**メリット**:
- コスト 0 円、外部サービス契約不要、データ・API キーは完全ローカル
- ログイン即起動 → ブラウザのブックマークで一発アクセス
- クラッシュしても launchd が自動再起動 (KeepAlive)

**デメリット**:
- Mac を起動・ログインしている時間にのみ動作
- 他デバイス (スマホ等) からはアクセス不可 (→ LINE 連携時に案 B 検討)

### ワンコマンドセットアップ (推奨)

リポジトリに含まれる install スクリプトで **Streamlit 常駐 + 毎朝 9:00 のスケジューラ** を 1 コマンドで登録できます。

```bash
cd ~/Desktop/5agents
bash scripts/install-autostart.sh --with-scheduler
```

実行内容:
1. `~/Library/LaunchAgents/com.5agents.streamlit.plist` を生成して `launchctl load` (Streamlit 常駐)
2. `~/Library/LaunchAgents/com.5agents.scheduler.plist` を生成して `launchctl load` (毎朝 9:00)
3. `launchctl list` で登録状況を表示
4. ブラウザ用 URL と停止コマンドを案内

成功すると **`http://localhost:8501`** に Streamlit が常駐します。ブラウザでブックマーク登録すれば次から快適。

> **ヒント**: `bash scripts/install-autostart.sh` (引数なし) なら Streamlit のみ。scheduler を後から足したくなったら `--with-scheduler` で再実行 OK (冪等)。

### 動作確認

```bash
# 登録された launchd ジョブを確認
launchctl list | grep 5agents
# → -    0    com.5agents.streamlit
# → -    0    com.5agents.scheduler

# Streamlit のログを追う
tail -f ~/Desktop/5agents/logs/streamlit.log

# ブラウザで http://localhost:8501 を開いて UI 表示
```

### よくある運用コマンド

```bash
# Streamlit を一時停止
launchctl unload ~/Library/LaunchAgents/com.5agents.streamlit.plist

# 再度起動
launchctl load ~/Library/LaunchAgents/com.5agents.streamlit.plist

# 完全アンインストール (Streamlit + scheduler 両方)
bash scripts/install-autostart.sh --uninstall
```

### 通知の設定 (任意、scheduler 用)

#### Discord Webhook

1. 通知を受け取りたい Discord サーバー → サーバー設定 → 連携サービス
2. 「ウェブフック」→ 「新しいウェブフック」
3. 名前と通知先チャンネルを設定 → URL をコピー
4. `.env` の `DISCORD_WEBHOOK_URL=` に書き込み

> ⚠️ **LINE Notify は 2025/3/31 でサービス終了済み**。LINE 連携が欲しい場合は LINE Messaging API (Webhook) が必要で、これは **案 B (Cloudflare Tunnel + Access)** と組み合わせて別途設計します。

### scheduler の動作確認 (dry-run)

```bash
uv run python -m src.scheduler --dry-run
```

→ ウォッチリストの全質問が順次処理され、結果が標準出力に表示されます（通知は送られない）。
無料枠が足りない場合は冒頭でガードが効いてスキップされます。

### plist の構成内訳

`scripts/com.5agents.streamlit.plist.template` がテンプレート。install スクリプトが以下を置換して生成:

| プレースホルダ | 置換内容 (例) |
|---|---|
| `{{PROJECT_DIR}}` | `/Users/yamadakoshiro/Desktop/5agents` |
| `{{UV_PATH}}` | `/opt/homebrew/bin/uv` |

主な設定:
- `RunAtLoad`: ログイン時に自動起動
- `KeepAlive`: クラッシュしても再起動
- `ThrottleInterval=10`: 再起動ループ防止
- `--server.address 127.0.0.1`: localhost のみ listen (外部公開しない)
- `--server.headless true`: ブラウザを自動で開かない (ポップアップ抑制)
- `--server.fileWatcherType none`: ファイル変更 reload を無効化 (リソース節約)

> ✏️ 開発中にコード変更を即反映したい時は plist を unload して `uv run streamlit run src/app.py` で手動起動してください。

---

## 案 B: 軽量 VPS (さくらの VPS 等)

**メリット**: Mac を常時起動しなくて良い・複数デバイスから Streamlit にアクセス可能
**デメリット**: 月数百〜千円のコスト、運用知識が必要

### 1. VPS を契約 (例: さくらの VPS 1G プラン)

### 2. SSH 接続して環境構築

```bash
# Ubuntu 24.04 想定
sudo apt update && sudo apt install -y python3.11 git
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/koshiro-y-0/5agents.git
cd 5agents
uv sync

cp .env.example .env
# .env を編集して API キーを設定
cp watchlist.example.txt watchlist.txt
```

### 3. systemd で常時稼働

`/etc/systemd/system/5agents-streamlit.service`:

```ini
[Unit]
Description=5agents Streamlit
After=network.target

[Service]
Type=simple
User=koshiro
WorkingDirectory=/home/koshiro/5agents
ExecStart=/home/koshiro/.local/bin/uv run streamlit run src/app.py --server.address 0.0.0.0 --server.port 8501
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now 5agents-streamlit
```

### 4. cron で定期実行

```bash
crontab -e
# 以下を追加 (毎朝 9:00 JST)
0 9 * * * cd /home/koshiro/5agents && /home/koshiro/.local/bin/uv run python -m src.scheduler >> logs/scheduler.log 2>&1
```

### 5. nginx + Basic 認証で保護 (重要)

VPS は外部公開されているので **必ず認証をかけること**。例:

```nginx
# /etc/nginx/sites-available/5agents
server {
    listen 80;
    server_name 5agents.example.com;
    auth_basic "Restricted";
    auth_basic_user_file /etc/nginx/.htpasswd;
    location / {
        proxy_pass http://localhost:8501;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

```bash
sudo apt install apache2-utils
sudo htpasswd -c /etc/nginx/.htpasswd koshiro
sudo ln -s /etc/nginx/sites-available/5agents /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

可能なら Let's Encrypt で HTTPS 化も:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d 5agents.example.com
```

---

## 案 C: AWS Lambda + EventBridge

**メリット**: 完全サーバレス・無料枠で収まる可能性
**デメリット**: Streamlit は動かせない (定期実行のみ)、ChromaDB の永続化に工夫が必要

> 個人利用では案 A/B のほうがシンプルなので、Lambda 化はやらないこと推奨。
> どうしても Lambda にしたい場合は別途設計を検討（Container イメージで Python ランタイム + ChromaDB を EFS にマウント等）。

---

## コスト監視

### Google Cloud Billing アラート設定 (必須)

1. https://console.cloud.google.com/billing → Budgets & alerts
2. 「予算を作成」→ 月次予算を **¥500** 等に設定
3. アラートを 50%, 80%, 100% で設定 → メール通知

### Tavily の使用量確認

https://app.tavily.com/home → API Usage タブで月間リクエスト数を確認。
無料枠（1,000 req/月）を超えそうなら警告メールが届く。

---

## トラブルシューティング

| 症状 | 確認ポイント |
|---|---|
| launchd で実行されない | `launchctl list` で `0` が返るか、`logs/scheduler.error.log` に何が出ているか |
| API レート超過 | `data/agents.sqlite3` を SQL で確認 (`SELECT COUNT(*) FROM runs WHERE date(started_at) = date('now')`) |
| 通知が来ない | `uv run python -m src.scheduler --dry-run` で標準出力にだけは出るか確認 → 通知設定の `.env` を再確認 |
| Streamlit が固まる | `data/chroma_db` を一旦削除して再起動。ChromaDB が壊れている可能性 |

---

## 運用チェックリスト

- [ ] ウォッチリスト `watchlist.txt` を作成・編集
- [ ] 通知チャネルを `.env` に設定 (LINE か Discord か両方)
- [ ] `uv run python -m src.scheduler --dry-run` で動作確認
- [ ] 案 A/B/C のいずれかで定期実行を登録
- [ ] Google Cloud Billing アラートを月次予算で設定
- [ ] 数日運用してログ (`logs/scheduler.log`) を確認
