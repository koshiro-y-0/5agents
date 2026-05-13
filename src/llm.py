"""Gemini クライアントのファクトリ.

各エージェントは `get_llm(role)` 経由でクライアントを取得する。
モデル名やパラメータをここに集約することで、変更箇所を一箇所に閉じ込める。
"""

from __future__ import annotations

from enum import StrEnum
from functools import cache

from langchain_google_genai import ChatGoogleGenerativeAI

from src.config import get_settings


class AgentRole(StrEnum):
    """5エージェントの役割識別子."""

    RESEARCHER = "researcher"
    ANALYST = "analyst"
    CRITIC = "critic"
    FACT_CHECKER = "fact_checker"
    FINALIZER = "finalizer"


_ROLE_MODEL_CONFIG: dict[AgentRole, dict[str, object]] = {
    # メインモデル (Flash) — 重要な判断・出力品質が求められる
    AgentRole.RESEARCHER: {"use_main": True, "temperature": 0.3},
    AgentRole.ANALYST: {"use_main": True, "temperature": 0.2},
    AgentRole.FINALIZER: {"use_main": True, "temperature": 0.4},
    # サブモデル (Flash-Lite) — 軽量タスク
    AgentRole.CRITIC: {"use_main": False, "temperature": 0.7},  # 反論なので発散気味
    AgentRole.FACT_CHECKER: {"use_main": False, "temperature": 0.0},  # 判定なので決定的
}


@cache
def get_llm(role: AgentRole) -> ChatGoogleGenerativeAI:
    """役割に応じた Gemini クライアントを返す (役割ごとにキャッシュ)."""
    settings = get_settings()
    config = _ROLE_MODEL_CONFIG[role]
    model = settings.gemini_model_main if config["use_main"] else settings.gemini_model_sub

    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=settings.google_api_key,
        temperature=config["temperature"],
    )
