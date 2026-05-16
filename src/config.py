"""アプリケーション設定 (環境変数を pydantic-settings で一元管理)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
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
    line_notify_token: str = Field(default="", description="LINE Notify token")
    discord_webhook_url: str = Field(default="", description="Discord Webhook URL")

    # --- 定期実行 (Phase 4) ---
    watchlist_file: Path = Field(default=Path("./watchlist.txt"))

    # --- Persistence ---
    chroma_persist_dir: Path = Field(default=Path("./data/chroma_db"))
    sqlite_path: Path = Field(default=Path("./data/agents.sqlite3"))

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
