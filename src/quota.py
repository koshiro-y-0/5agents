"""Gemini Flash 無料枠の使用量トラッキングと事前ガード.

責務:
- SQLite の agent_calls から今日の Flash 呼び出し回数を取得
- 上限への接近度をレベル (ok / warn / danger / exhausted) で返す
- Streamlit / scheduler の双方から共通利用される

呼び出し例:
    from src.quota import get_flash_quota_status, has_quota_for_question

    status = get_flash_quota_status()
    if not has_quota_for_question():
        ...  # ブロック or スキップ
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from src.config import get_settings
from src.memory.logger import RunLogger

logger = logging.getLogger(__name__)

# 1 質問あたりの Gemini Flash 呼び出し回数
# 案 X-1 では A Researcher + E Finalizer のみ Flash を使用 (B は Lite, C/D は Groq)
FLASH_CALLS_PER_QUESTION = 2

QuotaLevel = Literal["ok", "warn", "danger", "exhausted"]


@dataclass(frozen=True)
class QuotaStatus:
    """Gemini Flash の今日の使用状況."""

    used: int          # 今日すでに消費した Flash 呼び出し回数
    limit: int         # 1 日の上限 (settings.gemini_flash_daily_limit)
    remaining: int     # 残り呼び出し回数 (max(0, limit - used))
    pct: float         # 使用率 (0.0 - 1.0)
    level: QuotaLevel  # 警告レベル

    @property
    def can_run_question(self) -> bool:
        """もう 1 質問処理する余裕があるか (Flash 2 calls 必要)."""
        return self.remaining >= FLASH_CALLS_PER_QUESTION


def get_flash_quota_status() -> QuotaStatus:
    """現在の Gemini Flash 使用状況を返す.

    SQLite アクセスに失敗した場合は使用量 0 (ok) として返し、メイン処理を止めない。
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

    return QuotaStatus(used=used, limit=limit, remaining=remaining, pct=pct, level=level)


def has_quota_for_question() -> bool:
    """今、もう 1 質問を処理する余裕があるか."""
    return get_flash_quota_status().can_run_question
