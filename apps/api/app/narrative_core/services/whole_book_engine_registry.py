"""In-memory WholeBook engine registry stub (Agent G owns fuller impl)."""

from __future__ import annotations

from typing import Sequence

from app.narrative_core.contracts.engine import WholeBookAnalysisEngine
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode


class InMemoryWholeBookEngineRegistry:
    def __init__(self) -> None:
        self._engines: dict[str, WholeBookAnalysisEngine] = {}

    def register_engine(self, engine: WholeBookAnalysisEngine) -> None:
        self._engines[engine.engine_id] = engine

    def get_engine(self, engine_id: str) -> WholeBookAnalysisEngine:
        engine = self._engines.get(engine_id)
        if engine is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_ENGINE_NOT_FOUND,
                f"engine not found: {engine_id}",
            )
        return engine

    def list_engines(self) -> Sequence[str]:
        return tuple(sorted(self._engines.keys()))
