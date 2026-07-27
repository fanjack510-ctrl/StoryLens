"""Read-only whole-book preflight (Phase 1C Integration).

POST /api/v1/books/{book_id}/whole-book-runs/preflight

Checks only — never creates AnalysisRun / RunStage / Snapshot, never calls
Mock Engine execute_stage, never reserves quota/budget, never writes assets.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AnalysisRun, Book, BookSnapshot, Chapter, Paragraph
from app.narrative_core.contracts.api_dto import (
    WHOLE_BOOK_RUNS_ENDPOINT_DISABLED,
    CapabilityDecisionDTO,
    WholeBookPreflightDTO,
    WholeBookPreflightRequestDTO,
)
from app.narrative_core.enums import (
    CapabilityKey,
    CapabilityReasonCode,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
)
from app.narrative_core.services.capability_api_payloads import (
    decision_payload,
    quota_payload,
)
from app.narrative_core.services.capability_service import DefaultCapabilityService
from app.narrative_core.services.mock_whole_book_engine import MOCK_ENGINE_ID
from app.narrative_core.services.run_permission_guard import (
    require_whole_book_run_permission,
    whole_book_runs_endpoint_disabled,
)
from app.narrative_core.services.whole_book_engine_registry import (
    PRODUCTION_DEFAULT_ENGINE_ID,
)
from app.narrative_core.services.whole_book_stage_plan import build_whole_book_stage_plan
from app.narrative_core.whole_book_stages import WHOLE_BOOK_STAGE_CATALOG


def _parse_mode(raw: str | WholeBookAnalysisMode) -> WholeBookAnalysisMode | None:
    if isinstance(raw, WholeBookAnalysisMode):
        return raw
    try:
        return WholeBookAnalysisMode(str(raw))
    except ValueError:
        return None


def build_whole_book_preflight(
    session: Session,
    capability_service: DefaultCapabilityService,
    *,
    book_id: int,
    request: WholeBookPreflightRequestDTO | dict[str, Any],
) -> WholeBookPreflightDTO:
    """Evaluate preflight without mutating the database."""

    if isinstance(request, dict):
        mode_raw = request.get("analysis_mode") or request.get("requested_mode")
        modules_raw = request.get("requested_modules") or ()
        snapshot_id = request.get("book_snapshot_id")
        fingerprint = request.get("configuration_fingerprint")
        mode_parsed = _parse_mode(str(mode_raw) if mode_raw is not None else "")
        req = WholeBookPreflightRequestDTO(
            analysis_mode=mode_parsed or WholeBookAnalysisMode.NATIVE,
            requested_modules=tuple(str(m) for m in modules_raw),
            book_snapshot_id=int(snapshot_id) if snapshot_id is not None else None,
            configuration_fingerprint=str(fingerprint) if fingerprint else None,
        )
        invalid_mode = mode_parsed is None
        raw_mode_for_display = str(mode_raw) if mode_raw is not None else ""
    else:
        req = request
        invalid_mode = False
        raw_mode_for_display = req.analysis_mode.value

    book = session.get(Book, int(book_id))
    if book is None:
        # Still return a structured deny payload (read-only check).
        decision = capability_service.evaluate_capability(CapabilityKey.WHOLE_BOOK_ANALYSIS)
        return WholeBookPreflightDTO(
            book_id=int(book_id),
            analysis_mode=req.analysis_mode,
            capability=CapabilityDecisionDTO(
                capability_key=CapabilityKey.WHOLE_BOOK_ANALYSIS,
                allowed=False,
                reason_code=decision.reason_code,
                availability=decision.availability,
                message="book not found",
                preview_only=decision.preview_only,
            ),
            book_snapshot_id=req.book_snapshot_id,
            requested_mode=raw_mode_for_display or req.analysis_mode.value,
            run_creation_enabled=False,
            blocking_reasons=("BOOK_NOT_FOUND",),
            warnings=("book_id does not exist",),
            capability_decision=decision_payload(decision),
            engine_status={
                "production_default_engine_id": PRODUCTION_DEFAULT_ENGINE_ID,
                "mock_engine_id": MOCK_ENGINE_ID,
                "production_engine_available": False,
                "mock_not_production": True,
            },
            notes={"book_found": False},
        )

    chapter_count = int(
        session.scalar(
            select(func.count()).select_from(Chapter).where(Chapter.book_id == int(book_id))
        )
        or 0
    )
    character_count = int(
        session.scalar(
            select(func.coalesce(func.sum(func.length(Paragraph.raw_text)), 0))
            .select_from(Paragraph)
            .where(Paragraph.book_id == int(book_id))
        )
        or 0
    )

    snapshot_status: str | None = None
    snapshot_id = req.book_snapshot_id
    if snapshot_id is not None:
        snap = session.get(BookSnapshot, int(snapshot_id))
        if snap is None:
            snapshot_status = "missing"
        elif int(snap.book_id) != int(book_id):
            snapshot_status = "book_mismatch"
        else:
            snapshot_status = str(getattr(snap, "status", None) or "unknown")

    meta = capability_service.get_capability_metadata(CapabilityKey.WHOLE_BOOK_ANALYSIS)
    supported_modules = tuple(m.value for m in WholeBookModuleKey)

    # Stage plan is informational only — does not execute.
    stage_plan_rows: list[dict[str, Any]] = []
    if not invalid_mode:
        plan = build_whole_book_stage_plan(mode=req.analysis_mode)
        stage_plan_rows = [
            {
                "stage_key": s.stage_key.value,
                "display_name": s.display_name,
                "order": s.order,
                "required": s.required,
            }
            for s in plan.stages
        ]
    else:
        # Still expose catalog shape for diagnostics.
        stage_plan_rows = [
            {
                "stage_key": s.stage_key.value,
                "display_name": s.display_name,
                "order": s.order,
                "required": s.required,
            }
            for s in WHOLE_BOOK_STAGE_CATALOG
        ]

    mode_decision = (
        capability_service.evaluate_mode(CapabilityKey.WHOLE_BOOK_ANALYSIS, req.analysis_mode)
        if not invalid_mode
        else capability_service.evaluate_mode(
            CapabilityKey.WHOLE_BOOK_ANALYSIS, raw_mode_for_display or "invalid"
        )
    )
    capability = capability_service.evaluate_capability(
        CapabilityKey.WHOLE_BOOK_ANALYSIS,
        context={
            "book_id": int(book_id),
            "book_snapshot_id": snapshot_id,
            "character_count": character_count,
        },
    )
    quota = capability_service.evaluate_quota(
        CapabilityKey.WHOLE_BOOK_ANALYSIS,
        context={
            "book_id": int(book_id),
            "book_snapshot_id": snapshot_id,
            "character_count": character_count,
        },
    )

    blocking: list[str] = []
    warnings: list[str] = []

    if whole_book_runs_endpoint_disabled() or WHOLE_BOOK_RUNS_ENDPOINT_DISABLED:
        blocking.append("WHOLE_BOOK_RUNS_ENDPOINT_DISABLED=true")
    if not meta.shipped:
        blocking.append("whole_book_analysis shipped=false")
    if PRODUCTION_DEFAULT_ENGINE_ID is None:
        blocking.append("no production Engine")
    blocking.append("mock Engine is non-production and must not be reported as production-ready")

    if invalid_mode or mode_decision.reason_code == CapabilityReasonCode.CAPABILITY_MODE_NOT_SUPPORTED:
        blocking.append(CapabilityReasonCode.CAPABILITY_MODE_NOT_SUPPORTED.value)
    if not capability.allowed:
        blocking.append(capability.reason_code.value)
    if not quota.allowed:
        blocking.append(quota.reason_code.value if hasattr(quota.reason_code, "value") else str(quota.reason_code))
    if snapshot_status == "missing":
        warnings.append("book_snapshot_id not found; check-only, no snapshot created")
    elif snapshot_status == "book_mismatch":
        blocking.append("SNAPSHOT_BOOK_MISMATCH")
    elif snapshot_status is not None and snapshot_status not in {"completed", "COMPLETED"}:
        warnings.append(f"snapshot_status={snapshot_status}")

    # Guard path for structured checks — never creates runs.
    try:
        guard = require_whole_book_run_permission(
            capability_service,
            analysis_mode=req.analysis_mode if not invalid_mode else WholeBookAnalysisMode.NATIVE,
            book_id=int(book_id),
            book_snapshot_id=int(snapshot_id or 0) or 0,
            snapshot_status=snapshot_status if snapshot_status not in {None, "missing", "book_mismatch"} else None,
            context={
                "book_id": int(book_id),
                "book_snapshot_id": snapshot_id,
                "character_count": character_count,
            },
        )
        guard_notes = {
            "guard_allowed": guard.allowed,
            "guard_reason_code": guard.reason_code,
            "guard_message": guard.message,
            "checks": list(guard.checks),
        }
    except Exception as exc:  # noqa: BLE001 — preflight must remain read-only
        guard_notes = {
            "guard_allowed": False,
            "guard_reason_code": type(exc).__name__,
            "guard_message": str(exc),
            "checks": [],
        }

    # Ensure no accidental run creation during this check.
    # (Callers / tests assert AnalysisRun count unchanged.)
    _ = session.scalar(select(func.count()).select_from(AnalysisRun))

    engine_status = {
        "production_default_engine_id": PRODUCTION_DEFAULT_ENGINE_ID,
        "mock_engine_id": MOCK_ENGINE_ID,
        "production_engine_available": False,
        "mock_reported_as_production": False,
        "mock_not_production": True,
        "note": "Mock Engine must never be treated as production-ready",
    }

    return WholeBookPreflightDTO(
        book_id=int(book_id),
        book_snapshot_id=snapshot_id,
        analysis_mode=req.analysis_mode,
        capability=CapabilityDecisionDTO(
            capability_key=CapabilityKey.WHOLE_BOOK_ANALYSIS,
            allowed=False,  # production default: never allow creation via preflight
            reason_code=capability.reason_code,
            availability=capability.availability,
            message=capability.display_message,
            preview_only=capability.preview_only,
        ),
        snapshot_status=snapshot_status,
        chapter_count=chapter_count,
        character_count=character_count,
        requested_mode=raw_mode_for_display or req.analysis_mode.value,
        supported_modules=supported_modules,
        stage_plan=tuple(stage_plan_rows),
        capability_decision=decision_payload(capability),
        quota_decision=quota_payload(quota) or {},
        engine_status=engine_status,
        run_creation_enabled=False,
        blocking_reasons=tuple(dict.fromkeys(blocking)),
        warnings=tuple(warnings),
        engine_id=None,
        stage_count=len(stage_plan_rows),
        notes={
            **guard_notes,
            "configuration_fingerprint": req.configuration_fingerprint,
            "requested_modules": list(req.requested_modules),
            "endpoint_disabled": whole_book_runs_endpoint_disabled(),
            "no_side_effects": True,
        },
    )


def preflight_response_dict(dto: WholeBookPreflightDTO) -> dict[str, Any]:
    return {
        "book_id": dto.book_id,
        "book_snapshot_id": dto.book_snapshot_id,
        "snapshot_status": dto.snapshot_status,
        "chapter_count": dto.chapter_count,
        "character_count": dto.character_count,
        "requested_mode": dto.requested_mode,
        "analysis_mode": dto.analysis_mode.value,
        "supported_modules": list(dto.supported_modules),
        "stage_plan": list(dto.stage_plan),
        "capability_decision": dto.capability_decision,
        "quota_decision": dto.quota_decision,
        "engine_status": dto.engine_status,
        "run_creation_enabled": False,
        "blocking_reasons": list(dto.blocking_reasons),
        "warnings": list(dto.warnings),
        "engine_id": dto.engine_id,
        "stage_count": dto.stage_count,
        "capability": {
            "capability_key": dto.capability.capability_key.value,
            "allowed": dto.capability.allowed,
            "reason_code": dto.capability.reason_code.value,
            "availability": dto.capability.availability.value,
            "message": dto.capability.message,
            "preview_only": dto.capability.preview_only,
        },
        "notes": dto.notes or {},
    }
