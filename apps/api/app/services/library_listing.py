"""书库列表要显示的东西。

原来的列表只回 Book 行本身：书名、文件名、格式、导入日期。于是最要紧的两件事都看不出来——
**这是什么书**，和**分析到哪一步了**。回到书库最常见的问题恰恰是这两个：「我那本手册跑完
没有」「这本是我要拆的还是要读懂的」。

字段全在后端算好，客户端照着渲染（INV-P4）。状态文案也在这里定，因为「已评测 / 读懂·进行中 /
未分析」这句话该怎么说，取决于引擎与运行状态之间的对应关系，那是后端的知识。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Book, Chapter
from app.narrative_core.material_kind import REFERENCE, book_material_kind

__all__ = ["build_library_listing"]

_READING_LABEL = {
    "diagnostic": "评测",
    "story_breakdown": "拆文",
    "comprehend": "读懂",
}


def _analysis_state(session: Session, book_id: int) -> tuple[str, str]:
    """(状态文案, 状态类别)。类别给界面上色用，文案原样显示。"""
    from app.narrative_core.contracts.whole_book_contract_v1 import WholeBookRunStatus
    from app.narrative_core.services.whole_book_free_product_v1_service import (
        list_runs_for_book,
        reading_of_run,
    )

    running: list[str] = []
    done: list[str] = []
    for run in list_runs_for_book(session, book_id):
        label = _READING_LABEL.get(reading_of_run(run), "")
        if not label:
            continue
        if run.status == WholeBookRunStatus.running.value:
            if label not in running:
                running.append(label)
        elif run.status == WholeBookRunStatus.completed.value:
            if label not in done:
                done.append(label)
    if running:
        return f"{running[0]} · 正在进行", "running"
    if done:
        return "已" + "、已".join(done), "done"
    return "未分析", "idle"


def _last_activity(session: Session, book_id: int) -> str | None:
    """这本书最后一次被分析是什么时候。

    首页要按「最近动过」排，而 `Book` 上只有导入时间——一本三个月前导入、昨天才拆完的书，
    按导入时间排会沉到最底下，而它恰恰是用户最可能想接着看的那一本。

    取运行的完成 / 开始 / 创建时间里最新的那个；一次都没跑过就返回 None，
    调用方退回导入时间。
    """
    from app.db.models import WholeBookRun

    row = session.execute(
        select(
            func.max(
                func.coalesce(
                    WholeBookRun.completed_at, WholeBookRun.started_at, WholeBookRun.created_at
                )
            )
        ).where(WholeBookRun.book_id == int(book_id))
    ).scalar()
    return row.isoformat() if hasattr(row, "isoformat") else (str(row) if row else None)


def build_library_listing(
    session: Session, *, book_ids: list[int] | None = None
) -> list[dict[str, Any]]:
    """书库列表，或其中指定的几本。

    书单里的书要和书库里的书长得一模一样——同样的类型标、同样的分析状态。走两套渲染，
    两边迟早会不一致，而「这本跑完没有」在书单里问得只会更频繁：书单存在的理由就是
    一次看一批。所以书单不另建一套行，只是把范围收窄，并**按传进来的顺序**返回——
    扫榜排出来的次序本身是结论的一部分。
    """
    counts = dict(
        session.execute(
            select(Chapter.book_id, func.count(Chapter.id)).group_by(Chapter.book_id)
        ).all()
    )
    if book_ids is None:
        books = list(session.scalars(select(Book).order_by(Book.id.desc())))
    else:
        by_id = {
            int(b.id): b for b in session.scalars(select(Book).where(Book.id.in_(book_ids)))
        }
        # 找不到的 id 直接跳过，不塞占位行：一本被删掉的书应该从书单里消失，
        # 而不是变成一张点不开的卡片。
        books = [by_id[i] for i in book_ids if i in by_id]
    items: list[dict[str, Any]] = []
    for book in books:
        kind, confirmed = book_material_kind(session, int(book.id))
        form = str(book.analysis_form or "")
        # 工具书没有长短篇之分——读懂的分析单元是节。给它一个类型标就够了。
        if kind == REFERENCE:
            kind_label = "工具书"
        else:
            kind_label = "小说 · 短篇" if form == "short" else "小说 · 长篇"
        state_label, state = _analysis_state(session, int(book.id))
        title = str(book.title or "")
        source = str(book.source_file_name or "")
        items.append(
            {
                "id": int(book.id),
                "title": title,
                # 书名和文件名同名时不重复说一遍——那是同一句话讲两次。
                "source_file_name": "" if _same_work(title, source) else source,
                "format": source.rsplit(".", 1)[-1].upper() if "." in source else "",
                "created_at": book.created_at.isoformat() if book.created_at else None,
                "material_kind": kind,
                "material_kind_confirmed": confirmed,
                "kind_label": kind_label,
                "chapter_count": int(counts.get(int(book.id), 0) or 0),
                "analysis_state": state,
                "analysis_state_label": state_label,
                # 最后一次分析的时间。没跑过就退回导入时间——首页那一列不能空着，
                # 空白会被读成「不知道」，而我们其实知道。
                "last_activity_at": _last_activity(session, int(book.id))
                or (book.created_at.isoformat() if book.created_at else None),
            }
        )
    return items


def _same_work(title: str, source: str) -> bool:
    stem = source.rsplit(".", 1)[0] if "." in source else source
    return stem.strip() == title.strip()
