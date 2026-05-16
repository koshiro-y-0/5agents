"""5agents の Markdown 回答を LINE 用の複数メッセージに分割する.

LINE Messaging API のテキストメッセージは 5000 文字制限。
Finalizer は ## 結論 → ## 根拠 → ## リスク・反論 → ## 出典 の順で書くので、
それを 2 通に分割して送る。

設計:
- メッセージ 1: 結論 + 根拠
- メッセージ 2: リスク・反論 + 出典
- どちらも 5000 字を超える場合は冒頭 4900 字 + 末尾に「(続きは詳細から)」

Markdown のセクション抽出は正規表現で行う。Finalizer の system prompt で
セクション順序を保証しているので、想定通りの構造になっているはず。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# LINE テキストメッセージの最大長
LINE_MAX_TEXT_LENGTH = 5000
# 安全マージンを取った切り詰め長さ
_SAFE_TRUNCATE_LENGTH = 4900
_TRUNCATE_SUFFIX = "\n\n(...続きは「詳細を見る」から)"


@dataclass(frozen=True)
class ParsedSections:
    """Finalizer の Markdown 回答から抽出したセクション."""

    conclusion: str   # ## 結論
    evidence: str     # ## 根拠
    risks: str        # ## リスク・反論
    sources: str      # ## 出典
    raw: str          # 元の Markdown 全文


def parse_sections(markdown: str) -> ParsedSections:
    """Markdown 文字列から 4 セクションを抽出する.

    対応する見出しパターン: `## 結論` / `## 根拠` / `## リスク・反論` / `## リスク` / `## 出典`
    マッチしないセクションは空文字を返す (formatter 側でフォールバック)。
    """
    sections = _split_by_h2(markdown)

    def _pick(*keywords: str) -> str:
        """指定のキーワードを含む見出しを持つセクションを返す."""
        for heading, body in sections.items():
            normalized = heading.replace(" ", "").lower()
            for kw in keywords:
                if kw.replace(" ", "").lower() in normalized:
                    return body.strip()
        return ""

    return ParsedSections(
        conclusion=_pick("結論"),
        evidence=_pick("根拠"),
        risks=_pick("リスク・反論", "リスク", "反論"),
        sources=_pick("出典"),
        raw=markdown,
    )


def _split_by_h2(markdown: str) -> dict[str, str]:
    """Markdown を ## H2 見出しで区切って {見出し: 本文} の辞書を返す."""
    # H2 見出し: 行頭の `## ` で始まる行
    parts = re.split(r"^##\s+", markdown, flags=re.MULTILINE)
    result: dict[str, str] = {}
    # parts[0] は最初の H2 より前 (前文 or 空)
    for chunk in parts[1:]:
        lines = chunk.split("\n", 1)
        heading = lines[0].strip()
        body = lines[1] if len(lines) > 1 else ""
        result[heading] = body
    return result


def _truncate(text: str) -> str:
    """5000 字を超える場合は切り詰めて末尾に「続きは詳細から」を付ける."""
    if len(text) <= LINE_MAX_TEXT_LENGTH:
        return text
    return text[:_SAFE_TRUNCATE_LENGTH] + _TRUNCATE_SUFFIX


def split_for_line(markdown: str) -> tuple[str, str]:
    """5agents の Markdown 回答を LINE 用 2 通に分割.

    Returns:
        (msg1, msg2):
            msg1: 結論 + 根拠
            msg2: リスク・反論 + 出典
        どちらも 5000 字以内に切り詰め済み。
        セクション抽出に失敗した場合は、Markdown を半分で分割してフォールバック。
    """
    sections = parse_sections(markdown)

    # 主要セクションが抽出できなかった場合のフォールバック
    if not sections.conclusion and not sections.evidence:
        return _fallback_split(markdown)

    msg1_parts = []
    if sections.conclusion:
        msg1_parts.append(f"## 結論\n{sections.conclusion}")
    if sections.evidence:
        msg1_parts.append(f"## 根拠\n{sections.evidence}")
    msg1 = "\n\n".join(msg1_parts) if msg1_parts else "(結論・根拠の抽出に失敗)"

    msg2_parts = []
    if sections.risks:
        msg2_parts.append(f"## リスク・反論\n{sections.risks}")
    if sections.sources:
        msg2_parts.append(f"## 出典\n{sections.sources}")
    msg2 = "\n\n".join(msg2_parts) if msg2_parts else "(リスク・出典セクションは出力なし)"

    return _truncate(msg1), _truncate(msg2)


def _fallback_split(markdown: str) -> tuple[str, str]:
    """セクション抽出に失敗した場合、純粋に文字数で前半・後半に分ける."""
    mid = len(markdown) // 2
    # なるべく段落の切れ目で分けるため、mid の前後で最も近い "\n\n" を探す
    nearest = markdown.rfind("\n\n", 0, mid + 200)
    if nearest > mid - 500:
        mid = nearest
    return _truncate(markdown[:mid]), _truncate(markdown[mid:].lstrip())


def build_detail_url(streamlit_base_url: str, run_id: str | None) -> str:
    """Streamlit の詳細表示用 URL を組み立てる.

    run_id があれば ?run_id=xxx を付与 (Streamlit 側の対応は別タスク)。
    """
    base = streamlit_base_url.rstrip("/")
    if run_id:
        return f"{base}/?run_id={run_id}"
    return base
