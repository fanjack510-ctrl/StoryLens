"""WholeBook Engine Registry and Factory (Phase 1C Agent G).

In-memory only — does not read the database or License objects.
Production defaults must not register a real private engine; Mock only.
Capability selection is external; registry does not decide entitlement.
"""

from __future__ import annotations

from typing import Sequence

from app.narrative_core.contracts.capability import CapabilityDecision
from app.narrative_core.contracts.engine import WholeBookAnalysisEngine
from app.narrative_core.enums import WholeBookAnalysisMode
from app.narrative_core.errors import NarrativeCoreError, NarrativeCoreErrorCode
from app.narrative_core.services.mock_whole_book_engine import (
    MOCK_ENGINE_ID,
    MockWholeBookAnalysisEngine,
)

# Production entry points must not treat this as a real analysis engine.
PRODUCTION_DEFAULT_ENGINE_ID: str | None = None


class InMemoryWholeBookEngineRegistry:
    """Unique engine_id registry with Protocol + Agent G surface methods."""

    def __init__(self) -> None:
        self._engines: dict[str, WholeBookAnalysisEngine] = {}

    # ----- Protocol surface -----

    def register_engine(self, engine: WholeBookAnalysisEngine) -> None:
        self.register(engine)

    def get_engine(self, engine_id: str) -> WholeBookAnalysisEngine:
        return self.get(engine_id)

    def list_engines(self) -> Sequence[str]:
        return tuple(sorted(self._engines.keys()))

    # ----- Agent G surface -----

    def register(self, engine: WholeBookAnalysisEngine) -> None:
        engine_id = str(engine.engine_id)
        existing = self._engines.get(engine_id)
        if existing is not None:
            if existing is engine:
                return  # idempotent same instance
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_REQUEST_INVALID,
                f"duplicate engine_id registration: {engine_id}",
            )
        self._engines[engine_id] = engine

    def unregister(self, engine_id: str) -> None:
        if engine_id not in self._engines:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_ENGINE_NOT_FOUND,
                f"engine not found: {engine_id}",
            )
        del self._engines[engine_id]

    def get(self, engine_id: str) -> WholeBookAnalysisEngine:
        engine = self._engines.get(engine_id)
        if engine is None:
            raise NarrativeCoreError(
                NarrativeCoreErrorCode.WHOLE_BOOK_ENGINE_NOT_FOUND,
                f"engine not found: {engine_id}",
            )
        return engine

    def resolve_for_mode(self, mode: WholeBookAnalysisMode | str) -> WholeBookAnalysisEngine:
        """Pick a registered engine that supports ``mode``.

        Does not consult License / Capability — caller must already be allowed.
        Prefer non-mock engines when present; Phase 1C production registry should
        only contain Mock, so Mock is returned for tests only.
        """

        mode_value = (
            mode if isinstance(mode, WholeBookAnalysisMode) else WholeBookAnalysisMode(str(mode))
        )
        mock_match: WholeBookAnalysisEngine | None = None
        for engine_id in self.list_engines():
            engine = self._engines[engine_id]
            supported = {WholeBookAnalysisMode(m) for m in engine.supported_modes()}
            if mode_value not in supported:
                continue
            health = engine.health_check()
            if bool(health.get("mock")):
                mock_match = mock_match or engine
                continue
            return engine
        if mock_match is not None:
            return mock_match
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_MODE_NOT_SUPPORTED,
            f"no registered engine supports mode: {mode_value.value}",
        )

    def health_check_all(self) -> list[dict]:
        results: list[dict] = []
        for engine_id in self.list_engines():
            engine = self._engines[engine_id]
            health = dict(engine.health_check())
            health.setdefault("engine_id", engine.engine_id)
            results.append(health)
        return results


class DefaultWholeBookEngineFactory:
    """Factory for known engine ids. Production must not create private engines."""

    def __init__(
        self,
        *,
        registry: InMemoryWholeBookEngineRegistry | None = None,
        allow_mock: bool = True,
        production_mode: bool = False,
    ) -> None:
        self._registry = registry
        self._allow_mock = allow_mock
        self._production_mode = production_mode

    def create_engine(
        self,
        engine_id: str,
        *,
        capability_context: CapabilityDecision | None = None,
    ) -> WholeBookAnalysisEngine:
        _ = capability_context  # capability already evaluated externally
        if engine_id == MOCK_ENGINE_ID:
            if self._production_mode:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.WHOLE_BOOK_ENGINE_UNAVAILABLE,
                    "MockWholeBookAnalysisEngine must not serve production whole-book runs",
                )
            if not self._allow_mock:
                raise NarrativeCoreError(
                    NarrativeCoreErrorCode.WHOLE_BOOK_ENGINE_UNAVAILABLE,
                    "mock engine creation disabled",
                )
            engine = MockWholeBookAnalysisEngine()
            if self._registry is not None and MOCK_ENGINE_ID not in set(
                self._registry.list_engines()
            ):
                self._registry.register(engine)
            return engine
        raise NarrativeCoreError(
            NarrativeCoreErrorCode.WHOLE_BOOK_ENGINE_NOT_FOUND,
            f"unknown engine_id: {engine_id}",
        )


def create_default_test_registry() -> InMemoryWholeBookEngineRegistry:
    """Test helper — registers Mock only. Not for production run entry points."""

    registry = InMemoryWholeBookEngineRegistry()
    registry.register(MockWholeBookAnalysisEngine())
    return registry


# Back-compat alias used by Phase 1C-P contract tests.
WholeBookEngineRegistryImpl = InMemoryWholeBookEngineRegistry


__all__ = [
    "PRODUCTION_DEFAULT_ENGINE_ID",
    "InMemoryWholeBookEngineRegistry",
    "DefaultWholeBookEngineFactory",
    "create_default_test_registry",
    "WholeBookEngineRegistryImpl",
]
