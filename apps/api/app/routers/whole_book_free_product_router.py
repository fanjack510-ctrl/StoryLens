"""Free whole-book product coordination APIs (WB-1.7 backend)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
)
from app.narrative_core.services.whole_book_free_product_v1_service import (
    create_fixture_free_whole_book_analysis_v1,
    create_free_whole_book_analysis_v1,
    prepare_free_whole_book_analysis_v1,
)
from app.narrative_core.services.whole_book_minimal_read_v1_service import (
    get_run_overview,
)
from app.narrative_core.services.whole_book_product_capability_v1 import (
    AccessTier,
    require_capability_access,
)
from app.narrative_core.services.whole_book_structure_product_v1_service import (
    get_run_structure_product_v1,
)

router = APIRouter(prefix="/api/v1", tags=["whole-book-free-product"])

_NOT_FOUND_CODES = {
    WholeBookFoundationErrorCode.WHOLE_BOOK_BOOK_NOT_FOUND.value,
    WholeBookFoundationErrorCode.WHOLE_BOOK_RUN_NOT_FOUND.value,
    WholeBookFoundationErrorCode.WHOLE_BOOK_SNAPSHOT_NOT_FOUND.value,
}


class CreateFreeRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    estimate_id: int = Field(gt=0)
    consent_id: int = Field(gt=0)
    client_request_id: str = Field(min_length=1, max_length=128)


class CreateFixtureFreeRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_request_id: str | None = Field(default=None, max_length=128)
    execute_pipeline: bool = True


def _raise_foundation(exc: WholeBookFoundationError) -> None:
    status = 404 if exc.code in _NOT_FOUND_CODES else 400
    raise HTTPException(
        status_code=status,
        detail={"error_code": exc.code, "message": exc.message},
    )


def _prepare(book_id: int, db: Session) -> dict:
    try:
        result = prepare_free_whole_book_analysis_v1(db, book_id)
        db.commit()
        return result
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise


def _create_fixture(book_id: int, body: CreateFixtureFreeRunRequest, db: Session) -> dict:
    try:
        result = create_fixture_free_whole_book_analysis_v1(
            db,
            book_id,
            client_request_id=body.client_request_id,
            execute_pipeline=body.execute_pipeline,
        )
        db.commit()
        return result
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise


@router.get("/books/{book_id}/whole-book/free/prepare")
def prepare_free_analysis(book_id: int, db: Session = Depends(get_db)) -> dict:
    return _prepare(book_id, db)


@router.get("/books/{book_id}/whole-book/prepare")
def prepare_free_analysis_product_alias(book_id: int, db: Session = Depends(get_db)) -> dict:
    """Product-facing alias used by Wave D desktop client."""
    return _prepare(book_id, db)


@router.post("/books/{book_id}/whole-book/free/create")
def create_free_analysis(
    book_id: int,
    body: CreateFreeRunRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = create_free_whole_book_analysis_v1(
            db,
            book_id,
            estimate_id=body.estimate_id,
            consent_id=body.consent_id,
            client_request_id=body.client_request_id,
        )
        db.commit()
        return result
    except WholeBookFoundationError as exc:
        db.rollback()
        _raise_foundation(exc)
        raise


@router.post("/books/{book_id}/whole-book/free/create-fixture")
def create_fixture_free_analysis(
    book_id: int,
    body: CreateFixtureFreeRunRequest,
    db: Session = Depends(get_db),
) -> dict:
    return _create_fixture(book_id, body, db)


@router.post("/books/{book_id}/whole-book/runs/fixture")
def create_fixture_free_analysis_alias(
    book_id: int,
    body: CreateFixtureFreeRunRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Product-facing alias used by Wave D desktop client."""
    return _create_fixture(book_id, body, db)


@router.get("/whole-book/runs/{run_id}/overview-gated")
def gated_overview(run_id: int, db: Session = Depends(get_db)) -> dict:
    try:
        require_capability_access("whole_book.overview", AccessTier.free)
        overview = get_run_overview(db, run_id)
        if overview is None:
            raise HTTPException(
                status_code=404,
                detail={"error_code": "OVERVIEW_NOT_FOUND", "message": "全书总览尚未生成"},
            )
        return {"overview": overview}
    except WholeBookFoundationError as exc:
        _raise_foundation(exc)
        raise


@router.get("/whole-book/runs/{run_id}/structure")
def product_structure_result(run_id: int, db: Session = Depends(get_db)) -> dict:
    """Product StructureStagesResultV2 envelope (WB-2.1)."""

    try:
        require_capability_access("whole_book.structure", AccessTier.free)
        payload = get_run_structure_product_v1(db, run_id)
        if payload is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error_code": "STRUCTURE_RESULT_ABSENT",
                    "message": "故事结构结果尚未生成",
                },
            )
        return payload
    except WholeBookFoundationError as exc:
        _raise_foundation(exc)
        raise
