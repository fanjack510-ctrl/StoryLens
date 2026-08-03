"""Combined fixture minimal pipeline (WB-1.4–1.6 + WB-2.1 structure + WB-2.2 CF)."""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
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
    synthesize_minimal_book_overview_v1,
)
from app.narrative_core.services.whole_book_minimal_structure_stages_v1_service import (
    FixtureStructureTransport,
    synthesize_minimal_structure_stages_v1,
)
from app.narrative_core.services.whole_book_run_v1_service import get_run, start_whole_book_run_v1


def execute_fixture_minimal_pipeline_v1(
    session: Session,
    run_id: int,
    *,
    structure_mode: str = "multi_stage",
    chapter_functions_mode: str = "available",
) -> dict:
    if os.environ.get("STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise WholeBookFoundationError(
            WholeBookFoundationErrorCode.WHOLE_BOOK_CAPABILITY_DISABLED,
            "real provider path is not exposed in fixture pipeline",
        )

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

    transport = FixtureWindowAnalysisTransport()
    extraction = execute_minimal_entity_event_extraction_v1(session, run_id, transport=transport)
    materialization = materialize_minimal_narrative_assets_v1(session, run_id)
    overview = synthesize_minimal_book_overview_v1(session, run_id, finalize_run=False)
    structure = synthesize_minimal_structure_stages_v1(
        session,
        run_id,
        transport=FixtureStructureTransport(mode=structure_mode),  # type: ignore[arg-type]
        mode=structure_mode,  # type: ignore[arg-type]
        finalize_run=False,
    )
    chapter_functions = synthesize_minimal_chapter_functions_v1(
        session,
        run_id,
        transport=FixtureChapterFunctionsTransport(mode=chapter_functions_mode),  # type: ignore[arg-type]
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
