"""B: Analyst — 分析・予測を担当."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.state import AgentState
from src.llm import AgentRole, get_llm

_SYSTEM_PROMPT = """あなたは分析・予測の専門家です。
Researcher が集めた情報をもとに、質問の本質に踏み込んだ分析と、
妥当性のある予測・示唆を提供してください。

ルール:
- データに基づく定量的な分析を優先する
- 推測には「推測」「可能性」など確信度を示す語を必ず付ける
- トレンド・パターン・因果関係を意識する
- 投資判断などのアドバイスは「最終決定は本人」と明示する"""


def run_analyst(state: AgentState) -> AgentState:
    """Researcher の出力を受け、分析・予測を生成."""
    llm = get_llm(AgentRole.ANALYST)
    response = llm.invoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"# ユーザーの質問\n{state['question']}\n\n"
                    f"# Researcher の調査結果\n{state.get('research_notes', '(なし)')}\n\n"
                    f"上記をもとに、質問への分析・予測・示唆を 400〜600 文字でまとめてください。"
                )
            ),
        ]
    )

    return {**state, "analysis": str(response.content)}
