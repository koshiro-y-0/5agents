"""src/llm.py のテスト (API キー不要 — ファクトリのロジック検証のみ)."""

from __future__ import annotations

from unittest.mock import patch

from src.llm import _ROLE_MODEL_CONFIG, AgentRole, get_llm


def test_all_roles_have_config() -> None:
    """全 5 役割に対して設定が存在する."""
    assert set(_ROLE_MODEL_CONFIG.keys()) == set(AgentRole)


def test_main_model_assigned_to_critical_roles() -> None:
    """Researcher / Analyst / Finalizer はメインモデルを使う."""
    for role in (AgentRole.RESEARCHER, AgentRole.ANALYST, AgentRole.FINALIZER):
        assert _ROLE_MODEL_CONFIG[role]["use_main"] is True


def test_sub_model_assigned_to_lightweight_roles() -> None:
    """Critic / Fact-checker はサブモデルを使う (コスト最適化)."""
    for role in (AgentRole.CRITIC, AgentRole.FACT_CHECKER):
        assert _ROLE_MODEL_CONFIG[role]["use_main"] is False


def test_factchecker_temperature_is_deterministic() -> None:
    """Fact-checker は判定の決定性を担保するため temperature=0."""
    assert _ROLE_MODEL_CONFIG[AgentRole.FACT_CHECKER]["temperature"] == 0.0


def test_get_llm_caches_per_role() -> None:
    """同じロールで複数回呼んでも同一インスタンス (lru_cache)."""
    get_llm.cache_clear()
    with patch("src.llm.ChatGoogleGenerativeAI") as mock_cls:
        mock_cls.return_value = object()
        a = get_llm(AgentRole.RESEARCHER)
        b = get_llm(AgentRole.RESEARCHER)
        assert a is b
        assert mock_cls.call_count == 1
