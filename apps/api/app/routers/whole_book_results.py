"""Read-only whole-book result HTTP API (Phase 1D Agent K).

Routes (frozen contract):
  GET /api/v1/whole-book-runs/{run_id}/results
  GET /api/v1/whole-book-runs/{run_id}/results/{module_key}

Does not create Runs/Stages, does not call Engine/models, does not mutate Assets.
Loopback origin guard applies via app middleware when mounted.

Integration Issue: router is implemented here but NOT registered in app.main
(shared registration entry owned by Integration CHG-030).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.services.whole_book_result_projection import (
    WholeBookResultIndexService,
    envelope_to_dict,
    result_index_to_dict,
)

router = APIRouter(prefix="/api/v1", tags=["whole-book-results"])


def get_result_index_service(session: Session = Depends(get_db)) -> WholeBookResultIndexService:
    return WholeBookResultIndexService(session)


def _http_error(exc: NarrativeCoreError) -> HTTPException:
    status = 404
    if exc.code in {
        NarrativeCoreErrorCode.INVALID_RUN_SCOPE,
        NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
        NarrativeCoreErrorCode.WHOLE_BOOK_SNAPSHOT_REQUIRED,
    }:
        status = 400
    if exc.code == NarrativeCoreErrorCode.WHOLE_BOOK_MODULE_NOT_SUPPORTED:
        status = 404
    if "run not found" in str(exc).lower():
        status = 404
    return HTTPException(
        status_code=status,
        detail={
            "error_code": exc.code.value,
            "message": str(exc),
            "details": {},
        },
    )


@router.get("/whole-book-runs/{run_id}/results")
def get_whole_book_run_results(
    run_id: int,
    service: WholeBookResultIndexService = Depends(get_result_index_service),
) -> dict[str, Any]:
    """Result index — module statuses only; no full evidence bodies."""

    try:
        index = service.get_result_index(int(run_id))
    except NarrativeCoreError as exc:
        raise _http_error(exc) from exc
    return result_index_to_dict(index)


@router.get("/whole-book-runs/{run_id}/results/{module_key}")
def get_whole_book_run_module_result(
    run_id: int,
    module_key: str,
    view: str = Query(default="canonical", pattern="^(canonical|candidate)$"),
    service: WholeBookResultIndexService = Depends(get_result_index_service),
) -> dict[str, Any]:
    """Single module Envelope. Default view=canonical; candidate must be explicit."""

    try:
        envelope = service.get_module_result(
            int(run_id),
            module_key,
            view="candidate" if view == "candidate" else "canonical",
        )
    except NarrativeCoreError as exc:
        raise _http_error(exc) from exc
    body = envelope_to_dict(envelope)
    # Defense in depth: never leak prompt / credential / full text keys.
    for banned in ("prompt", "credential", "api_key", "full_text", "body", "raw_output"):
        body.pop(banned, None)
        if isinstance(body.get("payload"), dict):
            body["payload"].pop(banned, None)
    return body
