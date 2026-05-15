"""定期実行スクリプト — ウォッチリストの全質問を順次処理して通知.

実行例:
    uv run python -m src.scheduler
    uv run python -m src.scheduler --watchlist custom_list.txt
    uv run python -m src.scheduler --dry-run     # 通知せず標準出力に表示

cron 例 (毎朝 9:00 に実行):
    0 9 * * * cd ~/Desktop/5agents && /opt/homebrew/bin/uv run python -m src.scheduler >> logs/scheduler.log 2>&1

launchd (macOS) 用 plist のサンプルは docs/DEPLOYMENT.md を参照。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.agents.orchestrator import answer
from src.config import get_settings
from src.notifications.notifier import build_default_notifier

logger = logging.getLogger(__name__)


def load_watchlist(path: Path) -> list[str]:
    """ウォッチリストファイルを読み込み (コメント・空行を除外)."""
    if not path.exists():
        logger.error("ウォッチリストが見つかりません: %s", path)
        return []
    questions: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        questions.append(stripped)
    return questions


def _format_short_report(question: str, state: dict) -> str:  # type: ignore[type-arg]
    """通知用の短いレポート (1000 文字以内目安)."""
    final_answer = state.get("final_answer", "(回答なし)")
    retry = state.get("retry_count", 0)
    fact_verdict = state.get("fact_check", {}).get("verdict", "?")
    # final_answer の冒頭 600 文字を抜粋
    excerpt = final_answer[:600] + ("..." if len(final_answer) > 600 else "")
    return (
        f"質問: {question}\n"
        f"---\n"
        f"{excerpt}\n"
        f"---\n"
        f"verdict={fact_verdict}, retry={retry}"
    )


def run_scheduled(watchlist_path: Path | None = None, dry_run: bool = False) -> int:
    """ウォッチリストの全質問を実行 → 各回答を通知.

    Returns:
        処理した質問数。
    """
    settings = get_settings()
    path = watchlist_path or settings.watchlist_file
    questions = load_watchlist(path)
    if not questions:
        logger.warning("ウォッチリストが空です: %s", path)
        return 0

    notifier = build_default_notifier()
    if notifier.is_empty and not dry_run:
        logger.warning("通知チャネル未設定。--dry-run でない実行は意味が薄いため、stdout にも出力します")

    logger.info("定期実行開始: %d 件", len(questions))
    for i, q in enumerate(questions, start=1):
        logger.info("[%d/%d] %s", i, len(questions), q[:50])
        try:
            state = answer(q)
        except Exception as e:  # noqa: BLE001 — 1 件失敗で全体を止めない
            logger.exception("質問 %d 失敗: %s", i, e)
            err_body = f"質問: {q}\nエラー: {type(e).__name__}: {e}"
            if not dry_run:
                notifier.send(f"[5agents] エラー ({i}/{len(questions)})", err_body)
            else:
                print(f"=== [DRY-RUN] エラー ({i}/{len(questions)}) ===")
                print(err_body)
            continue

        report = _format_short_report(q, dict(state))
        title = f"[5agents] {i}/{len(questions)}"
        if dry_run:
            print(f"=== [DRY-RUN] {title} ===")
            print(report)
            print()
        else:
            results = notifier.send(title, report)
            logger.info("通知結果: %s", results)

    logger.info("定期実行完了: %d 件", len(questions))
    return len(questions)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="5agents 定期実行")
    parser.add_argument("--watchlist", type=Path, default=None, help="ウォッチリストファイル")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="通知を送らず標準出力に表示する",
    )
    args = parser.parse_args()
    count = run_scheduled(watchlist_path=args.watchlist, dry_run=args.dry_run)
    return 0 if count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
