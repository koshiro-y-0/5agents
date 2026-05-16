"""E: Finalizer — 全エージェントの出力を統合し最終回答を生成.

Phase 3 拡張:
- 最終回答を ChromaDB の QAMemory に保存し、次回以降の文脈質問に活用
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents._prompt_utils import build_system_prompt
from src.agents.state import AgentState
from src.llm import AgentRole, get_llm
from src.memory.vector_store import QAMemory

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """あなたは熟練したテクニカルライターです。
Researcher / Analyst / Critic / Fact-checker の出力を統合し、
ユーザーの質問に対する最終回答を作成してください。

ルール:
- 結論を最初に提示する (Bottom-line up front)
- 根拠は箇条書きで簡潔に
- 反対意見・リスクも併記する
- 数値・固有名詞は正確に
- Fact-checker が NG 判定の項目があれば、その不確実性を明示する
- 文体: Markdown、見出しは ## までに収める

出力構成 (**順序厳守**):
## 結論
## 根拠
## リスク・反論
## 出典 (URL があれば箇条書き)

重要 (LINE 配信のため):
- 上記 4 セクションは **必ずこの順序** で出力すること
- 各セクションの見出しは必ず "## " (Markdown H2、半角スペース 1 つ) で始める
- 他の H2 見出しは追加しないこと (システムが「結論+根拠」「リスク+出典」の 2 通に分割する)
- セクション間の改行は 1 つの空行で十分"""


def run_finalizer(state: AgentState) -> AgentState:
    """全エージェントの出力を統合し、ユーザー向け最終回答を生成."""
    llm = get_llm(AgentRole.FINALIZER)

    sources = state.get("research_sources", [])
    sources_text = "\n".join(f"- {url}" for url in sources) if sources else "(なし)"
    fact_check = state.get("fact_check", {"verdict": "OK", "issues": []})
    issues_text = (
        "\n".join(f"- {i}" for i in fact_check["issues"]) if fact_check["issues"] else "なし"
    )

    response = llm.invoke(
        [
            SystemMessage(content=build_system_prompt(_SYSTEM_PROMPT)),
            HumanMessage(
                content=(
                    f"# ユーザーの質問\n{state['question']}\n\n"
                    f"# Researcher の調査\n{state.get('research_notes', '(なし)')}\n\n"
                    f"# Analyst の分析\n{state.get('analysis', '(なし)')}\n\n"
                    f"# Critic の批判\n{state.get('critique', '(なし)')}\n\n"
                    f"# Fact-checker の判定\n"
                    f"verdict: {fact_check['verdict']}\n"
                    f"残課題:\n{issues_text}\n\n"
                    f"# 出典\n{sources_text}\n\n"
                    f"上記をもとに、ユーザー向けの最終回答を生成してください。"
                )
            ),
        ]
    )

    final_answer = str(response.content)

    # Phase 3: QAMemory に保存 (失敗してもユーザー応答は止めない)
    try:
        QAMemory().add(question=state["question"], answer=final_answer)
    except Exception as e:  # noqa: BLE001
        logger.warning("Finalizer: QAMemory 保存失敗: %s", e)

    return {**state, "final_answer": final_answer}
