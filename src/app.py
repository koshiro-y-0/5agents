"""Phase 3: Streamlit 5 エージェント可視化 UI + 実行統計.

起動: uv run streamlit run src/app.py
"""

from __future__ import annotations

import streamlit as st

from src.agents.orchestrator import answer
from src.agents.state import AgentState
from src.config import get_settings
from src.memory.logger import RunLogger

st.set_page_config(page_title="5agents", page_icon="🤖", layout="wide")

st.title("🤖 5agents — マルチエージェント調査システム")
st.caption("A: Researcher → B: Analyst → C: Critic → D: Fact-checker → E: Finalizer")

# --- セッション状態 ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- サイドバー: 環境チェック ---
with st.sidebar:
    st.header("環境")
    settings = get_settings()

    if not settings.google_api_key or settings.google_api_key.startswith("your_"):
        st.error("`.env` の GOOGLE_API_KEY が未設定です")
    else:
        st.success("Gemini API key OK")

    if not settings.tavily_api_key or settings.tavily_api_key.startswith("your_"):
        st.warning("Tavily 未設定 — Researcher は Web 検索なしで動作")
    else:
        st.success("Tavily API key OK")

    st.write(f"**メインモデル**: `{settings.gemini_model_main}`")
    st.write(f"**サブモデル**: `{settings.gemini_model_sub}`")
    st.write(f"**Fact-check 上限**: `{settings.max_factcheck_retries}` 回")

    if st.button("会話をクリア"):
        st.session_state.messages = []
        st.rerun()

    # --- 直近の実行統計 ---
    st.divider()
    st.subheader("直近の実行")
    try:
        rlog = RunLogger()
        recent = rlog.recent_runs(limit=5)
        if not recent:
            st.caption("まだ実行履歴はありません")
        else:
            for r in recent:
                duration_s = (r.get("duration_ms") or 0) / 1000
                verdict = r.get("final_verdict") or "?"
                retry = r.get("retry_count") or 0
                q_preview = (r.get("question") or "")[:30] + (
                    "..." if len(r.get("question") or "") > 30 else ""
                )
                st.caption(
                    f"- `{verdict}` {duration_s:.1f}s (retry={retry}) — {q_preview}"
                )
    except Exception as e:  # noqa: BLE001
        st.caption(f"統計取得失敗: {e}")


def _render_intermediate(state: AgentState) -> None:
    """各エージェントの中間出力を expander で描画."""
    fact_check = state.get("fact_check", {"verdict": "OK", "issues": []})
    retry = state.get("retry_count", 0)

    # 各エージェントの所要時間を SQLite から取得
    agent_durations: dict[str, int] = {}
    total_ms: int | None = None
    run_id = state.get("run_id")
    if run_id:
        try:
            stats = RunLogger().get_run_stats(run_id)
            if stats:
                agent_durations = stats.agent_durations
                total_ms = stats.duration_ms
        except Exception:  # noqa: BLE001
            pass

    def _dur(agent: str) -> str:
        ms = agent_durations.get(agent, 0)
        return f"{ms / 1000:.1f}s" if ms else "—"

    # ステータスバッジ (経過時間付き)
    cols = st.columns(5)
    cols[0].metric("A: Researcher", "✅", _dur("researcher"))
    cols[1].metric("B: Analyst", "✅", _dur("analyst"))
    cols[2].metric("C: Critic", "✅", _dur("critic"))
    cols[3].metric(
        "D: Fact-check",
        "✅ OK" if fact_check["verdict"] == "OK" else f"⚠️ NG (retry={retry})",
        _dur("factchecker"),
    )
    cols[4].metric("E: Finalizer", "✅", _dur("finalizer"))

    if total_ms:
        st.caption(f"合計所要時間: **{total_ms / 1000:.1f} 秒** (run_id: `{run_id}`)")

    with st.expander("🔍 A: Researcher (Web検索・情報収集)"):
        st.markdown(state.get("research_notes", "(なし)"))
        sources = state.get("research_sources", [])
        if sources:
            st.caption("出典:")
            for url in sources:
                st.caption(f"- {url}")

    with st.expander("📊 B: Analyst (分析・予測)"):
        st.markdown(state.get("analysis", "(なし)"))

    with st.expander("🔄 C: Critic (反論・別視点)"):
        st.markdown(state.get("critique", "(なし)"))

    with st.expander(f"✅ D: Fact-checker (verdict={fact_check['verdict']})"):
        if fact_check["issues"]:
            st.markdown("**検出された問題:**")
            for issue in fact_check["issues"]:
                st.markdown(f"- {issue}")
        else:
            st.markdown("問題なし")


# --- 会話履歴の描画 ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and isinstance(msg["content"], dict):
            state: AgentState = msg["content"]
            st.markdown(state.get("final_answer", "(回答なし)"))
            _render_intermediate(state)
        else:
            st.markdown(msg["content"])

# --- 入力 ---
if prompt := st.chat_input("質問を入力..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"), st.spinner("5 エージェントが調査・分析中..."):
        try:
            state = answer(prompt)
        except Exception as e:  # noqa: BLE001 - 表示用にあえて広く捕捉
            st.error(f"❌ エラー: {e}")
            st.session_state.messages.append(
                {"role": "assistant", "content": f"❌ エラー: {e}"}
            )
        else:
            st.markdown(state.get("final_answer", "(回答なし)"))
            _render_intermediate(state)
            st.session_state.messages.append({"role": "assistant", "content": state})
