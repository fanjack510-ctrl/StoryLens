"""Read-only whole-book preflight HTTP API (Phase 1C Integration).

POST /api/v1/books/{book_id}/whole-book-runs/preflight

Does not create AnalysisRun / Snapshot / Assets. Does not execute Mock Engine.
Loopback origin guard applies via app middleware.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.enums import WholeBookAnalysisMode
from app.narrative_core.services.capability_service import DefaultCapabilityService
from app.narrative_core.services.whole_book_preflight import (
    build_whole_book_preflight,
    preflight_response_dict,
)

router = APIRouter(prefix="/api/v1", tags=["whole-book-preflight"])


def get_capability_service(session: Session = Depends(get_db)) -> DefaultCapabilityService:
    return DefaultCapabilityService(session)


@router.post("/books/{book_id}/whole-book-runs/preflight")
def whole_book_run_preflight(
    book_id: int,
    body: dict[str, Any] | None = None,
    session: Session = Depends(get_db),
    service: DefaultCapabilityService = Depends(get_capability_service),
) -> dict[str, Any]:
    payload = dict(body or {})
    if "analysis_mode" not in payload and "requested_mode" not in payload:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "WHOLE_BOOK_REQUEST_INVALID",
                "message": "analysis_mode is required",
                "details": {},
            },
        )
    # Validate mode early for clearer errors (invalid mode still returns preflight body).
    mode_raw = payload.get("analysis_mode") or payload.get("requested_mode")
    try:
        WholeBookAnalysisMode(str(mode_raw))
    except ValueError:
        # Continue — preflight includes CAPABILITY_MODE_NOT_SUPPORTED in blocking_reasons.
        payload["analysis_mode"] = str(mode_raw)

    dto = build_whole_book_preflight(
        session,
        service,
        book_id=int(book_id),
        request=payload,
    )
    return preflight_response_dict(dto)
