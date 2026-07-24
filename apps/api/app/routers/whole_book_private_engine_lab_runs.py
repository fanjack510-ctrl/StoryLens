"""Private Engine Lab whole-book HTTP API (Phase 2B-R Agent S).

Routes under /api/v1/labs/private-whole-book-runs.
Conditionally registered in apps/api/app/main.py when environment is
development/test AND WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED=true.

Distinct from Mock Lab. Production POST /api/v1/books/{book_id}/whole-book-runs
remains disabled. No formal Prompt bodies. No four-module algorithms.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.narrative_core.contracts.api_dto import WHOLE_BOOK_RUNS_ENDPOINT_DISABLED
from app.narrative_core.run_shell_contract.api_routes import PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH
from app.narrative_core.run_shell_contract.mock_lab import WHOLE_BOOK_MOCK_LAB_ENABLED
from app.narrative_core.run_shell_contract.private_engine_lab import (
    OPENAPI_PRIVATE_ENGINE_LAB_TAGS,
    PRIVATE_ENGINE_LAB_API_PREFIX,
    PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER,
    PRIVATE_LAB_FIRST_MODEL_ID,
    PRIVATE_LAB_FIRST_PROVIDER_KEY,
    PRIVATE_LAB_FIRST_QUALITY_PROFILE,
    WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
    PrivateEngineLabDenyReason,
)
from app.narrative_core.services.private_engine_lab_authorization_service import (
    PrivateEngineLabAuthorizationDenied,
    PrivateEngineLabAuthorizationService,
    is_loopback_host,
    private_engine_lab_request_marker_present,
)
from app.narrative_core.services.whole_book_provider_gateway import (
    create_lab_provider_gateway,
)

router = APIRouter(
    prefix=PRIVATE_ENGINE_LAB_API_PREFIX,
    tags=list(OPENAPI_PRIVATE_ENGINE_LAB_TAGS),
)

_lock = threading.RLock()
_sessions: dict[str, "PrivateEngineLabSession"] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class PrivateEngineLabSession:
    lab_run_id: str
    book_id: int
    book_snapshot_id: int
    status: str
    dry_run: bool
    provider_key: str
    model_id: str
    quality_profile: str
    created_at: str
    updated_at: str
    cancelled: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class CreatePrivateEngineLabRunBody(BaseModel):
    book_id: int = Field(ge=1)
    book_snapshot_id: int = Field(ge=1)
    dry_run: bool = True
    data_transfer_consented: bool = False
    user_confirmed: bool = False
    credential_present: bool = False
    budget_ok: bool = True
    capability_ok: bool = True
    configuration_fingerprint: str = Field(default="private-lab-dry", min_length=1)
    idempotency_key: str = Field(default="private-lab", min_length=1, max_length=128)

    model_config = {
        "json_schema_extra": {
            "description": (
                "Private Engine Lab create — non-production; never includes novel body "
                "or credentials"
            ),
        }
    }


class PrivateEngineLabActionBody(BaseModel):
    confirm_cancel: bool = False


def _client_host(request: Request) -> str:
    if request.client is not None and request.client.host:
        return str(request.client.host)
    return ""


def _auth_service() -> PrivateEngineLabAuthorizationService:
    # Router is only mounted when Lab is enabled — treat requests as lab_enabled.
    return PrivateEngineLabAuthorizationService(lab_enabled=True)


def _require_write_lab_gate(
    request: Request,
    *,
    dry_run: bool = True,
    credential_present: bool = False,
    data_transfer_consented: bool = False,
    budget_ok: bool = True,
    capability_ok: bool = True,
    user_confirmed: bool = False,
) -> None:
    host = _client_host(request)
    try:
        _auth_service().require(
            loopback=is_loopback_host(host),
            request_marker_present=private_engine_lab_request_marker_present(request.headers),
            credential_present=credential_present,
            data_transfer_consented=data_transfer_consented,
            budget_ok=budget_ok,
            capability_ok=capability_ok,
            user_confirmed=user_confirmed,
            dry_run=dry_run,
        )
    except PrivateEngineLabAuthorizationDenied as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": exc.reason.value,
                "message": exc.message,
            },
        ) from exc


@router.post(
    "",
    summary="Create Private Engine Lab Run (non-production)",
    response_description="Lab session view — no novel body / no credentials",
)
def create_private_engine_lab_run(
    body: CreatePrivateEngineLabRunBody,
    request: Request,
) -> dict[str, Any]:
    _require_write_lab_gate(
        request,
        dry_run=bool(body.dry_run),
        credential_present=bool(body.credential_present),
        data_transfer_consented=bool(body.data_transfer_consented),
        budget_ok=bool(body.budget_ok),
        capability_ok=bool(body.capability_ok),
        user_confirmed=bool(body.user_confirmed),
    )
    # Concurrency: one active dry/real lab session per book.
    with _lock:
        for session in _sessions.values():
            if (
                session.book_id == int(body.book_id)
                and session.status == "active"
                and not session.cancelled
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error_code": PrivateEngineLabDenyReason.PRIVATE_ENGINE_LAB_CONCURRENCY_LIMIT.value,
                        "message": (
                            "An active Private Engine Lab run already exists for this book."
                        ),
                    },
                )
        now = _utc_now_iso()
        lab_run_id = f"pelab-{uuid.uuid4().hex[:12]}"
        session = PrivateEngineLabSession(
            lab_run_id=lab_run_id,
            book_id=int(body.book_id),
            book_snapshot_id=int(body.book_snapshot_id),
            status="active",
            dry_run=bool(body.dry_run),
            provider_key=PRIVATE_LAB_FIRST_PROVIDER_KEY,
            model_id=PRIVATE_LAB_FIRST_MODEL_ID,
            quality_profile=PRIVATE_LAB_FIRST_QUALITY_PROFILE,
            created_at=now,
            updated_at=now,
            metadata={
                "configuration_fingerprint": body.configuration_fingerprint,
                "idempotency_key": body.idempotency_key,
                "modules_implemented": False,
                "shell_only": True,
            },
        )
        _sessions[lab_run_id] = session

    # Dry provider probe through Lab gateway (Fake + Bailian dry adapter) — no live HTTP.
    gateway = create_lab_provider_gateway(dry_run=True)
    health = gateway.health_check(PRIVATE_LAB_FIRST_PROVIDER_KEY if not body.dry_run else "fake")
    return {
        "lab_run_id": session.lab_run_id,
        "book_id": session.book_id,
        "book_snapshot_id": session.book_snapshot_id,
        "status": session.status,
        "dry_run": session.dry_run,
        "provider_key": session.provider_key,
        "model_id": session.model_id,
        "quality_profile": session.quality_profile,
        "mock_lab": False,
        "private_engine_lab": True,
        "non_production": True,
        "modules_implemented": False,
        "formal_run_disabled": WHOLE_BOOK_RUNS_ENDPOINT_DISABLED,
        "provider_health": {
            "provider_kind": health.provider_kind,
            "healthy": health.healthy,
            "status": health.status,
            "details": list(health.details),
        },
        "created_at": session.created_at,
    }


@router.get("/_meta/contract")
def private_engine_lab_contract(request: Request) -> dict[str, Any]:
    """Static contract surface for tests — no novel body."""
    _require_write_lab_gate(request, dry_run=True)
    return lab_contract_assertions()


@router.get("/{lab_run_id}")
def get_private_engine_lab_run(lab_run_id: str, request: Request) -> dict[str, Any]:
    _require_write_lab_gate(request, dry_run=True)
    with _lock:
        session = _sessions.get(lab_run_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "PRIVATE_ENGINE_LAB_RUN_NOT_FOUND",
                "message": "Private Engine Lab run was not found.",
            },
        )
    return {
        "lab_run_id": session.lab_run_id,
        "book_id": session.book_id,
        "book_snapshot_id": session.book_snapshot_id,
        "status": "cancelled" if session.cancelled else session.status,
        "dry_run": session.dry_run,
        "provider_key": session.provider_key,
        "model_id": session.model_id,
        "quality_profile": session.quality_profile,
        "private_engine_lab": True,
        "non_production": True,
        "modules_implemented": False,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


@router.post("/{lab_run_id}/cancel")
def cancel_private_engine_lab_run(
    lab_run_id: str,
    request: Request,
    body: PrivateEngineLabActionBody | None = None,
) -> dict[str, Any]:
    _require_write_lab_gate(request, dry_run=True)
    payload = body or PrivateEngineLabActionBody(confirm_cancel=True)
    if body is not None and not payload.confirm_cancel:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "PRIVATE_ENGINE_LAB_CANCEL_CONFIRM_REQUIRED",
                "message": "confirm_cancel must be true.",
            },
        )
    with _lock:
        session = _sessions.get(lab_run_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error_code": "PRIVATE_ENGINE_LAB_RUN_NOT_FOUND",
                    "message": "Private Engine Lab run was not found.",
                },
            )
        session.cancelled = True
        session.status = "cancelled"
        session.updated_at = _utc_now_iso()
    return {
        "lab_run_id": lab_run_id,
        "status": "cancelled",
        "private_engine_lab": True,
        "non_production": True,
    }


def lab_contract_assertions() -> dict[str, Any]:
    return {
        "WHOLE_BOOK_RUNS_ENDPOINT_DISABLED": WHOLE_BOOK_RUNS_ENDPOINT_DISABLED,
        "WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED_DEFAULT": WHOLE_BOOK_PRIVATE_ENGINE_LAB_ENABLED,
        "WHOLE_BOOK_MOCK_LAB_ENABLED_DEFAULT": WHOLE_BOOK_MOCK_LAB_ENABLED,
        "PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH": PRODUCTION_WHOLE_BOOK_RUN_CREATE_PATH,
        "PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER": PRIVATE_ENGINE_LAB_REQUEST_MARKER_HEADER,
        "PRIVATE_ENGINE_LAB_API_PREFIX": PRIVATE_ENGINE_LAB_API_PREFIX,
        "FIRST_PROVIDER_KEY": PRIVATE_LAB_FIRST_PROVIDER_KEY,
        "FIRST_MODEL_ID": PRIVATE_LAB_FIRST_MODEL_ID,
        "FIRST_QUALITY_PROFILE": PRIVATE_LAB_FIRST_QUALITY_PROFILE,
    }


def reset_private_engine_lab_sessions_for_tests() -> None:
    with _lock:
        _sessions.clear()


__all__ = [
    "lab_contract_assertions",
    "reset_private_engine_lab_sessions_for_tests",
    "router",
]
