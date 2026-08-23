"""书单：一组可以被反复回到的书。

扫榜的做法是「一次过十几本新书，看它们怎么开头」，然后横着比。那批书需要一个名字才能被
反复回到——否则每次都要在书库里重新挑一遍，而「上次那批」这句话根本无法表达。

书单本身免费。它不调用模型，是个文件夹；对整理收钱等于对文件夹收钱。付费的是**在一组书
上做的事**——共性视图、跨书检索——那些各自把自己的门。

字段在这里算好，客户端照着渲染（INV-P4）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import Book, Collection, CollectionBook
from app.services.library_listing import build_library_listing

__all__ = [
    "CollectionError",
    "add_books",
    "create_collection",
    "delete_collection",
    "list_collections",
    "read_collection",
    "remove_book",
    "update_collection",
]

#: 书单名的长度上限，与列的宽度一致。超了直接说，不悄悄截断——截断过的名字下次再搜就搜不到。
NAME_MAX = 120


class CollectionError(Exception):
    """书单操作失败，带一个给用户看的原因。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _require(session: Session, collection_id: int) -> Collection:
    row = session.get(Collection, int(collection_id))
    if row is None:
        raise CollectionError("COLLECTION_NOT_FOUND", "这个书单不存在，可能已经被删掉了。")
    return row


def _clean_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise CollectionError("COLLECTION_NAME_REQUIRED", "书单要有名字。")
    if len(cleaned) > NAME_MAX:
        raise CollectionError(
            "COLLECTION_NAME_TOO_LONG", f"书单名最多 {NAME_MAX} 个字，现在是 {len(cleaned)} 个。"
        )
    return cleaned


def _summary(session: Session, row: Collection, counts: dict[int, int]) -> dict[str, Any]:
    return {
        "id": int(row.id),
        "name": str(row.name or ""),
        "note": str(row.note or ""),
        "book_count": int(counts.get(int(row.id), 0) or 0),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def list_collections(session: Session) -> list[dict[str, Any]]:
    """所有书单，最近改动的排在前面。

    按 updated_at 而不是建立时间：正在用的那个书单应该在手边，而它是刚被加过书的那个。
    """
    counts = dict(
        session.execute(
            select(CollectionBook.collection_id, func.count(CollectionBook.id)).group_by(
                CollectionBook.collection_id
            )
        ).all()
    )
    rows = session.scalars(select(Collection).order_by(Collection.updated_at.desc()))
    return [_summary(session, row, counts) for row in rows]


def create_collection(session: Session, *, name: str, note: str = "") -> dict[str, Any]:
    row = Collection(name=_clean_name(name), note=(note or "").strip())
    session.add(row)
    session.flush()
    return _summary(session, row, {})


def update_collection(
    session: Session, collection_id: int, *, name: str | None = None, note: str | None = None
) -> dict[str, Any]:
    row = _require(session, collection_id)
    if name is not None:
        row.name = _clean_name(name)
    if note is not None:
        row.note = note.strip()
    session.flush()
    counts = {int(row.id): _book_count(session, int(row.id))}
    return _summary(session, row, counts)


def delete_collection(session: Session, collection_id: int) -> None:
    """删书单不删书。

    书是导入进来的资产，书单只是一种看法；删掉一种看法不该让资料跟着消失。
    """
    row = _require(session, collection_id)
    session.execute(delete(CollectionBook).where(CollectionBook.collection_id == int(row.id)))
    session.delete(row)
    session.flush()


def _book_count(session: Session, collection_id: int) -> int:
    return int(
        session.scalar(
            select(func.count(CollectionBook.id)).where(
                CollectionBook.collection_id == int(collection_id)
            )
        )
        or 0
    )


def add_books(session: Session, collection_id: int, book_ids: list[int]) -> dict[str, Any]:
    """把书加进书单。已经在里面的跳过，不报错。

    重复加入是用户的常规动作（挑着挑着忘了加过没有），把它当成错误会让人以为操作失败了，
    然后再点一次。
    """
    row = _require(session, collection_id)
    existing = set(
        session.scalars(
            select(CollectionBook.book_id).where(CollectionBook.collection_id == int(row.id))
        )
    )
    known = set(session.scalars(select(Book.id).where(Book.id.in_(book_ids))))
    missing = [int(b) for b in book_ids if int(b) not in known]
    if missing:
        raise CollectionError(
            "BOOK_NOT_FOUND", f"有 {len(missing)} 本书不在书库里，可能已经被删掉了。"
        )
    position = int(
        session.scalar(
            select(func.coalesce(func.max(CollectionBook.position), 0)).where(
                CollectionBook.collection_id == int(row.id)
            )
        )
        or 0
    )
    added = 0
    for book_id in book_ids:
        if int(book_id) in existing:
            continue
        position += 1
        session.add(
            CollectionBook(
                collection_id=int(row.id), book_id=int(book_id), position=position
            )
        )
        added += 1
    # 加了书就是动过——列表按 updated_at 排，这一步让正在用的书单浮到手边。
    if added:
        row.updated_at = datetime.utcnow()
    session.flush()
    return {"added": added, "book_count": _book_count(session, int(row.id))}


def remove_book(session: Session, collection_id: int, book_id: int) -> dict[str, Any]:
    row = _require(session, collection_id)
    session.execute(
        delete(CollectionBook).where(
            CollectionBook.collection_id == int(row.id),
            CollectionBook.book_id == int(book_id),
        )
    )
    row.updated_at = datetime.utcnow()
    session.flush()
    return {"book_count": _book_count(session, int(row.id))}


def read_collection(session: Session, collection_id: int) -> dict[str, Any]:
    """书单本身，加上里面的书——书用的是书库那套卡片。

    同样的类型标、同样的分析状态。走两套渲染，两边迟早会不一致，而「这本跑完没有」
    在书单里问得只会更频繁：书单存在的理由就是一次看一批。
    """
    row = _require(session, collection_id)
    ordered = list(
        session.scalars(
            select(CollectionBook.book_id)
            .where(CollectionBook.collection_id == int(row.id))
            .order_by(CollectionBook.position, CollectionBook.id)
        )
    )
    books = build_library_listing(session, book_ids=[int(b) for b in ordered])
    summary = _summary(session, row, {int(row.id): len(books)})
    return {**summary, "books": books}
