"""A: Researcher — Web 検索と情報収集を担当.

Phase 3 拡張:
- ChromaDB の QAMemory から類似する過去の Q&A を取得し、State.memory_context に格納
- LLM プロンプトに過去 Q&A を注入することで「先週と比べて」等の文脈質問に対応
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.state import AgentState
from src.llm import AgentRole, get_llm
from src.memory.vector_store import QAMemory
from src.memory.vector_store import format_for_prompt as format_memory
from src.tools.web_search import format_for_prompt as format_search
from src.tools.web_search import search

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """あなたは熟練したリサーチアシスタントです。
ユーザーの質問に答えるために必要な情報を Web 検索結果と過去の関連 Q&A から整理し、
事実ベースで簡潔にまとめてください。

ルール:
- 推測や憶測を交えない (検索結果に書かれていない情報は書かない)
- 出典 URL を明示する (例: [1] のような参照番号で記載)
- 数値・日付は引用元のまま正確に転記する
- 矛盾する情報があれば両論併記する
- 過去の Q&A が提供されている場合、「先週」「前回」など時系列を意識した質問では、
  過去回答を参照して差分・変化を強調する"""


def run_researcher(state: AgentState) -> AgentState:
    """Web 検索 + 過去 Q&A → LLM で要約 → state を更新."""
    question = state["question"]

    # 1. 過去の関連 Q&A を取得 (ChromaDB)
    try:
        memory = QAMemory()
        past_records = memory.search(question, top_k=3)
        memory_text = format_memory(past_records)
        logger.info("Researcher: 過去 Q&A %d 件取得", len(past_records))
    except Exception as e:  # noqa: BLE001 — メモリ層の障害で本体を止めない
        logger.warning("Researcher: QAMemory 取得失敗: %s", e)
        memory_text = "(過去の関連 Q&A なし)"

    # 2. Web 検索
    results = search(question, max_results=5)
    sources = [r.url for r in results]
    search_text = format_search(results)

    # 3. LLM で要約
    llm = get_llm(AgentRole.RESEARCHER)
    response = llm.invoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"# ユーザーの質問\n{question}\n\n"
                    f"# 過去の関連 Q&A\n{memory_text}\n\n"
                    f"# Web 検索結果\n{search_text}\n\n"
                    f"上記をもとに、質問に答えるための事実情報を 300〜500 文字でまとめてください。"
                )
            ),
        ]
    )

    return {
        **state,
        "research_notes": str(response.content),
        "research_sources": sources,
        "memory_context": memory_text,
    }
