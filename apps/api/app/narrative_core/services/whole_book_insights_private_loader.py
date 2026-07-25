"""Optional import bridge to private Whole-Book Insights engine."""

from __future__ import annotations

from typing import Any, Protocol


class WholeBookInsightsEngineProtocol(Protocol):
    def compute(self, input_payload: dict[str, Any]) -> dict[str, Any]:
        ...


def try_import_whole_book_insights_engine() -> WholeBookInsightsEngineProtocol | None:
    """Return private engine instance when installed; never vendor private sources."""
    try:
        from storylens_private_engine.whole_book_insights import (  # type: ignore[import-not-found]
            WholeBookInsightsEngineV1,
        )
    except Exception:
        return None
    try:
        return WholeBookInsightsEngineV1()
    except Exception:
        return None
