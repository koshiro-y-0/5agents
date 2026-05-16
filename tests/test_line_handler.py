"""src/line/handler.py のテスト (LINE SDK をモック)."""

from __future__ import annotations

import base64
import hashlib
import hmac
from unittest.mock import MagicMock, patch

from src.line.handler import LineHandler

_SECRET = "test-channel-secret"
_TOKEN = "test-access-token"


def _make_signature(body: bytes, secret: str = _SECRET) -> str:
    """LINE 公式の署名生成手順を再現."""
    h = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(h).decode("utf-8")


def test_verify_signature_accepts_valid_signature() -> None:
    handler = LineHandler(_SECRET, _TOKEN)
    body = b'{"events":[{"type":"message"}]}'
    sig = _make_signature(body)
    assert handler.verify_signature(body, sig) is True


def test_verify_signature_rejects_invalid_signature() -> None:
    handler = LineHandler(_SECRET, _TOKEN)
    body = b'{"events":[{"type":"message"}]}'
    assert handler.verify_signature(body, "wrong-signature") is False


def test_verify_signature_rejects_tampered_body() -> None:
    """元のボディの署名を別ボディで検証すると失敗."""
    handler = LineHandler(_SECRET, _TOKEN)
    original = b"original"
    tampered = b"tampered"
    sig = _make_signature(original)
    assert handler.verify_signature(tampered, sig) is False


def test_verify_signature_rejects_empty_signature() -> None:
    handler = LineHandler(_SECRET, _TOKEN)
    assert handler.verify_signature(b"any", "") is False


def test_verify_signature_rejects_when_secret_missing() -> None:
    handler = LineHandler("", _TOKEN)
    assert handler.verify_signature(b"any", "any") is False


def test_reply_text_calls_messaging_api() -> None:
    handler = LineHandler(_SECRET, _TOKEN)
    with patch("src.line.handler.ApiClient") as mock_api_client:
        mock_api_client.return_value.__enter__.return_value = MagicMock()
        with patch("src.line.handler.MessagingApi") as mock_api_cls:
            mock_api = MagicMock()
            mock_api_cls.return_value = mock_api
            handler.reply_text("token-xxx", "hello")
            mock_api.reply_message.assert_called_once()


def test_push_messages_chunks_by_5() -> None:
    """6 通入れたら 2 回 push_message が呼ばれる (5+1)."""
    handler = LineHandler(_SECRET, _TOKEN)
    with patch("src.line.handler.ApiClient") as mock_api_client:
        mock_api_client.return_value.__enter__.return_value = MagicMock()
        with patch("src.line.handler.MessagingApi") as mock_api_cls:
            mock_api = MagicMock()
            mock_api_cls.return_value = mock_api
            handler.push_messages("U123", [f"msg{i}" for i in range(6)])
            assert mock_api.push_message.call_count == 2


def test_push_messages_skips_when_empty() -> None:
    handler = LineHandler(_SECRET, _TOKEN)
    with patch("src.line.handler.ApiClient") as mock_api_client:
        handler.push_messages("U123", [])
        mock_api_client.assert_not_called()
