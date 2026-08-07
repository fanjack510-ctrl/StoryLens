"""Shared Free whole-book minimal pipeline (fixture or formal gateway transports)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.narrative_core.services.whole_book_gateway_transport_v1 import (
    GatewayChapterFunctionsTransport,
    GatewayOverviewTransport,
    GatewayStructureTransport,
    GatewayWindowAnalysisTransport,
    resolve_formal_provider_row,
)
from app.narrative_core.services.whole_book_minimal_chapter_functions_v1_service import (
    FixtureChapterFunctionsTransport,
    synthesize_minimal_chapter_functions_v1,
)
from app.narrative_core.services.whole_book_minimal_extraction_v1_service import (
    FixtureWindowAnalysisTransport,
    execute_minimal_entity_event_extraction_v1,
)
from app.narrative_core.services.whole_book_minimal_materialization_v1_service import (
    materialize_minimal_narrative_assets_v1,
)
from app.narrative_core.services.whole_book_minimal_overview_v1_service import (
    FixtureOverviewTransport,
    synthesize_minimal_book_overview_v1,
)
from app.narrative_core.services.whole_book_minimal_structure_stages_v1_service import (
    FixtureStructureTransport,
    synthesize_minimal_structure_stages_v1,
)
from app.narrative_core.services.whole_book_provider_orchestrator import WholeBookProviderTransport
from app.narrative_core.services.whole_book_run_v1_service import get_run, start_whole_book_run_v1


@dataclass(frozen=True)
class MinimalPipelineTransports:
    window: WholeBookProviderTransport
    overview: WholeBookProviderTransport | None = None
    structure: WholeBookProviderTransport | None = None
    chapter_functions: WholeBookProviderTransport | None = None


def build_fixture_transports(
    *,
    structure_mode: str = "multi_stage",
    chapter_functions_mode: str = "available",
) -> MinimalPipelineTransports:
    return MinimalPipelineTransports(
        window=FixtureWindowAnalysisTransport(),
        overview=None,  # overview synthesizer defaults FixtureOverviewTransport from projection
        structure=FixtureStructureTransport(mode=structure_mode),  # type: ignore[arg-type]
        chapter_functions=FixtureChapterFunctionsTransport(mode=chapter_functions_mode),  # type: ignore[arg-type]
    )


def build_formal_gateway_transports(session: Session) -> MinimalPipelineTransports:
    row = resolve_formal_provider_row(session)
    return MinimalPipelineTransports(
        window=GatewayWindowAnalysisTransport(session, provider_row=row),
        overview=GatewayOverviewTransport(session, provider_row=row),
        structure=GatewayStructureTransport(session, provider_row=row),
        chapter_functions=GatewayChapterFunctionsTransport(session, provider_row=row),
    )


def execute_minimal_pipeline_v1(
    session: Session,
    run_id: int,
    *,
    transports: MinimalPipelineTransports,
    structure_mode: str = "multi_stage",
    chapter_functions_mode: str = "available",
) -> dict:
    run = get_run(session, run_id)
    if run.status == "completed":
        session.refresh(run)
        return {
            "run_id": run_id,
            "run_status": run.status,
            "current_stage_code": run.current_stage_code,
            "extraction": {"run_id": run_id, "reused": True, "provider_calls": 0},
            "materialization": {"run_id": run_id, "reused": True},
            "overview": {"run_id": run_id, "reused": True},
            "structure": {"run_id": run_id, "reused": True, "provider_calls": 0},
            "chapter_functions": {"run_id": run_id, "reused": True, "provider_calls": 0},
            "result_origin": run.result_origin,
        }

    if run.status == "pending":
        start_whole_book_run_v1(session, run_id)
        session.refresh(run)

    extraction = execute_minimal_entity_event_extraction_v1(
        session, run_id, transport=transports.window
    )
    materialization = materialize_minimal_narrative_assets_v1(session, run_id)
    overview = synthesize_minimal_book_overview_v1(
        session,
        run_id,
        transport=transports.overview,
        finalize_run=False,
    )
    structure = synthesize_minimal_structure_stages_v1(
        session,
        run_id,
        transport=transports.structure
        or FixtureStructureTransport(mode=structure_mode),  # type: ignore[arg-type]
        mode=structure_mode,  # type: ignore[arg-type]
        finalize_run=False,
    )
    chapter_functions = synthesize_minimal_chapter_functions_v1(
        session,
        run_id,
        transport=transports.chapter_functions
        or FixtureChapterFunctionsTransport(mode=chapter_functions_mode),  # type: ignore[arg-type]
        mode=chapter_functions_mode,  # type: ignore[arg-type]
        finalize_run=True,
    )

    session.refresh(run)
    return {
        "run_id": run_id,
        "run_status": run.status,
        "current_stage_code": run.current_stage_code,
        "extraction": extraction,
        "materialization": materialization,
        "overview": overview,
        "structure": structure,
        "chapter_functions": chapter_functions,
        "result_origin": run.result_origin,
    }
