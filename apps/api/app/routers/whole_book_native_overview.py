"""Native Overview walking-skeleton HTTP API (STEP 2.3-A2).

Create / Get Run / Get Overview / Retry / Resume.
Preflight stays on whole_book_preflight router.

Gated by ``is_pro_native_overview_enabled()``. Does not flip
WHOLE_BOOK_RUNS_ENDPOINT_DISABLED.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db, get_session_factory
from app.narrative_core.contracts.whole_book_overview_v1 import (
    CreateRunRequest,
    ResumeRunRequest,
    RetryRunRequest,
)
from app.narrative_core.services.native_overview_http_factory import (
    build_native_overview_service,
)
from app.narrative_core.services.native_overview_service import (
    NativeOverviewError,
    NativeOverviewService,
)
from app.services.native_overview_background import execute_native_overview_run_background

router = APIRouter(prefix="/api/v1", tags=["whole-book-native-overview"])


def _service(session: Session = Depends(get_db)) -> NativeOverviewService:
    # Product HTTP default: Private engine (never silent Fixture).
    return build_native_overview_service(session)


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
    background: BackgroundTasks,
    body: dict[str, Any] | None = None,
    session: Session = Depends(get_db),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
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
        # Resolve engine from request: Private product default; Fixture opt-in only.
        bound = build_native_overview_service(
            session,
            provider_id=request.provider_id,
            model_id=request.model_id,
        )
        # Defer execute_run so HTTP returns Run ID without waiting for all windows.
        response = bound.create_run(int(book_id), request, defer_execution=True)
    except NativeOverviewError as exc:
        _raise(exc)
        raise  # pragma: no cover
    background.add_task(
        execute_native_overview_run_background,
        session_factory,
        int(response.run_id),
        provider_id=request.provider_id,
        model_id=request.model_id,
    )
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


@router.post("/whole-book-runs/{run_id}/retry")
def retry_native_overview_run(
    run_id: int,
    body: dict[str, Any] | None = None,
    service: NativeOverviewService = Depends(_service),
) -> dict[str, Any]:
    try:
        request = RetryRunRequest.model_validate(body or {})
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "WHOLE_BOOK_REQUEST_INVALID",
                "message": "invalid retry request",
                "details": {"errors": exc.errors()},
            },
        ) from exc
    try:
        return service.retry_run(int(run_id), request).model_dump(mode="json")
    except NativeOverviewError as exc:
        _raise(exc)
        raise  # pragma: no cover


@router.post("/whole-book-runs/{run_id}/resume")
def resume_native_overview_run(
    run_id: int,
    body: dict[str, Any] | None = None,
    service: NativeOverviewService = Depends(_service),
) -> dict[str, Any]:
    try:
        request = ResumeRunRequest.model_validate(body or {})
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "WHOLE_BOOK_REQUEST_INVALID",
                "message": "invalid resume request",
                "details": {"errors": exc.errors()},
            },
        ) from exc
    try:
        return service.resume_run(int(run_id), request).model_dump(mode="json")
    except NativeOverviewError as exc:
        _raise(exc)
        raise  # pragma: no cover
