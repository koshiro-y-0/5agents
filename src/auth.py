"""HF OAuth ベースの認証と権限解決 (Phase 5 Theme C).

設計:
- HF Spaces が `hf_oauth: true` 設定で OAuth client を自動生成し
  OAUTH_CLIENT_ID / OAUTH_CLIENT_SECRET / OPENID_PROVIDER_URL / SPACE_HOST を env 注入.
- Streamlit 1.42+ のネイティブ OIDC 機能 (st.user / st.login / st.logout) を利用.
- secrets.toml は entrypoint.sh が env から生成 (huggingface/entrypoint.sh).
- 許可リストは SQLite の allowed_users テーブル (src/memory/logger.py で管理).

ローカル開発:
- OAUTH_CLIENT_ID 未設定なら認証スキップ (guest user として動作).
- 開発時にはサイドバーに警告を出す (src/app.py 側).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Literal

from src.memory.logger import RunLogger

logger = logging.getLogger(__name__)

Role = Literal["admin", "member", "guest"]


@dataclass(frozen=True)
class CurrentUser:
    """ログイン中ユーザーの正規化された表現."""

    username: str              # HF preferred_username (例: 'koshiro-y-12')
    display_name: str | None   # 表示名 (HF name)
    picture_url: str | None    # アバター URL
    role: Role                 # 'admin' / 'member' / 'guest' (許可外)

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_allowed(self) -> bool:
        """admin or member なら True (guest は False)."""
        return self.role in ("admin", "member")


def is_oauth_enabled() -> bool:
    """HF OAuth が有効な環境かどうか (OAUTH_CLIENT_ID の有無で判定).

    ローカル開発時は False を返し、認証ゲートをスキップする.
    """
    return bool(os.getenv("OAUTH_CLIENT_ID"))


def get_current_user() -> CurrentUser | None:
    """Streamlit セッションから現在のユーザーを取得.

    Returns:
        - HF OAuth 有効 + ログイン済み: CurrentUser
        - HF OAuth 有効 + 未ログイン: None
        - HF OAuth 無効 (ローカル開発): "_local_dev" username の admin 扱い CurrentUser

    Streamlit の st.user は属性アクセスで claims を取得できる
    (`st.user.is_logged_in` / `st.user.preferred_username` 等).
    HF が返す claims のうち利用するのは:
        - preferred_username (HF ログイン名)
        - name              (表示名)
        - picture           (アバター URL)
    """
    # ローカル開発: OAuth 無効 → ダミー admin として扱う (UI が常に開く)
    if not is_oauth_enabled():
        return CurrentUser(
            username="_local_dev",
            display_name="ローカル開発",
            picture_url=None,
            role="admin",
        )

    # Streamlit ネイティブ auth から取得
    try:
        import streamlit as st
    except ImportError:
        # Streamlit 文脈外 (テスト等) では None
        return None

    user_obj: Any = getattr(st, "user", None)
    if user_obj is None or not getattr(user_obj, "is_logged_in", False):
        return None

    # claims を安全に取り出す (HF OIDC の標準的なフィールド)
    username = (
        getattr(user_obj, "preferred_username", None)
        or getattr(user_obj, "sub", None)  # 万一 preferred_username が無い場合のフォールバック
        or ""
    )
    if not username:
        logger.warning("OAuth user without preferred_username/sub claim")
        return None

    display_name = getattr(user_obj, "name", None) or username
    picture_url = getattr(user_obj, "picture", None)

    # role 解決
    rlog = RunLogger()
    db_role = rlog.get_user_role(username)
    role: Role = db_role if db_role in ("admin", "member") else "guest"  # type: ignore[assignment]

    return CurrentUser(
        username=username,
        display_name=display_name,
        picture_url=picture_url,
        role=role,
    )


def register_login(user: CurrentUser) -> None:
    """ログインしたユーザーの last_login を更新 (許可ユーザーのみ)."""
    if not user.is_allowed:
        return
    try:
        RunLogger().touch_last_login(user.username, user.display_name)
    except Exception as e:  # noqa: BLE001
        logger.warning("touch_last_login 失敗 (user=%s): %s", user.username, e)


def line_username(line_user_id: str) -> str:
    """LINE 経由クエリの username (擬似) を生成する規約.

    HF username と衝突しないよう '@line:' プレフィックスを付ける.
    例: '@line:Uabcdef0123456789...'
    """
    return f"@line:{line_user_id}"
