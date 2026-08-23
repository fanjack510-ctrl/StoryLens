"""关键词检索。确定、即时、可核对——所以免费。

排序不用 TF-IDF 之类的东西：语料是几千条短文本，不是网页。真正决定「哪条更该排前面」的
是三件很朴素的事——命中在标题里比在正文里重要、命中的词越多越重要、写法层比逐章层重要。
第三条不是偏见：搜「反转」的人，多半想看的是「哪本书用过反转这个手法」，
而不是第 837 章某句话里出现了这两个字。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.narrative_core.cross_book.index import KIND_LABELS, SearchItem

__all__ = ["SearchHit", "keyword_search", "split_query"]

#: 一次最多回多少条。上限存在时必须说出来——见 `keyword_search` 的返回值。
DEFAULT_LIMIT = 50

#: 写法层排在前面。搜「反转」的人多半在找手法，不是在找某一章的原文。
_KIND_WEIGHT = {
    "technique": 3.0,
    "moment": 2.5,
    "cast": 2.0,
    "character": 2.0,
    "chapter": 1.2,
    "hook": 1.0,
    "evidence": 0.8,
}


@dataclass(frozen=True)
class SearchHit:
    item: SearchItem
    score: float
    #: 命中的词，原样回给界面去高亮。由后端给出而不是让客户端自己再切一遍词——
    #: 切法不一致时，高亮的位置会和排序的依据对不上。
    matched: list[str]


def split_query(query: str) -> list[str]:
    """把查询切成词。

    中文不分词——按连续的中文串整体匹配。给几千条短文本上一个分词器，
    换来的主要是「反转」被切成「反」和「转」之后的一堆噪音命中。
    """
    raw = (query or "").strip()
    if not raw:
        return []
    parts = re.findall(r"[一-鿿]+|[A-Za-z0-9_]+", raw)
    return [p for p in parts if len(p) >= 1]


def _snippet(text: str, terms: list[str], width: int = 90) -> str:
    """截出命中附近的一小段。

    从头截 90 字是最没用的截法——命中往往在中间，用户看到的是一段和他搜的东西
    毫无关系的开头。
    """
    if not text:
        return ""
    lowered = text.lower()
    pos = -1
    for t in terms:
        found = lowered.find(t.lower())
        if found >= 0 and (pos < 0 or found < pos):
            pos = found
    if pos < 0:
        return text[:width]
    start = max(0, pos - width // 3)
    end = min(len(text), start + width)
    return ("…" if start > 0 else "") + text[start:end] + ("…" if end < len(text) else "")


def keyword_search(
    items: list[SearchItem],
    query: str,
    *,
    kinds: list[str] | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """在条目里找关键词。

    返回里带 `total` 和 `truncated`：截断了就要说。一份悄悄截到 50 条的结果，
    读起来和「一共就这么多」完全一样——而这两件事该做的下一步正好相反。
    """
    terms = split_query(query)
    if not terms:
        return {
            "query": query,
            "hits": [],
            "total": 0,
            "truncated": False,
            "searched_items": len(items),
            "message": "输入要找的词。",
        }

    wanted = set(kinds) if kinds else None
    scored: list[SearchHit] = []
    for item in items:
        if wanted and item.kind not in wanted:
            continue
        haystack = item.text.lower()
        title = item.title.lower()
        matched = [t for t in terms if t.lower() in haystack]
        if not matched:
            continue
        score = float(len(matched)) * _KIND_WEIGHT.get(item.kind, 1.0)
        # 命中在标题里，比埋在正文里更可能是用户要的那条。
        score += sum(2.0 for t in matched if t.lower() in title)
        # 所有词都命中的，排在只命中一部分的前面。
        if len(matched) == len(terms):
            score += 3.0
        scored.append(SearchHit(item=item, score=score, matched=matched))

    scored.sort(key=lambda h: (-h.score, h.item.book_id, h.item.title))
    total = len(scored)
    shown = scored[: max(1, int(limit))]
    return {
        "query": query,
        "hits": [
            {
                "book_id": h.item.book_id,
                "book_title": h.item.book_title,
                "kind": h.item.kind,
                "kind_label": KIND_LABELS.get(h.item.kind, h.item.kind),
                "title": h.item.title,
                "snippet": _snippet(h.item.text, h.matched),
                "chapter": h.item.chapter,
                "matched": h.matched,
                "score": round(h.score, 2),
            }
            for h in shown
        ],
        "total": total,
        "truncated": total > len(shown),
        "searched_items": len(items),
        "message": "",
    }
