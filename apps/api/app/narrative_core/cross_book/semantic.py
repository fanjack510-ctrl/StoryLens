"""按意思找。

关键词检索答不了这种问题：「有没有哪本书让主角在开场就失去某样东西？」——「失去」两个字
可能一次都没出现，而《余罪》的「用未报名却入选制造悬念」正是那一类。这是这一层存在的理由。

只覆盖**写法层**（技法 / 高光片段 / 配角功能 / 主要人物）。逐章层实测上万条，既装不进
一次调用，也不是这个问题该问的地方——「这句话在哪儿」是关键词检索的活。这个边界要说给
用户听，不能让他以为搜过了全部。

和共性视图同一条纪律：模型只能引用**给它编号的条目**，编号不在范围内的一律丢掉。
它没法编出一个能通过校验的编号。
"""

from __future__ import annotations

import json
from typing import Any

from app.narrative_core.cross_book.index import KIND_LABELS, SearchItem

__all__ = ["MAX_CANDIDATES", "build_prompt", "parse_and_verify"]

#: 一次最多把多少条写法层条目交给模型。超过就截断——并且**必须说出来**。
#: 实测三本书 140 条、约 4 千 token；一百本书才会碰到这个上限。
MAX_CANDIDATES = 600


def build_prompt(query: str, candidates: list[SearchItem]) -> str:
    """给模型编号的条目和用户的问题。

    条目按编号列出，模型只需要回编号——它不用重复抄一遍标题，也就没有抄错的机会。
    """
    lines = []
    for i, item in enumerate(candidates, start=1):
        label = KIND_LABELS.get(item.kind, item.kind)
        lines.append(f"[{i}] （{label}·《{item.book_title}》）{item.title}：{item.text[:220]}")
    body = "\n".join(lines)

    return f"""下面是若干本小说的「写法」条目，每条前面有编号。

{body}

用户想找的是：{query}

挑出真正符合的条目。要求：

1. 只回编号，编号必须在 1 到 {len(candidates)} 之间。
2. **宁可少给，不要凑数。** 一条都不符合就回空列表——「找不到」是一个有用的答案，
   而一堆勉强沾边的结果会让用户以为自己问错了问题。
3. 每条给一句 why：说清楚它为什么符合**这个**要求，而不是复述这条本身是什么。
4. 按符合程度排序，最贴的放前面。

只输出 JSON，逐字按这个形状——键名不要改：

{{"matches": [{{"n": 1, "why": "它为什么符合这个要求"}}]}}"""


def parse_and_verify(raw: Any, candidates: list[SearchItem]) -> dict[str, Any]:
    """核对编号。越界的、重复的、编出来的，一律丢掉。"""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {"matches": [], "dropped": [], "parse_failed": True}
    if not isinstance(raw, dict):
        return {"matches": [], "dropped": [], "parse_failed": True}

    matches: list[dict[str, Any]] = []
    dropped: list[str] = []
    seen: set[int] = set()
    for entry in raw.get("matches") or []:
        if not isinstance(entry, dict):
            continue
        try:
            n = int(entry.get("n"))
        except (TypeError, ValueError):
            dropped.append("编号不是数字")
            continue
        if not (1 <= n <= len(candidates)):
            dropped.append(f"编号 {n} 不在范围内")
            continue
        if n in seen:
            # 同一条给两次不是两个结果。放过去的话，界面上会出现两张一模一样的卡片。
            dropped.append(f"编号 {n} 重复")
            continue
        seen.add(n)
        item = candidates[n - 1]
        matches.append(
            {
                "book_id": item.book_id,
                "book_title": item.book_title,
                "kind": item.kind,
                "kind_label": KIND_LABELS.get(item.kind, item.kind),
                "title": item.title,
                "detail": item.detail,
                "chapter": item.chapter,
                "why": str(entry.get("why") or "").strip(),
            }
        )
    return {"matches": matches, "dropped": dropped, "parse_failed": False}
