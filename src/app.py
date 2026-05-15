"""Phase 2: Streamlit 5 エージェント可視化 UI.

起動: uv run streamlit run src/app.py

各エージェント (A→B→C→D→E) の中間出力を expander で展開して確認できる。
"""

from __future__ import annotations

import streamlit as st

from src.agents.orchestrator import answer
from src.agents.state import AgentState
from src.config import get_settings

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


def _render_intermediate(state: AgentState) -> None:
    """各エージェントの中間出力を expander で描画."""
    fact_check = state.get("fact_check", {"verdict": "OK", "issues": []})
    retry = state.get("retry_count", 0)

    # ステータスバッジ
    cols = st.columns(5)
    cols[0].metric("A: Researcher", "✅")
    cols[1].metric("B: Analyst", "✅")
    cols[2].metric("C: Critic", "✅")
    cols[3].metric(
        "D: Fact-check",
        "✅ OK" if fact_check["verdict"] == "OK" else f"⚠️ NG (retry={retry})",
    )
    cols[4].metric("E: Finalizer", "✅")

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
