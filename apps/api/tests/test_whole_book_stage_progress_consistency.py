"""Multi-stage progress envelope: current never exceeds total; completed is consistent."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import WholeBookRunStageRow
from app.narrative_core.services.whole_book_minimal_helpers_v1 import set_stage_completed
from tests.whole_book_minimal_test_helpers import prepare_sample_s_run


def test_overview_structure_chapter_functions_progress_envelope(testing_session) -> None:
    run_id, _book_id = prepare_sample_s_run(testing_session)

    stages = {
        "synthesize_overview": 1,
        "synthesize_structure_stages": 1,
        "synthesize_chapter_functions": 4,
    }
    for stage_code, total in stages.items():
        set_stage_completed(testing_session, run_id, stage_code, progress_total=total)

    testing_session.flush()
    rows = list(
        testing_session.scalars(
            select(WholeBookRunStageRow).where(WholeBookRunStageRow.run_id == run_id)
        )
    )
    by_code = {row.stage_code: row for row in rows}
    for stage_code, total in stages.items():
        stage = by_code[stage_code]
        assert stage.progress_total == total
        assert stage.progress_current == total
        assert stage.progress_current <= stage.progress_total
        assert stage.status == "completed"
