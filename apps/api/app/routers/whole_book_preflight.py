"""Read-only whole-book preflight HTTP API (Phase 1C + STEP 2.2 Overview).

POST /api/v1/books/{book_id}/whole-book-runs/preflight

- Legacy Phase 1C preflight when request is not Overview-targeted.
- Native Overview PreflightResponse when module_key=book_overview (or
  native_overview=true).

Does not create AnalysisRun / Snapshot / Assets for the legacy path.
Native Overview create remains on a separate route and Feature Flag.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey
from app.narrative_core.services.capability_service import DefaultCapabilityService
from app.narrative_core.services.native_overview_service import NativeOverviewService
from app.narrative_core.services.whole_book_preflight import (
    build_whole_book_preflight,
    preflight_response_dict,
)

router = APIRouter(prefix="/api/v1", tags=["whole-book-preflight"])


def get_capability_service(session: Session = Depends(get_db)) -> DefaultCapabilityService:
    return DefaultCapabilityService(session)


def _is_native_overview_preflight(payload: dict[str, Any]) -> bool:
    module_key = str(payload.get("module_key") or "").strip()
    if module_key == WholeBookModuleKey.BOOK_OVERVIEW.value:
        return True
    if payload.get("native_overview") is True or payload.get("overview") is True:
        return True
    return False


@router.post("/books/{book_id}/whole-book-runs/preflight")
def whole_book_run_preflight(
    book_id: int,
    body: dict[str, Any] | None = None,
    session: Session = Depends(get_db),
    service: DefaultCapabilityService = Depends(get_capability_service),
) -> dict[str, Any]:
    payload = dict(body or {})

    if _is_native_overview_preflight(payload):
        return NativeOverviewService(session).preflight(int(book_id)).model_dump(mode="json")

    if "analysis_mode" not in payload and "requested_mode" not in payload and "mode" not in payload:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "WHOLE_BOOK_REQUEST_INVALID",
                "message": "analysis_mode is required",
                "details": {},
            },
        )
    # Validate mode early for clearer errors (invalid mode still returns preflight body).
    mode_raw = payload.get("analysis_mode") or payload.get("requested_mode") or payload.get("mode")
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
