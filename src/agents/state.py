"""LangGraph で 5 エージェント間を流れる共有 State の型定義."""

from __future__ import annotations

from typing import TypedDict


class FactCheckResult(TypedDict):
    """D エージェント (Fact-checker) の判定結果."""

    verdict: str  # "OK" | "NG"
    issues: list[str]


class AgentState(TypedDict, total=False):
    """5 エージェント間で受け渡される状態.

    各エージェントは自身が責任を持つフィールドのみを書き込む。
    """

    # 入力
    question: str

    # Phase 3: 過去の関連 Q&A (Researcher に注入)
    memory_context: str

    # A: Researcher
    research_notes: str
    research_sources: list[str]

    # B: Analyst
    analysis: str

    # C: Critic
    critique: str

    # D: Fact-checker
    fact_check: FactCheckResult
    retry_count: int  # 差し戻し回数 (上限ガードに使用)

    # E: Finalizer
    final_answer: str

    # Phase 3: SQLite ロガーが採番する run の識別子 (UI で経過時間表示などに利用)
    run_id: str
