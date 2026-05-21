"""src/line/formatter.py のテスト (LINE API なし、純粋なロジック検証)."""

from __future__ import annotations

from src.line.formatter import (
    LINE_MAX_TEXT_LENGTH,
    build_detail_url,
    markdown_to_line,
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
    """msg1 に結論+根拠、msg2 にリスク+出典が含まれる (Phase 5 Theme B 装飾後でも有効)."""
    msg1, msg2 = split_for_line(_SAMPLE_FINALIZER_OUTPUT)
    # msg1: 結論 + 根拠 (装飾後は `🎯 結論` / `📌 根拠` という形)
    assert "結論" in msg1
    assert "🎯" in msg1
    assert "根拠" in msg1
    assert "📌" in msg1
    assert "リスク" not in msg1
    # msg2: リスク + 出典
    assert "リスク" in msg2 or "反論" in msg2
    assert "⚠️" in msg2 or "💬" in msg2
    assert "出典" in msg2
    assert "🔗" in msg2
    assert "結論" not in msg2
    # Markdown 記号が生のまま残っていないこと
    assert "##" not in msg1
    assert "##" not in msg2


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


# ── Phase 5 Theme B: markdown_to_line() の単体テスト ──


def test_markdown_to_line_h2_known_sections_get_emoji() -> None:
    """既知のセクション見出しに対応する絵文字が付与される."""
    assert "🎯" in markdown_to_line("## 結論")
    assert "📌" in markdown_to_line("## 根拠")
    assert "⚠️" in markdown_to_line("## リスク・反論")
    assert "🔗" in markdown_to_line("## 出典")


def test_markdown_to_line_h2_unknown_section_uses_default_emoji() -> None:
    """未知のセクション見出しはデフォルト絵文字 (📝)."""
    out = markdown_to_line("## まとめ")
    assert "📝" in out
    assert "まとめ" in out


def test_markdown_to_line_h2_strips_markdown_hash() -> None:
    """`##` 自体は出力に残らない."""
    out = markdown_to_line("## 結論\n本文。")
    assert "##" not in out
    assert "結論" in out
    assert "本文。" in out


def test_markdown_to_line_h2_adds_rule_lines() -> None:
    """H2 見出しの前後に区切り線 (━) が入る."""
    out = markdown_to_line("## 結論")
    # 上下 2 本の区切り線 (3 行構成)
    lines = out.split("\n")
    assert len(lines) >= 3
    assert "━" in lines[0]
    assert "━" in lines[-1]


def test_markdown_to_line_h3_subheading() -> None:
    """`### サブ` → `▸ サブ`."""
    assert markdown_to_line("### サブ見出し").startswith("▸ サブ見出し")


def test_markdown_to_line_bold_becomes_brackets() -> None:
    """`**bold**` → `「bold」`."""
    assert markdown_to_line("これは **重要** です") == "これは 「重要」 です"


def test_markdown_to_line_bullets_use_squares() -> None:
    """行頭 `* ` / `- ` → `▪ `."""
    src = "* 項目A\n- 項目B\n"
    out = markdown_to_line(src)
    assert "▪ 項目A" in out
    assert "▪ 項目B" in out
    # bullet の前の `* ` / `- ` が残っていないこと
    assert "* 項目" not in out
    assert "- 項目" not in out


def test_markdown_to_line_indented_bullets_preserved() -> None:
    """インデントされた bullet も装飾され、インデントは維持される."""
    src = "  - インデント項目"
    out = markdown_to_line(src)
    assert out == "  ▪ インデント項目"


def test_markdown_to_line_horizontal_rule_replaced() -> None:
    """`---` (水平線) → 細い区切り線."""
    out = markdown_to_line("前\n\n---\n\n後")
    assert "─" in out
    assert "---" not in out


def test_markdown_to_line_url_passthrough() -> None:
    """URL はそのまま (LINE 側で自動リンク化される)."""
    src = "出典: https://example.com/foo"
    assert markdown_to_line(src) == src


def test_markdown_to_line_empty_input() -> None:
    assert markdown_to_line("") == ""


def test_markdown_to_line_no_markdown_passthrough() -> None:
    """Markdown 記号を含まない素のテキストは変化なし."""
    src = "ただの一行テキストです。"
    assert markdown_to_line(src) == src


def test_markdown_to_line_full_finalizer_output() -> None:
    """実 Finalizer 出力相当の全体に対する E2E 変換テスト."""
    out = markdown_to_line(_SAMPLE_FINALIZER_OUTPUT)
    # 装飾後にあるべきもの
    assert "🎯" in out and "結論" in out
    assert "📌" in out and "根拠" in out
    assert "⚠️" in out and "リスク" in out
    assert "🔗" in out and "出典" in out
    # 原本にあった本文は維持
    assert "AI 需要拡大により今期も成長" in out
    assert "https://example.com/nvda1" in out
    # Markdown 記号は除去
    assert "##" not in out
    # 行頭の `- 売上高...` は装飾される
    assert "▪ 売上高 500 億ドル予測 [1]" in out
