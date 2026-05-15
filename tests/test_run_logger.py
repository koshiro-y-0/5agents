"""RunLogger (SQLite ロガー) のテスト (一時 DB、ネットワーク不要)."""

from __future__ import annotations

import pytest

from src.memory.logger import RunLogger, time_agent


@pytest.fixture
def rlog(tmp_path):  # type: ignore[no-untyped-def]
    return RunLogger(db_path=tmp_path / "test.sqlite3")


def test_start_run_returns_unique_id(rlog: RunLogger) -> None:
    id1 = rlog.start_run("Q1")
    id2 = rlog.start_run("Q2")
    assert id1 != id2


def test_finish_run_persists_values(rlog: RunLogger) -> None:
    run_id = rlog.start_run("テスト質問")
    rlog.finish_run(run_id, duration_ms=1234, final_verdict="OK", retry_count=0)
    stats = rlog.get_run_stats(run_id)
    assert stats is not None
    assert stats.duration_ms == 1234
    assert stats.final_verdict == "OK"
    assert stats.retry_count == 0


def test_log_agent_call_persists(rlog: RunLogger) -> None:
    run_id = rlog.start_run("Q")
    rlog.log_agent_call(run_id, "researcher", "gemini-2.5-flash", 500)
    rlog.log_agent_call(run_id, "analyst", "gemini-2.5-flash", 800)
    rlog.finish_run(run_id, duration_ms=1300, final_verdict="OK", retry_count=0)

    stats = rlog.get_run_stats(run_id)
    assert stats is not None
    assert stats.agent_durations == {"researcher": 500, "analyst": 800}


def test_recent_runs_returns_newest_first(rlog: RunLogger) -> None:
    ids = []
    for i in range(3):
        rid = rlog.start_run(f"Q{i}")
        rlog.finish_run(rid, duration_ms=100 + i, final_verdict="OK", retry_count=0)
        ids.append(rid)

    recent = rlog.recent_runs(limit=10)
    assert len(recent) == 3
    # 新しい順に並ぶ (Q2 → Q1 → Q0)
    assert recent[0]["question"] == "Q2"
    assert recent[-1]["question"] == "Q0"


def test_recent_runs_respects_limit(rlog: RunLogger) -> None:
    for i in range(5):
        rid = rlog.start_run(f"Q{i}")
        rlog.finish_run(rid, duration_ms=100, final_verdict="OK", retry_count=0)
    assert len(rlog.recent_runs(limit=2)) == 2


def test_get_run_stats_returns_none_for_missing_id(rlog: RunLogger) -> None:
    assert rlog.get_run_stats("non-existent-id") is None


def test_time_agent_records_duration(rlog: RunLogger) -> None:
    """time_agent context manager が duration を記録する."""
    import time as _time

    run_id = rlog.start_run("Q")
    with time_agent(rlog, run_id, "researcher", "gemini-2.5-flash"):
        _time.sleep(0.05)

    stats = rlog.get_run_stats(run_id)
    assert stats is not None
    duration = stats.agent_durations.get("researcher", 0)
    # 50ms 以上、200ms 未満 (システム負荷で多少ぶれる)
    assert 40 <= duration < 200, f"unexpected duration: {duration}ms"


def test_time_agent_records_error_and_reraises(rlog: RunLogger) -> None:
    """time_agent: 例外を再送出しつつログに残す."""
    run_id = rlog.start_run("Q")
    with (
        pytest.raises(ValueError, match="boom"),
        time_agent(rlog, run_id, "researcher", "gemini-2.5-flash"),
    ):
        raise ValueError("boom")

    # ログにエラーが記録されている (agent_durations は記録される)
    stats = rlog.get_run_stats(run_id)
    assert stats is not None
    assert "researcher" in stats.agent_durations
