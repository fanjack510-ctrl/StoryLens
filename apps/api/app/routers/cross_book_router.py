"""跨书检索的口。

  · search / scope 免费——关键词检索确定、即时、可核对，而且覆盖全部条目。
    对搜索框收费站不住脚。
  · by-meaning 是 Pro——它做一次真正的语义判断。实测「让主角一出场就打破读者预期的写法」
    这个问题，关键词检索命中 0 条，按意思找回了 8 条。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.cross_book.search import DEFAULT_LIMIT
from app.narrative_core.cross_book.service import (
    CrossBookError,
    find_by_meaning,
    search,
    search_scope,
)

router = APIRouter(prefix="/api/v1", tags=["cross-book-search"])

_FEATURE = "cross_book_search"


class MeaningSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=500)
    #: 限定在几本书里找。省略＝整个书库，因为跨书检索的默认问题是「有没有哪本书……」。
    book_ids: list[int] | None = None


@router.get("/cross-book/scope")
def get_scope(db: Session = Depends(get_db)) -> dict:
    """检索能覆盖到什么。

    用户按下搜索之前该知道自己在搜多大范围——「没找到」在「搜了三本书」和「搜了八十本」
    之下是完全不同的两个结论。
    """
    return search_scope(db)


@router.get("/cross-book/search")
def get_search(
    q: str = Query(default="", max_length=500),
    kinds: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_LIMIT, gt=0, le=200),
    db: Session = Depends(get_db),
) -> dict:
    """关键词检索。免费。"""
    kind_list = [k for k in (kinds or "").split(",") if k.strip()] or None
    return search(db, q, kinds=kind_list, limit=limit)


@router.post("/cross-book/by-meaning")
def post_by_meaning(body: MeaningSearchRequest, db: Session = Depends(get_db)) -> dict:
    """按意思找。Pro。"""
    from app.services.entitlement import can_use_feature, commerce_config

    gate = can_use_feature(db, _FEATURE)
    if not gate.get("enabled"):
        commerce = commerce_config()
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "CROSS_BOOK_SEARCH_REQUIRES_PRO",
                "message": (
                    "「找相似写法」是 Pro 功能。上面的找原句功能保持免费，"
                    "而且覆盖全部条目；付费的是用自己的话描述、由模型挑出来这一步。"
                ),
                "details": {
                    "feature_key": _FEATURE,
                    "reason": str(gate.get("reason") or ""),
                    "edition": str(gate.get("edition") or "free"),
                    "afdian_product_url": str(commerce.get("afdian_product_url") or ""),
                    "product_label": str(commerce.get("product_label") or "StoryLens Pro"),
                },
            },
        )
    try:
        result = find_by_meaning(db, body.query, book_ids=body.book_ids)
        db.commit()
    except CrossBookError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail={"error_code": exc.code, "message": exc.message},
        ) from exc
    return result
