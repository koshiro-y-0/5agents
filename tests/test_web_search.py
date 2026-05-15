"""Tavily ラッパーのテスト (API キー不要 — フォーマット & スタブのみ検証)."""

from __future__ import annotations

from src.tools.web_search import WebSearchResult, format_for_prompt, search


def test_format_empty_results() -> None:
    """検索結果ゼロのときは「検索結果なし」が返る."""
    assert format_for_prompt([]) == "(検索結果なし)"


def test_format_includes_title_url_content() -> None:
    """整形結果にタイトル・URL・要約が含まれる."""
    results = [
        WebSearchResult(title="記事A", url="https://example.com/a", content="本文A", score=0.9),
        WebSearchResult(title="記事B", url="https://example.com/b", content="本文B", score=0.8),
    ]
    text = format_for_prompt(results)
    assert "記事A" in text
    assert "https://example.com/a" in text
    assert "本文A" in text
    assert "記事B" in text


def test_search_returns_empty_when_key_missing(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """TAVILY_API_KEY 未設定なら API を呼ばずに空リストを返す."""
    from src import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("TAVILY_API_KEY", "your_tavily_api_key_here")
    results = search("test query")
    assert results == []
    config.get_settings.cache_clear()
