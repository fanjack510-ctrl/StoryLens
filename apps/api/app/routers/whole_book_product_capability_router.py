"""Whole-book product capability APIs (WB-1.6A)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.narrative_core.services.whole_book_foundation_errors import WholeBookFoundationError
from app.narrative_core.services.whole_book_product_capability_v1 import (
    AccessTier,
    list_product_capabilities,
    resolve_capability_access,
)

router = APIRouter(prefix="/api/v1/whole-book", tags=["whole-book-product"])


def _raise_foundation(exc: WholeBookFoundationError) -> None:
    raise HTTPException(status_code=400, detail={"error_code": exc.code, "message": exc.message})


@router.get("/product-capabilities")
def get_product_capabilities(
    tier: str = Query(default=AccessTier.free.value),
) -> dict:
    try:
        AccessTier(tier)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_TIER", "message": "无效的用户等级"}) from exc
    return {"capabilities": list_product_capabilities(tier), "access_tier": tier}


@router.get("/product-capabilities/{capability_id}/access")
def get_capability_access(
    capability_id: str,
    tier: str = Query(default=AccessTier.free.value),
) -> dict:
    try:
        AccessTier(tier)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_TIER", "message": "无效的用户等级"}) from exc
    return resolve_capability_access(capability_id, tier)
