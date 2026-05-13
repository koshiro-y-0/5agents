"""Phase 1: 単体エージェントの最小オーケストレーター.

Phase 2 で LangGraph による 5 エージェント連携に置き換える予定。
現時点では Gemini API への疎通確認と E (Finalizer) ロール単体の動作確認が目的。
"""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from src.llm import AgentRole, get_llm

_PHASE1_SYSTEM_PROMPT = """あなたは調査・分析を支援する AI アシスタントです。
ユーザーの質問に対し、根拠を示しながら簡潔に日本語で回答してください。
不確実な情報は推測せず「不明」と明示してください。"""


def answer(question: str) -> str:
    """ユーザーの質問に単体エージェントで回答する (Phase 1 暫定実装).

    Args:
        question: ユーザーからの質問文字列。

    Returns:
        生成された回答テキスト。
    """
    llm = get_llm(AgentRole.FINALIZER)
    response = llm.invoke(
        [
            SystemMessage(content=_PHASE1_SYSTEM_PROMPT),
            HumanMessage(content=question),
        ]
    )
    return str(response.content)


if __name__ == "__main__":
    # 動作確認用: uv run python -m src.agents.orchestrator
    import sys

    q = " ".join(sys.argv[1:]) or "Pythonとは何ですか? 3行で。"
    print(f"Q: {q}\n")
    print(f"A: {answer(q)}")
