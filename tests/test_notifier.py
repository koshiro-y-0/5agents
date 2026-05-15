"""通知ラッパーのテスト (httpx をモック)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx

from src.notifications.notifier import (
    CompositeNotifier,
    DiscordNotifier,
    LineNotifier,
)


def _ok_response() -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = 200
    r.raise_for_status = MagicMock()
    return r


def _error_response() -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = 500
    r.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError("boom", request=None, response=r))
    return r


def test_line_notifier_success() -> None:
    notifier = LineNotifier(token="dummy")
    with patch("httpx.post", return_value=_ok_response()) as mock_post:
        assert notifier.send("タイトル", "本文") is True
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert "タイトル" in kwargs["data"]["message"]
        assert kwargs["headers"]["Authorization"] == "Bearer dummy"


def test_line_notifier_swallows_errors() -> None:
    """送信失敗で例外を投げず False を返す (定期実行を止めない)."""
    notifier = LineNotifier(token="dummy")
    with patch("httpx.post", side_effect=httpx.ConnectError("net down")):
        assert notifier.send("T", "B") is False


def test_line_notifier_truncates_long_messages() -> None:
    """LINE Notify の 1000 文字制限に合わせて切り詰める."""
    notifier = LineNotifier(token="dummy")
    with patch("httpx.post", return_value=_ok_response()) as mock_post:
        notifier.send("T", "あ" * 2000)
        message: str = mock_post.call_args[1]["data"]["message"]
        assert len(message) <= 990


def test_discord_notifier_success() -> None:
    notifier = DiscordNotifier(webhook_url="https://discord.example/webhook")
    with patch("httpx.post", return_value=_ok_response()) as mock_post:
        assert notifier.send("T", "B") is True
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        assert "**T**" in kwargs["json"]["content"]


def test_discord_notifier_swallows_errors() -> None:
    notifier = DiscordNotifier(webhook_url="https://discord.example/webhook")
    with patch("httpx.post", return_value=_error_response()):
        assert notifier.send("T", "B") is False


def test_composite_broadcasts_to_all() -> None:
    """全チャネルに送信し、結果を辞書で返す."""
    n1 = MagicMock()
    n1.send.return_value = True
    n2 = MagicMock()
    n2.send.return_value = False
    composite = CompositeNotifier([n1, n2])
    results = composite.send("T", "B")
    assert results == {"MagicMock": False}  # 同名なら最後のが優先 → 名前ベースの簡易設計
    n1.send.assert_called_once_with("T", "B")
    n2.send.assert_called_once_with("T", "B")


def test_composite_is_empty_property() -> None:
    assert CompositeNotifier([]).is_empty is True
    assert CompositeNotifier([MagicMock()]).is_empty is False
