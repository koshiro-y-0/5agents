"""Fact-checker の JSON パースロジックの単体テスト (API キー不要)."""

from __future__ import annotations

from src.agents.factchecker import _parse_json_response


def test_parse_plain_json() -> None:
    """素の JSON が正しくパースされる."""
    text = '{"verdict": "OK", "issues": []}'
    result = _parse_json_response(text)
    assert result["verdict"] == "OK"
    assert result["issues"] == []


def test_parse_json_in_markdown_fence() -> None:
    """Markdown コードフェンスで囲まれていてもパースできる."""
    text = '```json\n{"verdict": "NG", "issues": ["根拠不足"]}\n```'
    result = _parse_json_response(text)
    assert result["verdict"] == "NG"
    assert result["issues"] == ["根拠不足"]


def test_parse_json_with_leading_text() -> None:
    """前後に説明文が混じっていても抽出できる."""
    text = 'はい、検証しました。\n{"verdict": "NG", "issues": ["A", "B"]}\n以上です。'
    result = _parse_json_response(text)
    assert result["verdict"] == "NG"
    assert set(result["issues"]) == {"A", "B"}


def test_invalid_verdict_normalized_to_ng() -> None:
    """verdict が OK/NG 以外の場合は NG にフォールバック (フェイルセーフ)."""
    text = '{"verdict": "MAYBE", "issues": []}'
    result = _parse_json_response(text)
    assert result["verdict"] == "NG"


def test_unparseable_response_returns_ng() -> None:
    """JSON 解釈不能なテキストは NG + 生レスポンスを issue に残す."""
    text = "わかりません"
    result = _parse_json_response(text)
    assert result["verdict"] == "NG"
    assert len(result["issues"]) == 1
    assert "JSON パース失敗" in result["issues"][0]


def test_issues_coerced_to_list() -> None:
    """issues が文字列で返ってきた場合もリストに正規化."""
    text = '{"verdict": "NG", "issues": "single issue"}'
    result = _parse_json_response(text)
    assert result["verdict"] == "NG"
    assert result["issues"] == ["single issue"]
