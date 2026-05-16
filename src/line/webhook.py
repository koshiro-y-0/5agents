"""LINE Messaging API Webhook 受信エンドポイント (FastAPI).

起動:
    uv run uvicorn src.line.webhook:app --host 127.0.0.1 --port 8080

公開 (例: Tailscale Funnel):
    tailscale funnel 8080

LINE Console の Webhook URL に
    https://<your-tailscale-domain>.ts.net/line/webhook
を設定する。

設計:
1. POST /line/webhook で events を受信
2. 署名検証 (X-Line-Signature) — 失敗で 403
3. ユーザーID フィルタ — 許可外なら静かに無視
4. Quota guard — Flash 残量不足なら「枠を使い切りました」と即返信
5. Reply Token で即「考え中...」をユーザーに返す
6. BackgroundTasks で 5agents.answer() を起動
7. 完了後、Push API で 2 通 + Flex (詳細ボタン) を送信
"""

from __future__ import annotations

import logging

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from src.agents.orchestrator import answer
from src.config import get_settings
from src.line.formatter import build_detail_url, split_for_line
from src.line.handler import LineHandler
from src.quota import get_flash_quota_status, has_quota_for_question

# uvicorn は自身のアクセスログだけ出すため、アプリ側 (logger.info 等) が
# 何も出ない問題がある。INFO 以上を stdout/stderr に出すよう明示的に basicConfig。
# launchd の StandardOutPath / StandardErrorPath で logs/webhook.log に流れる。
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(title="5agents LINE Webhook")


# --- ヘルスチェック (Tailscale Funnel の疎通確認用) ---


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# --- メインの Webhook ---


@app.post("/line/webhook")
async def line_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    settings = get_settings()

    if not settings.line_channel_secret or not settings.line_channel_access_token:
        logger.error("LINE 環境変数未設定 (LINE_CHANNEL_SECRET / LINE_CHANNEL_ACCESS_TOKEN)")
        raise HTTPException(
            status_code=503,
            detail="LINE channel is not configured on the server",
        )

    handler = LineHandler(
        channel_secret=settings.line_channel_secret,
        channel_access_token=settings.line_channel_access_token,
    )

    # 署名検証 — 偽 webhook を即破棄
    raw_body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")
    if not handler.verify_signature(raw_body, signature):
        logger.warning("LINE 署名検証失敗 (raw len=%d, sig=%s)", len(raw_body), signature[:10])
        raise HTTPException(status_code=403, detail="invalid signature")

    payload = await request.json()
    events = payload.get("events", [])

    for event in events:
        try:
            _handle_event(event, handler, background_tasks)
        except Exception as e:  # noqa: BLE001 — 1 event の失敗で他を止めない
            logger.exception("event 処理失敗: %s", e)

    return {"status": "ok"}


# --- イベント処理 ---


def _handle_event(
    event: dict,  # type: ignore[type-arg]
    handler: LineHandler,
    background_tasks: BackgroundTasks,
) -> None:
    """1 つの LINE event を処理する."""
    settings = get_settings()
    event_type = event.get("type")
    if event_type != "message":
        # follow / unfollow / join 等は無視 (ログのみ)
        logger.info("LINE event type=%s をスキップ", event_type)
        return

    message = event.get("message", {})
    if message.get("type") != "text":
        # スタンプ・画像等は対応外
        logger.info("LINE message type=%s をスキップ (text のみ対応)", message.get("type"))
        return

    source = event.get("source", {})
    user_id = source.get("userId", "")
    text = message.get("text", "").strip()
    reply_token = event.get("replyToken", "")

    # ユーザーID をログに残す (自分の User ID を取得するため)
    logger.info("LINE 受信: user_id=%s text=%s...", user_id, text[:30])

    # 許可ユーザー以外は無視 (静かに、相手にエラーを返さない = 個人ボットを露呈しない)
    allowed = settings.line_allowed_user_id_list
    if allowed and user_id not in allowed:
        logger.warning("非許可ユーザーからのメッセージを無視: user_id=%s", user_id)
        return

    if not text:
        return

    # Quota guard
    if not has_quota_for_question():
        status = get_flash_quota_status()
        try:
            handler.reply_text(
                reply_token,
                f"⚠️ 本日の Gemini Flash 無料枠 ({status.used}/{status.limit}) を"
                "使い切りました。明日リセット後にもう一度お送りください。",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("枯渇 reply 送信失敗: %s", e)
        return

    # 即時 "考え中..." 返信 (Reply Token は 30 秒制限)
    try:
        handler.reply_text(
            reply_token,
            "🤔 5 エージェントが調査・分析中... (1〜2 分かかります)\n"
            "完了し次第、結果を 2 通に分けて送ります。",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("loading reply 送信失敗 (継続): %s", e)

    # バックグラウンドで 5agents を実行 → 完了後 Push 送信
    background_tasks.add_task(_run_pipeline_and_push, text, user_id, handler)


def _run_pipeline_and_push(question: str, user_id: str, handler: LineHandler) -> None:
    """5agents を実行し、結果を Push で送信."""
    settings = get_settings()
    try:
        state = answer(question)
    except Exception as e:  # noqa: BLE001
        logger.exception("5agents 実行失敗: %s", e)
        try:
            handler.push_messages(
                user_id,
                [f"❌ エラーが発生しました: {type(e).__name__}: {e!s}"[:1000]],
            )
        except Exception:  # noqa: BLE001
            logger.exception("エラー push 送信失敗")
        return

    final_answer = state.get("final_answer", "(回答なし)")
    msg1, msg2 = split_for_line(final_answer)
    detail_url = build_detail_url(
        settings.streamlit_base_url, state.get("run_id")
    )

    try:
        handler.push_with_detail_button(user_id, [msg1, msg2], detail_url)
        logger.info("LINE Push 送信完了: user_id=%s (msg1=%d, msg2=%d chars)",
                    user_id, len(msg1), len(msg2))
    except Exception as e:  # noqa: BLE001
        logger.exception("LINE Push 送信失敗: %s", e)
