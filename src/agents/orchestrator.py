"""5 エージェント連携オーケストレーター (LangGraph).

パイプライン:
    START → A → B → C → D → (条件分岐) → E → END
                              ├ verdict=OK             → finalizer
                              ├ verdict=NG, retry<max → analyst (差し戻し)
                              └ verdict=NG, retry≥max → finalizer (注釈付き)

各エージェントは AgentState を受け取り、自身が責任を持つフィールドを書き込む。
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, START, StateGraph

from src.agents.analyst import run_analyst
from src.agents.critic import run_critic
from src.agents.factchecker import run_factchecker
from src.agents.finalizer import run_finalizer
from src.agents.researcher import run_researcher
from src.agents.state import AgentState
from src.config import get_settings

logger = logging.getLogger(__name__)


def _route_after_factcheck(state: AgentState) -> Literal["analyst", "finalizer"]:
    """Fact-checker の判定とリトライ回数から次ノードを決定."""
    settings = get_settings()
    fact_check = state.get("fact_check", {"verdict": "OK", "issues": []})
    retry_count = state.get("retry_count", 0)

    if fact_check["verdict"] == "OK":
        return "finalizer"
    if retry_count >= settings.max_factcheck_retries:
        logger.warning("Fact-check リトライ上限到達 (%d 回) — Finalizer に進む", retry_count)
        return "finalizer"
    logger.info("Fact-check NG — Analyst へ差し戻し (retry=%d)", retry_count)
    return "analyst"


def build_graph():  # type: ignore[no-untyped-def]
    """5 エージェントの LangGraph を構築して compile したものを返す."""
    graph = StateGraph(AgentState)

    graph.add_node("researcher", run_researcher)
    graph.add_node("analyst", run_analyst)
    graph.add_node("critic", run_critic)
    graph.add_node("factchecker", run_factchecker)
    graph.add_node("finalizer", run_finalizer)

    graph.add_edge(START, "researcher")
    graph.add_edge("researcher", "analyst")
    graph.add_edge("analyst", "critic")
    graph.add_edge("critic", "factchecker")
    graph.add_conditional_edges(
        "factchecker",
        _route_after_factcheck,
        {"analyst": "analyst", "finalizer": "finalizer"},
    )
    graph.add_edge("finalizer", END)

    return graph.compile()


# モジュールロード時に 1 度だけコンパイル (LangGraph はステートレス、再利用可)
_graph = build_graph()


def answer(question: str) -> AgentState:
    """5 エージェントを通してユーザーの質問に回答.

    Args:
        question: ユーザーからの質問。

    Returns:
        最終状態 (各エージェントの中間出力 + final_answer を含む)。
    """
    initial_state: AgentState = {"question": question, "retry_count": 0}
    final_state = _graph.invoke(initial_state)
    return final_state  # type: ignore[return-value]


if __name__ == "__main__":
    # 動作確認: uv run python -m src.agents.orchestrator "質問内容"
    import sys

    q = " ".join(sys.argv[1:]) or "2025年のAIエージェント市場の動向は?"
    result = answer(q)
    print(f"Q: {q}\n")
    print("=== Researcher ===")
    print(result.get("research_notes", "(なし)"))
    print("\n=== Analyst ===")
    print(result.get("analysis", "(なし)"))
    print("\n=== Critic ===")
    print(result.get("critique", "(なし)"))
    print("\n=== Fact-checker ===")
    print(result.get("fact_check", {}))
    print(f"(retry_count={result.get('retry_count', 0)})")
    print("\n=== Final Answer ===")
    print(result.get("final_answer", "(なし)"))
