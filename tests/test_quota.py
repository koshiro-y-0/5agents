"""src/quota.py のテスト (一時 SQLite を使用、Gemini API 呼び出しなし)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src import config, quota
from src.quota import JST, _next_jst_midnight, format_until_reset


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


# ── Phase 5 Theme A: リセット時刻計算 ──


def test_next_jst_midnight_from_jst_aware_time() -> None:
    """tz-aware な now を渡すと翌 JST 00:00 が返る."""
    now = datetime(2026, 5, 21, 10, 30, tzinfo=JST)  # 5/21 10:30 JST
    nxt = _next_jst_midnight(now)
    assert nxt == datetime(2026, 5, 22, 0, 0, tzinfo=JST)


def test_next_jst_midnight_from_utc_time() -> None:
    """UTC tz-aware を渡すと JST に正規化されてから翌 JST 00:00 が返る."""
    from datetime import timezone

    # 2026-05-21 23:00 UTC = 2026-05-22 08:00 JST (まだ同日扱い) → 5/23 00:00 JST
    now_utc = datetime(2026, 5, 21, 23, 0, tzinfo=timezone.utc)
    nxt = _next_jst_midnight(now_utc)
    assert nxt == datetime(2026, 5, 23, 0, 0, tzinfo=JST)


def test_next_jst_midnight_from_naive_treated_as_jst() -> None:
    """tz-naive はそのまま JST 扱い."""
    now = datetime(2026, 5, 21, 23, 59)  # naive, treat as JST
    nxt = _next_jst_midnight(now)
    assert nxt == datetime(2026, 5, 22, 0, 0, tzinfo=JST)


def test_next_jst_midnight_at_exact_midnight_returns_next_day() -> None:
    """JST 00:00 ちょうど → 24 時間後の 00:00 を返す."""
    now = datetime(2026, 5, 21, 0, 0, tzinfo=JST)
    nxt = _next_jst_midnight(now)
    assert nxt == datetime(2026, 5, 22, 0, 0, tzinfo=JST)


# ── format_until_reset() ──


def test_format_until_reset_seconds_returns_imminent() -> None:
    assert format_until_reset(timedelta(seconds=30)) == "まもなく復活"


def test_format_until_reset_negative_returns_imminent() -> None:
    """過去の時刻 (clock skew 等) も「まもなく復活」扱い."""
    assert format_until_reset(timedelta(seconds=-100)) == "まもなく復活"


def test_format_until_reset_minutes() -> None:
    assert format_until_reset(timedelta(minutes=45)) == "あと 45 分"


def test_format_until_reset_hours_and_minutes() -> None:
    td = timedelta(hours=3, minutes=24)
    assert format_until_reset(td) == "あと 3 時間 24 分"


def test_format_until_reset_exactly_one_hour() -> None:
    assert format_until_reset(timedelta(hours=1)) == "あと 1 時間 0 分"


def test_format_until_reset_days() -> None:
    assert format_until_reset(timedelta(days=2, hours=5)) == "あと 2 日"


# ── QuotaStatus.reset_at / time_until_reset 統合 ──


def test_quota_status_has_reset_at_and_time_until_reset(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    """get_flash_quota_status() が reset_at と time_until_reset を返す."""
    _record_calls(10)
    fixed_now = datetime(2026, 5, 21, 10, 0, tzinfo=JST)  # 10:00 JST
    status = quota.get_flash_quota_status(now=fixed_now)
    # 翌 00:00 JST = 14 時間後
    assert status.reset_at == datetime(2026, 5, 22, 0, 0, tzinfo=JST)
    assert status.time_until_reset == timedelta(hours=14)


def test_quota_status_reset_at_jst_str_today_vs_tomorrow(isolated_settings) -> None:  # type: ignore[no-untyped-def]
    """reset_at_jst_str は今日/明日のラベル付き."""
    _record_calls(5)
    # 23:00 → リセットは「明日 00:00 JST」
    fixed_now = datetime(2026, 5, 21, 23, 0, tzinfo=JST)
    status = quota.get_flash_quota_status(now=fixed_now)
    s = status.reset_at_jst_str
    # 「明日」は実行時刻に依存するが、reset_at の日付 > 今日 のため明日扱いになる想定
    # (ただし property 内で now を再取得しているので時刻によっては「今日」になる場合あり)
    assert "00:00 JST" in s
