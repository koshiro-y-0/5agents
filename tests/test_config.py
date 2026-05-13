"""src/config.py のテスト (API キー不要)."""

from __future__ import annotations

from src.config import Settings, get_settings


def test_settings_defaults_load() -> None:
    """環境変数未設定でもインスタンス化できる (Field のデフォルト値が効く)."""
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.gemini_model_main == "gemini-2.5-flash"
    assert s.gemini_model_sub == "gemini-2.5-flash-lite"
    assert s.max_factcheck_retries == 2
    assert s.app_env == "development"
    assert s.is_development is True


def test_is_development_false_when_production() -> None:
    s = Settings(_env_file=None, app_env="production")  # type: ignore[call-arg]
    assert s.is_development is False


def test_get_settings_is_singleton() -> None:
    """lru_cache により同じインスタンスが返される."""
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b
