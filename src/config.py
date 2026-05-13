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

    # --- LLM ---
    google_api_key: str = Field(default="", description="Gemini API key")
    gemini_model_main: str = Field(default="gemini-2.5-flash")
    gemini_model_sub: str = Field(default="gemini-2.5-flash-lite")

    # --- Web search ---
    tavily_api_key: str = Field(default="", description="Tavily API key")

    # --- Persistence ---
    chroma_persist_dir: Path = Field(default=Path("./data/chroma_db"))
    sqlite_path: Path = Field(default=Path("./data/agents.sqlite3"))

    # --- Runtime ---
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # --- Loop guard (D エージェントの差し戻し上限) ---
    max_factcheck_retries: int = Field(default=2)

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """設定をシングルトンで取得 (テストでは get_settings.cache_clear() で再読込)."""
    return Settings()
