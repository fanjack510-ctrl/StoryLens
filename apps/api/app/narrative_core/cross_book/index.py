"""把存好的分析文档摊平成可检索的条目。

「我记得有本书用过一个『主角没报名却被选上』的桥段——是哪本？」这个问题今天在产品里
无法回答：分析结果按书分开存着，每本要自己点进去翻。跨书检索就是为它存在的。

两层条目，检索时的待遇不一样：

  · **写法层**（技法 / 爆点 / 配角功能 / 主要人物）——约每本二三十条。这是「怎么写的」，
    也是扫榜真正要问的东西。数量小，整层能一次装进模型上下文。
  · **逐章层**（章末钩子 / 章节功能 / 证据原文）——实测三本书就有一万两千条。
    关键词能查，但整层塞给模型既装不下也不划算。

分层不是为了做两个功能，是因为这两层能回答的问题不一样：写法层回答「这一招谁用过」，
逐章层回答「这句话在哪儿」。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Book
from app.narrative_core.stored_documents import all_documents

__all__ = ["CRAFT_KINDS", "KIND_LABELS", "SearchItem", "build_index"]

#: 写法层。这几种条目回答的是「怎么写的」。
CRAFT_KINDS = ("technique", "moment", "cast", "character")

KIND_LABELS = {
    "technique": "可复用技法",
    "moment": "高光片段",
    "cast": "配角功能",
    "character": "主要人物",
    "hook": "章末钩子",
    "chapter": "章节功能",
    "evidence": "原文证据",
}


@dataclass(frozen=True)
class SearchItem:
    """一条可检索的东西。

    `text` 是拿去匹配的全部内容；`title` 和 `detail` 是显示用的。分开是因为匹配要看到
    所有字段（一条技法的「可迁移到什么故事」经常正是用户搜的那句话），而显示只需要标题
    加一句说明——把用于匹配的长文本整段显示出来，十条结果就占满一屏。
    """

    book_id: int
    book_title: str
    kind: str
    title: str
    detail: str
    text: str
    #: 第几章。写法层的条目大多没有确切章号，那时是 None——**不要填 0**：
    #: 界面会把 0 显示成「第 0 章」，那是一个不存在的位置。
    chapter: int | None = None

    @property
    def is_craft(self) -> bool:
        return self.kind in CRAFT_KINDS


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _chapter_of(raw: Any) -> int | None:
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return None
    return n if n >= 1 else None


def _items_from_document(book_id: int, title: str, doc: dict[str, Any]) -> list[SearchItem]:
    out: list[SearchItem] = []

    def add(kind: str, item_title: str, detail: str, parts: list[str], chapter: Any = None) -> None:
        item_title = _clean(item_title)
        if not item_title:
            return
        out.append(
            SearchItem(
                book_id=book_id,
                book_title=title,
                kind=kind,
                title=item_title,
                detail=_clean(detail),
                # 匹配看全部字段。一条技法的「可迁移到什么故事」经常正是用户搜的那句话。
                text=" ".join(_clean(p) for p in parts if _clean(p)),
                chapter=_chapter_of(chapter),
            )
        )

    breakdown = doc.get("story_breakdown") or {}

    for t in breakdown.get("reusable_techniques") or []:
        add(
            "technique",
            t.get("name"),
            t.get("what_it_is"),
            [t.get("name"), t.get("what_it_is"), t.get("why_it_works"), t.get("transfers_to")],
        )

    for m in breakdown.get("standout_moments") or []:
        add(
            "moment",
            m.get("title"),
            m.get("why_it_lands") or m.get("quote"),
            [m.get("title"), m.get("quote"), m.get("why_it_lands")],
            m.get("chapter"),
        )

    for c in breakdown.get("supporting_cast") or []:
        add("cast", c.get("name"), c.get("function"), [c.get("name"), c.get("function")])

    for c in (doc.get("characters") or {}).get("major_characters") or []:
        add(
            "character",
            c.get("name"),
            c.get("role") or c.get("description"),
            [c.get("name"), c.get("role"), c.get("description")],
        )

    for h in breakdown.get("chapter_hooks") or []:
        add("hook", h.get("question"), "", [h.get("question")], h.get("chapter"))

    for f in (doc.get("chapters") or {}).get("functions") or []:
        add(
            "chapter",
            f.get("title") or f.get("function"),
            f.get("summary") or f.get("function"),
            [f.get("title"), f.get("function"), f.get("summary")],
            f.get("chapter") or f.get("chapter_index"),
        )

    for ref in (doc.get("evidence_index") or {}).values():
        if not isinstance(ref, dict):
            continue
        add(
            "evidence",
            ref.get("quote_or_excerpt"),
            ref.get("reason"),
            [ref.get("quote_or_excerpt"), ref.get("reason")],
            ref.get("chapter_index"),
        )

    return out


def build_index(session: Session, book_ids: list[int] | None = None) -> list[SearchItem]:
    """所有（或指定几本）分析过的书的可检索条目。

    `book_ids=None` 表示整个书库——跨书检索的默认问题是「有没有哪本书……」，
    而不是「这几本书里有没有……」。
    """
    stmt = select(Book)
    if book_ids is not None:
        stmt = stmt.where(Book.id.in_([int(b) for b in book_ids]))
    items: list[SearchItem] = []
    for book in session.scalars(stmt.order_by(Book.id)):
        # 一本书的几份文档取**并集**，不是二选一。整本那次留下了逐章的钩子和证据，
        # 只拆开篇那次留下了技法——挑其中一份，另一份里的东西就搜不到了，
        # 而用户不会知道自己搜不到它。实测《余罪》按覆盖挑中的那份技法为零，
        # 于是「用一句反常识的话立住人物」这条从检索里整个消失。
        seen: set[tuple[str, str]] = set()
        for doc in all_documents(session, int(book.id)):
            for item in _items_from_document(int(book.id), str(book.title or ""), doc):
                # 重跑过的书会有同名条目。按「种类＋标题」去重：同名的技法就是同一条技法。
                fingerprint = (item.kind, item.title)
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                items.append(item)
    return items
