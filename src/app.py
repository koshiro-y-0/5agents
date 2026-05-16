"""Phase 4: Streamlit チャット UI + ダッシュボード.

起動: uv run streamlit run src/app.py

タブ:
- 💬 チャット: 質問を投げて 5 エージェントの中間出力を確認
- 📊 ダッシュボード: 実行履歴・所要時間・コスト傾向を可視化
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
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
        st.error("`.env` の GOOGLE_API_KEY が未設定です (A/B/E が動作不可)")
    else:
        st.success("Gemini API key OK")

    if not settings.groq_api_key or settings.groq_api_key.startswith("your_"):
        st.error("`.env` の GROQ_API_KEY が未設定です (C/D が動作不可)")
    else:
        st.success("Groq API key OK")

    if not settings.tavily_api_key or settings.tavily_api_key.startswith("your_"):
        st.warning("Tavily 未設定 — Researcher は Web 検索なしで動作")
    else:
        st.success("Tavily API key OK")

    st.divider()
    st.caption("**役割 → モデル**")
    st.caption(f"A Researcher : `{settings.gemini_model_main}` (Google)")
    st.caption(f"B Analyst    : `{settings.gemini_model_sub}` (Google)")
    st.caption(f"C Critic     : `{settings.groq_model}` (Groq)")
    st.caption(f"D Fact-check : `{settings.groq_model}` (Groq)")
    st.caption(f"E Finalizer  : `{settings.gemini_model_main}` (Google)")
    st.caption(f"Fact-check 差し戻し上限: `{settings.max_factcheck_retries}` 回")

    if st.button("会話をクリア"):
        st.session_state.messages = []
        st.rerun()


def _render_intermediate(state: AgentState) -> None:
    """各エージェントの中間出力を expander で描画."""
    fact_check = state.get("fact_check", {"verdict": "OK", "issues": []})
    retry = state.get("retry_count", 0)

    # 各エージェントの所要時間を SQLite から取得
    agent_durations: dict[str, int] = {}
    agent_call_counts: dict[str, int] = {}
    total_ms: int | None = None
    run_id = state.get("run_id")
    if run_id:
        try:
            stats = RunLogger().get_run_stats(run_id)
            if stats:
                agent_durations = stats.agent_durations
                agent_call_counts = stats.agent_call_counts
                total_ms = stats.duration_ms
        except Exception:  # noqa: BLE001
            pass

    def _dur(agent: str) -> str:
        ms = agent_durations.get(agent, 0)
        count = agent_call_counts.get(agent, 0)
        if not ms:
            return "—"
        # 複数回呼び出されている場合 (差し戻し) は × N を併記
        suffix = f" ×{count}" if count > 1 else ""
        return f"{ms / 1000:.1f}s{suffix}"

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


def _render_chat_tab() -> None:
    """チャットタブの描画."""
    # 会話履歴の描画
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant" and isinstance(msg["content"], dict):
                state: AgentState = msg["content"]
                st.markdown(state.get("final_answer", "(回答なし)"))
                _render_intermediate(state)
            else:
                st.markdown(msg["content"])

    # 入力
    if prompt := st.chat_input("質問を入力..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"), st.spinner("5 エージェントが調査・分析中..."):
            try:
                state = answer(prompt)
            except Exception as e:  # noqa: BLE001
                st.error(f"❌ エラー: {e}")
                st.session_state.messages.append(
                    {"role": "assistant", "content": f"❌ エラー: {e}"}
                )
            else:
                st.markdown(state.get("final_answer", "(回答なし)"))
                _render_intermediate(state)
                st.session_state.messages.append({"role": "assistant", "content": state})


def _render_dashboard_tab() -> None:
    """ダッシュボードタブ: 実行履歴とコスト傾向を可視化."""
    st.subheader("📊 実行統計ダッシュボード")

    days = st.slider("集計期間 (日)", min_value=1, max_value=60, value=14)
    rlog = RunLogger()

    # --- KPI カード ---
    runs = rlog.all_runs_for_dashboard(limit=1000)
    if not runs:
        st.info("まだ実行履歴がありません。チャットタブで質問を投げてみてください。")
        return

    df_runs = pd.DataFrame(runs)
    df_runs["started_at"] = pd.to_datetime(df_runs["started_at"], utc=True)
    cutoff = pd.Timestamp.utcnow() - pd.Timedelta(days=days)
    df_window = df_runs[df_runs["started_at"] >= cutoff]

    total_runs = len(df_window)
    ng_count = int((df_window["final_verdict"] == "NG").sum()) if total_runs else 0
    avg_duration = (
        float(df_window["duration_ms"].fillna(0).mean()) / 1000 if total_runs else 0.0
    )
    avg_retries = float(df_window["retry_count"].fillna(0).mean()) if total_runs else 0.0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("実行回数", f"{total_runs}")
    col2.metric("NG 率", f"{(ng_count / total_runs * 100) if total_runs else 0:.1f}%")
    col3.metric("平均所要時間", f"{avg_duration:.1f} 秒")
    col4.metric("平均リトライ", f"{avg_retries:.2f}")

    st.divider()

    # --- 日別実行数 (折れ線) ---
    daily = rlog.daily_run_counts(last_n_days=days)
    if daily:
        df_daily = pd.DataFrame(daily)
        df_daily["date"] = pd.to_datetime(df_daily["date"])
        fig = px.bar(
            df_daily,
            x="date",
            y="count",
            title=f"日別実行数 (直近 {days} 日)",
            labels={"date": "日付", "count": "実行数"},
        )
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)

    # --- エージェント別合計所要時間 (横棒) ---
    agent_totals = rlog.agent_total_durations(last_n_days=days)
    if agent_totals:
        df_agent = pd.DataFrame(agent_totals)
        fig2 = px.bar(
            df_agent,
            x="total_s",
            y="agent",
            orientation="h",
            title=f"エージェント別 合計所要時間 (秒、直近 {days} 日)",
            labels={"total_s": "合計秒数", "agent": "エージェント"},
            text="calls",
            hover_data={"calls": True},
        )
        fig2.update_layout(height=300, yaxis={"categoryorder": "total ascending"})
        fig2.update_traces(texttemplate="%{text} 回", textposition="outside")
        st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # --- 実行履歴テーブル ---
    st.subheader("🗂️ 実行履歴")
    display_df = df_window.copy()
    display_df["所要時間 (秒)"] = (display_df["duration_ms"].fillna(0) / 1000).round(1)
    display_df = display_df[
        ["started_at", "question", "final_verdict", "retry_count", "所要時間 (秒)", "error"]
    ].rename(
        columns={
            "started_at": "実行時刻",
            "question": "質問",
            "final_verdict": "判定",
            "retry_count": "リトライ",
            "error": "エラー",
        }
    )
    st.dataframe(display_df, use_container_width=True, height=400)


# --- タブ構成 ---
tab_chat, tab_dashboard = st.tabs(["💬 チャット", "📊 ダッシュボード"])
with tab_chat:
    _render_chat_tab()
with tab_dashboard:
    _render_dashboard_tab()
