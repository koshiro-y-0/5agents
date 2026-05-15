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
    error           TEXT
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
"""


@dataclass
class RunStats:
    """1 run の集計値 (UI 表示用)."""

    run_id: str
    question: str
    duration_ms: int | None
    final_verdict: str | None
    retry_count: int
    agent_durations: dict[str, int]  # agent name → ms


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

    # --- runs ---

    def start_run(self, question: str) -> str:
        run_id = str(uuid.uuid4())
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO runs (id, question, started_at) VALUES (?, ?, ?)",
                (run_id, question, datetime.now(UTC).isoformat()),
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
        """1 run の集計を返す (UI 表示用)."""
        with self._connect() as conn:
            run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if run is None:
                return None
            calls = conn.execute(
                "SELECT agent, duration_ms FROM agent_calls WHERE run_id = ?", (run_id,)
            ).fetchall()
        return RunStats(
            run_id=run["id"],
            question=run["question"],
            duration_ms=run["duration_ms"],
            final_verdict=run["final_verdict"],
            retry_count=run["retry_count"] or 0,
            agent_durations={c["agent"]: c["duration_ms"] or 0 for c in calls},
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
