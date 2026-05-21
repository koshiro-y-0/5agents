"""Gemini Flash 無料枠の使用量トラッキングと事前ガード.

責務:
- SQLite の agent_calls から今日の Flash 呼び出し回数を取得
- 上限への接近度をレベル (ok / warn / danger / exhausted) で返す
- Phase 5 Theme A: 次のリセット時刻 (reset_at) と残り時間 (time_until_reset) を提供
- Streamlit / scheduler の双方から共通利用される

呼び出し例:
    from src.quota import get_flash_quota_status, has_quota_for_question

    status = get_flash_quota_status()
    if not has_quota_for_question():
        # 例: "⏰ あと 3 時間 24 分 で復活します (明日 00:00 JST)"
        ...

リセット時刻の注意:
- 本モジュールは「アプリ視点のリセット = 翌 JST 00:00」を返す。
  これは SQLite の `today_jst` 集計と一致させるための仕様。
- 実際の Google AI Free Tier (Gemini Flash 20 RPD) のリセットは
  米国 Pacific Time 00:00 (= JST 16:00 PDT / 17:00 PST) で起きる。
  従って JST 00:00〜16:00 の時間帯は Google 側は既にリセット済みだが
  アプリの今日カウントが残っているため「保守的に多く計上」される。安全側。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

from src.config import get_settings
from src.memory.logger import RunLogger

logger = logging.getLogger(__name__)

# 1 質問あたりの Gemini Flash 呼び出し回数
# 案 X-1 では A Researcher + E Finalizer のみ Flash を使用 (B は Lite, C/D は Groq)
FLASH_CALLS_PER_QUESTION = 2

# 日本標準時 (UTC+9)
JST = timezone(timedelta(hours=9))

QuotaLevel = Literal["ok", "warn", "danger", "exhausted"]


@dataclass(frozen=True)
class QuotaStatus:
    """Gemini Flash の今日の使用状況."""

    used: int                      # 今日すでに消費した Flash 呼び出し回数
    limit: int                     # 1 日の上限 (settings.gemini_flash_daily_limit)
    remaining: int                 # 残り呼び出し回数 (max(0, limit - used))
    pct: float                     # 使用率 (0.0 - 1.0)
    level: QuotaLevel              # 警告レベル
    reset_at: datetime             # 次にリセットされる時刻 (JST aware = 翌 JST 00:00)
    time_until_reset: timedelta    # 今から reset_at までの残り時間

    @property
    def can_run_question(self) -> bool:
        """もう 1 質問処理する余裕があるか (Flash 2 calls 必要)."""
        return self.remaining >= FLASH_CALLS_PER_QUESTION

    @property
    def reset_at_jst_str(self) -> str:
        """`reset_at` の JST 表現. 例: '明日 00:00 JST' / '今日 16:00 JST'."""
        now = datetime.now(JST)
        prefix = "明日" if self.reset_at.date() > now.date() else "今日"
        return f"{prefix} {self.reset_at.strftime('%H:%M')} JST"


def _next_jst_midnight(now: datetime | None = None) -> datetime:
    """次の JST 00:00 (翌日午前 0:00) を返す.

    `now` が JST 00:00 ちょうどの場合も「次の」00:00 を返す (= 24 時間後)。
    `now` の tzinfo は JST に正規化される (timezone-aware 必須)。
    """
    if now is None:
        now = datetime.now(JST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=JST)
    else:
        now = now.astimezone(JST)
    tomorrow = (now + timedelta(days=1)).date()
    return datetime.combine(tomorrow, datetime.min.time(), tzinfo=JST)


def format_until_reset(td: timedelta) -> str:
    """timedelta を人間が読みやすい日本語の残り時間文字列に変換.

    例:
      - 30 秒          → "まもなく復活"
      - 45 分          → "あと 45 分"
      - 3 時間 24 分   → "あと 3 時間 24 分"
      - 1 日           → "あと 1 日"
      - 負の値         → "まもなく復活" (時刻ズレ等の保険)
    """
    total = int(td.total_seconds())
    if total < 60:
        return "まもなく復活"
    if total < 3600:
        return f"あと {total // 60} 分"
    if total < 86400:
        h = total // 3600
        m = (total % 3600) // 60
        return f"あと {h} 時間 {m} 分"
    return f"あと {total // 86400} 日"


def get_flash_quota_status(now: datetime | None = None) -> QuotaStatus:
    """現在の Gemini Flash 使用状況を返す.

    Args:
        now: 計算基準時刻 (test 用に注入可能). None なら datetime.now(JST).

    SQLite アクセスに失敗した場合は使用量 0 (ok) として返し、メイン処理を止めない。
    reset_at は常に翌 JST 00:00 を返す (アプリの集計基準と一致).
    """
    settings = get_settings()
    limit = settings.gemini_flash_daily_limit
    main_model = settings.gemini_model_main

    used = 0
    try:
        used = RunLogger().get_today_model_call_count(main_model)
    except Exception as e:  # noqa: BLE001
        logger.warning("Quota status check failed (treating as ok): %s", e)

    remaining = max(0, limit - used)
    pct = used / limit if limit > 0 else 0.0

    level: QuotaLevel
    if remaining < FLASH_CALLS_PER_QUESTION:
        # 次の 1 質問が走れないので「実質的に枯渇」と扱う
        level = "exhausted"
    elif pct >= settings.quota_danger_threshold:
        level = "danger"
    elif pct >= settings.quota_warn_threshold:
        level = "warn"
    else:
        level = "ok"

    # リセット時刻の計算 (Phase 5 Theme A)
    if now is None:
        now = datetime.now(JST)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=JST)
    else:
        now = now.astimezone(JST)
    reset_at = _next_jst_midnight(now)
    time_until_reset = reset_at - now

    return QuotaStatus(
        used=used,
        limit=limit,
        remaining=remaining,
        pct=pct,
        level=level,
        reset_at=reset_at,
        time_until_reset=time_until_reset,
    )


def has_quota_for_question() -> bool:
    """今、もう 1 質問を処理する余裕があるか."""
    return get_flash_quota_status().can_run_question
