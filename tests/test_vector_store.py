"""QAMemory (ChromaDB ラッパー) のテスト.

一時ディレクトリを使い、ネットワーク不要。
ChromaDB のデフォルト embedding (ONNX runtime) が動くので初回ロードに数秒かかる。
"""

from __future__ import annotations

import pytest

from src.memory.vector_store import (
    MemoryRecord,
    QAMemory,
    format_for_prompt,
)


@pytest.fixture
def memory(tmp_path):  # type: ignore[no-untyped-def]
    """テスト用の一時 QAMemory を提供."""
    return QAMemory(persist_dir=str(tmp_path / "chroma"))


def test_empty_memory_count_is_zero(memory: QAMemory) -> None:
    assert memory.count() == 0


def test_empty_search_returns_empty_list(memory: QAMemory) -> None:
    """空コレクションで search してもエラーにならず空リストが返る."""
    assert memory.search("any query") == []


def test_add_and_search_round_trip(memory: QAMemory) -> None:
    """保存 → 検索で同じ質問が引ける."""
    memory.add(question="トヨタの業績は?", answer="トヨタの業績は好調です。")
    memory.add(question="今日の天気は?", answer="晴れです。")

    results = memory.search("トヨタの業績", top_k=1)
    assert len(results) == 1
    assert "トヨタ" in results[0].question
    assert "好調" in results[0].answer


def test_search_top_k_respects_collection_size(memory: QAMemory) -> None:
    """top_k がコレクション件数を超えてもクラッシュしない."""
    memory.add("Q1", "A1")
    results = memory.search("query", top_k=10)
    assert len(results) == 1


def test_clear_removes_all_records(memory: QAMemory) -> None:
    memory.add("Q1", "A1")
    memory.add("Q2", "A2")
    assert memory.count() == 2
    memory.clear()
    assert memory.count() == 0


def test_add_returns_unique_ids(memory: QAMemory) -> None:
    id1 = memory.add("Q1", "A1")
    id2 = memory.add("Q1", "A1")  # 同じ内容でも別 ID
    assert id1 != id2


def test_format_for_prompt_empty() -> None:
    assert format_for_prompt([]) == "(過去の関連 Q&A なし)"


def test_format_for_prompt_includes_qa() -> None:
    records = [
        MemoryRecord(
            id="abc", question="Qテスト", answer="Aテスト", timestamp="2026-05-15T10:00:00+00:00"
        )
    ]
    text = format_for_prompt(records)
    assert "Qテスト" in text
    assert "Aテスト" in text
    assert "2026-05-15" in text


def test_long_answer_is_truncated() -> None:
    """answer が 400 文字を超えると抜粋表示."""
    long_answer = "あ" * 600
    records = [
        MemoryRecord(id="x", question="Q", answer=long_answer, timestamp="2026-01-01T00:00:00+00:00")
    ]
    text = format_for_prompt(records)
    assert "あ" * 400 in text
    assert "あ" * 500 not in text
