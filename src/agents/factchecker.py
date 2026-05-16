"""D: Fact-checker — 根拠なし・矛盾・誇張を構造化判定."""

from __future__ import annotations

import json
import logging
import re
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents._prompt_utils import build_system_prompt
from src.agents.state import AgentState, FactCheckResult
from src.llm import AgentRole, get_llm

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """あなたは厳格な事実確認の専門家です。
Analyst の分析と Critic の批判を読み、以下を検出してください:

1. 根拠が示されていない主張
2. 出典と矛盾する記述
3. 過度な誇張・断定 (「絶対」「必ず」など)
4. 数値や日付の不整合
5. **時系列の不整合 (最重要)**:
   - 「先日」「直近」「今期」「最新」等の相対表現が、システム冒頭の本日の日付と
     大きくずれた日付の出来事を指していないか
   - 例: 本日が 2026年5月16日 のときに、「先日の出来事 (2024年11月)」のような
     1 年以上前のことを「先日」と表現していたら NG
   - 例: 未来の日付の出来事が「既に起きた」と書かれていたら NG
   - 検索結果に最新情報がなかった場合は「○○年○月時点の情報」と明示されているか確認

判定結果を **JSON のみ** で返してください (Markdown のコードフェンスは不要)。
フォーマット:

{
  "verdict": "OK" または "NG",
  "issues": ["問題点1", "問題点2", ...]
}

- 問題が 0 件なら verdict=OK, issues=[]
- 軽微な誇張表現は OK、明らかな根拠不足や矛盾、特に時系列の不整合は NG"""


def _parse_json_response(text: str) -> FactCheckResult:
    """LLM レスポンスから JSON を頑健に抽出.

    Markdown コードフェンスや前後の説明文が混じっても動くよう、
    最初に見つかる `{...}` ブロックを取り出す。
    """
    # ``` で囲まれていれば中身を取り出す
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        # 最初の { 〜 最後の } を抽出
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0)

    try:
        data = json.loads(text)
        verdict = data.get("verdict", "NG")
        issues = data.get("issues", [])
        if verdict not in ("OK", "NG"):
            verdict = "NG"
        if not isinstance(issues, list):
            issues = [str(issues)]
        return cast(FactCheckResult, {"verdict": verdict, "issues": [str(i) for i in issues]})
    except json.JSONDecodeError:
        logger.warning("Fact-checker の JSON パースに失敗: %s", text[:200])
        # パース失敗時はフェイルセーフで NG にし、生レスポンスを issue に残す
        return cast(
            FactCheckResult,
            {"verdict": "NG", "issues": [f"JSON パース失敗: {text[:200]}"]},
        )


def run_factchecker(state: AgentState) -> AgentState:
    """Analyst/Critic の出力を検証し、verdict + issues を返す."""
    llm = get_llm(AgentRole.FACT_CHECKER)
    response = llm.invoke(
        [
            SystemMessage(content=build_system_prompt(_SYSTEM_PROMPT)),
            HumanMessage(
                content=(
                    f"# ユーザーの質問\n{state['question']}\n\n"
                    f"# Researcher の調査\n{state.get('research_notes', '(なし)')}\n\n"
                    f"# Analyst の分析\n{state.get('analysis', '(なし)')}\n\n"
                    f"# Critic の批判\n{state.get('critique', '(なし)')}\n\n"
                    f"上記を検証し、判定結果を JSON で返してください。"
                )
            ),
        ]
    )

    fact_check = _parse_json_response(str(response.content))
    retry_count = state.get("retry_count", 0)
    if fact_check["verdict"] == "NG":
        retry_count += 1

    return {**state, "fact_check": fact_check, "retry_count": retry_count}
