"""src/auth.py のテスト (HF OAuth + 権限解決, Phase 5 Theme C)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src import auth, config
from src.auth import CurrentUser, is_oauth_enabled, line_username


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "auth_test.sqlite3"))
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


# --- is_oauth_enabled() ---


def test_is_oauth_enabled_true_when_client_id_set(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OAUTH_CLIENT_ID", "abc123")
    assert is_oauth_enabled() is True


def test_is_oauth_enabled_false_when_unset(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("OAUTH_CLIENT_ID", raising=False)
    assert is_oauth_enabled() is False


def test_is_oauth_enabled_false_when_empty(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OAUTH_CLIENT_ID", "")
    assert is_oauth_enabled() is False


# --- get_current_user() ローカル開発モード ---


def test_local_dev_returns_dummy_admin(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """OAUTH_CLIENT_ID 未設定なら _local_dev admin が返る."""
    monkeypatch.delenv("OAUTH_CLIENT_ID", raising=False)
    user = auth.get_current_user()
    assert user is not None
    assert user.username == "_local_dev"
    assert user.is_admin is True
    assert user.is_allowed is True


# --- get_current_user() HF OAuth 有効・未ログイン ---


def test_oauth_enabled_not_logged_in_returns_none(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OAUTH_CLIENT_ID", "abc")
    fake_st = MagicMock()
    fake_st.user.is_logged_in = False
    with patch.dict("sys.modules", {"streamlit": fake_st}):
        user = auth.get_current_user()
    assert user is None


# --- get_current_user() HF OAuth 有効・ログイン済み・許可外 ---


def test_oauth_logged_in_but_not_allowed_returns_guest(
    monkeypatch, isolated_db
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OAUTH_CLIENT_ID", "abc")
    fake_st = MagicMock()
    fake_st.user.is_logged_in = True
    fake_st.user.preferred_username = "stranger"
    fake_st.user.name = "Stranger Person"
    fake_st.user.picture = "https://example.com/pic.png"
    with patch.dict("sys.modules", {"streamlit": fake_st}):
        user = auth.get_current_user()
    assert user is not None
    assert user.username == "stranger"
    assert user.role == "guest"
    assert user.is_allowed is False
    assert user.is_admin is False


# --- get_current_user() HF OAuth 有効・ログイン済み・許可済み ---


def test_oauth_logged_in_as_admin(monkeypatch, isolated_db) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OAUTH_CLIENT_ID", "abc")
    # 事前に admin として登録
    from src.memory.logger import RunLogger

    RunLogger().ensure_admin("koshiro-y-12", display_name="Koshiro")

    fake_st = MagicMock()
    fake_st.user.is_logged_in = True
    fake_st.user.preferred_username = "koshiro-y-12"
    fake_st.user.name = "Koshiro"
    fake_st.user.picture = "https://example.com/pic.png"
    with patch.dict("sys.modules", {"streamlit": fake_st}):
        user = auth.get_current_user()

    assert user is not None
    assert user.username == "koshiro-y-12"
    assert user.role == "admin"
    assert user.is_admin is True
    assert user.is_allowed is True


def test_oauth_logged_in_as_member(monkeypatch, isolated_db) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("OAUTH_CLIENT_ID", "abc")
    from src.memory.logger import RunLogger

    RunLogger().add_allowed_user("alice", role="member", added_by="admin")

    fake_st = MagicMock()
    fake_st.user.is_logged_in = True
    fake_st.user.preferred_username = "alice"
    fake_st.user.name = "Alice"
    fake_st.user.picture = None
    with patch.dict("sys.modules", {"streamlit": fake_st}):
        user = auth.get_current_user()

    assert user is not None
    assert user.role == "member"
    assert user.is_admin is False
    assert user.is_allowed is True


# --- register_login() ---


def test_register_login_updates_last_login(monkeypatch, isolated_db) -> None:  # type: ignore[no-untyped-def]
    from src.memory.logger import RunLogger

    rlog = RunLogger()
    rlog.ensure_admin("koshiro-y-12")
    assert rlog.list_allowed_users()[0]["last_login"] is None

    auth.register_login(
        CurrentUser(
            username="koshiro-y-12",
            display_name="Koshiro",
            picture_url=None,
            role="admin",
        )
    )
    assert rlog.list_allowed_users()[0]["last_login"] is not None


def test_register_login_skips_guest_user(monkeypatch, isolated_db) -> None:  # type: ignore[no-untyped-def]
    """guest ユーザーは last_login 記録しない (DB に存在しないため)."""
    # 例外が出ないことだけ確認
    auth.register_login(
        CurrentUser(
            username="stranger",
            display_name=None,
            picture_url=None,
            role="guest",
        )
    )


# --- line_username() ---


def test_line_username_format() -> None:
    assert line_username("Uabc123") == "@line:Uabc123"


def test_line_username_does_not_collide_with_hf_username() -> None:
    """@line: プレフィックスは HF username として有効でないので衝突しない."""
    # HF username は英数とハイフンのみ、'@' や ':' は使えない
    assert "@" in line_username("Uxxxxx")
    assert ":" in line_username("Uxxxxx")
