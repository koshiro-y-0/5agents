"""src/agents/_prompt_utils.py のテスト (LLM 呼び出しなし)."""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

from src.agents._prompt_utils import build_system_prompt, current_date_block


def test_current_date_block_contains_today() -> None:
    """日付ブロックに今日の年月日が含まれる."""
    block = current_date_block()
    now = datetime.now(ZoneInfo("Asia/Tokyo"))
    assert str(now.year) in block
    assert f"{now.month}月" in block
    assert f"{now.day}日" in block


def test_current_date_block_includes_weekday() -> None:
    """日本語の曜日が含まれる."""
    block = current_date_block()
    # 月火水木金土日 のいずれかが含まれる
    assert re.search(r"\([月火水木金土日]\)", block) is not None


def test_current_date_block_includes_temporal_rules() -> None:
    """相対表現の解釈ルールが含まれる."""
    block = current_date_block()
    assert "先日" in block or "最近" in block  # 相対表現の例示
    assert "未来" in block  # 未来日付の禁止ルール


def test_build_system_prompt_prepends_date_block() -> None:
    """役割固有プロンプトの先頭に日付ブロックが付く."""
    role_prompt = "あなたはテストアシスタントです。"
    composed = build_system_prompt(role_prompt)
    # 日付ブロックが先に来て、その後に役割プロンプトが続く
    assert composed.index("# 現在の日付情報") < composed.index("テストアシスタント")
    assert "---" in composed  # 区切り線
