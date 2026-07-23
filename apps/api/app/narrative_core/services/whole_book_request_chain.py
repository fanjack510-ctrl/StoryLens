"""Test-level whole-book request creation chain (Phase 1C Integration).

CapabilityService → require_whole_book_run_permission → CapabilityDecision
→ WholeBookAnalysisRequest → Engine.validate_request → build_stage_plan

Production defaults never reach Engine. Tests must inject an allowed Decision
and Mock Engine explicitly. Frontend-provided `allowed` is ignored.
"""

from __future__ import annotations

from typing import Any

from app.narrative_core.contracts.capability import CapabilityDecision
from app.narrative_core.contracts.stage import WholeBookStagePlan
from app.narrative_core.contracts.whole_book_dto import (
    WholeBookAnalysisRequest,
    validate_request_shape,
)
from app.narrative_core.enums import (
    CapabilityKey,
    SnapshotStatus,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.services.capability_service import DefaultCapabilityService
from app.narrative_core.services.run_permission_guard import require_whole_book_run_permission
from app.narrative_core.services.whole_book_stage_plan import build_whole_book_stage_plan


def build_backend_capability_context(
    capability_service: DefaultCapabilityService,
    *,
    context: dict[str, Any] | None = None,
    decision_override: CapabilityDecision | None = None,
) -> CapabilityDecision:
    """Backend-owned capability context. Ignores any client-supplied allowed flag."""

    if decision_override is not None:
        if decision_override.capability_key != CapabilityKey.WHOLE_BOOK_ANALYSIS:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED,
                "decision_override must be whole_book_analysis",
            )
        return decision_override
    return capability_service.evaluate_capability(
        CapabilityKey.WHOLE_BOOK_ANALYSIS, context=context
    )


def create_whole_book_analysis_request_for_test(
    capability_service: DefaultCapabilityService,
    *,
    book_id: int,
    book_snapshot_id: int,
    analysis_mode: WholeBookAnalysisMode | str,
    run_id: int | None = None,
    requested_modules: tuple[str, ...] | list[str] = (),
    snapshot_status: SnapshotStatus | str = SnapshotStatus.COMPLETED,
    context: dict[str, Any] | None = None,
    decision_override: CapabilityDecision | None = None,
    client_allowed: bool | None = None,
    engine: Any | None = None,
    skip_guard: bool = False,
) -> tuple[WholeBookAnalysisRequest, WholeBookStagePlan]:
    """Build request after Guard. Does not create DB runs.

    ``client_allowed`` is accepted only to prove it is ignored.
    ``decision_override`` is required for the happy path while shipped=false.
    """

    del client_allowed  # intentionally ignored — backend rebuilds decision
    mode = (
        analysis_mode
        if isinstance(analysis_mode, WholeBookAnalysisMode)
        else WholeBookAnalysisMode(str(analysis_mode))
    )
    ctx = dict(context or {})
    ctx.setdefault("book_id", book_id)
    ctx.setdefault("book_snapshot_id", book_snapshot_id)

    if not skip_guard:
        # When injecting an allowed override for tests, also allow endpoint override.
        if decision_override is not None and decision_override.allowed:
            ctx.setdefault("allow_endpoint_for_test", True)
        result = require_whole_book_run_permission(
            capability_service,
            analysis_mode=mode,
            book_id=int(book_id),
            book_snapshot_id=int(book_snapshot_id),
            snapshot_status=snapshot_status,
            context=ctx,
        )
        if not result.allowed and decision_override is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED,
                result.message,
            )
        if decision_override is None and result.capability is not None:
            decision_override = result.capability

    decision = build_backend_capability_context(
        capability_service, context=ctx, decision_override=decision_override
    )
    if not decision.allowed:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED,
            decision.display_message or "capability denied",
        )

    modules: list[WholeBookModuleKey | str] = []
    for item in requested_modules:
        try:
            modules.append(WholeBookModuleKey(str(item)))
        except ValueError:
            modules.append(str(item))

    status = (
        snapshot_status
        if isinstance(snapshot_status, SnapshotStatus)
        else SnapshotStatus(str(snapshot_status))
    )
    request = WholeBookAnalysisRequest(
        book_id=int(book_id),
        book_snapshot_id=int(book_snapshot_id),
        analysis_mode=mode,
        capability_context=decision,
        run_id=run_id,
        requested_modules=tuple(modules),
        snapshot_status=status,
    )

    if engine is None:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_ENGINE_UNAVAILABLE,
            "test chain requires explicit Mock Engine injection",
        )
    engine.validate_request(request)
    plan = engine.build_stage_plan(request)
    if not isinstance(plan, WholeBookStagePlan):
        plan = build_whole_book_stage_plan(mode)
    validate_request_shape(request)
    return request, plan
