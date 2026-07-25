"""STEP 2.3-I0 — Overview Engine Loader.

Loads engines by explicit engine_id. Never silently downgrades formal engines
to Fixture. Fixture engine requires the Private fixture adapter package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.narrative_core.contracts.pro_native_overview_flags import (
    FIXTURE_ENGINE_ID,
    PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
)
from app.narrative_core.contracts.whole_book_overview_errors import (
    WholeBookOverviewErrorCode,
)
from app.narrative_core.services.whole_book_overview_engine_protocol import (
    WholeBookOverviewEngineAdapter,
)


@dataclass(frozen=True, slots=True)
class EngineLoadError(Exception):
    """Structured loader failure mapped to frozen overview error codes."""

    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover - repr helper
        return f"{self.code}: {self.message}"


def load_overview_engine(engine_id: str) -> WholeBookOverviewEngineAdapter:
    """Resolve an overview engine by id. No silent Fixture fallback."""

    eid = (engine_id or "").strip()
    if eid == FIXTURE_ENGINE_ID:
        return _load_fixture_engine()
    if eid == PRIVATE_NATIVE_OVERVIEW_ENGINE_ID:
        return _load_private_native_engine()
    raise EngineLoadError(
        WholeBookOverviewErrorCode.PRIVATE_ENGINE_INCOMPATIBLE.value,
        f"Unknown overview engine_id: {engine_id!r}",
        {"engine_id": engine_id},
    )


def _load_fixture_engine() -> WholeBookOverviewEngineAdapter:
    from app.narrative_core.services.native_overview_fixture_adapter import (
        load_private_fixture_engine_adapter,
    )

    try:
        return load_private_fixture_engine_adapter()
    except EngineLoadError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise EngineLoadError(
            WholeBookOverviewErrorCode.PRIVATE_ENGINE_UNAVAILABLE.value,
            "Fixture overview engine requires Private fixture_adapter on PYTHONPATH.",
            {"engine_id": FIXTURE_ENGINE_ID, "cause": type(exc).__name__},
        ) from exc


def _load_private_native_engine() -> WholeBookOverviewEngineAdapter:
    """Formal Private engine (STEP 2.3-B). Must not fall back to Fixture."""

    try:
        from storylens_private_engine.modules.book_overview.native_engine import (  # type: ignore
            load_native_overview_engine,
        )
    except Exception as exc:  # noqa: BLE001
        raise EngineLoadError(
            WholeBookOverviewErrorCode.PRIVATE_ENGINE_UNAVAILABLE.value,
            "Private native overview engine is not available.",
            {
                "engine_id": PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
                "cause": type(exc).__name__,
            },
        ) from exc

    try:
        engine = load_native_overview_engine()
    except Exception as exc:  # noqa: BLE001
        raise EngineLoadError(
            WholeBookOverviewErrorCode.PRIVATE_ENGINE_UNAVAILABLE.value,
            "Private native overview engine failed to initialize.",
            {
                "engine_id": PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
                "cause": type(exc).__name__,
            },
        ) from exc

    if getattr(engine, "engine_id", None) != PRIVATE_NATIVE_OVERVIEW_ENGINE_ID:
        raise EngineLoadError(
            WholeBookOverviewErrorCode.PRIVATE_ENGINE_INCOMPATIBLE.value,
            "Loaded Private engine_id does not match private-native-overview-v1.",
            {
                "expected": PRIVATE_NATIVE_OVERVIEW_ENGINE_ID,
                "actual": getattr(engine, "engine_id", None),
            },
        )
    return engine
