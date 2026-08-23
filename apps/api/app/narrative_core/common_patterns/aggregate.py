"""能数的先数清楚。

共性视图最容易变成一段「看起来很有道理的废话」——「这些书都很会写钩子」。防止这件事的办法
不是把话说得更谨慎，是**先把可以核对的数字摆出来**，再让模型在这些数字上面说话。

所以这一层不调用模型：它读已经存好的分析文档，把每本书的事实抽出来。这些数字可以逐条回到
原书核对，也可以在没有 Pro 授权时照样看——数出来的东西不该收费。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Book
from app.narrative_core.stored_documents import best_document, by_techniques
from app.narrative_core.material_kind import REFERENCE, book_material_kind

__all__ = ["BookFacts", "Technique", "collect_facts", "count_genres"]

@dataclass(frozen=True)
class Technique:
    """一本书里的一条可复用技法。"""

    name: str
    what_it_is: str
    why_it_works: str
    transfers_to: str


@dataclass
class BookFacts:
    """一本书在这组里贡献的事实。

    每一项都能回到原书核对，没有一项是推断出来的。
    """

    book_id: int
    title: str
    #: 这次分析读了多少章 / 全书多少章。只拆了开篇的书，结论只覆盖开篇——
    #: 这件事必须跟着这本书一路走到共性结论里，否则会拿五章的观察冒充整本的规律。
    chapters_analysed: int = 0
    chapters_total: int = 0
    scope_kind: str = "full"
    primary_genre: str = ""
    narrative_drivers: list[str] = field(default_factory=list)
    techniques: list[Technique] = field(default_factory=list)
    #: 章末钩子数。除以读过的章数才有意义——1245 个钩子听起来很多，
    #: 但那本书有 1299 章，意思是「几乎每章都留钩子」，而不是「钩子特别密」。
    hook_count: int = 0
    standout_moment_count: int = 0
    beat_count: int = 0
    #: 这本书为什么没能进入共性比较。空字符串＝进得来。
    excluded_reason: str = ""

    @property
    def usable(self) -> bool:
        return not self.excluded_reason

    @property
    def hooks_per_chapter(self) -> float | None:
        if not self.chapters_analysed:
            return None
        return round(self.hook_count / self.chapters_analysed, 2)


def collect_facts(session: Session, book_ids: list[int]) -> list[BookFacts]:
    """按传进来的顺序，逐本收集事实。

    读不到文档、或者文档里没有拆文的书**不会被悄悄跳过**——它们带着理由留在结果里。
    一本书从共性比较里消失而不说明原因，用户会以为自己选错了书；而真正的原因通常是
    「这本还没拆过文」，那是一句他能直接照做的话。
    """
    books = {
        int(b.id): b
        for b in session.scalars(select(Book).where(Book.id.in_([int(i) for i in book_ids])))
    }
    out: list[BookFacts] = []
    for book_id in book_ids:
        book = books.get(int(book_id))
        if book is None:
            out.append(
                BookFacts(book_id=int(book_id), title="", excluded_reason="这本书已经不在书库里")
            )
            continue
        title = str(book.title or "")
        # 共性视图比的是「怎么写的」，所以有技法的那份优先——覆盖最广的那份可能一条技法都没有。
        doc = best_document(session, int(book_id), key=by_techniques)
        if doc is None:
            # 工具书跑的是「读懂」，产出的是主张 / 依据 / 做法，不是小说的写法。
            # 对一个刚刚跑完读懂的人说「还没有分析过」，他会去重跑一遍已经跑过的东西。
            kind, _ = book_material_kind(session, int(book_id))
            out.append(
                BookFacts(
                    book_id=int(book_id),
                    title=title,
                    excluded_reason=(
                        "这是工具书——共性视图比的是小说怎么写，读懂的产出不在这个维度上"
                        if kind == REFERENCE
                        else "还没有分析过——先跑一次拆解"
                    ),
                )
            )
            continue

        meta = doc.get("analysis_metadata") or {}
        cov = meta.get("coverage") or {}
        profile = doc.get("type_profile") or {}
        breakdown = doc.get("story_breakdown") or {}
        techniques = [
            Technique(
                name=str(t.get("name") or "").strip(),
                what_it_is=str(t.get("what_it_is") or "").strip(),
                why_it_works=str(t.get("why_it_works") or "").strip(),
                transfers_to=str(t.get("transfers_to") or "").strip(),
            )
            for t in (breakdown.get("reusable_techniques") or [])
            if str(t.get("name") or "").strip()
        ]
        chapters_total = int(cov.get("chapters_total") or 0) or int(
            (doc.get("book_metadata") or {}).get("chapter_count") or 0
        )
        facts = BookFacts(
            book_id=int(book_id),
            title=title,
            chapters_analysed=int(cov.get("chapters_analysed") or 0),
            chapters_total=chapters_total,
            scope_kind=str(cov.get("scope_kind") or "full"),
            primary_genre=str(profile.get("primary_genre") or ""),
            narrative_drivers=[str(d) for d in (profile.get("narrative_drivers") or [])],
            techniques=techniques,
            hook_count=len(breakdown.get("chapter_hooks") or []),
            standout_moment_count=len(breakdown.get("standout_moments") or []),
            beat_count=len(breakdown.get("four_beats") or []),
        )
        if not techniques:
            # 评测（诊断）跑出来的文档没有拆文那一节。共性视图比的是「怎么写的」，
            # 那些东西只有拆文才产出——所以说清楚要跑哪一种，而不是笼统说「数据不足」。
            facts.excluded_reason = "这本书跑的是评测，没有拆文——共性比较要用拆文的结果"
        out.append(facts)
    return out


def count_genres(facts: list[BookFacts]) -> list[tuple[str, int]]:
    """类型分布，多的在前。只数进得来的那些书。"""
    counter = Counter(f.primary_genre for f in facts if f.usable and f.primary_genre)
    return counter.most_common()
