"""Tavily Web 検索の薄いラッパー.

責務:
- API キー未設定時はスタブを返し、開発環境で Tavily 未取得でも動くようにする
- 結果を `WebSearchResult` の dataclass で正規化し、エージェント側から扱いやすくする
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from tavily import TavilyClient

from src.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class WebSearchResult:
    """1 件の Web 検索結果."""

    title: str
    url: str
    content: str  # Tavily が抽出した本文の要約
    score: float  # 関連度スコア (0.0 〜 1.0)


def search(query: str, max_results: int = 5, topic: str = "general") -> list[WebSearchResult]:
    """Tavily で Web 検索を実行.

    Args:
        query: 検索クエリ。
        max_results: 取得件数の上限 (Tavily の料金最適化のため 5 以下推奨)。
        topic: "general" | "news" — ニュース指定で `days=7` 相当の鮮度フィルタが効く。

    Returns:
        WebSearchResult のリスト。API キー未設定時は空リストを返す。
    """
    settings = get_settings()
    if not settings.tavily_api_key or settings.tavily_api_key.startswith("your_"):
        logger.warning("TAVILY_API_KEY 未設定 — 空の検索結果を返します")
        return []

    client = TavilyClient(api_key=settings.tavily_api_key)
    response = client.search(
        query=query,
        max_results=max_results,
        topic=topic,
        search_depth="basic",  # "advanced" は料金 2 倍なので basic で開始
    )

    results = response.get("results", [])
    return [
        WebSearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            content=item.get("content", ""),
            score=float(item.get("score", 0.0)),
        )
        for item in results
    ]


def format_for_prompt(results: list[WebSearchResult]) -> str:
    """検索結果を LLM プロンプト埋め込み用のテキストに整形."""
    if not results:
        return "(検索結果なし)"

    lines = []
    for i, r in enumerate(results, start=1):
        lines.append(f"[{i}] {r.title}")
        lines.append(f"    URL: {r.url}")
        lines.append(f"    要約: {r.content}")
        lines.append("")
    return "\n".join(lines)
