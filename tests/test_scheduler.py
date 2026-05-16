"""定期実行スクリプトのテスト (answer / notifier をモック)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.scheduler import _format_short_report, load_watchlist, run_scheduled


@pytest.fixture(autouse=True)
def _quota_always_available():  # type: ignore[no-untyped-def]
    """既存テストでは quota guard が常に通る前提に固定."""
    with patch("src.scheduler.has_quota_for_question", return_value=True):
        yield


def test_load_watchlist_skips_comments_and_blank_lines(tmp_path) -> None:  # type: ignore[no-untyped-def]
    f = tmp_path / "wl.txt"
    f.write_text(
        "# コメント\n\nNVDA を分析して\n\n# もう一つコメント\nAAPL の業績は?\n",
        encoding="utf-8",
    )
    assert load_watchlist(f) == ["NVDA を分析して", "AAPL の業績は?"]


def test_load_watchlist_missing_file_returns_empty(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert load_watchlist(tmp_path / "missing.txt") == []


def test_format_short_report_includes_essentials() -> None:
    state = {
        "final_answer": "回答本体。",
        "retry_count": 1,
        "fact_check": {"verdict": "OK", "issues": []},
    }
    report = _format_short_report("テスト質問", state)
    assert "テスト質問" in report
    assert "回答本体" in report
    assert "verdict=OK" in report
    assert "retry=1" in report


def test_format_short_report_truncates_long_answer() -> None:
    state = {"final_answer": "あ" * 1000, "retry_count": 0, "fact_check": {"verdict": "OK"}}
    report = _format_short_report("Q", state)
    # answer の抜粋は 600 文字までで省略記号 ...
    assert "..." in report


def test_run_scheduled_dry_run_calls_answer_for_each_question(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    wl = tmp_path / "wl.txt"
    wl.write_text("Q1\nQ2\n", encoding="utf-8")

    mock_state = {
        "final_answer": "A",
        "retry_count": 0,
        "fact_check": {"verdict": "OK", "issues": []},
    }
    with patch("src.scheduler.answer", return_value=mock_state) as mock_answer:
        count = run_scheduled(watchlist_path=wl, dry_run=True)

    assert count == 2
    assert mock_answer.call_count == 2
    captured = capsys.readouterr()
    assert "Q1" in captured.out
    assert "Q2" in captured.out


def test_run_scheduled_continues_on_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """1 件目が失敗しても 2 件目を処理する."""
    wl = tmp_path / "wl.txt"
    wl.write_text("Q1\nQ2\n", encoding="utf-8")

    mock_state = {"final_answer": "A", "retry_count": 0, "fact_check": {"verdict": "OK"}}

    def side_effect(q):  # type: ignore[no-untyped-def]
        if q == "Q1":
            raise RuntimeError("boom")
        return mock_state

    notifier = MagicMock()
    notifier.is_empty = True
    notifier.send.return_value = {}
    with (
        patch("src.scheduler.answer", side_effect=side_effect),
        patch("src.scheduler.build_default_notifier", return_value=notifier),
    ):
        count = run_scheduled(watchlist_path=wl, dry_run=False)

    assert count == 2  # 全件処理試行
    # 1 件目はエラー通知、2 件目は通常通知
    assert notifier.send.call_count == 2
    error_call = notifier.send.call_args_list[0]
    assert "エラー" in error_call[0][0]


def test_run_scheduled_empty_watchlist_returns_zero(tmp_path) -> None:  # type: ignore[no-untyped-def]
    wl = tmp_path / "wl.txt"
    wl.write_text("# only comment\n", encoding="utf-8")
    assert run_scheduled(watchlist_path=wl, dry_run=True) == 0


@pytest.mark.parametrize("flag", [True, False])
def test_run_scheduled_dry_run_does_not_send(tmp_path, flag) -> None:  # type: ignore[no-untyped-def]
    wl = tmp_path / "wl.txt"
    wl.write_text("Q1\n", encoding="utf-8")

    mock_state = {"final_answer": "A", "retry_count": 0, "fact_check": {"verdict": "OK"}}
    notifier = MagicMock()
    notifier.is_empty = False
    notifier.send.return_value = {"Line": True}
    with (
        patch("src.scheduler.answer", return_value=mock_state),
        patch("src.scheduler.build_default_notifier", return_value=notifier),
    ):
        run_scheduled(watchlist_path=wl, dry_run=flag)
    if flag:
        notifier.send.assert_not_called()
    else:
        notifier.send.assert_called_once()


# --- Quota guard ---


def test_run_scheduled_skips_when_quota_exhausted(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """事前に Flash 枠が足りない場合、answer() を呼ばずスキップして抜ける."""
    wl = tmp_path / "wl.txt"
    wl.write_text("Q1\nQ2\nQ3\n", encoding="utf-8")

    notifier = MagicMock()
    notifier.is_empty = True
    notifier.send.return_value = {}
    fake_status = MagicMock()
    fake_status.remaining = 1
    fake_status.used = 19
    fake_status.limit = 20

    with (
        patch("src.scheduler.answer") as mock_answer,
        patch("src.scheduler.build_default_notifier", return_value=notifier),
        # 既存の autouse fixture をオーバーライド
        patch("src.scheduler.has_quota_for_question", return_value=False),
        patch("src.scheduler.get_flash_quota_status", return_value=fake_status),
    ):
        result = run_scheduled(watchlist_path=wl, dry_run=True)

    # 1 質問も処理しない
    mock_answer.assert_not_called()
    # 戻り値は処理した件数 (= 0)
    assert result == 0


def test_run_scheduled_quota_check_runs_before_each_question(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """質問ごとに quota check が走る (途中で枯渇したら以降スキップ)."""
    wl = tmp_path / "wl.txt"
    wl.write_text("Q1\nQ2\nQ3\n", encoding="utf-8")

    # 1 件目は OK、2 件目以降は枯渇
    has_quota_results = [True, False, False]
    fake_status = MagicMock(remaining=1, used=19, limit=20)
    mock_state = {"final_answer": "A", "retry_count": 0, "fact_check": {"verdict": "OK"}}

    notifier = MagicMock()
    notifier.is_empty = True
    notifier.send.return_value = {}

    with (
        patch("src.scheduler.answer", return_value=mock_state) as mock_answer,
        patch("src.scheduler.build_default_notifier", return_value=notifier),
        patch("src.scheduler.has_quota_for_question", side_effect=has_quota_results),
        patch("src.scheduler.get_flash_quota_status", return_value=fake_status),
    ):
        result = run_scheduled(watchlist_path=wl, dry_run=True)

    # 1 件だけ処理
    assert mock_answer.call_count == 1
    assert result == 1
