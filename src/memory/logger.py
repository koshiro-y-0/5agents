"""エージェント呼び出しの SQLite ロガー.

責務:
- 各エージェント (A〜E) の呼び出し開始・終了・所要時間・エラーを記録
- 後の分析・可視化 (Phase 4) のためのベースデータを提供

スキーマ:
    runs           1 質問 = 1 行 (全体の所要時間と最終 verdict)
    agent_calls    各エージェントノード呼び出し = 1 行
"""

from __future__ import annotations

import logging
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.config import get_settings

logger = logging.getLogger(__name__)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id              TEXT PRIMARY KEY,
    question        TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    duration_ms     INTEGER,
    final_verdict   TEXT,
    retry_count     INTEGER DEFAULT 0,
    error           TEXT,
    -- Phase 5 Theme C: 質問の発信者 (HF preferred_username or '@line:<UserId>')
    username        TEXT
);

CREATE TABLE IF NOT EXISTS agent_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    agent           TEXT NOT NULL,
    model           TEXT,
    started_at      TEXT NOT NULL,
    duration_ms     INTEGER,
    error           TEXT,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);

CREATE INDEX IF NOT EXISTS idx_agent_calls_run_id ON agent_calls(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at);

-- Phase 5 Theme C: 許可ユーザー (HF OAuth ベース)
-- ・username  = HF の preferred_username (例: 'koshiro-y-12')
-- ・role      = 'admin' (管理画面操作可) / 'member' (利用のみ)
-- ・LINE 経由のクエリは '@line:<UserId>' という擬似 username で記録する
CREATE TABLE IF NOT EXISTS allowed_users (
    username        TEXT PRIMARY KEY,
    role            TEXT NOT NULL CHECK(role IN ('admin', 'member')),
    added_at        TEXT NOT NULL,
    added_by        TEXT,
    last_login      TEXT,
    display_name    TEXT
);
"""

# 既存 DB に対する後方互換マイグレーション (Phase 5 Theme C 追加)
# 重要: 既存 DB の runs テーブルは username カラムが無いまま CREATE TABLE IF NOT EXISTS
#       を no-op で通過するので、ALTER TABLE → CREATE INDEX の順で個別実行が必要.
#       executescript() で SCHEMA に CREATE INDEX を含めると、ALTER 前に走って
#       "no such column: username" で全 SCHEMA がロールバックされ allowed_users も
#       作られない (Phase 5.C デプロイで実際に発生したバグ).
_MIGRATIONS: tuple[str, ...] = (
    # 1. 既存 runs テーブルへの username カラム追加 (既に存在すれば duplicate column で無視)
    "ALTER TABLE runs ADD COLUMN username TEXT",
    # 2. username インデックスを ALTER の後に作成 (上の ALTER が必須なので順序固定)
    "CREATE INDEX IF NOT EXISTS idx_runs_username ON runs(username)",
)


@dataclass
class RunStats:
    """1 run の集計値 (UI 表示用)."""

    run_id: str
    question: str
    duration_ms: int | None
    final_verdict: str | None
    retry_count: int
    agent_durations: dict[str, int]  # agent name → 合計 ms (差し戻し時は複数回呼ばれるので加算)
    agent_call_counts: dict[str, int]  # agent name → 呼び出し回数


class RunLogger:
    """SQLite に runs と agent_calls を記録する."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        settings = get_settings()
        path = Path(db_path) if db_path else settings.sqlite_path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db_path = path
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        # 外部キー制約を有効化 (デフォルト無効)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            # 既存 DB への追加カラム migration (失敗は無視: 既に追加済み)
            for stmt in _MIGRATIONS:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    # "duplicate column name" 等 — すでに適用済みなので OK
                    pass

    # --- runs ---

    def start_run(self, question: str, username: str | None = None) -> str:
        """新しい run を作成して ID を返す.

        Args:
            question: ユーザー質問
            username: 誰の質問か (Phase 5 Theme C で追加)。
                      HF ユーザーは preferred_username, LINE 経由は '@line:<UserId>'.
                      None なら NULL (旧ローカル CLI 等)。
        """
        run_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, question, started_at, username) VALUES (?, ?, ?, ?)",
                (run_id, question, datetime.now(UTC).isoformat(), username),
            )
        return run_id

    def finish_run(
        self,
        run_id: str,
        duration_ms: int,
        final_verdict: str | None,
        retry_count: int,
        error: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE runs SET finished_at = ?, duration_ms = ?, final_verdict = ?, "
                "retry_count = ?, error = ? WHERE id = ?",
                (
                    datetime.now(UTC).isoformat(),
                    duration_ms,
                    final_verdict,
                    retry_count,
                    error,
                    run_id,
                ),
            )

    # --- agent_calls ---

    def log_agent_call(
        self,
        run_id: str,
        agent: str,
        model: str | None,
        duration_ms: int,
        error: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO agent_calls (run_id, agent, model, started_at, duration_ms, error) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, agent, model, datetime.now(UTC).isoformat(), duration_ms, error),
            )

    # --- analytics ---

    def get_run_stats(self, run_id: str) -> RunStats | None:
        """1 run の集計を返す (UI 表示用).

        差し戻しループで同じエージェントが複数回呼ばれている場合は、
        所要時間を合計し、呼び出し回数を別途記録する。
        """
        with self._connect() as conn:
            run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if run is None:
                return None
            calls = conn.execute(
                "SELECT agent, duration_ms FROM agent_calls WHERE run_id = ?", (run_id,)
            ).fetchall()

        agent_durations: dict[str, int] = {}
        agent_call_counts: dict[str, int] = {}
        for c in calls:
            agent = c["agent"]
            agent_durations[agent] = agent_durations.get(agent, 0) + (c["duration_ms"] or 0)
            agent_call_counts[agent] = agent_call_counts.get(agent, 0) + 1

        return RunStats(
            run_id=run["id"],
            question=run["question"],
            duration_ms=run["duration_ms"],
            final_verdict=run["final_verdict"],
            retry_count=run["retry_count"] or 0,
            agent_durations=agent_durations,
            agent_call_counts=agent_call_counts,
        )

    def recent_runs(self, limit: int = 10) -> list[dict]:
        """直近 N 件の run を新しい順で取得."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, question, duration_ms, final_verdict, retry_count, started_at "
                "FROM runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_today_model_call_count(self, model_name: str) -> int:
        """指定モデル名の今日 (UTC 日付ベース) の呼び出し回数を返す.

        Gemini Flash 無料枠などの **日次クォータ事前チェック** に使用する。
        agent_calls.model に保存された exact 一致でカウント。
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM agent_calls "
                "WHERE DATE(started_at) = DATE('now') AND model = ?",
                (model_name,),
            ).fetchone()
        return int(row["c"] or 0) if row else 0

    def daily_run_counts(self, last_n_days: int = 14) -> list[dict]:
        """直近 N 日分の日別実行数 (新しい順 → 古い順に並べ替えて返却)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DATE(started_at) AS date, COUNT(*) AS count "
                "FROM runs WHERE started_at >= DATE('now', ? ) "
                "GROUP BY DATE(started_at) ORDER BY date ASC",
                (f"-{last_n_days} days",),
            ).fetchall()
        return [dict(r) for r in rows]

    def agent_total_durations(self, last_n_days: int = 14) -> list[dict]:
        """直近 N 日のエージェント別合計所要時間 (秒)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT agent, "
                "SUM(duration_ms) AS total_ms, "
                "COUNT(*) AS call_count "
                "FROM agent_calls "
                "WHERE started_at >= DATE('now', ?) "
                "GROUP BY agent ORDER BY total_ms DESC",
                (f"-{last_n_days} days",),
            ).fetchall()
        return [
            {"agent": r["agent"], "total_s": (r["total_ms"] or 0) / 1000, "calls": r["call_count"]}
            for r in rows
        ]

    def all_runs_for_dashboard(self, limit: int = 100) -> list[dict]:
        """ダッシュボードのテーブル表示用に直近 N 件を取得."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, question, duration_ms, final_verdict, retry_count, "
                "started_at, finished_at, error, username "
                "FROM runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # --- allowed_users (Phase 5 Theme C) ---

    def ensure_admin(self, username: str, display_name: str | None = None) -> None:
        """初期 admin を投入 (起動時に呼ぶ).

        既に存在する場合は何もしない (誤って role を上書きしないため)。
        """
        if not username:
            return
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO allowed_users "
                "(username, role, added_at, added_by, display_name) "
                "VALUES (?, 'admin', ?, 'system', ?)",
                (username, datetime.now(UTC).isoformat(), display_name),
            )

    def list_allowed_users(self) -> list[dict]:
        """全許可ユーザーを admin → member、各グループ内では追加日時順で返す."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT username, role, added_at, added_by, last_login, display_name "
                "FROM allowed_users "
                "ORDER BY CASE role WHEN 'admin' THEN 0 ELSE 1 END, added_at ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def is_user_allowed(self, username: str) -> bool:
        """username が allowed_users にいるか (大小区別あり)."""
        if not username:
            return False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM allowed_users WHERE username = ?", (username,)
            ).fetchone()
        return row is not None

    def get_user_role(self, username: str) -> str | None:
        """username の role ('admin' / 'member') を返す. 未登録なら None."""
        if not username:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT role FROM allowed_users WHERE username = ?", (username,)
            ).fetchone()
        return row["role"] if row else None

    def add_allowed_user(
        self,
        username: str,
        role: str,
        added_by: str,
        display_name: str | None = None,
    ) -> None:
        """新規ユーザーを追加. role は 'admin' or 'member'."""
        if role not in ("admin", "member"):
            raise ValueError(f"invalid role: {role}")
        if not username:
            raise ValueError("username is required")
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO allowed_users "
                "(username, role, added_at, added_by, display_name, last_login) "
                "VALUES (?, ?, ?, ?, ?, "
                "  COALESCE((SELECT last_login FROM allowed_users WHERE username = ?), NULL))",
                (
                    username,
                    role,
                    datetime.now(UTC).isoformat(),
                    added_by,
                    display_name,
                    username,
                ),
            )

    def update_user_role(self, username: str, new_role: str) -> None:
        """既存ユーザーの role を更新."""
        if new_role not in ("admin", "member"):
            raise ValueError(f"invalid role: {new_role}")
        with self._connect() as conn:
            conn.execute(
                "UPDATE allowed_users SET role = ? WHERE username = ?",
                (new_role, username),
            )

    def remove_allowed_user(self, username: str) -> None:
        """ユーザーを削除. 自分自身は削除できない仕様は呼び出し側で担保."""
        with self._connect() as conn:
            conn.execute("DELETE FROM allowed_users WHERE username = ?", (username,))

    def touch_last_login(self, username: str, display_name: str | None = None) -> None:
        """最終ログイン時刻を更新. display_name も差し替え (HF プロフィール変更追従)."""
        if not username:
            return
        with self._connect() as conn:
            conn.execute(
                "UPDATE allowed_users SET last_login = ?, "
                "display_name = COALESCE(?, display_name) "
                "WHERE username = ?",
                (datetime.now(UTC).isoformat(), display_name, username),
            )

    def user_run_count(self, username: str) -> int:
        """指定 username の累計 run 数を返す."""
        if not username:
            return 0
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM runs WHERE username = ?", (username,)
            ).fetchone()
        return int(row["c"] or 0) if row else 0


@contextmanager
def time_agent(run_logger: RunLogger, run_id: str, agent: str, model: str) -> Iterator[None]:
    """エージェント呼び出しを計測してログに記録する context manager.

    使い方:
        with time_agent(rlog, run_id, "researcher", "gemini-2.5-flash"):
            ... LLM 呼び出し ...
    """
    started = time.perf_counter()
    error: str | None = None
    try:
        yield
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
        raise
    finally:
        duration_ms = int((time.perf_counter() - started) * 1000)
        try:
            run_logger.log_agent_call(run_id, agent, model, duration_ms, error)
        except Exception as e:  # noqa: BLE001
            logger.warning("RunLogger: agent_call ログ失敗 (run_id=%s, agent=%s): %s",
                          run_id, agent, e)
