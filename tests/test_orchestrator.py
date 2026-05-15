"""Orchestrator のルーティングロジックのテスト (API キー不要).

LLM 呼び出しは行わず、`_route_after_factcheck` の判定だけを検証する。
"""

from __future__ import annotations

from src.agents.orchestrator import _route_after_factcheck
from src.agents.state import AgentState
from src.config import get_settings


def _make_state(verdict: str, retry_count: int) -> AgentState:
    return {  # type: ignore[typeddict-item]
        "question": "test",
        "fact_check": {"verdict": verdict, "issues": []},
        "retry_count": retry_count,
    }


def test_route_to_finalizer_when_ok() -> None:
    """verdict=OK ならリトライ回数に関係なく Finalizer."""
    assert _route_after_factcheck(_make_state("OK", 0)) == "finalizer"
    assert _route_after_factcheck(_make_state("OK", 99)) == "finalizer"


def test_route_to_analyst_when_ng_within_limit() -> None:
    """verdict=NG かつ retry < max なら Analyst に差し戻し."""
    max_retries = get_settings().max_factcheck_retries
    assert _route_after_factcheck(_make_state("NG", 0)) == "analyst"
    assert _route_after_factcheck(_make_state("NG", max_retries - 1)) == "analyst"


def test_route_to_finalizer_when_ng_exceeds_limit() -> None:
    """verdict=NG かつ retry >= max なら Finalizer (注釈付き)."""
    max_retries = get_settings().max_factcheck_retries
    assert _route_after_factcheck(_make_state("NG", max_retries)) == "finalizer"
    assert _route_after_factcheck(_make_state("NG", max_retries + 10)) == "finalizer"
