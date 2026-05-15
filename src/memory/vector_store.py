"""ChromaDB を用いた Q&A 履歴の永続化と類似検索.

設計方針:
- collection 名は `qa_history` 固定 (Phase 3 ではシングル collection)
- 永続化先は settings.chroma_persist_dir
- ChromaDB のデフォルト embedding (all-MiniLM-L6-v2 相当) を使用し、外部 API を呼ばない
- メタデータには必須で `timestamp` と `question` を含める
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.config import get_settings

if TYPE_CHECKING:
    from chromadb.api.models.Collection import Collection

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "qa_history"


@dataclass
class MemoryRecord:
    """ベクトル DB に保存される 1 件の Q&A 記録."""

    id: str
    question: str
    answer: str
    timestamp: str  # ISO 8601


class QAMemory:
    """過去の Q&A をベクトル化・検索するメモリ."""

    def __init__(self, persist_dir: str | None = None) -> None:
        settings = get_settings()
        path = persist_dir or str(settings.chroma_persist_dir)

        # PersistentClient: ローカルファイルに永続化
        # anonymized_telemetry=False で起動時の警告を抑制
        self._client = chromadb.PersistentClient(
            path=path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection: Collection = self._client.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"description": "5agents の Q&A 履歴"},
        )

    def add(self, question: str, answer: str) -> str:
        """Q&A を保存."""
        record_id = str(uuid.uuid4())
        timestamp = datetime.now(UTC).isoformat()
        # ChromaDB の document は検索対象テキスト、metadata はフィルタ・付随情報
        self._collection.add(
            ids=[record_id],
            documents=[question],  # 検索キーは「質問」テキスト
            metadatas=[{"answer": answer, "timestamp": timestamp, "question": question}],
        )
        logger.info("QAMemory: 保存 id=%s", record_id)
        return record_id

    def search(self, query: str, top_k: int = 3) -> list[MemoryRecord]:
        """類似する過去の Q&A を取得 (新しい順ではなく、類似度順)."""
        # 空コレクションでは query が失敗するため事前チェック
        if self._collection.count() == 0:
            return []

        # top_k が collection サイズを超えるとエラーになるためクランプ
        n = min(top_k, self._collection.count())
        result = self._collection.query(query_texts=[query], n_results=n)

        ids: list[str] = (result.get("ids") or [[]])[0]
        metadatas: list[dict] = (result.get("metadatas") or [[]])[0]

        records: list[MemoryRecord] = []
        for rid, meta in zip(ids, metadatas, strict=False):
            records.append(
                MemoryRecord(
                    id=rid,
                    question=str(meta.get("question", "")),
                    answer=str(meta.get("answer", "")),
                    timestamp=str(meta.get("timestamp", "")),
                )
            )
        return records

    def count(self) -> int:
        """保存件数を返す."""
        return self._collection.count()

    def clear(self) -> None:
        """全件削除 (テスト・リセット用)."""
        self._client.delete_collection(_COLLECTION_NAME)
        self._collection = self._client.get_or_create_collection(name=_COLLECTION_NAME)


def format_for_prompt(records: list[MemoryRecord]) -> str:
    """過去の Q&A 履歴を LLM プロンプト用に整形."""
    if not records:
        return "(過去の関連 Q&A なし)"
    lines: list[str] = []
    for i, r in enumerate(records, start=1):
        lines.append(f"## 過去の質問 {i} ({r.timestamp[:10]})")
        lines.append(f"Q: {r.question}")
        # answer は長すぎる可能性があるため 400 文字でカット
        lines.append(f"A (抜粋): {r.answer[:400]}")
        lines.append("")
    return "\n".join(lines)
