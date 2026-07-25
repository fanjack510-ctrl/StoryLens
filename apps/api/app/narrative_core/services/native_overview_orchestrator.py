"""Compatibility shim — production logic lives in ``native_overview_service``.

STEP 2.3-A kept a brief orchestrator split; the canonical entry remains
``NativeOverviewService``. This module re-exports symbols so any interim imports
resolve without a second implementation.
"""

from __future__ import annotations

from app.narrative_core.services.native_overview_service import (
    OVERVIEW_PROJECTION_ARTIFACT_TYPE,
    NativeOverviewService,
)

# Historical name used during the A2 split.
NativeOverviewOrchestrator = NativeOverviewService

__all__ = [
    "OVERVIEW_PROJECTION_ARTIFACT_TYPE",
    "NativeOverviewOrchestrator",
    "NativeOverviewService",
]
