"""WholeBook Analysis Engine Protocol contracts (Agent G implements)."""

from __future__ import annotations

from typing import Any, Protocol, Sequence

from app.narrative_core.contracts.capability import CapabilityDecision
from app.narrative_core.contracts.stage import (
    WholeBookStageContext,
    WholeBookStagePlan,
    WholeBookStageResult,
)
from app.narrative_core.contracts.whole_book_dto import WholeBookAnalysisRequest
from app.narrative_core.enums import WholeBookAnalysisMode, WholeBookModuleKey, WholeBookStageKey


class WholeBookAnalysisEngine(Protocol):
    @property
    def engine_id(self) -> str:
        ...

    @property
    def engine_version(self) -> str:
        ...

    def supported_modes(self) -> Sequence[WholeBookAnalysisMode]:
        ...

    def supported_modules(self) -> Sequence[WholeBookModuleKey]:
        ...

    def validate_request(self, request: WholeBookAnalysisRequest) -> None:
        """Uses DTO validators; must not parse License objects."""

    def build_stage_plan(self, request: WholeBookAnalysisRequest) -> WholeBookStagePlan:
        ...

    def execute_stage(self, context: WholeBookStageContext) -> WholeBookStageResult:
        ...

    def resume_stage(self, context: WholeBookStageContext) -> WholeBookStageResult:
        ...

    def cancel_stage(self, run_id: int, stage_key: WholeBookStageKey | str) -> None:
        ...

    def health_check(self) -> dict[str, Any]:
        ...


class WholeBookEngineFactory(Protocol):
    def create_engine(
        self,
        engine_id: str,
        *,
        capability_context: CapabilityDecision | None = None,
    ) -> WholeBookAnalysisEngine:
        ...


class WholeBookEngineRegistry(Protocol):
    def register_engine(self, engine: WholeBookAnalysisEngine) -> None:
        ...

    def get_engine(self, engine_id: str) -> WholeBookAnalysisEngine:
        ...

    def list_engines(self) -> Sequence[str]:
        ...
