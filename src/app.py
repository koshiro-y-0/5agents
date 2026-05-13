"""Phase 1: Streamlit 最小チャット画面.

起動: uv run streamlit run src/app.py

Phase 2 以降で 5 エージェントの中間出力を可視化するパネルを追加予定。
"""

from __future__ import annotations

import streamlit as st

from src.agents.orchestrator import answer
from src.config import get_settings

st.set_page_config(page_title="5agents (Phase 1)", page_icon="🤖", layout="wide")

st.title("🤖 5agents — Phase 1 (単体エージェント)")
st.caption("Phase 2 で 5 エージェント連携に拡張予定")

# --- セッション状態 ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- サイドバー: 環境チェック ---
with st.sidebar:
    st.header("環境")
    settings = get_settings()
    if not settings.google_api_key:
        st.error("`.env` の GOOGLE_API_KEY が未設定です")
    else:
        st.success("Gemini API key OK")
    st.write(f"**メインモデル**: `{settings.gemini_model_main}`")
    st.write(f"**サブモデル**: `{settings.gemini_model_sub}`")
    st.write(f"**APP_ENV**: `{settings.app_env}`")

    if st.button("会話をクリア"):
        st.session_state.messages = []
        st.rerun()

# --- 会話履歴の描画 ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- 入力 ---
if prompt := st.chat_input("質問を入力..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("考え中..."):
            try:
                reply = answer(prompt)
            except Exception as e:  # noqa: BLE001 - 表示用にあえて広く捕捉
                reply = f"❌ エラー: {e}"
        st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
