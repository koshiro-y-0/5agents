"""LINE Messaging API クライアントの薄いラッパー.

責務:
- 署名検証 (X-Line-Signature) — 偽 webhook を即破棄するセキュリティの要
- Reply API (Reply Token、30 秒制限) — 「考え中...」即返信用
- Push API — 5agents 完了後の最終回答送信用 (時間制限なし)
- Flex Message - 「詳細を見る」ボタン付きメッセージ
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging

import certifi
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    FlexBox,
    FlexBubble,
    FlexButton,
    FlexMessage,
    FlexText,
    MessagingApi,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
    URIAction,
)

logger = logging.getLogger(__name__)


class LineHandler:
    """LINE Messaging API への送信と署名検証を担当."""

    def __init__(self, channel_secret: str, channel_access_token: str) -> None:
        self._channel_secret = channel_secret
        # macOS の Python.org 版だと urllib3 が CA 証明書を見つけられず
        # SSLCertVerificationError が出るため、certifi の cacert.pem を明示指定する
        self._config = Configuration(
            access_token=channel_access_token,
            ssl_ca_cert=certifi.where(),
        )

    # --- 署名検証 ---

    def verify_signature(self, raw_body: bytes, signature: str) -> bool:
        """X-Line-Signature ヘッダを検証.

        Args:
            raw_body: HTTP リクエストボディ (raw bytes、JSON パース前)
            signature: X-Line-Signature ヘッダの値

        Returns:
            True なら正規の LINE Platform からのリクエスト
        """
        if not self._channel_secret or not signature:
            return False
        h = hmac.new(
            self._channel_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).digest()
        expected = base64.b64encode(h).decode("utf-8")
        # タイミング攻撃対策で hmac.compare_digest を使用
        return hmac.compare_digest(expected, signature)

    # --- メッセージ送信 ---

    def reply_text(self, reply_token: str, text: str) -> None:
        """Reply Token で 1 通のテキストを返信 (30 秒以内推奨).

        Reply は 1 回しか使えないので、ローディング表示用に使う想定。
        """
        with ApiClient(self._config) as api_client:
            api = MessagingApi(api_client)
            api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[TextMessage(text=text)],
                )
            )

    def push_messages(self, user_id: str, texts: list[str]) -> None:
        """Push API で複数メッセージを送信 (時間制限なし).

        LINE は 1 リクエストあたり最大 5 メッセージまで。
        テキストは個別に 5000 字制限。
        """
        if not texts:
            return
        # 5 件ごとに分けて送信
        with ApiClient(self._config) as api_client:
            api = MessagingApi(api_client)
            for chunk in _chunks(texts, 5):
                api.push_message(
                    PushMessageRequest(
                        to=user_id,
                        messages=[TextMessage(text=t) for t in chunk],
                    )
                )

    def push_with_detail_button(
        self,
        user_id: str,
        texts: list[str],
        detail_url: str,
        detail_label: str = "📊 Streamlit で詳細を見る",
    ) -> None:
        """テキスト N 通 + 末尾に「詳細を見る」ボタン付き Flex Message を送る."""
        flex = _build_detail_flex(detail_url, detail_label)
        with ApiClient(self._config) as api_client:
            api = MessagingApi(api_client)
            # まずテキストたちを push
            for chunk in _chunks(texts, 5):
                api.push_message(
                    PushMessageRequest(
                        to=user_id,
                        messages=[TextMessage(text=t) for t in chunk],
                    )
                )
            # 最後にボタン
            api.push_message(
                PushMessageRequest(to=user_id, messages=[flex]),
            )


def _chunks(items: list[str], size: int):  # type: ignore[no-untyped-def]
    """リストを size 件ずつのチャンクに分けるジェネレータ."""
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _build_detail_flex(url: str, label: str) -> FlexMessage:
    """Streamlit リンクボタン用の Flex Message."""
    bubble = FlexBubble(
        body=FlexBox(
            layout="vertical",
            contents=[
                FlexText(
                    text="📊 詳細・履歴・他エージェントの中間出力",
                    weight="bold",
                    size="md",
                    wrap=True,
                ),
                FlexText(
                    text="Streamlit ダッシュボードで確認できます (Mac 端末から)",
                    size="sm",
                    color="#888888",
                    wrap=True,
                    margin="sm",
                ),
                FlexButton(
                    style="primary",
                    color="#5B7CFF",
                    action=URIAction(label=label, uri=url),
                    margin="md",
                ),
            ],
        ),
    )
    return FlexMessage(alt_text="詳細を Streamlit で見る", contents=bubble)
