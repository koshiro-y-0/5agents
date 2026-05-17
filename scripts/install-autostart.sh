#!/usr/bin/env bash
# 5agents auto-start インストーラ (macOS launchd)
#
# 使い方:
#   bash scripts/install-autostart.sh                    # Streamlit のみ
#   bash scripts/install-autostart.sh --with-scheduler   # + 毎朝 9:00 scheduler
#   bash scripts/install-autostart.sh --with-line        # + LINE webhook (FastAPI :8080) + Tailscale Funnel
#   bash scripts/install-autostart.sh --all              # 全部入り
#   bash scripts/install-autostart.sh --uninstall        # 全部削除
#
# 役割:
#   1. scripts/*.plist.template の {{...}} を実環境で置換
#   2. ~/Library/LaunchAgents/ に配置
#   3. launchctl load で常駐開始
#
# 登録される launchd ジョブ:
#   com.5agents.streamlit  : Streamlit UI (常駐, 127.0.0.1:8501)
#   com.5agents.scheduler  : 毎朝 9:00 に scheduler 実行 (--with-scheduler / --all)
#   com.5agents.webhook    : FastAPI webhook (常駐, 127.0.0.1:8080) (--with-line / --all)
#   com.5agents.funnel     : Tailscale Funnel (ログイン時に --bg 8080 実行) (--with-line / --all)
#
# 既存の plist があれば一旦 unload してから上書きするので冪等。

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
STREAMLIT_LABEL="com.5agents.streamlit"
STREAMLIT_PLIST="$LAUNCH_AGENTS_DIR/$STREAMLIT_LABEL.plist"
SCHEDULER_LABEL="com.5agents.scheduler"
SCHEDULER_PLIST="$LAUNCH_AGENTS_DIR/$SCHEDULER_LABEL.plist"
WEBHOOK_LABEL="com.5agents.webhook"
WEBHOOK_PLIST="$LAUNCH_AGENTS_DIR/$WEBHOOK_LABEL.plist"
WEBHOOK_PORT="${WEBHOOK_PORT:-8080}"
FUNNEL_LABEL="com.5agents.funnel"
FUNNEL_PLIST="$LAUNCH_AGENTS_DIR/$FUNNEL_LABEL.plist"

UV_PATH="$(command -v uv || echo /opt/homebrew/bin/uv)"
TAILSCALE_PATH="$(command -v tailscale || echo /usr/local/bin/tailscale)"

# --- ヘルパー ---
log()  { printf '\033[36m[install]\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m[ok]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[warn]\033[0m %s\n' "$*"; }
err()  { printf '\033[31m[err]\033[0m %s\n' "$*"; }

unload_if_loaded() {
    local plist="$1"
    if [ -f "$plist" ]; then
        launchctl unload "$plist" 2>/dev/null || true
    fi
}

install_streamlit() {
    log "Streamlit auto-start を準備..."
    log "  PROJECT_DIR = $PROJECT_DIR"
    log "  UV_PATH     = $UV_PATH"

    mkdir -p "$LAUNCH_AGENTS_DIR" "$PROJECT_DIR/logs"

    unload_if_loaded "$STREAMLIT_PLIST"

    # テンプレートのプレースホルダを置換
    sed -e "s|{{PROJECT_DIR}}|$PROJECT_DIR|g" \
        -e "s|{{UV_PATH}}|$UV_PATH|g" \
        "$PROJECT_DIR/scripts/com.5agents.streamlit.plist.template" \
        > "$STREAMLIT_PLIST"

    launchctl load "$STREAMLIT_PLIST"
    ok "$STREAMLIT_LABEL を登録しました"
}

install_scheduler() {
    log "Scheduler auto-start を準備..."

    mkdir -p "$LAUNCH_AGENTS_DIR" "$PROJECT_DIR/logs"

    unload_if_loaded "$SCHEDULER_PLIST"

    # Scheduler 用 plist (既存の docs/DEPLOYMENT.md と同じ内容を生成)
    cat > "$SCHEDULER_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$SCHEDULER_LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$UV_PATH</string>
        <string>run</string>
        <string>python</string>
        <string>-m</string>
        <string>src.scheduler</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/scheduler.log</string>
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/scheduler.error.log</string>
    <key>RunAtLoad</key>
    <false/>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
PLIST

    launchctl load "$SCHEDULER_PLIST"
    ok "$SCHEDULER_LABEL を登録しました (毎朝 9:00 実行)"
}

install_webhook() {
    log "LINE Webhook auto-start を準備..."
    log "  WEBHOOK_PORT = $WEBHOOK_PORT"

    mkdir -p "$LAUNCH_AGENTS_DIR" "$PROJECT_DIR/logs"

    unload_if_loaded "$WEBHOOK_PLIST"

    sed -e "s|{{PROJECT_DIR}}|$PROJECT_DIR|g" \
        -e "s|{{UV_PATH}}|$UV_PATH|g" \
        -e "s|{{PORT}}|$WEBHOOK_PORT|g" \
        "$PROJECT_DIR/scripts/com.5agents.webhook.plist.template" \
        > "$WEBHOOK_PLIST"

    launchctl load "$WEBHOOK_PLIST"
    ok "$WEBHOOK_LABEL を登録しました (localhost:$WEBHOOK_PORT)"
}

install_funnel() {
    log "Tailscale Funnel auto-restart を準備..."
    log "  TAILSCALE_PATH = $TAILSCALE_PATH"
    log "  PORT           = $WEBHOOK_PORT"

    if [ ! -x "$TAILSCALE_PATH" ]; then
        warn "tailscale CLI が見つかりません: $TAILSCALE_PATH"
        warn "Tailscale 公式版 (.pkg) をインストールしてから再実行してください"
        warn "詳細: docs/LINE_SETUP.md"
        return 1
    fi

    mkdir -p "$LAUNCH_AGENTS_DIR" "$PROJECT_DIR/logs"

    unload_if_loaded "$FUNNEL_PLIST"

    sed -e "s|{{PROJECT_DIR}}|$PROJECT_DIR|g" \
        -e "s|{{TAILSCALE_BIN}}|$TAILSCALE_PATH|g" \
        -e "s|{{PORT}}|$WEBHOOK_PORT|g" \
        "$PROJECT_DIR/scripts/com.5agents.funnel.plist.template" \
        > "$FUNNEL_PLIST"

    launchctl load "$FUNNEL_PLIST"
    ok "$FUNNEL_LABEL を登録しました (Funnel ポート $WEBHOOK_PORT を公開)"
    log "ログイン毎に 'tailscale funnel --bg $WEBHOOK_PORT' が自動実行されます"
}

uninstall_all() {
    log "全 launchd ジョブをアンインストール..."
    unload_if_loaded "$STREAMLIT_PLIST"
    unload_if_loaded "$SCHEDULER_PLIST"
    unload_if_loaded "$WEBHOOK_PLIST"
    unload_if_loaded "$FUNNEL_PLIST"
    rm -f "$STREAMLIT_PLIST" "$SCHEDULER_PLIST" "$WEBHOOK_PLIST" "$FUNNEL_PLIST"
    ok "削除完了"
}

verify_install() {
    log "登録状態を確認..."
    if launchctl list | grep -q "5agents"; then
        launchctl list | grep "5agents"
    else
        warn "登録された 5agents ジョブが見つかりません"
    fi
}

# --- main ---
case "${1:-}" in
    --uninstall)
        uninstall_all
        ;;
    --all)
        install_streamlit
        install_scheduler
        install_webhook
        install_funnel
        verify_install
        ;;
    --with-scheduler)
        install_streamlit
        install_scheduler
        verify_install
        ;;
    --with-line)
        install_streamlit
        install_webhook
        install_funnel
        verify_install
        ;;
    "")
        install_streamlit
        verify_install
        ;;
    *)
        err "不明な引数: $1"
        echo "Usage: $0 [--all|--with-scheduler|--with-line|--uninstall]"
        exit 1
        ;;
esac

cat <<TIP

────────────────────────────────────────────────────
✅ セットアップ完了

▶ アクセス先: http://localhost:8501

ブラウザでブックマーク登録すると次から快適です。
Mac を再起動 / ログアウトしても次回ログイン時に自動再起動します。

ログ確認:
  tail -f $PROJECT_DIR/logs/streamlit.log

停止:
  launchctl unload $STREAMLIT_PLIST

完全アンインストール:
  bash scripts/install-autostart.sh --uninstall
────────────────────────────────────────────────────
TIP
