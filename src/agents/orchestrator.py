"""5 エージェント連携オーケストレーター (LangGraph).

パイプライン:
    START → A → B → C → D → (条件分岐) → E → END
                              ├ verdict=OK             → finalizer
                              ├ verdict=NG, retry<max → analyst (差し戻し)
                              └ verdict=NG, retry≥max → finalizer (注釈付き)

Phase 3:
- 各ノード呼び出しを RunLogger で計測し、SQLite に永続化する。
- run_id をモジュール変数で受け渡し (LangGraph state にロガーを直接持たせない)。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Literal

from langgraph.graph import END, START, StateGraph

from src.agents.analyst import run_analyst
from src.agents.critic import run_critic
from src.agents.factchecker import run_factchecker
from src.agents.finalizer import run_finalizer
from src.agents.researcher import run_researcher
from src.agents.state import AgentState
from src.config import get_settings
from src.llm import AgentRole
from src.memory.logger import RunLogger

logger = logging.getLogger(__name__)


# 計測時の現在 run の参照 (answer() 内で書き換え)
_CURRENT_RUN_ID: str | None = None
_CURRENT_RUN_LOGGER: RunLogger | None = None

# メインモデルを使うロール
_MAIN_MODEL_ROLES = {AgentRole.RESEARCHER, AgentRole.ANALYST, AgentRole.FINALIZER}


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


def _instrument(
    node_fn: Callable[[AgentState], AgentState],
    agent_name: str,
    role: AgentRole,
) -> Callable[[AgentState], AgentState]:
    """エージェント関数を SQLite ロガー付きでラップする."""
    settings = get_settings()
    model = settings.gemini_model_main if role in _MAIN_MODEL_ROLES else settings.gemini_model_sub

    def wrapped(state: AgentState) -> AgentState:
        started = time.perf_counter()
        error: str | None = None
        try:
            return node_fn(state)
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"
            raise
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            if _CURRENT_RUN_LOGGER is not None and _CURRENT_RUN_ID is not None:
                try:
                    _CURRENT_RUN_LOGGER.log_agent_call(
                        _CURRENT_RUN_ID, agent_name, model, duration_ms, error
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning("RunLogger.log_agent_call 失敗: %s", e)

    wrapped.__name__ = f"instrumented_{node_fn.__name__}"
    return wrapped


def build_graph():  # type: ignore[no-untyped-def]
    """5 エージェントの LangGraph を構築して compile したものを返す."""
    graph = StateGraph(AgentState)

    graph.add_node("researcher", _instrument(run_researcher, "researcher", AgentRole.RESEARCHER))
    graph.add_node("analyst", _instrument(run_analyst, "analyst", AgentRole.ANALYST))
    graph.add_node("critic", _instrument(run_critic, "critic", AgentRole.CRITIC))
    graph.add_node(
        "factchecker", _instrument(run_factchecker, "factchecker", AgentRole.FACT_CHECKER)
    )
    graph.add_node("finalizer", _instrument(run_finalizer, "finalizer", AgentRole.FINALIZER))

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


# モジュールロード時に 1 度だけコンパイル
_graph = build_graph()


def answer(question: str) -> AgentState:
    """5 エージェントを通してユーザーの質問に回答 (SQLite ロガー付き)."""
    global _CURRENT_RUN_ID, _CURRENT_RUN_LOGGER

    # SQLite ロガー初期化 (失敗してもメイン処理は止めない)
    run_logger: RunLogger | None
    run_id: str | None
    try:
        run_logger = RunLogger()
        run_id = run_logger.start_run(question)
    except Exception as e:  # noqa: BLE001
        logger.warning("RunLogger 初期化失敗: %s", e)
        run_logger = None
        run_id = None

    _CURRENT_RUN_ID = run_id
    _CURRENT_RUN_LOGGER = run_logger

    final_state: AgentState = {"question": question, "retry_count": 0}
    started = time.perf_counter()
    error: str | None = None
    try:
        final_state = _graph.invoke(  # type: ignore[assignment]
            {"question": question, "retry_count": 0}
        )
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
        raise
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        if run_logger is not None and run_id is not None:
            fact_check = final_state.get("fact_check", {"verdict": "ERROR", "issues": []})
            try:
                run_logger.finish_run(
                    run_id=run_id,
                    duration_ms=duration_ms,
                    final_verdict=fact_check.get("verdict"),
                    retry_count=final_state.get("retry_count", 0),
                    error=error,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("RunLogger.finish_run 失敗: %s", e)
        _CURRENT_RUN_ID = None
        _CURRENT_RUN_LOGGER = None

    # State に run_id を埋め込んで UI から参照可能にする
    if run_id is not None:
        final_state["run_id"] = run_id
    return final_state


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
