# 5agents on Hugging Face Spaces — マルチプロセス Docker イメージ
#
# ビルドの全体像:
#   1. python:3.11-slim をベースに、nginx + supervisor + curl などの最低限の OS パッケージを入れる
#   2. uv (Astral) を pip でインストール → uv で依存関係を /app/.venv に同期
#   3. アプリコードをコピー
#   4. nginx.conf / supervisord.conf / entrypoint.sh を所定の場所に配置
#   5. port 7860 (HF Spaces 仕様) を expose
#   6. entrypoint.sh が supervisord を起動
#
# HF Spaces はコンテナを root では動かせないが、Docker SDK の場合は
# 「USER 1000」推奨。本イメージはルート権限の supervisord が必要なので
# Spaces のデフォルト UID を尊重しつつ、書き込み先は /tmp と /data に逃がす。

FROM python:3.11-slim AS base

# ─────────── 1. OS パッケージ ───────────
# - nginx       : 7860 → uvicorn/streamlit のリバプロ
# - supervisor  : マルチプロセス管理
# - curl        : ヘルスチェック / uv インストール用
# - ca-certificates : LINE API / Tavily の TLS
# - tini はあえて使わず supervisord を PID 1 にして reaping させる
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        nginx \
        supervisor \
        curl \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

# ─────────── 2. uv で依存関係を解決 ───────────
# uv は Astral の Rust 製パッケージマネージャ。pip より 10〜100 倍速い。
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# 依存関係定義を先にコピーして Docker レイヤキャッシュを効かせる
COPY pyproject.toml uv.lock README.md ./

# src/ を「インストール可能パッケージ」として扱えるよう、空の src/__init__.py だけ
# 先に置いてビルドを通す (実コードは後でまとめてコピーする)
RUN mkdir -p src && touch src/__init__.py

# 依存関係を /app/.venv に同期 (--frozen で lock 厳守)
RUN uv sync --frozen --no-dev --no-install-project

# アプリコードを上書きコピー
COPY src/    ./src/

# 本体パッケージ (5agents) を editable で入れる
RUN uv sync --frozen --no-dev

# ─────────── 3. 設定ファイル配置 ───────────
COPY huggingface/nginx.conf       /etc/nginx/nginx.conf
COPY huggingface/supervisord.conf /etc/supervisor/supervisord.conf
COPY huggingface/entrypoint.sh    /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# ─────────── 4. HF Spaces 用パーミッション ───────────
# HF Spaces は非 root (uid=1000) でコンテナを起動するため、必要なディレクトリに
# 書き込み権限を付ける (chmod 777 はコンテナ内なのでセキュリティ的に許容範囲)
RUN mkdir -p /tmp /data \
    && chmod -R 777 /tmp /data \
    && chmod -R 755 /app

# ─────────── 5. ランタイム設定 ───────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app" \
    APP_ENV=production

# HF Spaces 規約: 7860 を expose
EXPOSE 7860

# ヘルスチェック (nginx → FastAPI /health で疎通確認)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fs http://127.0.0.1:7860/health || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
