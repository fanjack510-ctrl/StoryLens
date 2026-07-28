"""Combined fixture minimal pipeline (WB-1.4–1.6)."""

from __future__ import annotations

import os

from sqlalchemy.orm import Session

from app.narrative_core.services.whole_book_foundation_errors import (
    WholeBookFoundationError,
    WholeBookFoundationErrorCode,
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
from app.narrative_core.services.whole_book_run_v1_service import get_run, start_whole_book_run_v1


def execute_fixture_minimal_pipeline_v1(session: Session, run_id: int) -> dict:
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
            "result_origin": run.result_origin,
        }

    if run.status == "pending":
        start_whole_book_run_v1(session, run_id)
        session.refresh(run)

    transport = FixtureWindowAnalysisTransport()
    extraction = execute_minimal_entity_event_extraction_v1(session, run_id, transport=transport)
    materialization = materialize_minimal_narrative_assets_v1(session, run_id)
    overview = synthesize_minimal_book_overview_v1(session, run_id)

    session.refresh(run)
    return {
        "run_id": run_id,
        "run_status": run.status,
        "current_stage_code": run.current_stage_code,
        "extraction": extraction,
        "materialization": materialization,
        "overview": overview,
        "result_origin": run.result_origin,
    }
