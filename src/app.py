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
from src.auth import CurrentUser, get_current_user, is_oauth_enabled, register_login
from src.config import get_settings
from src.memory.logger import RunLogger
from src.quota import FLASH_CALLS_PER_QUESTION, format_until_reset, get_flash_quota_status

st.set_page_config(page_title="5agents", page_icon="🤖", layout="wide")


# --- 認証ゲート (Phase 5 Theme C: HF OAuth ベース) ---
def _require_auth() -> CurrentUser:
    """HF OAuth でログイン済み + 許可ユーザーまで本体 UI をブロックする.

    戻り値: 認証通過した CurrentUser. それ以外は st.stop() で中断.

    動作モード:
    - ローカル開発 (OAUTH_CLIENT_ID 未設定): 認証スキップ、'_local_dev' admin として通過
    - HF Space 未ログイン: "Sign in with Hugging Face" ボタンを表示
    - HF Space ログイン済み・許可外: "アクセス権なし" 画面
    - HF Space ログイン済み・許可済み: 本体 UI へ
    """
    user = get_current_user()

    # OAuth 無効 (ローカル開発) → ダミー admin で素通り
    if not is_oauth_enabled():
        if user is not None:
            register_login(user)
        return user  # type: ignore[return-value]  # is_oauth_enabled False のときは必ず非 None

    # 未ログイン
    if user is None:
        st.title("🔒 5agents")
        st.caption("Hugging Face アカウントでログインしてください。")
        st.write("")
        # 注意: Streamlit native auth は `if st.button(...): st.login()` のパターンが
        #       公式推奨。on_click=st.login コールバックだと内部 rerun 順序の都合で
        #       redirect が発火しない (実機 HF Spaces で確認済み).
        if st.button("🤗  Sign in with Hugging Face", type="primary"):
            st.login()
        st.caption(
            "Hugging Face アカウントをお持ちでない場合は "
            "[こちらから無料作成 (30 秒)](https://huggingface.co/join) できます。"
        )
        st.stop()

    # ログイン済みだが allowed_users にいない (role='guest')
    if not user.is_allowed:
        st.title("⛔ アクセス権がありません")
        st.write(
            f"HF ユーザー **`{user.username}`** はこの 5agents の許可リストに含まれていません。"
        )
        st.write("利用したい場合は管理者に依頼してください。")
        if st.button("ログアウト"):
            st.logout()
        st.stop()

    # 通過: 最終ログイン時刻を更新
    register_login(user)
    return user


_current_user = _require_auth()

st.title("🤖 5agents — マルチエージェント調査システム")
st.caption("A: Researcher → B: Analyst → C: Critic → D: Fact-checker → E: Finalizer")

# --- セッション状態 ---
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- サイドバー: ログインユーザー + 環境チェック ---
with st.sidebar:
    # Phase 5 Theme C: ログインユーザー表示
    st.header("👤 ユーザー")
    if _current_user.picture_url:
        st.image(_current_user.picture_url, width=64)
    role_badge = "🛡️ admin" if _current_user.is_admin else "👤 member"
    st.markdown(
        f"**{_current_user.display_name or _current_user.username}**  \n"
        f"`{_current_user.username}` ({role_badge})"
    )
    if is_oauth_enabled():
        if st.button("ログアウト", key="sidebar_logout"):
            st.logout()
    else:
        st.caption("⚠️ ローカル開発モード (OAuth スキップ中)")

    st.divider()
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

    # --- Gemini Flash 無料枠の使用状況 ---
    st.divider()
    st.caption("**無料枠 (Gemini Flash, 1日)**")
    _quota = get_flash_quota_status()
    _quota_text = (
        f"{_quota.used} / {_quota.limit} 使用 "
        f"(残り {_quota.remaining} calls = "
        f"あと約 {_quota.remaining // FLASH_CALLS_PER_QUESTION} 質問)"
    )
    if _quota.level == "exhausted":
        st.error(f"❌ {_quota_text}\n本日の無料枠を使い切りました。")
    elif _quota.level == "danger":
        st.error(f"🚨 {_quota_text}\n上限間近です。質問を控えるか明日に回してください。")
    elif _quota.level == "warn":
        st.warning(f"⚠️ {_quota_text}\nもう少しで上限です。")
    else:
        st.caption(f"✅ {_quota_text}")
    st.progress(min(_quota.pct, 1.0))
    # Phase 5 Theme A: 次のリセットまでの残り時間
    st.caption(
        f"⏰ 次のリセット: {format_until_reset(_quota.time_until_reset)} "
        f"({_quota.reset_at_jst_str})"
    )

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

    # 入力前の Quota ガード
    quota = get_flash_quota_status()
    if not quota.can_run_question:
        st.error(
            f"❌ Gemini Flash の本日無料枠 ({quota.used}/{quota.limit}) "
            f"がもう質問 1 件分 ({FLASH_CALLS_PER_QUESTION} calls) を満たせません。\n\n"
            "明日 00:00 (PT) リセット後に再開してください。"
        )
        # チャット入力を無効化
        st.chat_input("本日の無料枠を使い切りました", disabled=True)
        return
    if quota.level == "danger":
        st.warning(
            f"🚨 残り {quota.remaining} calls (≒ {quota.remaining // FLASH_CALLS_PER_QUESTION} 質問)。"
            "次の質問で上限に達する可能性があります。"
        )

    # 入力
    if prompt := st.chat_input("質問を入力..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"), st.spinner("5 エージェントが調査・分析中..."):
            try:
                # Phase 5 Theme C: 質問の発信者を runs.username に記録
                state = answer(prompt, username=_current_user.username)
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
    col2.metric(
        "要確認率",
        f"{(ng_count / total_runs * 100) if total_runs else 0:.1f}%",
        help=(
            "Fact-checker が分析に問題 (根拠不足・矛盾・日付不整合など) を検出し、"
            "差し戻し上限 (デフォルト 2 回) 内に解消できなかった割合。\n\n"
            "**システムは止まらず最終回答は生成されている**が、回答内の「リスク・反論」"
            "セクションで Fact-checker の指摘が反映されている。\n\n"
            "予測系・推測を含む質問では本質的に NG になりやすい (例: 「来期の予測」)。"
        ),
    )
    col3.metric("平均所要時間", f"{avg_duration:.1f} 秒")
    col4.metric(
        "平均リトライ",
        f"{avg_retries:.2f}",
        help="1 質問あたりの Fact-checker → Analyst 差し戻し回数の平均",
    )

    # 凡例
    st.caption(
        "💡 **凡例**: `OK` = Fact-checker が問題なしと判定した状態 / "
        "`NG (要確認)` = 差し戻し後も問題が残った状態 (最終回答に注釈付きで反映)"
    )

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
        st.plotly_chart(fig, width="stretch")

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
        st.plotly_chart(fig2, width="stretch")

    st.divider()

    # --- 実行履歴テーブル ---
    st.subheader("🗂️ 実行履歴")
    display_df = df_window.copy()
    display_df["所要時間 (秒)"] = (display_df["duration_ms"].fillna(0) / 1000).round(1)
    # 判定値を人間に分かる形に変換
    display_df["判定"] = display_df["final_verdict"].map(
        {"OK": "✅ OK", "NG": "⚠️ 要確認 (NG)"}
    ).fillna(display_df["final_verdict"])
    display_df = display_df[
        ["started_at", "question", "判定", "retry_count", "所要時間 (秒)", "error"]
    ].rename(
        columns={
            "started_at": "実行時刻",
            "question": "質問",
            "retry_count": "リトライ",
            "error": "エラー",
        }
    )
    st.dataframe(display_df, width="stretch", height=400)


# --- 管理画面 (Phase 5 Theme C, admin のみ) ---
def _render_admin_tab() -> None:
    """admin 専用: 許可ユーザー CRUD + 統計."""
    rlog = RunLogger()

    st.subheader("👥 許可ユーザー一覧")
    users = rlog.list_allowed_users()
    if users:
        # 各ユーザーの累計質問数を付与
        for u in users:
            u["queries"] = rlog.user_run_count(u["username"])
        df = pd.DataFrame(users)
        df = df.rename(
            columns={
                "username": "HF Username",
                "role": "Role",
                "display_name": "表示名",
                "added_at": "追加日時",
                "added_by": "追加者",
                "last_login": "最終ログイン",
                "queries": "質問数",
            }
        )
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("許可ユーザーが登録されていません。")

    st.divider()

    # 新規追加フォーム
    with st.expander("➕ 新規ユーザー追加", expanded=False):
        with st.form("add_user_form", clear_on_submit=True):
            new_username = st.text_input(
                "HF Username",
                placeholder="例: friend-username",
                help="<https://huggingface.co/> のプロフィール URL の最後の部分",
            )
            new_role = st.selectbox("Role", ["member", "admin"])
            submitted = st.form_submit_button("追加")
            if submitted:
                username_clean = new_username.strip().lstrip("@")
                if not username_clean:
                    st.error("Username を入力してください")
                elif username_clean.startswith("@line:"):
                    st.error("`@line:` で始まる username は予約済みです (LINE 用)")
                else:
                    try:
                        rlog.add_allowed_user(
                            username=username_clean,
                            role=new_role,
                            added_by=_current_user.username,
                        )
                        st.success(f"✅ `{username_clean}` を **{new_role}** として追加しました")
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"追加失敗: {e}")

    # ロール変更
    with st.expander("✏️ ロール変更"):
        if users:
            target_username = st.selectbox(
                "対象ユーザー",
                [u["username"] for u in users],
                key="role_change_target",
            )
            target_new_role = st.selectbox(
                "新しい Role",
                ["member", "admin"],
                key="role_change_new",
            )
            if st.button("ロール変更", key="btn_role_change"):
                if target_username == _current_user.username and target_new_role != "admin":
                    st.error("自分自身を admin から外すことはできません")
                else:
                    try:
                        rlog.update_user_role(target_username, target_new_role)
                        st.success(
                            f"✅ `{target_username}` の role を **{target_new_role}** に変更"
                        )
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"変更失敗: {e}")
        else:
            st.caption("変更対象のユーザーがいません")

    # 削除
    with st.expander("🗑️ ユーザー削除"):
        if users:
            del_target = st.selectbox(
                "削除するユーザー",
                [u["username"] for u in users],
                key="del_target",
            )
            del_confirm = st.checkbox(f"`{del_target}` を本当に削除する", key="del_confirm")
            if st.button("削除", type="primary", key="btn_del"):
                if del_target == _current_user.username:
                    st.error("自分自身は削除できません")
                elif not del_confirm:
                    st.error("確認チェックを入れてください")
                else:
                    try:
                        rlog.remove_allowed_user(del_target)
                        st.success(f"✅ `{del_target}` を削除しました")
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.error(f"削除失敗: {e}")
        else:
            st.caption("削除対象のユーザーがいません")


# --- タブ構成 (admin のみ管理タブ追加) ---
if _current_user.is_admin:
    tab_chat, tab_dashboard, tab_admin = st.tabs(
        ["💬 チャット", "📊 ダッシュボード", "👥 管理"]
    )
    with tab_chat:
        _render_chat_tab()
    with tab_dashboard:
        _render_dashboard_tab()
    with tab_admin:
        _render_admin_tab()
else:
    tab_chat, tab_dashboard = st.tabs(["💬 チャット", "📊 ダッシュボード"])
    with tab_chat:
        _render_chat_tab()
    with tab_dashboard:
        _render_dashboard_tab()
