"""Combined fixture minimal pipeline (WB-1.4–1.6 + WB-2.1 structure + WB-2.2 CF)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.narrative_core.services.whole_book_minimal_pipeline_v1_service import (
    build_fixture_transports,
    execute_minimal_pipeline_v1,
)


def execute_fixture_minimal_pipeline_v1(
    session: Session,
    run_id: int,
    *,
    structure_mode: str = "multi_stage",
    chapter_functions_mode: str = "available",
) -> dict:
    """Fixture Preview path — always Fixture* transports; never Gateway/Real.

    Independent of STORYLENS_WHOLE_BOOK_REAL_PROVIDER_ENABLED: real flag only
    gates formal create, not fixture preview.
    """

    return execute_minimal_pipeline_v1(
        session,
        run_id,
        transports=build_fixture_transports(
            structure_mode=structure_mode,
            chapter_functions_mode=chapter_functions_mode,
        ),
        structure_mode=structure_mode,
        chapter_functions_mode=chapter_functions_mode,
    )
