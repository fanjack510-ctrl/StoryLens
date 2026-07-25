"""Native Overview walking-skeleton HTTP API (STEP 2.2-A).

Create / Get Run / Get Overview. Preflight stays on whole_book_preflight router
(extended to return contract PreflightResponse for book_overview).

Gated by ``is_pro_native_overview_enabled()``. Does not flip
WHOLE_BOOK_RUNS_ENDPOINT_DISABLED.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.contracts.whole_book_overview_v1 import CreateRunRequest
from app.narrative_core.services.native_overview_service import (
    NativeOverviewError,
    NativeOverviewService,
)

router = APIRouter(prefix="/api/v1", tags=["whole-book-native-overview"])


def _service(session: Session = Depends(get_db)) -> NativeOverviewService:
    return NativeOverviewService(session)


def _raise(exc: NativeOverviewError) -> None:
    envelope = exc.as_envelope()
    raise HTTPException(
        status_code=exc.http_status,
        detail={
            "error_code": exc.code,
            "message": exc.message,
            "details": {
                **exc.details,
                "error": envelope.get("error"),
            },
            "retryable": exc.retryable,
        },
    ) from exc


@router.post("/books/{book_id}/whole-book-runs", status_code=201)
def create_native_overview_run(
    book_id: int,
    body: dict[str, Any] | None = None,
    service: NativeOverviewService = Depends(_service),
) -> dict[str, Any]:
    try:
        request = CreateRunRequest.model_validate(body or {})
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "WHOLE_BOOK_REQUEST_INVALID",
                "message": "invalid create run request",
                "details": {"errors": exc.errors()},
            },
        ) from exc
    try:
        response = service.create_run(int(book_id), request)
    except NativeOverviewError as exc:
        _raise(exc)
        raise  # pragma: no cover
    return response.model_dump(mode="json")


@router.get("/whole-book-runs/{run_id}")
def get_native_overview_run(
    run_id: int,
    service: NativeOverviewService = Depends(_service),
) -> dict[str, Any]:
    try:
        return service.get_run(int(run_id)).model_dump(mode="json")
    except NativeOverviewError as exc:
        _raise(exc)
        raise  # pragma: no cover


@router.get("/whole-book-runs/{run_id}/overview")
def get_native_overview(
    run_id: int,
    service: NativeOverviewService = Depends(_service),
) -> dict[str, Any]:
    try:
        return service.get_overview(int(run_id)).model_dump(mode="json")
    except NativeOverviewError as exc:
        _raise(exc)
        raise  # pragma: no cover
