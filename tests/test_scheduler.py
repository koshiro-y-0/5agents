"""定期実行スクリプトのテスト (answer / notifier をモック)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.scheduler import _format_short_report, load_watchlist, run_scheduled


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
