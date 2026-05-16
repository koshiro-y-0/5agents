"""エージェントのシステムプロンプト構築ユーティリティ.

全エージェントが共通で使うべき要素 (現在日付など) をここに集約することで、
LLM が「最新」と判断する基準を明確にし、古い情報を「先日」と誤解する
ハルシネーションを防ぐ。
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


def current_date_block() -> str:
    """全エージェントのシステムプロンプト先頭に挿入する日付ブロック.

    Returns:
        例: "# 現在の日付情報\\n本日は 2026年5月16日 (土) です..."
    """
    now = datetime.now(JST)
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    weekday = weekdays[now.weekday()]
    return (
        "# 現在の日付情報\n"
        f"本日の日付: **{now.year}年{now.month}月{now.day}日 ({weekday})** (JST)\n"
        "\n"
        "重要なルール:\n"
        "- 「先日」「直近」「最近」「今期」などの相対的な時間表現を解釈する際は、\n"
        "  必ずこの日付を基準にすること。\n"
        "- 検索結果や記憶された過去 Q&A に含まれる日付が、現在より過去すぎる場合は\n"
        "  「最新の情報ではない可能性」を明示すること。\n"
        "- 未来の日付の出来事を「既に起きた」と書かないこと。\n"
    )


def build_system_prompt(role_specific: str) -> str:
    """役割別プロンプトの先頭に共通の日付ブロックを付けて返す."""
    return f"{current_date_block()}\n---\n{role_specific.strip()}\n"
