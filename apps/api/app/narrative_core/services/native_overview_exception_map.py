"""Map Private engine / transport exceptions onto Public NativeOverviewError.

Private raises structured errors with wire-aligned ``code`` values. Public must
not collapse them into PRIVATE_ENGINE_UNAVAILABLE.
"""

from __future__ import annotations

from typing import Any

from app.narrative_core.contracts.whole_book_overview_errors import (
    WholeBookOverviewErrorCode,
)
from app.narrative_core.services.native_overview_errors import NativeOverviewError


def map_engine_exception(
    exc: BaseException,
    *,
    run_id: str | None = None,
    stage_key: str | None = None,
    window_index: int | None = None,
    fallback_code: str | None = None,
) -> NativeOverviewError:
    """Convert Private/Public engine failures into NativeOverviewError."""

    if isinstance(exc, NativeOverviewError):
        if run_id and not exc.run_id:
            exc.run_id = run_id
        if stage_key and not getattr(exc, "stage_key", None):
            exc.stage_key = stage_key
        if window_index is not None and getattr(exc, "window_index", None) is None:
            exc.window_index = window_index
        return exc

    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None)
    details_raw = getattr(exc, "details", None)
    details: dict[str, Any] = dict(details_raw) if isinstance(details_raw, dict) else {}
    details.setdefault("cause", type(exc).__name__)

    if isinstance(code, str) and code.strip():
        wire = code.strip()
        try:
            WholeBookOverviewErrorCode(wire)
        except ValueError:
            wire = fallback_code or WholeBookOverviewErrorCode.PRIVATE_ENGINE_UNAVAILABLE.value
        return NativeOverviewError(
            wire,
            str(message) if message else str(exc),
            run_id=run_id,
            stage_key=stage_key,
            window_index=window_index,
            details=details,
        )

    return NativeOverviewError(
        fallback_code or WholeBookOverviewErrorCode.PRIVATE_ENGINE_UNAVAILABLE.value,
        f"Overview engine execution failed: {exc}",
        run_id=run_id,
        stage_key=stage_key,
        window_index=window_index,
        details=details,
    )


__all__ = ["map_engine_exception"]
