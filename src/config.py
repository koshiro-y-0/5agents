"""アプリケーション設定 (環境変数を pydantic-settings で一元管理)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """環境変数から読み込まれるアプリケーション設定."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- LLM: Google Gemini (A Researcher / B Analyst / E Finalizer) ---
    google_api_key: str = Field(default="", description="Gemini API key")
    gemini_model_main: str = Field(default="gemini-2.5-flash")
    gemini_model_sub: str = Field(default="gemini-2.5-flash-lite")

    # --- LLM: Groq Llama (C Critic / D Fact-checker) ---
    # Groq の無料枠は 14,400 RPD と豊富。Gemini Flash の 20 RPD 制限を回避するため
    # 「視点の多様性」も兼ねて C/D を Meta 系 LLM に分散する。
    groq_api_key: str = Field(default="", description="Groq API key")
    groq_model: str = Field(default="llama-3.3-70b-versatile")

    # --- Web search ---
    tavily_api_key: str = Field(default="", description="Tavily API key")

    # --- 通知 (Phase 4, 任意) ---
    line_notify_token: str = Field(default="", description="LINE Notify token (廃止予定)")
    discord_webhook_url: str = Field(default="", description="Discord Webhook URL")

    # --- LINE Messaging API (Phase 5: LINE 連携, 任意) ---
    # 取得: https://developers.line.biz/ (Messaging API channel 作成)
    line_channel_secret: str = Field(default="", description="LINE Channel Secret (署名検証用)")
    line_channel_access_token: str = Field(
        default="", description="LINE Channel Access Token (push 送信用)"
    )
    # 自分の LINE User ID をカンマ区切りで指定 (例: 'Uxxxx,Uyyyy')
    # 設定された User ID 以外からのメッセージは無視される (公開時の安全装置)
    line_allowed_user_ids: str = Field(default="")
    # webhook 受信用 FastAPI の listen ポート
    webhook_port: int = Field(default=8080)
    # LINE Flex Message の「詳細を見る」ボタンが開く URL
    streamlit_base_url: str = Field(default="http://localhost:8501")

    # --- 定期実行 (Phase 4) ---
    watchlist_file: Path = Field(default=Path("./watchlist.txt"))

    @property
    def line_allowed_user_id_list(self) -> list[str]:
        """カンマ区切りの allowed_user_ids をリストに正規化."""
        return [
            uid.strip() for uid in self.line_allowed_user_ids.split(",") if uid.strip()
        ]

    # --- UI 認証 (HF Spaces 公開デプロイ用) ---
    # 設定すると Streamlit 起動時にパスワード入力フォームが出る。未設定だと素通り (ローカル開発互換).
    streamlit_password: str = Field(default="", description="Streamlit UI のアクセスパスワード")

    # --- Persistence ---
    # データの保存ルート。
    #   - ローカル開発 : ./data (リポジトリ内)
    #   - HF Spaces    : /data (Persistent Storage マウント点)
    # chroma_persist_dir / sqlite_path は data_dir からの相対で派生する (未指定時).
    # 個別パスを明示的に指定したい場合は CHROMA_PERSIST_DIR / SQLITE_PATH を env でセットする
    # (env 値が空文字なら派生パスにフォールバック).
    data_dir: Path = Field(
        default=Path("./data"),
        validation_alias=AliasChoices("DATA_DIR", "data_dir"),
        description="永続化ルートディレクトリ",
    )
    chroma_persist_dir_override: str = Field(
        default="",
        validation_alias=AliasChoices(
            "CHROMA_PERSIST_DIR", "chroma_persist_dir_override"
        ),
        description="ChromaDB の永続化先 (空なら data_dir/chroma_db)",
    )
    sqlite_path_override: str = Field(
        default="",
        validation_alias=AliasChoices("SQLITE_PATH", "sqlite_path_override"),
        description="SQLite ファイルパス (空なら data_dir/agents.sqlite3)",
    )

    @property
    def chroma_persist_dir(self) -> Path:
        """ChromaDB 永続化先. CHROMA_PERSIST_DIR が空なら data_dir/chroma_db."""
        if self.chroma_persist_dir_override:
            return Path(self.chroma_persist_dir_override)
        return self.data_dir / "chroma_db"

    @property
    def sqlite_path(self) -> Path:
        """SQLite ログファイル. SQLITE_PATH が空なら data_dir/agents.sqlite3."""
        if self.sqlite_path_override:
            return Path(self.sqlite_path_override)
        return self.data_dir / "agents.sqlite3"

    # --- Runtime ---
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # --- Loop guard (D エージェントの差し戻し上限) ---
    max_factcheck_retries: int = Field(default=2)

    # --- 無料枠ガード (Gemini Flash の 1 日上限) ---
    # 2026/5 時点の実測: gemini-2.5-flash = 20 RPD (free tier)
    # 1 質問あたり A + E = 2 calls 消費するので、無料枠で約 10 質問/日が現実的上限
    gemini_flash_daily_limit: int = Field(default=20)
    # 警告を出し始める使用率 (0.0-1.0)
    quota_warn_threshold: float = Field(default=0.7)
    # 強い警告 (赤色) を出す使用率
    quota_danger_threshold: float = Field(default=0.9)

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """設定をシングルトンで取得 (テストでは get_settings.cache_clear() で再読込)."""
    return Settings()
