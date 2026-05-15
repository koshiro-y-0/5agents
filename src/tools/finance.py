"""yfinance を用いた株価・財務データ取得ラッパー.

責務:
- ユーザー質問から銘柄ティッカーを抽出（簡易ヒューリスティック）
- 株価サマリ・財務指標を取得して LLM 用のテキストに整形
- ネットワーク・API エラー時は空文字を返し、Analyst 側の処理を止めない
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import yfinance as yf

logger = logging.getLogger(__name__)


# 主要日本株 (社名 → ティッカー) のミニ辞書。
# 必要に応じて拡張可能。完全網羅は yfinance API では困難なため最頻出のみ。
_NAME_TO_TICKER_JP: dict[str, str] = {
    "トヨタ": "7203.T",
    "ソニー": "6758.T",
    "任天堂": "7974.T",
    "ソフトバンク": "9984.T",
    "ファーストリテイリング": "9983.T",
    "ユニクロ": "9983.T",
    "三菱ufj": "8306.T",
    "三井住友": "8316.T",
    "キーエンス": "6861.T",
    "リクルート": "6098.T",
    "東京エレクトロン": "8035.T",
    "信越化学": "4063.T",
}

# 米国主要株
_NAME_TO_TICKER_US: dict[str, str] = {
    "apple": "AAPL",
    "アップル": "AAPL",
    "microsoft": "MSFT",
    "マイクロソフト": "MSFT",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "amazon": "AMZN",
    "アマゾン": "AMZN",
    "nvidia": "NVDA",
    "エヌビディア": "NVDA",
    "tesla": "TSLA",
    "テスラ": "TSLA",
    "meta": "META",
    "openai": "",  # 非上場
    "anthropic": "",  # 非上場
}

# 直接ティッカー指定: "AAPL", "7203.T", "$NVDA" を拾う
_TICKER_RE = re.compile(r"\b(?:\$)?([A-Z]{1,5}(?:\.[A-Z])?|\d{4}\.T)\b")


@dataclass
class StockSnapshot:
    """1 銘柄の現在の株価スナップショット."""

    ticker: str
    name: str
    price: float | None
    currency: str
    change_pct_1d: float | None
    market_cap: int | None
    pe_ratio: float | None
    summary: str  # 業種・事業内容の短い要約


def extract_tickers(text: str, max_tickers: int = 3) -> list[str]:
    """質問テキストから関連しそうな銘柄ティッカーを抽出.

    優先順位: 直接ティッカー記述 > 社名 (日) > 社名 (米)
    """
    found: list[str] = []

    # 1. 直接ティッカーをマッチ (大文字を維持するため text を変えない)
    for match in _TICKER_RE.finditer(text):
        ticker = match.group(1)
        # 単純な単語 (e.g. "A", "I", "THE") を除外する簡易ガード
        if len(ticker) == 1:
            continue
        if ticker not in found:
            found.append(ticker)

    # 2. 社名マッチ (大文字小文字を無視)
    lowered = text.lower()
    for name, ticker in {**_NAME_TO_TICKER_JP, **_NAME_TO_TICKER_US}.items():
        if not ticker:  # 非上場は除外
            continue
        if name.lower() in lowered and ticker not in found:
            found.append(ticker)

    return found[:max_tickers]


def fetch_snapshot(ticker: str) -> StockSnapshot | None:
    """1 銘柄の最新スナップショットを取得.

    ネットワーク・API エラー時は None を返す。
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        hist = t.history(period="2d", auto_adjust=False)

        price = float(hist["Close"].iloc[-1]) if not hist.empty else info.get("currentPrice")
        change_pct: float | None = None
        if not hist.empty and len(hist) >= 2:
            prev = float(hist["Close"].iloc[-2])
            if prev:
                change_pct = (float(hist["Close"].iloc[-1]) - prev) / prev * 100.0

        return StockSnapshot(
            ticker=ticker,
            name=info.get("longName") or info.get("shortName") or ticker,
            price=price,
            currency=info.get("currency", ""),
            change_pct_1d=change_pct,
            market_cap=info.get("marketCap"),
            pe_ratio=info.get("trailingPE"),
            summary=(info.get("longBusinessSummary") or "")[:300],
        )
    except Exception as e:  # noqa: BLE001 - yfinance は多様な例外を投げるため広く捕捉
        logger.warning("yfinance fetch failed for %s: %s", ticker, e)
        return None


def fetch_snapshots(tickers: list[str]) -> list[StockSnapshot]:
    """複数銘柄のスナップショットを順次取得 (失敗銘柄はスキップ)."""
    out: list[StockSnapshot] = []
    for t in tickers:
        snap = fetch_snapshot(t)
        if snap is not None:
            out.append(snap)
    return out


def format_for_prompt(snapshots: list[StockSnapshot]) -> str:
    """スナップショットを LLM プロンプト用テキストに整形."""
    if not snapshots:
        return "(株価データなし)"

    lines: list[str] = []
    for s in snapshots:
        lines.append(f"## {s.name} ({s.ticker})")
        if s.price is not None:
            change_str = (
                f" ({s.change_pct_1d:+.2f}%)" if s.change_pct_1d is not None else ""
            )
            lines.append(f"- 株価: {s.price:.2f} {s.currency}{change_str}")
        if s.market_cap:
            lines.append(f"- 時価総額: {s.market_cap:,} {s.currency}")
        if s.pe_ratio:
            lines.append(f"- PER: {s.pe_ratio:.2f}")
        if s.summary:
            lines.append(f"- 事業概要: {s.summary}")
        lines.append("")
    return "\n".join(lines)
