#!/usr/bin/env bash
# 5agents auto-start インストーラ (macOS launchd)
#
# 使い方:
#   bash scripts/install-autostart.sh            # Streamlit のみインストール
#   bash scripts/install-autostart.sh --with-scheduler  # Scheduler も同時登録
#   bash scripts/install-autostart.sh --uninstall        # アンインストール
#
# 役割:
#   1. scripts/com.5agents.streamlit.plist.template の {{...}} を実環境で置換
#   2. ~/Library/LaunchAgents/ に配置
#   3. launchctl load で常駐開始
#
# 既存の plist があれば一旦 unload してから上書きするので冪等。

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
STREAMLIT_LABEL="com.5agents.streamlit"
STREAMLIT_PLIST="$LAUNCH_AGENTS_DIR/$STREAMLIT_LABEL.plist"
SCHEDULER_LABEL="com.5agents.scheduler"
SCHEDULER_PLIST="$LAUNCH_AGENTS_DIR/$SCHEDULER_LABEL.plist"

UV_PATH="$(command -v uv || echo /opt/homebrew/bin/uv)"

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

uninstall_all() {
    log "全 launchd ジョブをアンインストール..."
    unload_if_loaded "$STREAMLIT_PLIST"
    unload_if_loaded "$SCHEDULER_PLIST"
    rm -f "$STREAMLIT_PLIST" "$SCHEDULER_PLIST"
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
    --with-scheduler)
        install_streamlit
        install_scheduler
        verify_install
        ;;
    "")
        install_streamlit
        verify_install
        ;;
    *)
        err "不明な引数: $1"
        echo "Usage: $0 [--with-scheduler|--uninstall]"
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
