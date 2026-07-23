"""Capability query API (Phase 1C Agent H).

GET /api/v1/capabilities
GET /api/v1/capabilities/{key}

Does not expose license secrets or credentials. Does not register live
whole-book run creation. Loopback origin guard applies via app middleware.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.narrative_core.services.capability_api_payloads import (
    CapabilityApiError,
    build_capabilities_list_response,
    build_capability_detail_response,
)
from app.narrative_core.services.capability_service import DefaultCapabilityService

router = APIRouter(prefix="/api/v1", tags=["capabilities"])


def get_capability_service(session: Session = Depends(get_db)) -> DefaultCapabilityService:
    return DefaultCapabilityService(session)


@router.get("/capabilities")
def list_capabilities(
    service: DefaultCapabilityService = Depends(get_capability_service),
) -> dict:
    return build_capabilities_list_response(service)


@router.get("/capabilities/{capability_key}")
def get_capability(
    capability_key: str,
    service: DefaultCapabilityService = Depends(get_capability_service),
) -> dict:
    try:
        return build_capability_detail_response(service, capability_key)
    except CapabilityApiError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "error_code": exc.error_code,
                "message": exc.message,
                "details": {},
            },
        ) from exc
