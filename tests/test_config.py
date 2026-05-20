"""src/config.py のテスト (API キー不要)."""

from __future__ import annotations

from pathlib import Path

from src.config import Settings, get_settings


def test_settings_defaults_load() -> None:
    """環境変数未設定でもインスタンス化できる (Field のデフォルト値が効く)."""
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.gemini_model_main == "gemini-2.5-flash"
    assert s.gemini_model_sub == "gemini-2.5-flash-lite"
    assert s.max_factcheck_retries == 2
    assert s.app_env == "development"
    assert s.is_development is True


def test_persistence_paths_derived_from_data_dir() -> None:
    """data_dir 配下に派生パスができる (HF Spaces 用 /data マウントの動作確認)."""
    s = Settings(_env_file=None, data_dir=Path("/tmp/test-data"))  # type: ignore[call-arg]
    assert s.chroma_persist_dir == Path("/tmp/test-data/chroma_db")
    assert s.sqlite_path == Path("/tmp/test-data/agents.sqlite3")


def test_persistence_paths_overridden_by_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """CHROMA_PERSIST_DIR / SQLITE_PATH が明示されればそれを優先する."""
    monkeypatch.setenv("CHROMA_PERSIST_DIR", "/custom/chroma")
    monkeypatch.setenv("SQLITE_PATH", "/custom/db.sqlite")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.chroma_persist_dir == Path("/custom/chroma")
    assert s.sqlite_path == Path("/custom/db.sqlite")


def test_is_development_false_when_production() -> None:
    s = Settings(_env_file=None, app_env="production")  # type: ignore[call-arg]
    assert s.is_development is False


def test_get_settings_is_singleton() -> None:
    """lru_cache により同じインスタンスが返される."""
    get_settings.cache_clear()
    a = get_settings()
    b = get_settings()
    assert a is b
