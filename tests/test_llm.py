"""src/llm.py のテスト (API キー不要 — ファクトリのロジック検証のみ)."""

from __future__ import annotations

from unittest.mock import patch

from src.llm import (
    _ROLE_CONFIG,
    AgentRole,
    Provider,
    get_llm,
    get_model_name,
    get_provider,
)


def test_all_roles_have_config() -> None:
    """全 5 役割に対して設定が存在する."""
    assert set(_ROLE_CONFIG.keys()) == set(AgentRole)


def test_google_provider_assigned_to_a_b_e() -> None:
    """Researcher / Analyst / Finalizer は Google (Gemini) を使う."""
    for role in (AgentRole.RESEARCHER, AgentRole.ANALYST, AgentRole.FINALIZER):
        assert _ROLE_CONFIG[role].provider == Provider.GOOGLE


def test_groq_provider_assigned_to_c_d() -> None:
    """Critic / Fact-checker は Groq (Llama) を使う — 視点の多様性 + Flash 枠温存."""
    for role in (AgentRole.CRITIC, AgentRole.FACT_CHECKER):
        assert _ROLE_CONFIG[role].provider == Provider.GROQ


def test_analyst_uses_gemini_flash_lite_attr() -> None:
    """Analyst は Flash-Lite (gemini_model_sub) を使う — Flash 枠を温存."""
    assert _ROLE_CONFIG[AgentRole.ANALYST].model_attr == "gemini_model_sub"


def test_researcher_and_finalizer_use_main_gemini_attr() -> None:
    """Researcher / Finalizer は Flash (gemini_model_main) を使う."""
    assert _ROLE_CONFIG[AgentRole.RESEARCHER].model_attr == "gemini_model_main"
    assert _ROLE_CONFIG[AgentRole.FINALIZER].model_attr == "gemini_model_main"


def test_groq_roles_use_groq_model_attr() -> None:
    """Critic / Fact-checker は groq_model を参照する."""
    assert _ROLE_CONFIG[AgentRole.CRITIC].model_attr == "groq_model"
    assert _ROLE_CONFIG[AgentRole.FACT_CHECKER].model_attr == "groq_model"


def test_factchecker_temperature_is_deterministic() -> None:
    """Fact-checker は判定の決定性を担保するため temperature=0."""
    assert _ROLE_CONFIG[AgentRole.FACT_CHECKER].temperature == 0.0


def test_critic_temperature_is_high_for_divergence() -> None:
    """Critic は反論生成のため発散気味 (temperature 高め)."""
    assert _ROLE_CONFIG[AgentRole.CRITIC].temperature >= 0.5


def test_get_model_name_returns_settings_value() -> None:
    """get_model_name() が settings の対応フィールドを返す."""
    from src import config

    config.get_settings.cache_clear()
    name = get_model_name(AgentRole.RESEARCHER)
    assert "gemini" in name.lower()


def test_get_provider_helper() -> None:
    """get_provider() がロールのプロバイダーを返す."""
    assert get_provider(AgentRole.RESEARCHER) == Provider.GOOGLE
    assert get_provider(AgentRole.CRITIC) == Provider.GROQ


def test_get_llm_caches_per_role() -> None:
    """同じロールで複数回呼んでも同一インスタンス (cache)."""
    get_llm.cache_clear()
    with (
        patch("src.llm.ChatGoogleGenerativeAI") as mock_google,
        patch("src.llm.ChatGroq"),
    ):
        mock_google.return_value = object()
        a = get_llm(AgentRole.RESEARCHER)
        b = get_llm(AgentRole.RESEARCHER)
        assert a is b
        assert mock_google.call_count == 1


def test_get_llm_uses_correct_provider_class() -> None:
    """ロールに応じて Google / Groq クライアントが正しく呼び分けられる."""
    get_llm.cache_clear()
    with (
        patch("src.llm.ChatGoogleGenerativeAI") as mock_google,
        patch("src.llm.ChatGroq") as mock_groq,
    ):
        get_llm(AgentRole.RESEARCHER)
        get_llm(AgentRole.CRITIC)
        assert mock_google.call_count == 1
        assert mock_groq.call_count == 1
