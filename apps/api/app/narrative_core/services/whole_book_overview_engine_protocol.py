"""STEP 2.3-I0 — Unified Whole-Book Overview engine Protocol.

Public Orchestrator depends only on this Protocol. Fixture and Private engines
must implement the same surface. No divergent Fake payload schemas.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from app.narrative_core.contracts.whole_book_overview_v1 import (
    WholeBookOverviewProjectionCandidateV1,
    WholeBookOverviewSynthesisInputV1,
    WholeBookOverviewWindowInputV1,
    WholeBookOverviewWindowResultV1,
)


@runtime_checkable
class ProviderTransport(Protocol):
    """Provider-neutral transport injected by Public (Private never reads keys)."""

    def request(
        self,
        prompt: str,
        model_options: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]: ...


@runtime_checkable
class WholeBookOverviewEngineAdapter(Protocol):
    """Single Public↔Private overview engine surface (STEP 2.3-I0)."""

    @property
    def engine_id(self) -> str: ...

    def analyze_window(
        self,
        payload: WholeBookOverviewWindowInputV1,
        transport: ProviderTransport | None = None,
    ) -> WholeBookOverviewWindowResultV1: ...

    def synthesize_overview(
        self,
        payload: WholeBookOverviewSynthesisInputV1,
        transport: ProviderTransport | None = None,
    ) -> WholeBookOverviewProjectionCandidateV1: ...
