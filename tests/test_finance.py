"""yfinance ラッパーのテスト (ネットワーク不要 — 抽出・整形ロジックのみ)."""

from __future__ import annotations

from src.tools.finance import (
    StockSnapshot,
    extract_tickers,
    format_for_prompt,
)


def test_extract_direct_us_ticker() -> None:
    """米国株の直接ティッカー記述を抽出."""
    assert "AAPL" in extract_tickers("AAPL の今後について教えて")
    assert "NVDA" in extract_tickers("$NVDA は買いですか?")


def test_extract_direct_jp_ticker() -> None:
    """日本株のティッカー (4桁数字 + .T) を抽出."""
    assert "7203.T" in extract_tickers("7203.T の業績を教えて")


def test_extract_company_name_jp() -> None:
    """社名から日本株ティッカーへの逆引き."""
    tickers = extract_tickers("トヨタの業績はどうですか")
    assert "7203.T" in tickers


def test_extract_company_name_us_with_kana() -> None:
    """カタカナ社名から米国株ティッカーへの逆引き."""
    tickers = extract_tickers("エヌビディアとアップルの比較")
    assert "NVDA" in tickers
    assert "AAPL" in tickers


def test_extract_skips_unlisted() -> None:
    """非上場企業 (空ティッカー) はスキップ."""
    assert extract_tickers("OpenAI と Anthropic はどっちが優勢?") == []


def test_extract_returns_max_3() -> None:
    """max_tickers=3 を超える銘柄が言及されていても 3 件に制限."""
    text = "Apple, Microsoft, Google, Amazon, Tesla を比較"
    assert len(extract_tickers(text, max_tickers=3)) == 3


def test_extract_no_ticker_in_general_question() -> None:
    """銘柄に関係ない質問では空リスト."""
    assert extract_tickers("今日の天気は?") == []


def test_format_empty() -> None:
    """空リストは「株価データなし」."""
    assert format_for_prompt([]) == "(株価データなし)"


def test_format_includes_key_fields() -> None:
    """整形結果に主要フィールドが含まれる."""
    snap = StockSnapshot(
        ticker="AAPL",
        name="Apple Inc.",
        price=180.50,
        currency="USD",
        change_pct_1d=1.23,
        market_cap=3_000_000_000_000,
        pe_ratio=29.5,
        summary="Apple designs consumer electronics.",
    )
    text = format_for_prompt([snap])
    assert "Apple Inc." in text
    assert "AAPL" in text
    assert "180.50" in text
    assert "+1.23%" in text
    assert "29.5" in text
    assert "consumer electronics" in text


def test_format_handles_missing_fields() -> None:
    """価格欠損銘柄もクラッシュせず整形できる."""
    snap = StockSnapshot(
        ticker="XYZ",
        name="Unknown Co",
        price=None,
        currency="",
        change_pct_1d=None,
        market_cap=None,
        pe_ratio=None,
        summary="",
    )
    text = format_for_prompt([snap])
    assert "Unknown Co" in text
    assert "XYZ" in text
