"""LINE Notify / Discord Webhook への通知送信.

設計:
- 環境変数で複数チャネルを並列に有効化可能 (LINE_NOTIFY_TOKEN, DISCORD_WEBHOOK_URL)
- どれも未設定なら no-op (ログのみ)
- 送信失敗で例外を投げず警告ログのみ (定期実行を止めない)
"""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    """通知チャネルの共通インターフェース."""

    def send(self, title: str, body: str) -> bool: ...


class LineNotifier:
    """LINE Notify への送信.

    トークンは https://notify-bot.line.me/ で発行。
    LINE_NOTIFY_TOKEN を環境変数に設定。
    """

    API_URL = "https://notify-api.line.me/api/notify"

    def __init__(self, token: str) -> None:
        self._token = token

    def send(self, title: str, body: str) -> bool:
        message = f"\n【{title}】\n{body}"
        # LINE Notify は 1000 文字制限
        if len(message) > 990:
            message = message[:987] + "..."
        try:
            r = httpx.post(
                self.API_URL,
                headers={"Authorization": f"Bearer {self._token}"},
                data={"message": message},
                timeout=10.0,
            )
            r.raise_for_status()
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("LINE Notify 送信失敗: %s", e)
            return False


class DiscordNotifier:
    """Discord Webhook への送信.

    Webhook URL は Discord サーバー設定 → 連携サービス で取得。
    DISCORD_WEBHOOK_URL を環境変数に設定。
    """

    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    def send(self, title: str, body: str) -> bool:
        # Discord は 2000 文字制限
        content = f"**{title}**\n{body}"
        if len(content) > 1990:
            content = content[:1987] + "..."
        try:
            r = httpx.post(
                self._url,
                json={"content": content},
                timeout=10.0,
            )
            r.raise_for_status()
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("Discord 送信失敗: %s", e)
            return False


class CompositeNotifier:
    """設定されている全チャネルにブロードキャスト送信."""

    def __init__(self, notifiers: list[Notifier]) -> None:
        self._notifiers = notifiers

    def send(self, title: str, body: str) -> dict[str, bool]:
        """各チャネルの送信結果を {channel: success} で返す."""
        results: dict[str, bool] = {}
        for n in self._notifiers:
            channel = type(n).__name__
            results[channel] = n.send(title, body)
        return results

    @property
    def is_empty(self) -> bool:
        return not self._notifiers


def build_default_notifier() -> CompositeNotifier:
    """環境変数から有効なチャネルを集めて CompositeNotifier を構築."""
    settings = get_settings()
    notifiers: list[Notifier] = []

    if settings.line_notify_token and not settings.line_notify_token.startswith("your_"):
        notifiers.append(LineNotifier(settings.line_notify_token))
    if settings.discord_webhook_url and not settings.discord_webhook_url.startswith("your_"):
        notifiers.append(DiscordNotifier(settings.discord_webhook_url))

    if not notifiers:
        logger.info("通知チャネル未設定 — 送信は no-op")

    return CompositeNotifier(notifiers)
