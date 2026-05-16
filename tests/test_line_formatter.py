"""src/line/formatter.py のテスト (LINE API なし、純粋なロジック検証)."""

from __future__ import annotations

from src.line.formatter import (
    LINE_MAX_TEXT_LENGTH,
    build_detail_url,
    parse_sections,
    split_for_line,
)

_SAMPLE_FINALIZER_OUTPUT = """## 結論

NVDA は AI 需要拡大により今期も成長見込み。

## 根拠

- 売上高 500 億ドル予測 [1]
- データセンター GPU 需要が継続 [2]

## リスク・反論

- AI ブーム持続性への疑問
- 競合 (AMD, Cerebras) の追い上げ

## 出典

[1] https://example.com/nvda1
[2] https://example.com/nvda2
"""


def test_parse_sections_extracts_all_four() -> None:
    sections = parse_sections(_SAMPLE_FINALIZER_OUTPUT)
    assert "AI 需要拡大" in sections.conclusion
    assert "売上高 500 億ドル" in sections.evidence
    assert "AI ブーム持続性" in sections.risks
    assert "https://example.com/nvda1" in sections.sources


def test_parse_sections_handles_risk_alternate_label() -> None:
    """「リスク」「リスク・反論」「反論」のいずれの見出しでもマッチ."""
    md = "## 結論\nC\n\n## 反論\nR\n"
    sections = parse_sections(md)
    assert sections.risks == "R"


def test_split_for_line_creates_two_messages() -> None:
    msg1, msg2 = split_for_line(_SAMPLE_FINALIZER_OUTPUT)
    # msg1: 結論 + 根拠
    assert "## 結論" in msg1
    assert "## 根拠" in msg1
    assert "## リスク" not in msg1
    # msg2: リスク + 出典
    assert "## リスク" in msg2 or "リスク・反論" in msg2
    assert "## 出典" in msg2
    assert "## 結論" not in msg2


def test_split_for_line_truncates_oversize_text() -> None:
    """各メッセージが 5000 字以内に収まる."""
    huge_evidence = "あ" * 6000
    md = f"## 結論\nC\n\n## 根拠\n{huge_evidence}\n\n## リスク\nR\n\n## 出典\nS\n"
    msg1, msg2 = split_for_line(md)
    assert len(msg1) <= LINE_MAX_TEXT_LENGTH
    assert len(msg2) <= LINE_MAX_TEXT_LENGTH
    assert "続き" in msg1  # 切り詰めサフィックス


def test_split_for_line_fallback_when_no_sections() -> None:
    """セクション見出しが無い場合は文字数で半分割するフォールバック."""
    plain = "ただのテキスト。" * 200
    msg1, msg2 = split_for_line(plain)
    # 両方とも何らかの内容を持つ
    assert msg1
    assert msg2
    assert len(msg1) + len(msg2) >= len(plain) - 50  # 多少のロスは許容


def test_build_detail_url_without_run_id() -> None:
    assert build_detail_url("http://localhost:8501", None) == "http://localhost:8501"


def test_build_detail_url_with_run_id() -> None:
    url = build_detail_url("http://localhost:8501/", "abc-123")
    assert url == "http://localhost:8501/?run_id=abc-123"


def test_split_for_line_handles_missing_evidence_section() -> None:
    """根拠が無くても結論セクションだけで msg1 を作る."""
    md = "## 結論\n結論のみ。\n\n## 出典\n[1] xxx\n"
    msg1, msg2 = split_for_line(md)
    assert "結論のみ" in msg1
    assert "出典" in msg2
