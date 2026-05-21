# Phase 5: 改善計画 (実運用フィードバック反映)

> **位置付け**: Phase 4 (HF Spaces 移行) 完了後の運用フィードバックに基づく改善計画。
> 実装は次セッション以降。本ドキュメントは仕様と受け入れ基準の合意ベース。
>
> **計画日**: 2026-05-21
> **対象ブランチ**: `feature/phase5-improvement-plan` (仕様) → 各実装は別 feature ブランチで

---

## 背景: 実運用で見えた課題

HF Spaces デプロイ後、実際に LINE 経由で 5agents を使用した結果、3 つの改善ニーズが顕在化した。

| # | 課題 | ユーザー体験への影響 |
|---|---|---|
| A | 無料枠が枯れたとき「明日リセット」とだけ表示 → いつ復活するか曖昧 | 待ち時間の予測が立たず再試行のタイミングを誤る |
| B | LINE での回答が Markdown 生表示で読みにくい (`##` `**` がそのまま見える) | スクロール量が増え、要点把握に時間がかかる |
| C | Streamlit ダッシュボードを Windows で開けない (Mac は OK)<br>+ 複数人共有時のパスワード使い回しリスク | クロスデバイス UX 不全 + セキュリティ懸念 |

---

## 全体方針

- **順番**: B (見た目) → A (タイマー) → C (認証) — 効果体感の早いものから着手
- **スコープ**: 機能追加が中心。エージェントのロジック (汎用調査の中核) は触らない
- **コスト**: すべて無料枠内で完結。新規依存も最小限
- **後方互換**: 既存 SQLite/ChromaDB は破壊せず、マイグレーションは安全側 (`IF NOT EXISTS` / `ALTER TABLE` 追加のみ)

---

## Theme B: LINE メッセージの見やすさ向上

### 現状の問題

スクショから判明:
- `## 結論` `## 根拠` 等の Markdown ヘッダが LINE では装飾されず生表示 (LINE は Markdown 非対応)
- `**強調**` が `**強調**` のまま見える
- `* 項目` の bullet も装飾されない
- セクション境界が視覚的に弱い

### 設計判断

| 選択肢 | 判断 |
|---|---|
| Finalizer のプロンプトで最初から LINE 用フォーマット生成 | ❌ Streamlit でも崩れた表示になる |
| **post-process で Markdown → LINE 用装飾に変換 (採用)** | ✅ Streamlit は綺麗な Markdown のまま、LINE だけ変換 |
| Flex Message (バブル UI) で完全カスタム表示 | ⏸ 将来検討。今回は段落単位の装飾で十分 |

### 変換ルール (`markdown_to_line()`)

| 入力 | 出力 |
|---|---|
| `## 結論` | `━━━ 🎯 結論 ━━━` |
| `## 根拠` | `━━━ 📌 根拠 ━━━` |
| `## リスク・反論` | `━━━ ⚠️ リスク・反論 ━━━` |
| `## 出典` | `━━━ 🔗 出典 ━━━` |
| `### サブ見出し` | `▸ サブ見出し` |
| `**強調**` | `「強調」` |
| `^\* 項目` (行頭の bullet) | `▪ 項目` |
| `^\d+\. 項目` (番号付き) | そのまま (LINE で読みやすい) |
| URL 単独行 | そのまま (LINE が自動リンク化) |
| `---` (水平線) | `─────────────` |

> セクション見出しの絵文字マップは Finalizer の出力セクションに合わせる。
> 想定外見出しは `▪ 見出し` にフォールバック。

### 実装ファイル

- `src/line/formatter.py`
  - 新規 `markdown_to_line(md: str) -> str`
  - 既存 `split_for_line()` の中で `markdown_to_line()` を呼んでから分割
- `tests/test_line_formatter.py` (新規 or 既存追記)
  - 各変換ルールの単体テスト 8 件
  - mixed セクションを通した E2E テスト 1 件
  - 変換なし入力 (passthrough) テスト 1 件

### 受け入れ基準

- [ ] 既存の 2 メッセージ分割ロジックは挙動変わらず (msg1=結論+根拠, msg2=リスク+出典)
- [ ] `## 結論` が `━━━ 🎯 結論 ━━━` になる (現物 LINE で目視)
- [ ] `**bold**` が LINE で `「bold」` と表示される
- [ ] `pytest tests/test_line_formatter.py` 全 PASS
- [ ] Streamlit ダッシュボードの表示には影響なし

### 規模見積もり

**0.5 day** (実装 2h + テスト 1h + 現物 LINE 確認 1h)

---

## Theme A: クォータ復活タイマー

### 現状の問題

`src/line/webhook.py` の枯渇メッセージ:
```
⚠️ 本日の Gemini Flash 無料枠 (20/20) を使い切りました。
明日リセット後にもう一度お送りください。
```
「明日リセット後」が曖昧 (具体的に何時?)。

`src/app.py` のサイドバーの残数バッジにもリセット時刻情報なし。

### 各 API のリセット周期 (2026-05 時点の調査)

| API | リセット周期 | 実際のリセット時刻 | アプリ側の追跡 |
|---|---|---|---|
| Gemini Flash 20 RPD | 日次 | 米国 PT 00:00 = JST 16:00 (PDT) / 17:00 (PST) | SQLite の `today_jst` で集計 → JST 00:00 リセット扱い |
| Tavily 1,000/月 | 月次 | UTC 月初 00:00 | (今は追跡なし) |
| LINE Push 200/月 | 月次 | JST 月初 00:00 (LINE 公式仕様) | (今は追跡なし) |
| Groq 14,400/日 | 日次 | UTC 00:00 | (実質枯れないので警告対象外) |

### 設計上の注意点

- アプリの `today_jst` 集計と Google PT のリセット時刻はズレる:
  - JST 00:00〜JST 16:00 の間: Google 側は既にリセット済み (アプリ側はまだリセット待ち) → **保守的に多く計上** (安全側)
  - JST 16:00 以降: 一致
- 「リセット時刻」は **アプリ視点 (JST 翌 00:00)** を表示する旨を docstring で明示

### `QuotaStatus` 拡張

```python
@dataclass(frozen=True)
class QuotaStatus:
    used: int
    limit: int
    remaining: int
    pct: float
    level: QuotaLevel
    # 新規追加
    reset_at: datetime          # 次にリセットされる時刻 (JST aware)
    time_until_reset: timedelta # 今から reset_at までの差分

    @property
    def reset_at_local_str(self) -> str:
        """HH:MM JST 形式の文字列 (例: '16:00 JST')."""
        ...
```

### `format_until_reset()` ヘルパー

| 残り時間 | 表示 |
|---|---|
| < 60 秒 | `まもなく復活` |
| < 1 時間 | `あと N 分` |
| < 24 時間 | `あと N 時間 M 分` |
| >= 24 時間 | `あと N 日` |

### LINE 枯渇メッセージの新フォーマット

```
⚠️ 本日の Gemini Flash 無料枠 (20/20) を使い切りました。
⏰ あと 3 時間 24 分で復活します (明日 00:00 JST)
```

### Streamlit サイドバー

```
無料枠 (Gemini Flash, 1 日)
[████████████████░░░░] 18 / 20 使用
🟡 残り 2 calls (= あと 1 質問)
⏰ 次のリセット: あと 3 時間 24 分
```

### 実装ファイル

- `src/quota.py`: QuotaStatus 拡張 + 計算ロジック + format_until_reset()
- `src/line/webhook.py`: 枯渇 reply のフォーマット差し替え
- `src/app.py`: サイドバーに行追加
- `tests/test_quota.py`: reset_at 計算ロジック + フォーマッタテスト

### 受け入れ基準

- [ ] `QuotaStatus.reset_at` が常に「次の JST 00:00」を返す (テスト)
- [ ] LINE 枯渇メッセージに復活時刻と残り時間が出る (現物確認)
- [ ] Streamlit サイドバーに「次のリセット: あと ...」が出る
- [ ] `pytest tests/test_quota.py` 全 PASS

### 規模見積もり

**0.5 day** (実装 2h + テスト 1h + 動作確認 1h)

### 将来拡張 (今回はやらない)

- Tavily / LINE Push の月次クォータ追跡 (現状未追跡)
- リセット時刻に対応した自動リトライキュー (高度なので別 Phase で)

---

## Theme C: HF OAuth + 管理画面 + マルチデバイス対応

### 現状の問題

- Streamlit ゲートが単一 `STREAMLIT_PASSWORD` のみ
- Windows で開けない (要原因切り分け: パスワード忘れ? Cookie? ネットワーク?)
- 家族・友人に共有する際にパスワード使い回し → 漏洩リスク
- 「誰がいつ何を質問したか」のログが username に紐付かない

### 設計判断: C-5 (HF OAuth + 許可リスト + 管理画面)

| 採用理由 |
|---|
| **HF Space は OAuth ネイティブサポート** (`hf_oauth: true` で 1 行設定) |
| HF アカウントは無料 30 秒で作れる → 家族・友人にも負担少 |
| Cookie ベースなので Mac/Windows/Mobile 全てシームレス |
| パスワード管理コードが不要 (HF が肩代わり) |
| 管理画面で「誰が許可されているか」を視覚的に把握可能 |

### アーキテクチャ

```
ブラウザ
   ↓
HF Space (Public) - port 7860
   ↓
nginx
   ↓
Streamlit
   ↓
_require_auth() → st.experimental_user (HF OAuth セッション)
   ↓
get_current_user() → username 取得
   ↓
is_allowed(username) ?
   ├─ False → "アクセス権なし" 画面
   └─ True  → 本体 UI
              └─ is_admin(username) → 管理タブ表示
```

### HF Space の OAuth 設定

`huggingface/README.md` frontmatter に追加:

```yaml
---
title: 5agents
emoji: 🤖
sdk: docker
app_port: 7860
hf_oauth: true                  # 追加
hf_oauth_scopes:                # 追加
  - openid
  - profile
suggested_storage: small
---
```

これを HF Space に push すると HF が自動で以下の環境変数をコンテナに注入:

| 環境変数 | 値 |
|---|---|
| `OAUTH_CLIENT_ID` | HF が発行 |
| `OAUTH_CLIENT_SECRET` | HF が発行 |
| `OAUTH_SCOPES` | 上で指定したスコープ |
| `OPENID_PROVIDER_URL` | `https://huggingface.co` |
| `SPACE_HOST` | `koshiro-y-12-5agents.hf.space` |

Streamlit 側からは `st.experimental_user` (or `st.user`, 2026 時点の Streamlit 1.45+ で stable) でアクセス可能。

### SQLite スキーマ追加

```sql
-- 既存テーブル: runs(run_id, question, started_at, completed_at, status, ...)
-- 既存テーブル: agent_calls(call_id, run_id, agent, model, ...)

-- 新規: 許可ユーザー
CREATE TABLE IF NOT EXISTS allowed_users (
    username   TEXT PRIMARY KEY,    -- HF username
    role       TEXT NOT NULL CHECK(role IN ('admin', 'member')),
    added_at   DATETIME NOT NULL,
    added_by   TEXT,                -- 追加した admin の username
    last_login DATETIME             -- 最終ログイン時刻 (UI 表示用)
);

-- 既存 runs テーブルに username カラム追加 (誰の質問か追跡)
ALTER TABLE runs ADD COLUMN username TEXT;  -- 既存 row は NULL
```

### 初期 admin 投入

`huggingface/entrypoint.sh` で起動時に以下を実行:

```bash
if [ -n "${INITIAL_ADMIN_HF_USERNAME:-}" ]; then
    .venv/bin/python -c "
from src.memory.logger import RunLogger
RunLogger().ensure_admin('$INITIAL_ADMIN_HF_USERNAME')
"
fi
```

`RunLogger.ensure_admin(username)`:
- `INSERT OR IGNORE INTO allowed_users (username, role, added_at, added_by) VALUES (?, 'admin', NOW, 'system')`
- 既に存在しても上書きしない (誤って role を member にしないため)

HF Space Secrets に `INITIAL_ADMIN_HF_USERNAME=koshiro-y-12` を追加。

### `src/auth.py` (新規)

```python
"""HF OAuth ベースの認証 / 権限解決."""

@dataclass
class CurrentUser:
    username: str
    name: str | None
    picture_url: str | None
    role: Literal["admin", "member", "guest"]  # guest = 未許可

def get_current_user() -> CurrentUser | None:
    """Streamlit セッションから現在のユーザーを取得.

    HF OAuth が無効化されてる (ローカル開発) なら None を返す.
    """
    ...

def is_allowed(username: str) -> bool:
    """allowed_users テーブルにいるか."""
    ...

def is_admin(username: str) -> bool:
    """role == 'admin' か."""
    ...

def register_login(username: str) -> None:
    """最終ログイン時刻を更新."""
    ...
```

### `src/app.py` の認証ゲート差し替え

```python
def _require_auth() -> None:
    # ローカル開発 (HF OAuth 環境変数なし) は素通り
    if not os.getenv("OAUTH_CLIENT_ID"):
        st.warning("⚠️ ローカル開発モード: 認証スキップ中")
        return

    user = get_current_user()
    if user is None:
        # 未ログイン
        st.title("🔒 5agents")
        st.caption("Hugging Face アカウントでログインしてください。")
        st.button("Sign in with Hugging Face", on_click=st.login)  # 仮 API
        st.stop()

    if not is_allowed(user.username):
        st.title("⛔ アクセス権がありません")
        st.write(f"`{user.username}` はこの 5agents の許可ユーザーに含まれていません。")
        st.write("利用したい場合は管理者 (`koshiro-y-12`) に依頼してください。")
        st.button("ログアウト", on_click=st.logout)
        st.stop()

    register_login(user.username)
    # ← 通過したら本体 UI へ
```

> ⚠️ `st.login()` / `st.logout()` / `st.experimental_user` の正確な API は実装直前に
> Streamlit + HF OAuth ドキュメントで再確認 (1 年で変わる可能性大)。

### 管理画面タブ

```python
if is_admin(user.username):
    with st.tabs(["💬 チャット", "📊 ダッシュボード", "👥 管理"])[2]:
        st.subheader("許可ユーザー一覧")
        users_df = list_allowed_users()  # username, role, added_at, last_login, query_count
        st.dataframe(users_df)

        with st.expander("➕ 新規ユーザー追加"):
            new_username = st.text_input("HF Username")
            new_role = st.selectbox("Role", ["member", "admin"])
            if st.button("追加"):
                add_user(new_username, new_role, added_by=user.username)
                st.success(f"{new_username} を追加しました")
                st.rerun()

        with st.expander("✏️ ロール変更 / 削除"):
            target = st.selectbox("対象ユーザー", users_df["username"])
            new_role = st.selectbox("新しい Role", ["member", "admin"])
            col1, col2 = st.columns(2)
            with col1:
                if st.button("ロール変更"):
                    update_role(target, new_role)
            with col2:
                if st.button("削除", type="primary"):
                    remove_user(target)
```

### 実装ファイル一覧

| ファイル | 操作 | 内容 |
|---|---|---|
| `huggingface/README.md` | 更新 | frontmatter に `hf_oauth: true` 追加 |
| `huggingface/entrypoint.sh` | 更新 | 起動時に `ensure_admin` 実行 |
| `src/config.py` | 更新 | `initial_admin_hf_username` 追加 |
| `src/auth.py` | **新規** | OAuth 取得 / 権限解決 |
| `src/memory/logger.py` | 更新 | allowed_users スキーマ + `ensure_admin` / `list_allowed_users` / `add_user` / `update_role` / `remove_user` |
| `src/app.py` | 更新 | 認証ゲート差し替え + 管理タブ追加 |
| `src/agents/orchestrator.py` | 更新 | answer() に username 引数追加 → runs に記録 |
| `src/line/webhook.py` | 更新 | LINE 経由は `username = f"line:{user_id}"` で記録 (HF user と区別) |
| `tests/test_auth.py` | **新規** | is_allowed / is_admin のテスト (DB モック) |
| `tests/test_users_table.py` | **新規** | スキーマ追加 / マイグレーションのテスト |
| `docs/HF_OAUTH_SETUP.md` | **新規** | OAuth 有効化手順 + 管理画面の使い方 |

### 受け入れ基準

- [ ] Mac/Windows どちらのブラウザでも「Sign in with Hugging Face」が機能する
- [ ] 自分 (koshiro-y-12) で開く → ダッシュボード + 管理タブ表示
- [ ] 別の HF アカウントで開く → 「アクセス権なし」画面
- [ ] 管理画面から `friend-username` を member 追加 → そのユーザーで開ける
- [ ] 管理画面の質問回数が orchestrator の username 紐付けで正しく出る
- [ ] LINE 経由の質問は `line:Uxxx...` という username で runs に記録される
- [ ] ローカル開発 (`OAUTH_CLIENT_ID` 未設定) では認証スキップで動作 (後方互換)
- [ ] `pytest tests/test_auth.py tests/test_users_table.py` 全 PASS

### 規模見積もり

**1〜2 days** (調査含む)
- HF OAuth + Streamlit の連携 API 確認 (3h)
- auth.py + DB スキーマ実装 (3h)
- app.py の差し替え (2h)
- 管理画面 UI (3h)
- テスト + E2E (3h)
- ドキュメント (2h)

### 将来拡張 (今回はやらない)

- 2FA (HF 側で対応してるので不要)
- per-user の使用量制限 (家族で枠を分け合うなど)
- "Audit log" (誰が誰を追加/削除したか)
- LINE 側にも HF username 連携 (現状は LINE User ID で別管理)

---

## ロードマップ

| 順序 | テーマ | ブランチ名 | 規模 | 完了基準 |
|---|---|---|---|---|
| 1 | B: LINE 装飾 | `feature/line-formatter-decoration` | 0.5d | 全 ✓ on B 受け入れ基準 |
| 2 | A: クォータタイマー | `feature/quota-reset-timer` | 0.5d | 全 ✓ on A 受け入れ基準 |
| 3 | C: HF OAuth + 管理画面 | `feature/hf-oauth-admin-panel` | 1〜2d | 全 ✓ on C 受け入れ基準 |

各テーマで:
1. feature ブランチ切る
2. 実装 + テスト
3. ローカル動作確認
4. PR 作成 → main へマージ
5. HF Space (`hf-deploy` ブランチ) にも反映:
   - `git checkout hf-deploy && git merge main` で main の変更を取り込み
   - HF 用 README は上書き済みのままで OK
   - `git push -f hf hf-deploy:main` で再デプロイ

---

## 検証チェックリスト (Phase 5 完了時)

実装完了後の総合検証:

- [ ] LINE で質問 → 絵文字付き読みやすいフォーマットで返信 (B)
- [ ] 枯渇まで質問連発 → 枯渇時に「あと N 時間で復活」が表示 (A)
- [ ] Mac で HF OAuth ログイン (C)
- [ ] Windows で同じく HF OAuth ログイン (C)
- [ ] 管理画面から友人の HF username を追加 (C)
- [ ] 友人がログインして使える (C)
- [ ] 友人の質問回数が管理画面に反映される (C)
- [ ] `pytest` 全 PASS
- [ ] HF Space で `Running` 状態を維持

---

## 関連ドキュメント

- [HF Spaces デプロイガイド](./HF_SPACES_DEPLOY.md) — Phase 4 で作成
- [LINE 連携セットアップ](./LINE_SETUP.md) — Phase 3 で作成
- [AI エージェント構築計画書](./AIエージェント構築計画書.docx) — 全体構想 (Phase 1〜)
