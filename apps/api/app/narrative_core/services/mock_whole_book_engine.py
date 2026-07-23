"""Minimal Mock WholeBook engine for Phase 1C-P contract import tests.

Agent G owns fuller implementation — no model calls, no book text reads.
"""

from __future__ import annotations

from typing import Any, Sequence

from app.narrative_core.contracts.stage import (
    WholeBookStageContext,
    WholeBookStagePlan,
    WholeBookStageResult,
)
from app.narrative_core.contracts.whole_book_dto import (
    WholeBookAnalysisRequest,
    validate_request_shape,
)
from app.narrative_core.enums import (
    StageStatus,
    WholeBookAnalysisMode,
    WholeBookModuleKey,
    WholeBookStageKey,
)
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.whole_book_stages import WHOLE_BOOK_STAGE_CATALOG

MOCK_ENGINE_ID = "mock_whole_book_v0"
MOCK_ENGINE_VERSION = "0.0.0-contract"


class MockWholeBookAnalysisEngine:
    """Contract-test stub implementing WholeBookAnalysisEngine Protocol."""

    @property
    def engine_id(self) -> str:
        return MOCK_ENGINE_ID

    @property
    def engine_version(self) -> str:
        return MOCK_ENGINE_VERSION

    def supported_modes(self) -> Sequence[WholeBookAnalysisMode]:
        return (WholeBookAnalysisMode.NATIVE, WholeBookAnalysisMode.ENHANCED)

    def supported_modules(self) -> Sequence[WholeBookModuleKey]:
        return tuple(WholeBookModuleKey)

    def validate_request(self, request: WholeBookAnalysisRequest) -> None:
        validate_request_shape(request)

    def build_stage_plan(self, request: WholeBookAnalysisRequest) -> WholeBookStagePlan:
        self.validate_request(request)
        return WholeBookStagePlan(
            mode=request.analysis_mode,
            stages=WHOLE_BOOK_STAGE_CATALOG,
        )

    def execute_stage(self, context: WholeBookStageContext) -> WholeBookStageResult:
        if not context.capability_context.allowed:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_CAPABILITY_DENIED,
                "capability denied",
            )
        return WholeBookStageResult(
            stage_key=context.stage_key,
            status=StageStatus.COMPLETED,
            message="mock stage completed (no model)",
            metrics={"engine": MOCK_ENGINE_ID, "mock": True},
        )

    def resume_stage(self, context: WholeBookStageContext) -> WholeBookStageResult:
        return self.execute_stage(context)

    def cancel_stage(self, run_id: int, stage_key: WholeBookStageKey | str) -> None:
        _ = (run_id, stage_key)

    def health_check(self) -> dict[str, Any]:
        return {
            "engine_id": MOCK_ENGINE_ID,
            "engine_version": MOCK_ENGINE_VERSION,
            "healthy": True,
            "mock": True,
        }
