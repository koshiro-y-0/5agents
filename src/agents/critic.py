"""C: Critic — A/B の出力に対する反論・別視点を生成."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents._prompt_utils import build_system_prompt
from src.agents.state import AgentState
from src.llm import AgentRole, get_llm

_SYSTEM_PROMPT = """あなたは批判的思考の専門家です。
Researcher / Analyst の出力に対し、見落とされている視点・反対意見・別の解釈を提示してください。

ルール:
- ただ否定するのではなく、建設的な代替案・補強の方向を示す
- リスク・前提条件の弱さ・サンプリングバイアスがあれば指摘する
- 「もし X が違ったら」という反実仮想を活用する
- 自分の意見を断定的に押し付けない (「考慮すべき」「可能性」などの表現)"""


def run_critic(state: AgentState) -> AgentState:
    """A/B の出力に反論・別視点を加える."""
    llm = get_llm(AgentRole.CRITIC)
    response = llm.invoke(
        [
            SystemMessage(content=build_system_prompt(_SYSTEM_PROMPT)),
            HumanMessage(
                content=(
                    f"# ユーザーの質問\n{state['question']}\n\n"
                    f"# Researcher の調査\n{state.get('research_notes', '(なし)')}\n\n"
                    f"# Analyst の分析\n{state.get('analysis', '(なし)')}\n\n"
                    f"上記に対する反論・見落とし・別視点を 300〜500 文字でまとめてください。"
                )
            ),
        ]
    )

    return {**state, "critique": str(response.content)}
