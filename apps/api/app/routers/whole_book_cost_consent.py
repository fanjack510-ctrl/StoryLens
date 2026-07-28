"""Internal APIs for whole-book cost estimates and consents (WB-0.3).

Product entries remain hidden; these endpoints are for internal/planning use.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.capability_registry import get_capability_metadata
from app.narrative_core.enums import CapabilityKey
from app.narrative_core.services.whole_book_consent_service import (
    consent_to_dict,
    create_whole_book_consent,
    revoke_whole_book_consent,
)
from app.narrative_core.services.whole_book_cost_estimate_service import (
    estimate_to_dict,
    estimate_whole_book_analysis,
)
from app.narrative_core.services.whole_book_foundation_errors import WholeBookFoundationError

router = APIRouter(prefix="/api/v1", tags=["whole-book-cost-consent"])


class CostEstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: str
    provider_config_id: int = Field(gt=0)


class ConsentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    estimate_id: int = Field(gt=0)
    user_budget_limit_cny: str
    max_provider_calls: int | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    auto_retry_enabled: bool = False
    max_retries_per_unit: int = 0


def _raise_foundation(exc: WholeBookFoundationError) -> None:
    raise HTTPException(status_code=400, detail={"error_code": exc.code, "message": exc.message})


def _assert_capability_not_auto_enabled(mode: str) -> None:
    key = (
        CapabilityKey.WHOLE_BOOK_NATIVE
        if mode == "whole_book_native"
        else CapabilityKey.WHOLE_BOOK_ENHANCED
    )
    meta = get_capability_metadata(key)
    if meta.enabled or meta.entry_visible:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "WHOLE_BOOK_CAPABILITY_DISABLED",
                "message": "whole-book product entry must remain disabled in Wave A",
            },
        )


@router.post("/books/{book_id}/whole-book/cost-estimates")
def create_cost_estimate(
    book_id: int,
    body: CostEstimateRequest,
    db: Session = Depends(get_db),
) -> dict:
    _assert_capability_not_auto_enabled(body.mode)
    try:
        row = estimate_whole_book_analysis(db, book_id, body.mode, body.provider_config_id)
        db.commit()
        db.refresh(row)
        return estimate_to_dict(row)
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_MODE", "message": str(exc)}) from exc


@router.post("/books/{book_id}/whole-book/consents")
def create_consent(
    book_id: int,
    body: ConsentCreateRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        row = create_whole_book_consent(
            db,
            book_id=book_id,
            estimate_id=body.estimate_id,
            user_budget_limit_cny=Decimal(body.user_budget_limit_cny),
            max_provider_calls=body.max_provider_calls,
            max_input_tokens=body.max_input_tokens,
            max_output_tokens=body.max_output_tokens,
            auto_retry_enabled=body.auto_retry_enabled,
            max_retries_per_unit=body.max_retries_per_unit,
        )
        db.commit()
        db.refresh(row)
        return consent_to_dict(row)
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise


@router.post("/whole-book/consents/{consent_id}/revoke")
def revoke_consent(consent_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        row = revoke_whole_book_consent(db, consent_id)
        db.commit()
        db.refresh(row)
        return consent_to_dict(row)
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise
