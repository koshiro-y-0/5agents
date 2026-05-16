"""src/quota.py のテスト (一時 SQLite を使用、Gemini API 呼び出しなし)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src import config, quota


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    """一時 SQLite パスと既知の limit を設定で上書き.

    limit=100 を使うのは「FLASH_CALLS_PER_QUESTION=2 と境界が交錯しない」よう
    上限を大きく取って各レベル境界を素直にテストするため。
    """
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "q.sqlite3"))
    monkeypatch.setenv("GEMINI_FLASH_DAILY_LIMIT", "100")
    monkeypatch.setenv("QUOTA_WARN_THRESHOLD", "0.7")
    monkeypatch.setenv("QUOTA_DANGER_THRESHOLD", "0.9")
    monkeypatch.setenv("GEMINI_MODEL_MAIN", "gemini-2.5-flash")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def _record_calls(n: int) -> None:
    """指定回数だけ Gemini Flash 呼び出しをログに記録."""
    from src.memory.logger import RunLogger

    rlog = RunLogger()
    rid = rlog.start_run("test")
    for _ in range(n):
        rlog.log_agent_call(rid, "researcher", "gemini-2.5-flash", 100)


def test_quota_ok_below_warn_threshold(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    _record_calls(30)  # 30% < 70%
    status = quota.get_flash_quota_status()
    assert status.used == 30
    assert status.limit == 100
    assert status.remaining == 70
    assert status.level == "ok"
    assert status.can_run_question is True


def test_quota_warn_at_70_percent(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    _record_calls(70)  # 70% == 0.7 (warn 境界)
    status = quota.get_flash_quota_status()
    assert status.level == "warn"


def test_quota_danger_at_90_percent(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    _record_calls(90)  # 90% == 0.9 (danger 境界、残り 10 calls あるので質問は可能)
    status = quota.get_flash_quota_status()
    assert status.level == "danger"
    assert status.can_run_question is True


def test_quota_exhausted_when_cannot_fit_question(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    """remaining < FLASH_CALLS_PER_QUESTION (=2) で exhausted."""
    _record_calls(99)  # 残り 1 calls、質問 1 件 (2 calls) は不可
    status = quota.get_flash_quota_status()
    assert status.remaining == 1
    assert status.level == "exhausted"
    assert status.can_run_question is False


def test_quota_exhausted_at_limit(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    _record_calls(100)
    status = quota.get_flash_quota_status()
    assert status.remaining == 0
    assert status.level == "exhausted"


def test_quota_handles_logger_error_gracefully() -> None:
    """RunLogger 例外時は使用量 0 扱い (ok) を返す."""
    config.get_settings.cache_clear()
    with patch("src.quota.RunLogger") as mock_logger:
        mock_logger.side_effect = RuntimeError("db down")
        status = quota.get_flash_quota_status()
        assert status.used == 0
        assert status.level == "ok"


def test_has_quota_for_question_helper(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    _record_calls(98)  # 残り 2 = ちょうど質問 1 件分
    assert quota.has_quota_for_question() is True
    _record_calls(1)  # 残り 1
    assert quota.has_quota_for_question() is False


def test_flash_lite_calls_dont_consume_main_quota(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    """Flash-Lite の呼び出しは Flash 枠を消費しない (model exact match)."""
    from src.memory.logger import RunLogger

    rlog = RunLogger()
    rid = rlog.start_run("test")
    # Flash-Lite を 5 回呼んでも、Flash 枠は減らない
    for _ in range(5):
        rlog.log_agent_call(rid, "analyst", "gemini-2.5-flash-lite", 100)
    status = quota.get_flash_quota_status()
    assert status.used == 0
    assert status.level == "ok"
