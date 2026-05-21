"""src/line/webhook.py のテスト (FastAPI TestClient + answer/handler モック)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.line.webhook import app

_SECRET = "test-channel-secret"
_TOKEN = "test-access-token"


@pytest.fixture
def client(monkeypatch):  # type: ignore[no-untyped-def]
    """環境変数を設定したテストクライアント."""
    from src import config

    monkeypatch.setenv("LINE_CHANNEL_SECRET", _SECRET)
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", _TOKEN)
    monkeypatch.setenv("LINE_ALLOWED_USER_IDS", "Uallowed123")
    config.get_settings.cache_clear()
    yield TestClient(app)
    config.get_settings.cache_clear()


def _sig(body: bytes) -> str:
    h = hmac.new(_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(h).decode("utf-8")


def _event_payload(user_id: str = "Uallowed123", text: str = "テスト質問") -> dict:  # type: ignore[type-arg]
    return {
        "events": [
            {
                "type": "message",
                "replyToken": "token-test",
                "source": {"userId": user_id, "type": "user"},
                "message": {"id": "m1", "type": "text", "text": text},
            }
        ]
    }


def test_health_endpoint(client) -> None:  # type: ignore[no-untyped-def]
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_webhook_rejects_invalid_signature(client) -> None:  # type: ignore[no-untyped-def]
    body = json.dumps(_event_payload()).encode()
    r = client.post(
        "/line/webhook",
        content=body,
        headers={"X-Line-Signature": "wrong"},
    )
    assert r.status_code == 403


def test_webhook_accepts_valid_signature_and_dispatches(client) -> None:  # type: ignore[no-untyped-def]
    body = json.dumps(_event_payload()).encode()

    with (
        patch("src.line.webhook.LineHandler") as mock_handler_cls,
        patch("src.line.webhook.has_quota_for_question", return_value=True),
    ):
        mock_handler = MagicMock()
        mock_handler.verify_signature.return_value = True
        mock_handler_cls.return_value = mock_handler

        r = client.post(
            "/line/webhook",
            content=body,
            headers={"X-Line-Signature": _sig(body)},
        )
    assert r.status_code == 200
    # loading reply が送られた
    mock_handler.reply_text.assert_called_once()


def test_webhook_ignores_non_allowed_user(client) -> None:  # type: ignore[no-untyped-def]
    body = json.dumps(_event_payload(user_id="Uattacker")).encode()
    with patch("src.line.webhook.LineHandler") as mock_handler_cls:
        mock_handler = MagicMock()
        mock_handler.verify_signature.return_value = True
        mock_handler_cls.return_value = mock_handler

        r = client.post(
            "/line/webhook",
            content=body,
            headers={"X-Line-Signature": _sig(body)},
        )
    assert r.status_code == 200
    # 非許可ユーザーには返信しない
    mock_handler.reply_text.assert_not_called()


def test_webhook_returns_quota_message_when_exhausted(client) -> None:  # type: ignore[no-untyped-def]
    """Phase 5 Theme A: 枯渇 reply に復活時刻 (⏰) と reset_at_jst_str が含まれる."""
    from datetime import timedelta

    body = json.dumps(_event_payload()).encode()
    fake_status = MagicMock(
        used=20,
        limit=20,
        remaining=0,
        time_until_reset=timedelta(hours=3, minutes=24),
        reset_at_jst_str="明日 00:00 JST",
    )
    with (
        patch("src.line.webhook.LineHandler") as mock_handler_cls,
        patch("src.line.webhook.has_quota_for_question", return_value=False),
        patch("src.line.webhook.get_flash_quota_status", return_value=fake_status),
    ):
        mock_handler = MagicMock()
        mock_handler.verify_signature.return_value = True
        mock_handler_cls.return_value = mock_handler

        r = client.post(
            "/line/webhook",
            content=body,
            headers={"X-Line-Signature": _sig(body)},
        )
    assert r.status_code == 200
    # 枯渇メッセージを reply で返す
    mock_handler.reply_text.assert_called_once()
    sent_text = mock_handler.reply_text.call_args[0][1]
    # 使い切り通知
    assert "使い切り" in sent_text
    assert "20" in sent_text  # used/limit
    # Phase 5 Theme A: 復活時刻情報
    assert "⏰" in sent_text
    assert "3 時間 24 分" in sent_text
    assert "明日 00:00 JST" in sent_text


def test_webhook_ignores_non_text_messages(client) -> None:  # type: ignore[no-untyped-def]
    payload = _event_payload()
    payload["events"][0]["message"]["type"] = "image"
    body = json.dumps(payload).encode()
    with patch("src.line.webhook.LineHandler") as mock_handler_cls:
        mock_handler = MagicMock()
        mock_handler.verify_signature.return_value = True
        mock_handler_cls.return_value = mock_handler

        r = client.post(
            "/line/webhook",
            content=body,
            headers={"X-Line-Signature": _sig(body)},
        )
    assert r.status_code == 200
    mock_handler.reply_text.assert_not_called()


def test_webhook_returns_503_when_channel_not_configured(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from src import config

    # 開発者ローカルの .env に実値が入っていることがあるので、
    # delenv ではなく setenv("") で明示的に空文字列で上書きする
    # (pydantic-settings の優先順位: env > .env)
    monkeypatch.setenv("LINE_CHANNEL_SECRET", "")
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    config.get_settings.cache_clear()

    client = TestClient(app)
    r = client.post(
        "/line/webhook",
        content=b"{}",
        headers={"X-Line-Signature": "any"},
    )
    assert r.status_code == 503

    config.get_settings.cache_clear()
