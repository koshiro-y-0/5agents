"""B: Analyst — 分析・予測を担当.

Phase 3 拡張:
- 質問からティッカーを抽出 → yfinance でリアルタイム株価データを取得
- 取得できた場合は分析プロンプトに自動注入
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents._prompt_utils import build_system_prompt
from src.agents.state import AgentState
from src.llm import AgentRole, get_llm
from src.tools.finance import (
    extract_tickers,
    fetch_snapshots,
)
from src.tools.finance import (
    format_for_prompt as format_stock_data,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """あなたは分析・予測の専門家です。
Researcher が集めた情報と、可能であれば直近の株価データをもとに、
質問の本質に踏み込んだ分析と、妥当性のある予測・示唆を提供してください。

ルール:
- データに基づく定量的な分析を優先する
- 株価データが提供されている場合は、価格・PER・時価総額を分析に明示的に取り入れる
- 推測には「推測」「可能性」など確信度を示す語を必ず付ける
- トレンド・パターン・因果関係を意識する
- 投資判断などのアドバイスは「最終決定は本人」と明示する"""


def run_analyst(state: AgentState) -> AgentState:
    """Researcher の出力 + 株価データを受け、分析・予測を生成."""
    question = state["question"]

    # 1. 銘柄ティッカー抽出 → 株価取得
    tickers = extract_tickers(question)
    stock_block = "(株価データなし)"
    if tickers:
        logger.info("Analyst: 抽出されたティッカー = %s", tickers)
        snapshots = fetch_snapshots(tickers)
        stock_block = format_stock_data(snapshots)

    # 2. LLM で分析
    llm = get_llm(AgentRole.ANALYST)
    response = llm.invoke(
        [
            SystemMessage(content=build_system_prompt(_SYSTEM_PROMPT)),
            HumanMessage(
                content=(
                    f"# ユーザーの質問\n{question}\n\n"
                    f"# Researcher の調査結果\n{state.get('research_notes', '(なし)')}\n\n"
                    f"# 株価データ (yfinance)\n{stock_block}\n\n"
                    f"上記をもとに、質問への分析・予測・示唆を 400〜600 文字でまとめてください。"
                )
            ),
        ]
    )

    return {**state, "analysis": str(response.content)}
