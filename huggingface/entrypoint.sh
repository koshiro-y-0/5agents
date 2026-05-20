#!/usr/bin/env bash
# 5agents on Hugging Face Spaces — エントリポイント
#
# 役割:
#   1. /data (Persistent Storage) のサブディレクトリを用意して書き込み権限を確保
#   2. SQLite / ChromaDB 用パスを export
#   3. supervisord を foreground で起動 (PID 1)
#
# HF Spaces の挙動メモ:
#   - Persistent Storage を有効にすると /data がマウントされ、再起動後もファイルが残る
#   - 無効の場合は /tmp/data に書き出すフォールバック (再起動でロスト)

set -euo pipefail

log() { printf '[entrypoint] %s\n' "$*"; }

# ───────── 永続化ディレクトリ ─────────
# Persistent Storage 有効 → /data が書き込み可
# 無効                   → /tmp/data に逃がす
if [ -w /data ]; then
    DATA_DIR=/data
    log "Persistent Storage 検出: /data を使用"
else
    DATA_DIR=/tmp/data
    log "/data は書き込み不可。/tmp/data にフォールバック (再起動でロスト)"
fi

mkdir -p "$DATA_DIR/chroma_db"
mkdir -p "$DATA_DIR/logs"

# config.py が参照する環境変数として export
export DATA_DIR
export CHROMA_PERSIST_DIR="$DATA_DIR/chroma_db"
export SQLITE_PATH="$DATA_DIR/runs.sqlite"

log "DATA_DIR=$DATA_DIR"
log "CHROMA_PERSIST_DIR=$CHROMA_PERSIST_DIR"
log "SQLITE_PATH=$SQLITE_PATH"

# ───────── /tmp の nginx 用ディレクトリ ─────────
mkdir -p /tmp/nginx-client-body /tmp/nginx-proxy /tmp/nginx-fastcgi /tmp/nginx-uwsgi /tmp/nginx-scgi

# ───────── 必須環境変数の sanity check (Secrets 設定漏れの早期検知) ─────────
missing=()
for key in GOOGLE_API_KEY GROQ_API_KEY TAVILY_API_KEY; do
    if [ -z "${!key:-}" ]; then
        missing+=("$key")
    fi
done
if [ ${#missing[@]} -gt 0 ]; then
    log "⚠️  以下の Secrets が未設定です: ${missing[*]}"
    log "    HF Space の Settings → Variables and secrets で追加してください"
fi

# LINE は任意 (UI だけ使う場合は未設定でも起動できる)
if [ -z "${LINE_CHANNEL_SECRET:-}" ] || [ -z "${LINE_CHANNEL_ACCESS_TOKEN:-}" ]; then
    log "ℹ️  LINE_CHANNEL_SECRET/ACCESS_TOKEN 未設定 (LINE 連携を使わないなら無視)"
fi

# Streamlit パスワード未設定の警告
if [ -z "${STREAMLIT_PASSWORD:-}" ]; then
    log "⚠️  STREAMLIT_PASSWORD 未設定 — UI が誰でも閲覧可能になります"
fi

# ───────── supervisord 起動 ─────────
log "supervisord を起動..."
exec /usr/bin/supervisord -c /etc/supervisor/supervisord.conf
