"""src/memory/logger.py の allowed_users CRUD と runs.username 追加のテスト (Phase 5 Theme C)."""

from __future__ import annotations

import pytest

from src import config


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """毎テスト独立の SQLite を用意."""
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "users.sqlite3"))
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_ensure_admin_inserts_new_user(isolated_db) -> None:  # type: ignore[no-untyped-def]
    from src.memory.logger import RunLogger

    rlog = RunLogger()
    rlog.ensure_admin("koshiro-y-12", display_name="Koshiro")
    users = rlog.list_allowed_users()
    assert len(users) == 1
    assert users[0]["username"] == "koshiro-y-12"
    assert users[0]["role"] == "admin"
    assert users[0]["display_name"] == "Koshiro"


def test_ensure_admin_does_not_overwrite_existing(isolated_db) -> None:  # type: ignore[no-untyped-def]
    """既存ユーザーの role を ensure_admin が上書きしないこと."""
    from src.memory.logger import RunLogger

    rlog = RunLogger()
    # 先に member として追加
    rlog.add_allowed_user("alice", role="member", added_by="koshiro-y-12")
    # ensure_admin を後から呼んでも role は member のまま
    rlog.ensure_admin("alice")
    assert rlog.get_user_role("alice") == "member"


def test_is_user_allowed(isolated_db) -> None:  # type: ignore[no-untyped-def]
    from src.memory.logger import RunLogger

    rlog = RunLogger()
    rlog.ensure_admin("admin1")
    assert rlog.is_user_allowed("admin1") is True
    assert rlog.is_user_allowed("nonexistent") is False
    assert rlog.is_user_allowed("") is False


def test_get_user_role(isolated_db) -> None:  # type: ignore[no-untyped-def]
    from src.memory.logger import RunLogger

    rlog = RunLogger()
    rlog.ensure_admin("admin1")
    rlog.add_allowed_user("bob", role="member", added_by="admin1")
    assert rlog.get_user_role("admin1") == "admin"
    assert rlog.get_user_role("bob") == "member"
    assert rlog.get_user_role("nonexistent") is None


def test_add_allowed_user_rejects_invalid_role(isolated_db) -> None:  # type: ignore[no-untyped-def]
    from src.memory.logger import RunLogger

    rlog = RunLogger()
    with pytest.raises(ValueError, match="invalid role"):
        rlog.add_allowed_user("bob", role="superadmin", added_by="admin1")


def test_update_user_role(isolated_db) -> None:  # type: ignore[no-untyped-def]
    from src.memory.logger import RunLogger

    rlog = RunLogger()
    rlog.add_allowed_user("bob", role="member", added_by="admin1")
    rlog.update_user_role("bob", "admin")
    assert rlog.get_user_role("bob") == "admin"


def test_remove_allowed_user(isolated_db) -> None:  # type: ignore[no-untyped-def]
    from src.memory.logger import RunLogger

    rlog = RunLogger()
    rlog.ensure_admin("admin1")
    rlog.add_allowed_user("bob", role="member", added_by="admin1")
    rlog.remove_allowed_user("bob")
    assert rlog.is_user_allowed("bob") is False
    assert rlog.is_user_allowed("admin1") is True


def test_touch_last_login_updates_timestamp(isolated_db) -> None:  # type: ignore[no-untyped-def]
    from src.memory.logger import RunLogger

    rlog = RunLogger()
    rlog.ensure_admin("admin1")
    # 初期は NULL
    assert rlog.list_allowed_users()[0]["last_login"] is None
    rlog.touch_last_login("admin1", display_name="Updated Name")
    users = rlog.list_allowed_users()
    assert users[0]["last_login"] is not None
    assert users[0]["display_name"] == "Updated Name"


def test_runs_username_recorded(isolated_db) -> None:  # type: ignore[no-untyped-def]
    """start_run(username=...) で runs.username が記録される."""
    from src.memory.logger import RunLogger

    rlog = RunLogger()
    run_id = rlog.start_run("test question", username="alice")
    runs = rlog.all_runs_for_dashboard()
    assert any(r["id"] == run_id and r["username"] == "alice" for r in runs)


def test_runs_username_nullable_for_legacy_callers(isolated_db) -> None:  # type: ignore[no-untyped-def]
    """username を渡さない既存 caller でも壊れない (NULL になる)."""
    from src.memory.logger import RunLogger

    rlog = RunLogger()
    run_id = rlog.start_run("legacy question")
    runs = rlog.all_runs_for_dashboard()
    assert any(r["id"] == run_id and r["username"] is None for r in runs)


def test_user_run_count(isolated_db) -> None:  # type: ignore[no-untyped-def]
    from src.memory.logger import RunLogger

    rlog = RunLogger()
    for _ in range(3):
        rlog.start_run("q", username="alice")
    rlog.start_run("q", username="bob")
    assert rlog.user_run_count("alice") == 3
    assert rlog.user_run_count("bob") == 1
    assert rlog.user_run_count("nobody") == 0


def test_list_allowed_users_orders_admin_first(isolated_db) -> None:  # type: ignore[no-untyped-def]
    from src.memory.logger import RunLogger

    rlog = RunLogger()
    rlog.add_allowed_user("zmember", role="member", added_by="sys")
    rlog.add_allowed_user("aadmin", role="admin", added_by="sys")
    users = rlog.list_allowed_users()
    # admin が先 (role DESC)
    assert users[0]["role"] == "admin"
    assert users[1]["role"] == "member"
