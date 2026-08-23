"""共性视图的口。

两个接口，两种价钱：
  · overview 免费——它只是把已经存好的东西数一遍，数出来的东西不该收费。
  · patterns 是 Pro——它做一次真正的归纳，而归纳是这件事里唯一省不掉的人力。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.common_patterns.service import (
    CommonPatternsError,
    build_overview,
    synthesize_patterns,
)
from app.services.collection_service import CollectionError, read_collection

router = APIRouter(prefix="/api/v1", tags=["common-patterns"])

_FEATURE = "common_patterns"


def _collection_book_ids(db: Session, collection_id: int) -> list[int]:
    try:
        detail = read_collection(db, int(collection_id))
    except CollectionError as exc:
        raise HTTPException(
            status_code=404 if exc.code.endswith("NOT_FOUND") else 400,
            detail={"error_code": exc.code, "message": exc.message},
        ) from exc
    return [int(b["id"]) for b in detail.get("books") or []]


@router.get("/collections/{collection_id}/common-patterns/overview")
def get_overview(collection_id: int, db: Session = Depends(get_db)) -> dict:
    """数出来的那一半。免费。

    没有 Pro 的人也应该看得见这一屏：类型分布、每本读到第几章、哪几本还没拆过文。
    把它一起锁上，用户在付钱之前无法判断这组书值不值得归纳。
    """
    return build_overview(db, _collection_book_ids(db, collection_id))


@router.post("/collections/{collection_id}/common-patterns")
def post_patterns(collection_id: int, db: Session = Depends(get_db)) -> dict:
    """归纳那一半。Pro。"""
    from app.services.entitlement import can_use_feature, commerce_config

    gate = can_use_feature(db, _FEATURE)
    if not gate.get("enabled"):
        commerce = commerce_config()
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "COMMON_PATTERNS_REQUIRES_PRO",
                "message": (
                    "共性视图是 Pro 功能。上面那一屏（类型分布、每本读到第几章）保持免费，"
                    "付费的是把这些书归纳成共同手法这一步。"
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
        result = synthesize_patterns(
            db, _collection_book_ids(db, collection_id), collection_id=int(collection_id)
        )
        db.commit()
    except CommonPatternsError as exc:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail={"error_code": exc.code, "message": exc.message},
        ) from exc
    return result
