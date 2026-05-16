"""役割ベース・マルチプロバイダーの LLM ファクトリ.

各エージェントは `get_llm(role)` 経由でクライアントを取得する。
モデル名・温度・プロバイダーをここに集約することで、変更箇所を一箇所に閉じ込める。

設計:
    A Researcher    → Gemini 2.5 Flash       (Web 検索結果の要約に強い)
    B Analyst       → Gemini 2.5 Flash-Lite  (Gemini 系統で Researcher と連続)
    C Critic        → Llama 3.3 70B (Groq)   (Meta 系統で別視点)
    D Fact-checker  → Llama 3.3 70B (Groq)   (JSON 出力に強い + 別系統で検証)
    E Finalizer     → Gemini 2.5 Flash       (日本語 Markdown 整形品質)

メリット:
- Gemini Flash 消費を 2 calls/質問 に削減 → 無料枠で 1日 10 質問処理可
- 視点系統が 2 系統 (Google / Meta) に分散し、C/D が独立な検証視点を持つ
- Groq の無料枠が 14,400 RPD と豊富、Flash 枯渇時のリスク分散
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from functools import cache

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from src.config import get_settings


class AgentRole(StrEnum):
    """5 エージェントの役割識別子."""

    RESEARCHER = "researcher"
    ANALYST = "analyst"
    CRITIC = "critic"
    FACT_CHECKER = "fact_checker"
    FINALIZER = "finalizer"


class Provider(StrEnum):
    """LLM プロバイダー識別子."""

    GOOGLE = "google"
    GROQ = "groq"


@dataclass(frozen=True)
class RoleConfig:
    """1 つの役割に対するプロバイダー・モデル・パラメータ設定."""

    provider: Provider
    temperature: float
    model_attr: str  # settings のどのフィールドに model 名が入っているか


_ROLE_CONFIG: dict[AgentRole, RoleConfig] = {
    # Google Gemini Flash (メイン品質)
    AgentRole.RESEARCHER: RoleConfig(Provider.GOOGLE, 0.3, "gemini_model_main"),
    AgentRole.FINALIZER: RoleConfig(Provider.GOOGLE, 0.4, "gemini_model_main"),
    # Google Gemini Flash-Lite (Researcher との連続性 + Flash の枠を温存)
    AgentRole.ANALYST: RoleConfig(Provider.GOOGLE, 0.2, "gemini_model_sub"),
    # Groq Llama (別系統で検証視点を確保 + 無料枠豊富)
    AgentRole.CRITIC: RoleConfig(Provider.GROQ, 0.7, "groq_model"),  # 反論なので発散気味
    AgentRole.FACT_CHECKER: RoleConfig(Provider.GROQ, 0.0, "groq_model"),  # 判定なので決定的
}


def get_model_name(role: AgentRole) -> str:
    """指定された役割が使用するモデル名を返す (ログ・UI 表示用)."""
    settings = get_settings()
    return getattr(settings, _ROLE_CONFIG[role].model_attr)


def get_provider(role: AgentRole) -> Provider:
    """指定された役割が使用するプロバイダーを返す."""
    return _ROLE_CONFIG[role].provider


@cache
def get_llm(role: AgentRole) -> BaseChatModel:
    """役割に応じた LLM クライアントを返す (役割ごとにキャッシュ).

    Raises:
        ValueError: 設定されているプロバイダーが未対応の場合。
    """
    settings = get_settings()
    config = _ROLE_CONFIG[role]
    model_name = getattr(settings, config.model_attr)

    if config.provider == Provider.GOOGLE:
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=settings.google_api_key,
            temperature=config.temperature,
        )
    if config.provider == Provider.GROQ:
        return ChatGroq(
            model=model_name,
            api_key=settings.groq_api_key,
            temperature=config.temperature,
        )
    raise ValueError(f"Unknown provider: {config.provider}")
