"""A: Researcher — Web 検索と情報収集を担当."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.state import AgentState
from src.llm import AgentRole, get_llm
from src.tools.web_search import format_for_prompt, search

_SYSTEM_PROMPT = """あなたは熟練したリサーチアシスタントです。
ユーザーの質問に答えるために必要な情報を Web 検索結果から整理し、
事実ベースで簡潔にまとめてください。

ルール:
- 推測や憶測を交えない (検索結果に書かれていない情報は書かない)
- 出典 URL を明示する (例: [1] のような参照番号で記載)
- 数値・日付は引用元のまま正確に転記する
- 矛盾する情報があれば両論併記する"""


def run_researcher(state: AgentState) -> AgentState:
    """Web 検索 → LLM で要約 → state を更新."""
    question = state["question"]

    # 1. Web 検索
    results = search(question, max_results=5)
    sources = [r.url for r in results]
    search_text = format_for_prompt(results)

    # 2. LLM で要約
    llm = get_llm(AgentRole.RESEARCHER)
    response = llm.invoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"# ユーザーの質問\n{question}\n\n"
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
    }
