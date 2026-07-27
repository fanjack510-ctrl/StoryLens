"""Whole-book run creation permission guard (Phase 1C Agent H).

Production default: deny. Does not create AnalysisRun, Snapshot, Engine calls,
or cloud budget reservations on failure. Formal POST whole-book-runs stays
disabled via WHOLE_BOOK_RUNS_ENDPOINT_DISABLED.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from app.narrative_core.contracts.api_dto import (
    WHOLE_BOOK_RUNS_ENDPOINT_DISABLED,
    CapabilityDecisionDTO,
    WholeBookPreflightDTO,
)
from app.narrative_core.contracts.capability import CapabilityDecision
from app.narrative_core.enums import (
    CapabilityKey,
    CapabilityReasonCode,
    SnapshotStatus,
    WholeBookAnalysisMode,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.services.capability_service import DefaultCapabilityService

# Explicit test-only escape hatch. Production / packaged runtimes must not set this.
WHOLE_BOOK_RUN_TEST_OVERRIDE_ENV = "STORYLENS_ALLOW_WHOLE_BOOK_RUNS_FOR_TEST"


@dataclass(frozen=True, slots=True)
class WholeBookRunPermissionResult:
    allowed: bool
    reason_code: str
    message: str
    capability: CapabilityDecision | None = None
    run_creation_enabled: bool = False
    checks: tuple[str, ...] = ()


def whole_book_runs_endpoint_disabled() -> bool:
    return bool(WHOLE_BOOK_RUNS_ENDPOINT_DISABLED)


def _test_override_enabled(context: dict[str, Any] | None) -> bool:
    ctx = context or {}
    if ctx.get("allow_endpoint_for_test") is True:
        return True
    raw = os.environ.get(WHOLE_BOOK_RUN_TEST_OVERRIDE_ENV, "").strip().lower()
    return raw in {"1", "true", "yes"}


def require_whole_book_run_permission(
    capability_service: DefaultCapabilityService,
    *,
    analysis_mode: WholeBookAnalysisMode | str,
    book_id: int,
    book_snapshot_id: int,
    snapshot_status: SnapshotStatus | str | None = None,
    context: dict[str, Any] | None = None,
    cloud_budget_checker: Callable[[], tuple[bool, str]] | None = None,
    engine_invoker: Callable[..., Any] | None = None,
    run_factory: Callable[..., Any] | None = None,
    snapshot_factory: Callable[..., Any] | None = None,
) -> WholeBookRunPermissionResult:
    """Gate whole-book run creation. Failure must not create side effects.

    Check order:
    1. WHOLE_BOOK_RUNS_ENDPOINT_DISABLED (unless explicit test override)
    2. Capability shipped + license
    3. Mode supported by metadata
    4. Quota
    5. Snapshot completed
    6. Concurrent run quota (via quota service)
    7. Optional cloud budget gate (combinable; separate subsystem)
    """

    del engine_invoker, run_factory, snapshot_factory  # never call on this path
    ctx = dict(context or {})
    ctx.setdefault("book_id", book_id)
    ctx.setdefault("book_snapshot_id", book_snapshot_id)
    checks: list[str] = []

    if whole_book_runs_endpoint_disabled() and not _test_override_enabled(ctx):
        checks.append("endpoint_disabled")
        return WholeBookRunPermissionResult(
            allowed=False,
            reason_code="WHOLE_BOOK_RUNS_ENDPOINT_DISABLED",
            message="Whole-book run endpoint is disabled",
            run_creation_enabled=False,
            checks=tuple(checks),
        )
    checks.append("endpoint_override_or_enabled")

    try:
        mode = (
            analysis_mode
            if isinstance(analysis_mode, WholeBookAnalysisMode)
            else WholeBookAnalysisMode(str(analysis_mode))
        )
    except ValueError as exc:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_MODE_NOT_SUPPORTED,
            f"unsupported analysis_mode: {analysis_mode}",
        ) from exc

    mode_decision = capability_service.evaluate_mode(
        CapabilityKey.WHOLE_BOOK_ANALYSIS, mode
    )
    checks.append("mode")
    if (
        not mode_decision.allowed
        and mode_decision.reason_code == CapabilityReasonCode.CAPABILITY_MODE_NOT_SUPPORTED
    ):
        meta = capability_service.get_capability_metadata(CapabilityKey.WHOLE_BOOK_ANALYSIS)
        # If capability itself is not shipped, fall through to capability deny.
        if meta.shipped:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_MODE_NOT_SUPPORTED,
                mode_decision.display_message,
            )

    decision = capability_service.evaluate_capability(
        CapabilityKey.WHOLE_BOOK_ANALYSIS, context=ctx
    )
    checks.append("capability")
    if not decision.allowed:
        code = "WHOLE_BOOK_CAPABILITY_DENIED"
        if decision.reason_code == CapabilityReasonCode.CAPABILITY_QUOTA_EXCEEDED:
            code = "WHOLE_BOOK_QUOTA_EXCEEDED"
        return WholeBookRunPermissionResult(
            allowed=False,
            reason_code=code,
            message=decision.display_message or decision.reason_code.value,
            capability=decision,
            run_creation_enabled=False,
            checks=tuple(checks),
        )

    # Re-check mode after capability allowed (shipped + licensed).
    mode_decision = capability_service.evaluate_mode(
        CapabilityKey.WHOLE_BOOK_ANALYSIS, mode
    )
    checks.append("mode_after_capability")
    if not mode_decision.allowed:
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_MODE_NOT_SUPPORTED,
            mode_decision.display_message,
        )

    quota = capability_service.evaluate_quota(
        CapabilityKey.WHOLE_BOOK_ANALYSIS, context=ctx
    )
    checks.append("quota")
    if not quota.allowed:
        return WholeBookRunPermissionResult(
            allowed=False,
            reason_code="WHOLE_BOOK_QUOTA_EXCEEDED",
            message=quota.message or "Quota exceeded",
            capability=decision,
            run_creation_enabled=False,
            checks=tuple(checks),
        )

    status = snapshot_status
    if status is not None:
        status_value = status.value if isinstance(status, SnapshotStatus) else str(status)
        checks.append("snapshot")
        if status_value != SnapshotStatus.COMPLETED.value:
            return WholeBookRunPermissionResult(
                allowed=False,
                reason_code=NarrativeCoreErrorCode.WHOLE_BOOK_SNAPSHOT_REQUIRED.value,
                message="snapshot must be COMPLETED",
                capability=decision,
                run_creation_enabled=False,
                checks=tuple(checks),
            )

    if cloud_budget_checker is not None:
        checks.append("cloud_budget")
        ok, budget_message = cloud_budget_checker()
        if not ok:
            return WholeBookRunPermissionResult(
                allowed=False,
                reason_code=NarrativeCoreErrorCode.WHOLE_BOOK_BUDGET_DENIED.value,
                message=budget_message or "Cloud budget denied",
                capability=decision,
                run_creation_enabled=False,
                checks=tuple(checks),
            )

    return WholeBookRunPermissionResult(
        allowed=True,
        reason_code=CapabilityReasonCode.CAPABILITY_AVAILABLE.value,
        message="Whole-book run permitted",
        capability=decision,
        run_creation_enabled=False,  # Phase 1C: never enable live creation here
        checks=tuple(checks),
    )


def preflight_whole_book_run(
    capability_service: DefaultCapabilityService,
    *,
    book_id: int,
    book_snapshot_id: int,
    analysis_mode: WholeBookAnalysisMode | str,
    snapshot_status: SnapshotStatus | str | None = SnapshotStatus.COMPLETED,
    context: dict[str, Any] | None = None,
) -> WholeBookPreflightDTO:
    """Internal preflight — checks only; does not create Run / call Engine / model.

    ``run_creation_enabled`` is always false in Phase 1C Agent H.
    HTTP wiring deferred to Integration.
    """

    result = require_whole_book_run_permission(
        capability_service,
        analysis_mode=analysis_mode,
        book_id=book_id,
        book_snapshot_id=book_snapshot_id,
        snapshot_status=snapshot_status,
        context=context,
    )
    mode = (
        analysis_mode
        if isinstance(analysis_mode, WholeBookAnalysisMode)
        else WholeBookAnalysisMode(str(analysis_mode))
    )
    capability = result.capability
    if capability is None:
        capability = capability_service.evaluate_capability(
            CapabilityKey.WHOLE_BOOK_ANALYSIS, context=context
        )
    return WholeBookPreflightDTO(
        book_id=book_id,
        book_snapshot_id=book_snapshot_id,
        analysis_mode=mode,
        capability=CapabilityDecisionDTO(
            capability_key=CapabilityKey.WHOLE_BOOK_ANALYSIS,
            allowed=capability.allowed,
            reason_code=capability.reason_code,
            availability=capability.availability,
            message=capability.display_message,
            preview_only=capability.preview_only,
        ),
        engine_id=None,
        stage_count=0,
        run_creation_enabled=False,
        requested_mode=mode.value,
        capability_decision={
            "capability_key": CapabilityKey.WHOLE_BOOK_ANALYSIS.value,
            "allowed": capability.allowed,
            "reason_code": capability.reason_code.value,
        },
        notes={
            "run_creation_enabled": False,
            "guard_allowed": result.allowed,
            "guard_reason_code": result.reason_code,
            "guard_message": result.message,
            "checks": list(result.checks),
            "snapshot_status_checked": snapshot_status is not None,
        },
    )
